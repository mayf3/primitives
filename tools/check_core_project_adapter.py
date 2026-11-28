#!/usr/bin/env python3
"""Run the pinned Core model-based pilot, source mutations, and coverage controls."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from assumption_freshness import assess_receipt, digest
from capture_core_recovery_trace import CORE_REVISION
from core_recovery_trace import load_core_traces
from evidence_graph import assess, content_coordinate
from evidence_graph_fixture import materialize
from execution_recovery_oracle import generate_commands, load_table
from project_adapter import run_adapter
from trace_validate import validate_trace


TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
FIXTURE = ROOT / "docs/evidence-graph-fixtures/core"
MUTATIONS = FIXTURE / "batch4_mutations"
MODEL = ROOT / "domains/agent-workflow/lean/AgentWorkflow/ExecutionRecovery.lean"
DECISION = MODEL.with_name("ExecutionRecoveryDecision.lean")
CLAIM = "CORE.TRACE.PROJECT-ADAPTER"
VERIFIER = "CORE.VERIFIER.PROJECT-ADAPTER"
SCENARIOS = {
    "fixed": ["blockResolution", "recoverBlocked", "recoverAfterStart", "queryOriginal", "reconcileSettled", "restart"],
    "before-wal": ["blockResolution", "sigkillBeforeWal", "restart", "recoverBlocked"],
    "after-wal": ["blockResolution", "sigkillAfterWal", "restart", "recoverAfterStart", "queryOriginal",
                  "reconcileAfterStart"],
    "lost-ack": ["blockResolution", "sigkillAckLost", "restart", "recoverAfterStart", "queryOriginal",
                 "reconcileAfterStart"],
    "stale-generation": ["staleGeneration", "recoverAfterStart"],
}
MUTATION_CASES = {"post-wal-router": "lost-ack", "stale-generation": "stale-generation", "dropped-wal": "fixed"}
STUTTERS = {
    "restart_replay": "Read the same persisted attempt in a fresh reader without writing or dispatching.",
    "readonly_original_query": "Query the original Router key without changing its ledger projection.",
    "refused_invalid_event": "A forbidden native command changed neither the projected attempt nor external effects.",
    "pre_wal_process_exit": "The process exited before the durable fence, leaving the same blocked attempt.",
    "stale_identity_refused": "The displaced identity failed the CAS and retained the current generation.",
    "post_wal_recovery_refused": "The durable fence prevents reopening delivery, including after a confirmed admission.",
    "recovery_observation_metadata": "Recovery audit and readback metadata preserve identity, phase and fence.",
    "router_transport_observation": "First original-key loopback POST observes the fence recorded by a separate ledger event.",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open("xb") as out:
        out.write(json_bytes(value))


def observable_coverage(report):
    if report["status"] == "TRACE_CONFORMANT":
        return True
    steps = report["steps"]
    return (report["status"] == "UNKNOWN" and len(steps) == len(report["input"]["commands"])
            and all(step.get("transition_comparison") == "TRACE_CONFORMANT" for step in steps))


@contextmanager
def isolated_core(repository, dest):
    git = ["git", "-C", str(repository.resolve()), "worktree"]
    subprocess.run(git + ["add", "--quiet", "--detach", str(dest), CORE_REVISION], check=True, timeout=45)
    try:
        # The pinned tree has a developer-specific external symlink. These real
        # recovery modules use built-ins and local dependencies.
        modules = dest / "node_modules"
        if modules.is_symlink():
            modules.unlink()
        yield dest
    finally:
        subprocess.run(git + ["remove", "--force", str(dest)], check=True, timeout=30)


def current_probe(directory):
    context = read(directory / "contexts.json")["router"]
    receipt = read(directory / "router-recovered.json")
    fresh = assess_receipt(receipt, context, datetime.now(timezone.utc))
    expired = assess_receipt(receipt, context, datetime.fromisoformat(receipt["expires_at"]))
    require((fresh["status"], expired["status"]) == ("PASS", "STALE"),
            "Batch 3 input must be current when the pilot starts and expire at the recorded boundary")
    return ({**fresh, "receipt": receipt, "context": context},
            {**expired, "receipt": receipt, "context": context})


def trace_inputs(graph_file, capture_file):
    graph = read(graph_file)
    model = next(node for node in graph["nodes"] if node["id"] == "CORE.MODEL.EXECUTION-RECOVERY")
    require(model["coordinate_valid"] and model["resolved_coordinate"]["sha256"] == digest(MODEL.read_bytes()),
            "Oracle does not use the original Batch 1 model bytes")
    traces = load_core_traces(graph_file, FIXTURE / "recovery-trace-contract.json", capture_file)
    verdicts = {}
    for item in traces:
        verdicts[item["id"]] = validate_trace(graph, item["contract"], item["manifest"],
                                               item["normalized_bytes"], item["raw_bytes"])
    statuses = [result["status"] for result in verdicts.values()]
    require(statuses.count("TRACE_CONFORMANT") == 5 and statuses.count("UNKNOWN") == 1,
            "Batch 2 original classifications changed")
    case = next(item for item in traces if item["id"] == "B2-accepted-ACK-lost-SIGKILL")
    clipped = b"".join(case["normalized_bytes"].splitlines(keepends=True)[:-1])
    incomplete = validate_trace(graph, case["contract"], {**case["manifest"], "normalized_sha256": digest(clipped)},
                                clipped, case["raw_bytes"])
    require(incomplete["status"] == "TRACE_INCOMPLETE", "Batch 2 validator accepted a clipped segment")
    return verdicts, incomplete


def stop_revive(core, output, node):
    dest = core / "packages/workflow-execution/test/observation-cas/batch4-stop-revive.mjs"
    require(not dest.exists(), "Refusing to overwrite Core test support")
    shutil.copyfile(TOOLS / "core_stop_revive.mjs", dest)
    argv = [node, str(dest)]
    env = {"PATH": os.defpath, "HOME": str(core), "TMPDIR": str(core)}
    execution = subprocess.run(argv, cwd=core, env=env, capture_output=True, timeout=20)
    (output / "stop-revive.stdout.json").write_bytes(execution.stdout)
    (output / "stop-revive.stderr.txt").write_bytes(execution.stderr)
    evidence = {"argv": argv, "exit_code": execution.returncode, "source_revision": CORE_REVISION,
                "test_sha256": digest(dest.read_bytes()), "stdout_sha256": digest(execution.stdout),
                "scope": "Two real engines sharing one isolated ledger. Lifecycle interleaving is outside Lean Step."}
    write(output / "stop-revive.command.json", evidence)
    require(execution.returncode == 0 and json.loads(execution.stdout)["status"] == "PASS", "Core stop/revive control failed")
    return evidence


def patch_target(payload):
    matches = re.findall(rb"(?m)^\+\+\+ b/(packages/workflow-execution/src/[a-z0-9_./-]+\.js)$", payload)
    require(len(matches) == 1 and payload.count(b"\ndiff --git ") == 0 and b".." not in matches[0].split(b"/"),
            "Mutation must touch exactly one workflow-execution source file")
    return Path(matches[0].decode())


def changed_source(core):
    result = subprocess.check_output(["git", "diff", "--name-only", "--", "packages/workflow-execution/src"],
                                     cwd=core, text=True, timeout=15)
    return result.splitlines()


@contextmanager
def source_mutation(core, patch, output):
    payload = patch.read_bytes()
    target = patch_target(payload)
    source = core / target
    before = source.read_bytes()
    require(not changed_source(core), "Mutation worktree has preexisting Core source edits")
    command = ["git", "apply", "--include", target.as_posix(), str(patch.resolve())]
    subprocess.run(command + ["--check"], cwd=core, check=True, timeout=15)
    subprocess.run(command, cwd=core, check=True, timeout=15)
    changed = source.read_bytes()
    require(before != changed, "Mutation did not change source bytes")
    output.write_bytes(payload)
    try:
        require(changed_source(core) == [target.as_posix()], "Mutation changed more than its declared Core source")
        yield {"patch_sha256": digest(payload), "path": target.as_posix(), "original_sha256": digest(before),
               "mutant_sha256": digest(changed), "argv": command}
    finally:
        subprocess.run(command + ["--reverse"], cwd=core, check=True, timeout=15)
        require(source.read_bytes() == before and not changed_source(core), "Core source did not restore byte-for-byte")


class CoverageSnapshots:
    def __init__(self, project, output):
        self.project, self.output = project, output
        graph = assess(project, project / ".evidence-graph")["evidence-graph.json"]
        self.baseline = {node["id"]: node for node in graph["nodes"]}
        self.manifest_path = project / "fixture-sources.json"
        self.manifest = read(self.manifest_path)
        verifier = (TOOLS / "project_adapter.py").read_bytes()
        self.verifier = self.material("adapter-verifier.py", verifier, digest(verifier))
        self.history = {}

    def material(self, name, data, revision):
        target = self.project / name
        with target.open("xb") as out:
            out.write(data)
        sha = digest(data)
        self.manifest["files"][name] = {"revision": revision, "sha256": sha}
        return {"path": name, "revision": revision, "sha256": sha}

    def publish(self, phase, reports):
        nodes = [{"id": VERIFIER, "kind": "VERIFIER", "coordinate": self.verifier}]
        links = []
        targets = {i: content_coordinate(self.baseline[i]) for i in (
            "CORE.MODEL.EXECUTION-RECOVERY", "CORE.MAP.SAME-ATTEMPT-PROJECTION",
            "CORE.CODE.LEDGER", "CORE.CODE.ENGINE", "CORE.CODE.EVENTS")}
        targets[VERIFIER] = self.verifier
        bindings = {i: {key: node[key] for key in ("sha256", "revision")} for i, node in targets.items()}
        for label, report in sorted(reports.items()):
            status = report["status"]
            passed = observable_coverage(report)
            suffix = label.upper().replace("_", "-")
            identifier = f"{CLAIM}.{suffix}"
            receipt = {"status": "PASS_OBSERVABLE_TRANSITIONS" if passed else status,
                       "exit_code": 0 if passed else 1, "adapter_status": status,
                       "evidence_bindings": bindings, "adapter_receipt_sha256": digest(json_bytes(report))}
            filename = f"adapter-{phase}-{label}.json"
            coord = self.material(filename, json_bytes(receipt), CORE_REVISION)
            nodes.append({"id": identifier, "kind": "TRACE", "coordinate": coord, "bindings": bindings,
                          "evidence_state": "PASS" if passed else "FAIL" if status == "TRACE_DRIFTED" else "UNKNOWN",
                          "receipt_checks": {"adapter_status": status}, "adapter_verdict": status})
            links.extend({"from": identifier, "to": i, "relation": "binds"} for i in targets)
        self.manifest_path.write_bytes(json_bytes(self.manifest))
        (self.project / "batch4.evidence.json").write_bytes(json_bytes(
            {"schema_version": "evidence-receipt/v1", "nodes": nodes, "links": links}))
        results = assess(self.project, self.project / ".evidence-graph")
        state = results["coverage-report.json"]
        require(not results["evidence-graph.json"]["diagnostics"], "Batch 4 graph produced diagnostics")
        coverage = {row["id"].removeprefix(f"{CLAIM}.").lower(): row["covered"] for row in state["traces"]
                    if row["id"].startswith(f"{CLAIM}.")}
        require(coverage == {label: observable_coverage(report) for label, report in reports.items()},
                f"Batch 4 coverage contradicts evaluated receipts: {phase}")
        require(any(n["id"] == "CORE.LEAN.KERNEL-CI" and n["evidence_status"] == "VERIFIED"
                    for n in results["evidence-graph.json"]["nodes"]), "Static Lean audit unexpectedly changed")
        directory = self.output / f"coverage-{phase}"
        directory.mkdir()
        for filename, report in results.items():
            write(directory / filename, report)
        self.history[phase] = coverage
        return coverage


def build_oracle(output):
    build = ["lake", "build", "AgentWorkflow.ExecutionRecoveryDecision"]
    compiled = subprocess.run(build, cwd=ROOT, capture_output=True, check=False, timeout=120)
    (output / "oracle-build.stdout").write_bytes(compiled.stdout)
    (output / "oracle-build.stderr").write_bytes(compiled.stderr)
    require(compiled.returncode == 0, "Lean execution oracle did not build")
    command = ["lake", "env", "lean", "--run", str(DECISION)]
    checked = subprocess.run(command, cwd=ROOT, capture_output=True, check=False, timeout=60)
    table = output / "oracle-table.tsv"
    table.write_bytes(checked.stdout)
    (output / "oracle-table.stderr").write_bytes(checked.stderr)
    require(checked.returncode == 0, "Lean decision table could not be generated")
    write(output / "oracle-table.command.json", {"build": build, "command": command, "exit_code": checked.returncode,
          "table_sha256": digest(checked.stdout), "model_sha256": digest(MODEL.read_bytes()),
          "decision_sha256": digest(DECISION.read_bytes())})
    return table


def pinned_versions(table):
    mapping_inputs = [TOOLS / "core_recovery_adapter.py", MUTATIONS / "core-adapter-driver.mjs",
                      FIXTURE / "recovery-trace-contract.json"]
    oracle_inputs = [MODEL, DECISION, TOOLS / "execution_recovery_oracle.py", table]
    adapter_inputs = [TOOLS / "project_adapter.py", ROOT / "schemas/project-adapter-v1.schema.json",
                      TOOLS / "trace_validate.py", TOOLS / "evidence_graph.py", TOOLS / "assumption_freshness.py"]

    def aggregate(inputs):
        return digest("\n".join(digest(path.read_bytes()) for path in inputs).encode())

    return {"sut_revision": CORE_REVISION, "mapping_version": aggregate(mapping_inputs),
            "oracle_version": aggregate(oracle_inputs), "adapter_version": aggregate(adapter_inputs)}


def exercise(args, core, project, table, replay):
    output = args.output
    versions = pinned_versions(table)
    node = shutil.which("node")
    require(node is not None, "Node runtime is unavailable")
    graph = CoverageSnapshots(project, output)
    trace_verdicts, incomplete = trace_inputs(args.graph, args.capture)
    fresh, expired = current_probe(args.probes)
    bounded = trace_verdicts["B2-503-restart-automatic-first-admission"]
    inclusive = {"probe": fresh, "trace": bounded}
    oracle = load_table(table)
    observed = {}

    def run(label, scenario, seed, *, commands=None, evidence=None, mutation=None):
        plan = commands if commands is not None else [{"kind": command} for command in SCENARIOS[scenario]]
        case_versions = versions if mutation is None else {**versions, "sut_mutation_sha256": mutation["patch_sha256"]}
        environment = {"id": "core-generation-two" if scenario == "stale-generation" else "core-recovery",
                       "scope": "isolated-scratch-Core-Node", "core_source": CORE_REVISION,
                       "probe_scope": "companion Core fixture, independently collected; no inheritance of its live socket"}
        report = run_adapter(
            sut_argv=[sys.executable, str(TOOLS / "core_recovery_adapter.py"), "--core", str(core)],
            oracle_argv=[sys.executable, str(TOOLS / "execution_recovery_oracle.py"), "--table", str(table)],
            seed=seed, environment_profile=environment, commands=plan, mapping_id="CORE.MAP.SAME-ATTEMPT-PROJECTION",
            observation_id="CORE.OBS.ROUTER-ORIGINAL", versions=case_versions, stutters=STUTTERS,
            evidence=inclusive if evidence is None else evidence, sut_cwd=core,
        )
        report["core_pilot_replay"] = {"scenario": scenario, "mutation": mutation,
                                      "core_source": CORE_REVISION}
        write(output / f"{label}.json", report)
        observed[label] = {"status": report["status"], "coverage": observable_coverage(report),
                           "failure": report["failure"], "receipt_sha256": digest(json_bytes(report))}
        return report

    if replay is not None:
        saved = read(replay)
        plan, replay_info = saved["input"], saved["core_pilot_replay"]
        expected_versions = {k: v for k, v in plan["versions"].items() if k != "sut_mutation_sha256"}
        require(expected_versions == versions and replay_info["core_source"] == CORE_REVISION,
                "Replay source or verifier coordinates changed")
        require(digest(json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
                == saved["input_sha256"], "Saved command plan digest changed")
        scenario = replay_info["scenario"]
        require(scenario in SCENARIOS and plan["environment_profile"]["id"] ==
                ("core-generation-two" if scenario == "stale-generation" else "core-recovery"),
                "Saved replay scenario does not match the bound environment")
        mutation = replay_info["mutation"]
        require(plan["versions"].get("sut_mutation_sha256") == (mutation and mutation["patch_sha256"]),
                "Saved replay mutation does not match the bound command plan")
        gates = plan["evidence"]
        require(gates["probe"]["status"] in ("PASS", "STALE")
                and gates["trace"]["status"] in ("TRACE_CONFORMANT", "TRACE_INCOMPLETE"),
                "Saved plan has an unsupported evidence gate for this replay")
        replay_gates = {"probe": expired if gates["probe"]["status"] == "STALE" else fresh,
                        "trace": incomplete if gates["trace"]["status"] == "TRACE_INCOMPLETE" else bounded}
        if mutation is None:
            repeated = run("replay", scenario, plan["seed"], commands=plan["commands"], evidence=replay_gates)
        else:
            matches = [p for p in MUTATIONS.glob("*.patch") if digest(p.read_bytes()) == mutation["patch_sha256"]]
            require(len(matches) == 1, "Saved Core mutant is no longer available")
            with source_mutation(core, matches[0], output / "replayed.patch") as applied:
                require(all(applied[k] == mutation[k] for k in ("path", "original_sha256", "mutant_sha256")),
                        "Mutation replay source digests changed")
                repeated = run("replay", scenario, plan["seed"], commands=plan["commands"],
                               evidence=replay_gates, mutation=applied)
        require(repeated["status"] == saved["status"] and
                (repeated["failure"] or {}).get("step") == (saved["failure"] or {}).get("step"),
                "Replay did not reproduce the recorded verdict and failure position")
        return observed

    operational = stop_revive(core, output, node)
    baseline = {name: run(name, name, 0) for name in SCENARIOS}
    want = {"fixed": "TRACE_CONFORMANT", "before-wal": "TRACE_CONFORMANT", "after-wal": "UNKNOWN",
            "lost-ack": "UNKNOWN", "stale-generation": "TRACE_CONFORMANT"}
    for name, status in want.items():
        require(baseline[name]["status"] == status and observable_coverage(baseline[name]),
                f"Pristine Core disagrees with scoped oracle on {name}: {observed[name]}")
    for mode in ("legal", "illegal"):
        for seed in range(1, 7):
            commands = generate_commands(oracle, seed, mode, steps=8)
            report = run(f"random-{mode}-{seed}", "fixed", seed, commands=commands)
            require(report["status"] == "TRACE_CONFORMANT", f"Seeded {mode} sequence {seed} disagrees with Core")
            if mode == "illegal":
                require(any(step["oracle_result"].get("accepted") is False for step in report["steps"]),
                        "Seeded comparison did not exercise an illegal command")
    probe_control = run("expired-probe", "fixed", 0, evidence={**inclusive, "probe": expired})
    trace_control = run("missing-trace", "fixed", 0, evidence={**inclusive, "trace": incomplete})
    require((probe_control["status"], trace_control["status"]) == ("STALE", "TRACE_INCOMPLETE"),
            "Independent evidence gate accepted stale or incomplete inputs")
    controls = {"expired-probe": probe_control, "missing-trace": trace_control}
    graph.publish("baseline", {**baseline, **controls})
    mutation_results = {}
    for name, scenario in MUTATION_CASES.items():
        patch = MUTATIONS / f"{name}.patch"
        with source_mutation(core, patch, output / patch.name) as mutation:
            report = run(f"mutant-{name}", scenario, 0, mutation=mutation)
            require(pinned_versions(table) == versions, "Model, mapping, oracle or verification bytes changed with the mutant")
        require(report["status"] == "TRACE_DRIFTED" and bool(report["steps"]),
                f"Real Core mutant {name} was not semantically rejected: {observed[f'mutant-{name}']}")
        mutation_results[name] = {"scenario": scenario, **mutation}
        graph.publish(f"mutant-{name}", {**baseline, scenario: report})
        restored = run(f"restored-{name}", scenario, 0)
        require(restored["status"] == baseline[scenario]["status"] and observable_coverage(restored),
                f"Restored code did not restore the original verdict for {name}")
        graph.publish(f"restored-{name}", {**baseline, scenario: restored})
    return {"schema_version": "core-project-adapter-pilot/v1", "statuses": observed, "coverage": graph.history,
            "mutations": mutation_results, "stop_revive": operational,
            "batch2_verdicts": {key: value["status"] for key, value in trace_verdicts.items()}, "versions": versions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repositories", "core-repo", "graph", "capture", "probes", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--replay", type=Path, help="Independently rerun one saved Core command plan and optional mutation")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    table = build_oracle(args.output)
    with tempfile.TemporaryDirectory(prefix="batch4-core-adapter-") as temporary:
        root = Path(temporary).resolve()
        project = root / "graph-project"
        materialize(FIXTURE / "fixture.json", args.repositories, project, {"dsh-agent-core": args.core_repo})
        with isolated_core(args.core_repo, root / "core") as core:
            report = exercise(args, core, project, table, args.replay)
        write(args.output / "core-project-adapter.json", report)
    print(args.output / "core-project-adapter.json")


if __name__ == "__main__":
    main()
