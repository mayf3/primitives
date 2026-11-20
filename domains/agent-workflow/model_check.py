#!/usr/bin/env python3
"""Small bounded model checker for *synthetic* two-step Agent Workflow.

This is not a proof about production, an exhaustive infinite-state model,
or a reconstruction of any private historical model-checker result.

A -> B are durable obligations for one goal. Each logical effect can
commit before its acknowledgement arrives; a trusted readback can recover it.
The transition to B is atomic with the closing of A. Deliberately broken
variants expose distinct safety/progress counterexamples.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import json
from typing import Iterable

ABSENT, OPEN, DONE = 0, 1, 2


@dataclass(frozen=True)
class State:
    stages: tuple[int, int] = (OPEN, ABSENT)
    claimed: tuple[bool, bool] = (False, False)
    effects: tuple[int, int] = (0, 0)
    proofs: tuple[bool, bool] = (False, False)
    unknown: tuple[bool, bool] = (False, False)
    accepted: bool = False


def change_tuple(values: tuple, index: int, value):
    items = list(values)
    items[index] = value
    return tuple(items)


def step(s: State, variant: str = "safe") -> list[tuple[str, State]]:
    edges: list[tuple[str, State]] = []
    for index, label in enumerate(("A", "B")):
        if s.stages[index] != OPEN:
            continue
        if not s.claimed[index]:
            if variant == "orphan-successor" and index == 1:
                continue
            edges.append((f"claim-{label}", replace(
                s, claimed=change_tuple(s.claimed, index, True))))
            continue

        # Retained operation exists before submitting an effect. Network
        # may acknowledge or lose its reply, without rolling back the world.
        if not s.proofs[index] and not s.unknown[index] and s.effects[index] == 0:
            eff = change_tuple(s.effects, index, 1)
            edges.append((f"effect-ack-{label}", replace(
                s, effects=eff, proofs=change_tuple(s.proofs, index, True))))
            edges.append((f"effect-reply-lost-{label}", replace(
                s, effects=eff, unknown=change_tuple(s.unknown, index, True))))

        if s.unknown[index]:
            if variant != "no-readback":
                edges.append((f"trusted-readback-{label}", replace(
                    s,
                    unknown=change_tuple(s.unknown, index, False),
                    proofs=change_tuple(s.proofs, index, True))))
            if variant == "blind-replay":
                edges.append((f"unsafe-new-key-replay-{label}", replace(
                    s, effects=change_tuple(s.effects, index, s.effects[index] + 1))))

        if s.proofs[index]:
            stages = change_tuple(s.stages, index, DONE)
            if index == 0 and variant != "drop-successor":
                stages = change_tuple(stages, 1, OPEN)
            edges.append((f"verify-and-handoff-{label}", replace(
                s, stages=stages, accepted=(index == 1))))

        if variant == "false-pass" and not s.proofs[index]:
            stages = change_tuple(s.stages, index, DONE)
            if index == 0:
                stages = change_tuple(stages, 1, OPEN)
            edges.append((f"self-reported-pass-{label}", replace(
                s, stages=stages, accepted=(index == 1))))
    return edges


def violations(s: State) -> list[str]:
    failures: list[str] = []
    if any(count > 1 for count in s.effects):
        failures.append("S3_EFFECT_AT_MOST_ONCE")
    if any(stage == DONE and not (s.proofs[i] and s.effects[i] == 1)
           for i, stage in enumerate(s.stages)):
        failures.append("S2_UNVERIFIED_CLOSURE")
    if s.accepted and s.stages != (DONE, DONE):
        failures.append("S2_FALSE_GOAL_TERMINAL")
    if not s.accepted and s.stages[0] == DONE and s.stages[1] == ABSENT:
        failures.append("S1_MISSING_REQUIRED_SUCCESSOR")
    return failures


def explore(variant: str = "safe") -> dict:
    # BFS provides the shortest counterexample in this finite abstraction.
    start = State()
    queue = deque([(start, ())])
    visited: set[State] = set()
    transitions = 0
    accepted = 0
    while queue:
        state, trace = queue.popleft()
        if state in visited:
            continue
        visited.add(state)
        failures = violations(state)
        if failures:
            return dict(ok=False, states=len(visited), edges=transitions,
                        violation=failures[0], trace=list(trace))
        successors = step(state, variant)
        transitions += len(successors)
        if state.accepted:
            accepted += 1
        elif not successors:
            return dict(ok=False, states=len(visited), edges=transitions,
                        violation="L1_NO_ENABLED_CONSUMER_OR_READBACK", trace=list(trace))
        for action, successor in successors:
            if successor not in visited:
                queue.append((successor, trace + (action,)))
    return dict(ok=(accepted > 0), states=len(visited), edges=transitions,
                accepted_states=accepted,
                violation=None if accepted else "L2_NO_ACCEPTING_STATE", trace=[])


EXPECTED_MUTATIONS = {
    "drop-successor": "S1_MISSING_REQUIRED_SUCCESSOR",
    "false-pass": "S2_UNVERIFIED_CLOSURE",
    "blind-replay": "S3_EFFECT_AT_MOST_ONCE",
    "orphan-successor": "L1_NO_ENABLED_CONSUMER_OR_READBACK",
    "no-readback": "L1_NO_ENABLED_CONSUMER_OR_READBACK",
}


def report() -> dict:
    baseline = explore("safe")
    mutations = {name: explore(name) for name in EXPECTED_MUTATIONS}
    passed = (
        baseline["ok"]
        and all(not mutations[name]["ok"] and
                mutations[name]["violation"] == expected
                for name, expected in EXPECTED_MUTATIONS.items())
    )
    return {
        "model": "synthetic-two-obligation-finite-exploration",
        "passed": bool(passed),
        "baseline": baseline,
        "mutations": mutations,
        "scope": (
            "Two sequential obligations A->B, stable operation identity, "
            "one ambiguous reply per operation, persistent state, available "
            "trusted readback, executable action fairness assumed. "
            "Deadlock checking is not a proof of fairness in real schedulers."
        ),
        "does_not_prove": [
            "unbounded concurrency",
            "real-world authorization or external effects",
            "full L1/L2 temporal liveness",
            "production adoption or user goal completion",
        ],
    }


if __name__ == "__main__":
    result = report()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
