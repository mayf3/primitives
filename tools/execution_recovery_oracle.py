#!/usr/bin/env python3
"""Independent JSONL oracle for the Core Recovery pilot's single-attempt slice."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys


PHASES = ("planned", "resolutionBlocked", "deliveryStarted", "outcomeUnknown",
          "runDelivered", "settled", "needsReview")
EVENTS = ("blockResolution", "beginDelivery", "confirmDelivery", "observeUnknown",
          "rejectAfterStart", "reconcileSettled", "reconcileNeedsReview", "readOnlyRecheck",
          "recordHandoffMetadata")
NATIVE_EVENTS = ("blockResolution", "beginDelivery", "confirmDelivery",
                 "reconcileSettled", "reconcileNeedsReview")
VISIT = "0d5c2f0a-3f19-4a7e-9a3f-5d1c2b0a9e11"
DEFAULT_PROFILE = "core-recovery"


def load_table(path):
    """Load the finite table emitted by the pinned Lean decision program."""
    table = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        phase, started, event, next_phase, next_started = line.split("\t")
        key = (phase, started == "true", event)
        if phase not in PHASES or started not in ("false", "true") or event not in EVENTS or key in table:
            raise ValueError("invalid or repeated oracle table key")
        if (next_phase, next_started) == ("-", "-"):
            table[key] = None
        elif next_phase in PHASES and next_started in ("false", "true"):
            table[key] = (next_phase, next_started == "true")
        else:
            raise ValueError("unknown oracle target")
    if len(table) != len(PHASES) * 2 * len(EVENTS):
        raise ValueError("oracle decision table is incomplete")
    return table


def profile_name(profile):
    return profile.get("id") if isinstance(profile, dict) else profile


def initial_state(environment_profile):
    later = profile_name(environment_profile) == "core-generation-two"
    key = VISIT + ("#gen2" if later else "")
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return {"identity": {"nodeVisitId": VISIT, "attemptId": "wfeat-" + digest[:24],
                         "generation": 2 if later else 1},
            "phase": "runDelivered" if later else "planned", "deliveryStarted": later}


def next_state(table, state, event):
    result = table[(state["phase"], state["deliveryStarted"], event)]
    if result is None:
        return None
    phase, started = result
    return {**state, "phase": phase, "deliveryStarted": started}


class Oracle:
    def __init__(self, table):
        self.table = table
        self.state = None
        self.delivery_confirmed = False

    def execute(self, command, _test_context):
        if self.state is None or not isinstance(command, dict) or not isinstance(command.get("kind"), str):
            raise ValueError("reset the oracle and pass a command kind")
        kind = command["kind"]
        phase = self.state["phase"]
        started = self.state["deliveryStarted"]
        result = {"state": self.state, "events": [], "complete": True, "observation": "PASS"}
        if kind in EVENTS:
            state = next_state(self.table, self.state, kind)
            if state is None:
                return {**result, "stutter": "refused_invalid_event", "accepted": False}
            result["observation"] = "UNKNOWN" if kind in ("observeUnknown", "readOnlyRecheck", "rejectAfterStart") else "PASS"
            path = (kind,)
        elif kind in ("recoverBlocked", "sigkillAfterWal", "sigkillAckLost", "sigkillBeforeWal") and phase == "resolutionBlocked":
            if kind == "sigkillBeforeWal":
                return {**result, "stutter": "pre_wal_process_exit"}
            path = ("beginDelivery", "confirmDelivery") if kind == "recoverBlocked" else ("beginDelivery",)
            if kind != "recoverBlocked":
                result["observation"] = "UNKNOWN"
        elif kind == "reconcileAfterStart" and phase == "deliveryStarted":
            path = ("rejectAfterStart",)
            result["observation"] = "UNKNOWN"
        elif kind == "queryOriginal":
            observation = "UNKNOWN" if started and not self.delivery_confirmed else "PASS"
            return {**result, "stutter": "readonly_original_query", "observation": observation}
        elif kind == "restart":
            observation = "UNKNOWN" if started and not self.delivery_confirmed else "PASS"
            return {**result, "stutter": "restart_replay", "observation": observation}
        elif kind == "staleGeneration" and self.state["identity"]["generation"] == 2:
            return {**result, "stutter": "stale_identity_refused"}
        elif kind == "recoverAfterStart" and started:
            return {**result, "stutter": "post_wal_recovery_refused", "observation": "UNKNOWN"}
        else:
            return {**result, "supported": False, "observation": "UNKNOWN"}
        state = self.state
        trace = []
        for event in path:
            successor = next_state(self.table, state, event)
            if successor is None:
                raise ValueError("operational witness path violates the Lean transition relation")
            trace.append({"event": event, "from": state, "to": successor})
            state = successor
        self.state = state
        if "confirmDelivery" in path:
            self.delivery_confirmed = True
        return {**result, "state": state, "events": trace, "accepted": True}

    def call(self, method, params):
        if method == "reset":
            seed = params["seed"]
            if type(seed) is not int or not 0 <= seed < 2**53:
                raise ValueError("seed must be a nonnegative interoperable integer")
            self.state = initial_state(params["environment_profile"])
            self.delivery_confirmed = self.state["phase"] == "runDelivered"
            return self.state
        if self.state is None:
            raise ValueError("reset the oracle before reading state")
        if method == "snapshot":
            return self.state
        if method == "execute":
            return self.execute(params["command"], params.get("test_context", {}))
        if method == "abstract_state":
            return params["snapshot"]
        if method == "normalize":
            return params["event"]
        if method == "observe":
            return params["result"]["observation"]
        raise ValueError("unknown oracle method")


def generate_commands(table, seed, mode, steps=10):
    """Select events from Lean's allowed or denied sets without consulting the SUT."""
    if (type(seed) is not int or not 0 <= seed < 2**53 or type(steps) is not int
            or not 2 <= steps <= 1000 or mode not in ("legal", "illegal")):
        raise ValueError("invalid model sequence profile")
    rng = random.Random(seed)
    state = initial_state(DEFAULT_PROFILE)
    commands = []
    needs_denied = mode == "illegal"
    for index in range(steps):
        legal = [event for event in NATIVE_EVENTS if next_state(table, state, event) is not None]
        if needs_denied and state["deliveryStarted"]:
            denied = [event for event in ("blockResolution", "beginDelivery") if event not in legal]
            if denied and (index == steps - 1 or rng.choice((False, True))):
                commands.append({"kind": rng.choice(denied)})
                needs_denied = False
                continue
        if needs_denied and not state["deliveryStarted"] and index == steps - 2:
            kind = "beginDelivery"
            state = next_state(table, state, kind)
        elif legal:
            can_restart_with_known_observation = index >= 2 and state["phase"] != "deliveryStarted"
            kind = rng.choice(legal + ["restart"] if can_restart_with_known_observation else legal)
            if kind != "restart":
                state = next_state(table, state, kind)
        else:
            kind = "restart"
        commands.append({"kind": kind})
    if needs_denied:
        raise ValueError("sequence too short to reach a rejected event")
    return commands


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--generate", choices=("legal", "illegal"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=10)
    args = parser.parse_args(argv)
    table = load_table(args.table)
    if args.generate:
        print(json.dumps({"seed": args.seed, "mode": args.generate,
                          "commands": generate_commands(table, args.seed, args.generate, args.steps)}))
        return 0
    oracle = Oracle(table)
    for line in sys.stdin:
        identifier = None
        try:
            request = json.loads(line)
            identifier = request["id"]
            value = oracle.call(request["method"], request.get("params", {}))
            reply = {"id": identifier, "result": value}
        except (KeyError, TypeError, ValueError) as error:
            reply = {"id": identifier, "error": {"kind": "INVALID_REQUEST", "message": str(error)}}
        print(json.dumps(reply, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
