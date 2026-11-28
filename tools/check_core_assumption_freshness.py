#!/usr/bin/env python3
"""Run the Core assumption pilot and compile its current evidence across failure and recovery."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import select
import shutil
import subprocess
import tarfile
import tempfile

from assumption_freshness import CONTEXT, assess_receipt, digest, run_probe, scope_hash, verifier_revision
from evidence_graph import assess, content_coordinate
from evidence_graph_fixture import materialize


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/evidence-graph-fixtures/core/fixture.json"
CORE = "ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e"
PROBE_REVISION = "d9be9b62ab2580e9f9677ad6636a31588efcd724"
SUPPORT = "packages/workflow-execution/test-support"
PROBE = f"{SUPPORT}/recovery-assumption-probe.mjs"
PROFILE = f"{SUPPORT}/recovery-assumption-probes.json"
VERIFIER = "CORE.VERIFIER.ASSUMPTION-FRESHNESS"
ROUTER_STORE = "CORE.CODE.ROUTER-RECONCILIATION"
CLAIM = "CORE.TEST.RECOVERY.WITH-PROBES"
PINNED_SOURCES = {"ledger": ("CORE.CODE.LEDGER", "CORE.MAP.WAL-START"),
                  "runtime": ("CORE.CODE.ENGINE", "CORE.MAP.BLOCKED-RECOVERY"),
                  "router": (ROUTER_STORE, "CORE.MAP.SAME-ATTEMPT-PROJECTION")}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def import_core(repo, root):
    archive = subprocess.check_output(["git", "-C", str(repo), "archive", CORE], timeout=45)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        tree.extractall(root, members=(member for member in tree if member.name != "node_modules"), filter="data")
    for name in (PROBE, PROFILE):
        payload = subprocess.check_output(["git", "-C", str(repo), "show", f"{PROBE_REVISION}:{name}"], timeout=20)
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        with (root / name).open("xb") as out:
            out.write(payload)


def read_reply(process):
    require(select.select([process.stdout], [], [], 5)[0], "Router fixture did not answer")
    data = process.stdout.readline(8193)
    require(0 < len(data) <= 8192 and data.endswith("\n"), "Missing Router fixture reply")
    return json.loads(data)


def set_route(process, command, expected):
    process.stdin.write(command + "\n")
    process.stdin.flush()
    require(read_reply(process) == {"available": expected}, "Router control acknowledgement mismatch")


@contextmanager
def router_fixture(node, core):
    scratch = core / "router-scratch"
    scratch.mkdir()
    env = {"HOME": str(scratch), "TMPDIR": str(scratch), "PATH": os.defpath}
    with subprocess.Popen([node, str(core / PROBE), "router-fixture"], cwd=core, env=env,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True) as process:
        try:
            port = read_reply(process)["port"]
            require(type(port) is int and 0 < port <= 65535, "Invalid loopback fixture port")
            yield process, port
        finally:
            try:
                if process.poll() is None:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                require(process.wait(timeout=5) == 0, "Router fixture shutdown failed")
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)
                raise


def coordinate(path, revision, data):
    return {"path": path, "revision": revision, "sha256": digest(data)}


class PilotGraph:
    def __init__(self, project, profile_bytes, router_bytes):
        self.project = project
        self.overlay = project / "assumption-pilot.evidence.json"
        self.manifest_path = project / "fixture-sources.json"
        self.manifest = json.loads(self.manifest_path.read_bytes())
        baseline = assess(project, project / ".evidence-graph")["evidence-graph.json"]
        self.baseline_nodes = {node["id"]: node for node in baseline["nodes"]}
        self.baseline_links = baseline["links"]
        verifier = ROOT / "tools/assumption_freshness.py"
        self.verifier = self.store("freshness-verifier.py", verifier_revision(), verifier.read_bytes())
        self.profile = self.store("consumer-assumption-profile.json", PROBE_REVISION, profile_bytes)
        self.router = self.store("pinned-router-store.js", CORE, router_bytes)
        self.spec = "CORE.REQ.EKRWAE-005"
        self.model = "CORE.MODEL.EXECUTION-RECOVERY"

    def store(self, name, revision, data):
        coord = coordinate(name, revision, data)
        with (self.project / name).open("xb") as output:
            output.write(data)
        self.manifest["files"][name] = {"revision": revision, "sha256": coord["sha256"]}
        return coord

    def context(self, policy, scope, probe_hash):
        code, mapping = PINNED_SOURCES[policy["kind"]]
        ids = {self.spec, self.model, code, mapping}
        if policy["kind"] == "runtime":
            ids.update({"CORE.CODE.LEDGER", ROUTER_STORE})
        sources = {i: self.router if i == ROUTER_STORE else content_coordinate(self.baseline_nodes[i]) for i in sorted(ids)}
        sources.update({VERIFIER: self.verifier, policy["assumption_id"]: self.profile})
        bindings = {i: {k: source[k] for k in ("revision", "sha256")} for i, source in sources.items()}
        fields = ("assumption_id", "proposition", "owner", "probe_id", "ttl_seconds", "failure_behavior", "blind_spots")
        return {**{key: policy[key] for key in fields}, "schema_version": CONTEXT,
                "environment_scope_hash": scope_hash(scope), "evidence_bindings": bindings,
                "versions": {"spec": sources[self.spec]["revision"], "model": sources[self.model]["revision"],
                             "code": sources[code]["revision"], "mapping": sources[mapping]["revision"],
                             "verifier": self.verifier["revision"], "probe": probe_hash}}

    def compile(self, contexts, active, history, now):
        watched = [ctx["assumption_id"] for ctx in contexts.values()]
        original = self.baseline_nodes["CORE.TEST.RECOVERY"]
        alias = {key: original[key] for key in ("kind", "coordinate", "evidence_state", "bindings", "receipt_checks")}
        nodes = [{"id": VERIFIER, "kind": "VERIFIER", "coordinate": self.verifier},
                 {"id": ROUTER_STORE, "kind": "CODE", "coordinate": self.router},
                 {**alias, "id": CLAIM, "required_assumption_ids": watched}]
        links = [{"from": CLAIM, "to": item, "relation": "requires"} for item in watched]
        for edge in self.baseline_links:
            source, target = edge["from"], edge["to"]
            if "CORE.TEST.RECOVERY" in (source, target):
                links.append({"from": CLAIM if source == "CORE.TEST.RECOVERY" else source,
                              "to": CLAIM if target == "CORE.TEST.RECOVERY" else target,
                              "relation": edge["relation"]})
        for kind, ctx in contexts.items():
            aid = ctx["assumption_id"]
            current = active[kind]
            nodes.append({"id": aid, "kind": "ASSUMPTION", "coordinate": self.profile,
                          "current_probe_id": current})
            for identifier, receipt in history[kind].items():
                node = {"id": identifier, "kind": "PROBE", "probe_context": ctx}
                if receipt is not None:
                    node["coordinate"] = receipt
                nodes.append(node)
                links.extend({"from": identifier, "to": target,
                              "relation": "probes" if target == aid else "binds"}
                             for target in ctx["evidence_bindings"])
        write_json(self.manifest_path, self.manifest)
        write_json(self.overlay, {"schema_version": "evidence-receipt/v1", "nodes": nodes, "links": links})
        return assess(self.project, self.project / ".evidence-graph", now=now)


def pilot(args, core, project):
    node = str(Path(shutil.which("node")).resolve())
    profile_bytes = (core / PROFILE).read_bytes()
    profile = json.loads(profile_bytes)
    require(profile["core_revision"] == CORE, "Core probe profile targets a different implementation")
    probe_sha = digest((core / PROBE).read_bytes())
    router_source = "packages/agent-router/src/reconciliation/store.js"
    graph = PilotGraph(project, profile_bytes, (core / router_source).read_bytes())
    history = {kind: {} for kind in PINNED_SOURCES}
    active = {}
    snapshots = {}
    receipts = {}

    with router_fixture(node, core) as (process, port):
        scope = {"profile": profile["profile_id"], "platform": platform.system(), "machine": platform.machine(),
                 "node_sha256": digest(Path(node).read_bytes()), "core_revision": CORE,
                 "probe_commit": PROBE_REVISION, "profile_sha256": digest(profile_bytes), "loopback_port": port,
                 "scratch_device": core.stat().st_dev}
        contexts = {p["kind"]: graph.context(p, scope, probe_sha) for p in profile["probes"]}

        def observe(kind, label, expected):
            ctx = contexts[kind]
            argv = [node, str(core / PROBE), kind] + ([str(port)] if kind == "router" else [])
            inputs = {"probe": core / PROBE, "profile": core / PROFILE, "runtime": Path(node)}
            inputs.update({f"loaded_source_{i}": core / src["path"] for i, src in enumerate(profile["loaded_sources"])})
            receipt = run_probe(ctx, scope, inputs, argv, cwd=core)
            require(receipt["status"] == expected, f"Unexpected actual {kind}/{label}: {receipt['status']}")
            name = f"{kind}-{label}.json"
            write_json(args.output / name, receipt)
            identifier = f"{ctx['probe_id']}.{label.upper()}"
            history[kind][identifier] = graph.store(name, PROBE_REVISION, (args.output / name).read_bytes())
            active[kind] = identifier
            receipts[label if kind == "router" else kind] = receipt
            return identifier

        def snapshot(label, verdicts, claim, *, clock=None, current=None):
            expected_context = contexts if current is None else current
            compiled = graph.compile(expected_context, active, history, clock or datetime.now(timezone.utc))
            g = compiled["evidence-graph.json"]
            require(not g["diagnostics"], f"{label}: unexpected graph diagnostics: {g['diagnostics']}")
            nodes = {n["id"]: n for n in g["nodes"]}
            probe_states = {kind: nodes[i]["probe_assessment"]["status"] for kind, i in active.items()}
            require(probe_states == verdicts, f"{label}: unexpected probe verdicts: {probe_states}")
            result = nodes[CLAIM]
            require(result["evidence_status"] == claim and result["execution_evidence_status"] == "VERIFIED"
                    and nodes["CORE.LEAN.KERNEL-CI"]["evidence_status"] == "VERIFIED",
                    f"{label}: unexpected dependent coverage: {result['evidence_status']}")
            output = args.output / label
            output.mkdir()
            for filename, report in compiled.items():
                write_json(output / filename, report)
            snapshots[label] = {"probes": probe_states, "claim": claim, "current_probes": dict(active),
                                "assumptions": result["assumption_dependencies"]}

        all_pass = {kind: "PASS" for kind in contexts}
        write_json(args.output / "environment.json", scope)
        write_json(args.output / "contexts.json", contexts)
        observe("ledger", "initial", "PASS")
        observe("runtime", "initial", "PASS")
        missing = contexts["router"]["probe_id"] + ".NOT-RUN"
        history["router"][missing] = None
        active["router"] = missing
        snapshot("not-executed", {**all_pass, "router": "UNKNOWN"}, "UNKNOWN")
        prior = observe("router", "ready", "PASS")
        snapshot("fresh", all_pass, "VERIFIED")
        expiry = max(datetime.fromisoformat(r["expires_at"]) for r in receipts.values())
        snapshot("ttl-expired", {kind: "STALE" for kind in contexts}, "STALE", clock=expiry)
        changed_scope = {**contexts["router"], "environment_scope_hash": scope_hash({**scope, "profile": "other-fixture"})}
        snapshot("scope-drift", {**all_pass, "router": "STALE"}, "STALE", current={**contexts, "router": changed_scope})
        changed_versions = {**contexts["router"], "versions": {**contexts["router"]["versions"], "model": "0" * 40}}
        snapshot("version-drift", {**all_pass, "router": "STALE"}, "STALE", current={**contexts, "router": changed_versions})
        set_route(process, "unavailable", False)
        observe("router", "failed", "FAIL")
        require(receipts["failed"]["evidence"]["http_status"] == 503, "Expected real loopback HTTP 503")
        snapshot("route-failed", {**all_pass, "router": "FAIL"}, "UNKNOWN")
        set_route(process, "ready", True)
        snapshot("route-ready-with-old-receipts", {**all_pass, "router": "FAIL"}, "UNKNOWN")
        recovered = observe("router", "recovered", "PASS")
        require(receipts["ready"]["evidence"]["receipt_sha256"] == receipts["recovered"]["evidence"]["receipt_sha256"],
                "Recovery returned a different original correlation receipt")
        require(recovered != prior and assess_receipt(receipts["ready"], contexts["router"], datetime.now(timezone.utc))["status"] == "PASS",
                "The older PASS must still be within TTL for the fallback control")
        snapshot("recovered", all_pass, "VERIFIED")
    return {"schema_version": "core-assumption-freshness-check/v1", "core_revision": CORE,
            "probe_commit": PROBE_REVISION, "verifier_sha256": verifier_revision(), "snapshots": snapshots,
            "router_http": [receipts[key]["evidence"]["http_status"] for key in ("ready", "failed", "recovered")],
            "receipt_hashes": {name.name: digest(name.read_bytes()) for name in sorted(args.output.glob("*-*.json"))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories", type=Path, required=True)
    parser.add_argument("--core-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="core-assumptions-") as temporary:
        root = Path(temporary).resolve()
        core = root / "core"
        core.mkdir()
        import_core(args.core_repo, core)
        project = root / "graph-project"
        materialize(FIXTURE, args.repositories, project, {"dsh-agent-core": args.core_repo})
        result = pilot(args, core, project)
        write_json(args.output / "core-assumption-freshness.json", result)
    print(args.output / "core-assumption-freshness.json")


if __name__ == "__main__":
    main()
