#!/usr/bin/env python3
"""Evidence Graph Compiler 单元测试（Batch 1）。

覆盖任务书 §4 全部场景：
  正向：完整链 / 多 Spec 共享 Model / 一 Transition 多 MAP / DEFERRED /
        UNKNOWN 证据 / 重复 build 确定性 / Lean manifest 兼容
  负向：重复 ID / 悬空引用 / REQ 无 MODEL / PROP 未证明未 DEFERRED /
        TRANSITION 无 MAP / MAP 文件不存在 / MAP 符号不存在 /
        证明绑定错误 Model revision / 测试绑定错误 Code revision /
        Probe 过期 / 环境 scope 失配 / Acceptance 指错 REQ / 解析失败 /
        派生文件篡改后可再生 / 路径穿越
  特殊：编译器自身修改后旧回执不得冒充 / 未运行测试不得误报通过 /
        文档定理不得误识别为 Lean 定理
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_graph as eg

TOOL_DIR = Path(__file__).resolve().parent


def sha(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class Fixture:
    """在临时目录里搭一个最小可编译项目。"""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="egc-test-"))
        (self.root / "evidence" / "nodes").mkdir(parents=True)
        (self.root / "evidence" / "receipts").mkdir(parents=True)
        (self.root / "docs").mkdir()
        (self.root / "src").mkdir()
        (self.root / "tests_src").mkdir()
        # 权威源文件
        self.spec = "# SPEC-001 需求：引擎生命周期可控\n引擎可启停。\n"
        self.model = "# MODEL-FSM-E 引擎生命周期 FSM\n状态: STOPPED|STARTING|RUNNING|CRASHED\n"
        self.lean = "theorem fsm_e_stop_reaches_stopped : ∀ s, step s Stop = STOPPED\n"
        (self.root / "docs" / "spec.md").write_text(self.spec, encoding="utf-8")
        (self.root / "docs" / "model-fsm-e.md").write_text(self.model, encoding="utf-8")
        (self.root / "docs" / "model-fsm-e.lean").write_text(self.lean, encoding="utf-8")
        self.engine_code = (
            "class EngineBridge {\n"
            "  fun startEngine() {}\n"
            "  fun stopEngine() {}\n"
            "}\n")
        (self.root / "src" / "EngineBridge.kt").write_text(self.engine_code, encoding="utf-8")
        self.test_code = "class EngineBridgeTest { fun testStop() {} }\n"
        (self.root / "tests_src" / "EngineBridgeTest.kt").write_text(
            self.test_code, encoding="utf-8")

    # ---- manifest / declarations ----

    def write_manifest(self, fail_on=None, env=None, fail_on_stale=True):
        manifest = {
            "schema": eg.SCHEMA_MANIFEST,
            "project": "fixture",
            "repository": "example/fixture",
            "outputs": ".evidence",
            "policy": {"fail_on": fail_on if fail_on is not None else [
                "duplicate_id", "dangling_required_ref", "req_without_model",
                "prop_unproven_and_not_deferred", "transition_without_map",
                "dangling_code_mapping"],
                "fail_on_stale": fail_on_stale},
            "environment_scope": env or {"os": "android", "arch": "arm64"},
            "node_sources": [
                {"path": "evidence/nodes/core.json"},
            ],
            "receipt_sources": [
                {"path": "evidence/receipts/tests.json"},
                {"path": "evidence/receipts/lean.json"},
                {"path": "evidence/receipts/probes.json"},
            ],
        }
        (self.root / "evidence" / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def write_core_nodes(self, nodes, edges):
        payload = {"schema": eg.SCHEMA_NODES, "nodes": nodes, "edges": edges}
        (self.root / "evidence" / "nodes" / "core.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def default_chain(self):
        """完整合法最小链：REQ→MODEL→PROP→THM→MAP→CODE / TEST / ACCEPTANCE"""
        nodes = [
            {"id": "REQ-001", "type": "REQ",
             "source": {"path": "docs/spec.md",
                        "locator": "L1", "anchor": {"kind": "contains",
                                                    "value": "SPEC-001"}},
             "evidence_status": "DOCUMENTED"},
            {"id": "MODEL-FSM-E", "type": "MODEL",
             "source": {"path": "docs/model-fsm-e.md",
                        "anchor": {"kind": "contains", "value": "MODEL-FSM-E"}},
             "evidence_status": "DOCUMENTED"},
            {"id": "TRANS-STOP", "type": "TRANSITION",
             "source": {"path": "docs/model-fsm-e.md",
                        "anchor": {"kind": "contains", "value": "STOPPED"}},
             "attributes": {"from": "RUNNING", "to": "STOPPED"}},
            {"id": "PROP-STOP", "type": "PROP",
             "source": {"path": "docs/model-fsm-e.md",
                        "anchor": {"kind": "contains", "value": "STOPPED"}},
             "evidence_status": "DOCUMENTED_CLAIM"},
            {"id": "THM-STOP", "type": "THM",
             "source": {"path": "docs/model-fsm-e.lean",
                        "anchor": {"kind": "contains", "value": "theorem fsm_e_stop"}},
             "evidence_status": "NOT_PROVEN"},
            {"id": "MAP-STOP-BRIDGE", "type": "MAP",
             "source": {"path": "src/EngineBridge.kt"},
             "attributes": {"code": {"path": "src/EngineBridge.kt",
                                     "symbol": "stopEngine"},
                            "transition": "TRANS-STOP"}},
            {"id": "CODE-BRIDGE", "type": "CODE",
             "source": {"path": "src/EngineBridge.kt",
                        "anchor": {"kind": "contains", "value": "class EngineBridge"}},
             "evidence_status": "DOCUMENTED"},
            {"id": "TEST-STOP", "type": "TEST",
             "source": {"path": "tests_src/EngineBridgeTest.kt",
                        "anchor": {"kind": "contains", "value": "testStop"}},
             "evidence_status": "TEST_DECLARED"},
            {"id": "ACC-001", "type": "ACCEPTANCE",
             "source": {"path": "docs/spec.md",
                        "anchor": {"kind": "contains", "value": "SPEC-001"}},
             "evidence_status": "UNKNOWN"},
        ]
        edges = [
            {"from": "REQ-001", "rel": "DEFINES", "to": "MODEL-FSM-E",
             "source": {"path": "docs/spec.md"}},
            {"from": "MODEL-FSM-E", "rel": "DERIVED_FROM", "to": "REQ-001",
             "source": {"path": "docs/model-fsm-e.md"}},
            {"from": "TRANS-STOP", "rel": "TRANSITIONS_TO", "to": "MODEL-FSM-E",
             "source": {"path": "docs/model-fsm-e.md"}},
            {"from": "PROP-STOP", "rel": "PROVED_BY", "to": "THM-STOP",
             "source": {"path": "docs/model-fsm-e.md"}},
            {"from": "TRANS-STOP", "rel": "GUARDED_BY", "to": "PROP-STOP",
             "source": {"path": "docs/model-fsm-e.md"}},
            {"from": "TRANS-STOP", "rel": "IMPLEMENTED_BY", "to": "MAP-STOP-BRIDGE",
             "source": {"path": "docs/model-fsm-e.md"}},
            {"from": "MAP-STOP-BRIDGE", "rel": "IMPLEMENTED_BY", "to": "CODE-BRIDGE",
             "source": {"path": "src/EngineBridge.kt"}},
            {"from": "TRANS-STOP", "rel": "TESTED_BY", "to": "TEST-STOP",
             "source": {"path": "tests_src/EngineBridgeTest.kt"}},
            {"from": "ACC-001", "rel": "ACCEPTED_BY", "to": "REQ-001",
             "source": {"path": "docs/spec.md"}},
            {"from": "REQ-001", "rel": "REQUIRES", "to": "MODEL-FSM-E",
             "source": {"path": "docs/spec.md"}},
        ]
        self.write_core_nodes(nodes, edges)

    # ---- receipts ----

    def code_hash(self) -> str:
        return sha(self.engine_code)

    def write_test_receipt(self, result="PASS", exit_code=0, code_hash=None,
                           executed_at="2026-11-28T00:00:00Z", result_kind="TEST_PASSED",
                           verifier_file=None, verifier_revision=None,
                           model_revision=None, model_revision_current=None,
                           evidence_id="EV-TEST-001", scope=None):
        receipt = {
            "schema": eg.SCHEMA_RECEIPTS,
            "evidence_id": evidence_id,
            "evidence_type": result_kind,
            "targets": [{"node": "TEST-STOP", "rel": "VERIFIED_BY"}],
            "bindings": [{"kind": "code", "path": "src/EngineBridge.kt",
                          "content_hash": code_hash or self.code_hash()}],
            "toolchain": "gradle-8.14/jdk21",
            "command": "gradle :app:testDebugUnitTest",
            "exit_code": exit_code,
            "executed_at": executed_at,
            "result": result,
            "limitations": "有界单测，非一般性证明",
            "environment_scope": scope if scope is not None else {"os": "android", "arch": "arm64"},
        }
        if verifier_file:
            receipt["verifier_file"] = verifier_file
            receipt["verifier_revision"] = verifier_revision
        if model_revision is not None:
            receipt["model_revision"] = model_revision
            receipt["model_revision_current"] = model_revision_current
        (self.root / "evidence" / "receipts" / "tests.json").write_text(
            json.dumps({"schema": eg.SCHEMA_RECEIPTS, "receipts": [receipt]},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        return receipt

    def write_lean_receipt(self, thm_hash=None, verifier_file=None,
                           verifier_revision=None, model_revision=None,
                           model_revision_current=None):
        receipt = {
            "schema": eg.SCHEMA_RECEIPTS,
            "evidence_id": "EV-LEAN-001",
            "evidence_type": "PROVEN",
            "targets": [{"node": "THM-STOP", "rel": "VERIFIED_BY"}],
            "bindings": [{"kind": "lean", "path": "docs/model-fsm-e.lean",
                          "content_hash": thm_hash or sha(self.lean)}],
            "verifier_file": verifier_file,
            "verifier_revision": verifier_revision,
            "toolchain": "Lean 4.19.0",
            "command": "lake build + tools/verify_lean.py",
            "exit_code": 0,
            "executed_at": "2026-11-28T00:00:00Z",
            "result": "PASS",
            "limitations": "",
            "environment_scope": {"os": "any"},
        }
        if model_revision is not None:
            receipt["model_revision"] = model_revision
            receipt["model_revision_current"] = model_revision_current
        (self.root / "evidence" / "receipts" / "lean.json").write_text(
            json.dumps({"schema": eg.SCHEMA_RECEIPTS, "receipts": [receipt]},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    def write_probe_receipt(self, executed_at="2026-11-28T00:00:00Z",
                            ttl_hours=24, scope=None, result="PASS",
                            evidence_id="EV-PROBE-001"):
        receipt = {
            "schema": eg.SCHEMA_RECEIPTS,
            "evidence_id": evidence_id,
            "evidence_type": "PROBE_EXECUTED",
            "targets": [{"node": "MODEL-FSM-E", "rel": "VERIFIED_BY"}],
            "bindings": [],
            "command": "probe: proot userns available",
            "exit_code": 0,
            "executed_at": executed_at,
            "ttl_hours": ttl_hours,
            "result": result,
            "environment_scope": scope if scope is not None else {"os": "android", "arch": "arm64"},
            "limitations": "环境假设探针，非行为证明",
        }
        (self.root / "evidence" / "receipts" / "probes.json").write_text(
            json.dumps({"schema": eg.SCHEMA_RECEIPTS, "receipts": [receipt]},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 运行 ----

    def run(self, command="validate"):
        import subprocess
        return subprocess.run(
            [sys.executable, str(TOOL_DIR / "evidence_graph.py"), command,
             "--project", str(self.root)],
            capture_output=True, text=True)

    def graph(self) -> dict:
        return json.loads((self.root / ".evidence" / "evidence-graph.json").read_text())

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class EvidenceGraphTest(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.cleanup()

    # ---------- 正向 ----------

    def test_01_full_chain_passes(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        graph = self.fx.graph()
        self.assertEqual(len(graph["nodes"]), 9)
        verified = [e for e in graph["evidence"] if e["freshness"] == "CURRENT"]
        self.assertEqual(len(verified), 2)

    def test_02_multiple_specs_share_model(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        nodes_extra = {"schema": eg.SCHEMA_NODES, "nodes": [
            {"id": "REQ-002", "type": "REQ",
             "source": {"path": "docs/spec.md",
                        "anchor": {"kind": "contains", "value": "SPEC-001"}}}],
            "edges": [{"from": "REQ-002", "rel": "DEFINES", "to": "MODEL-FSM-E",
                       "source": {"path": "docs/spec.md"}}]}
        (self.fx.root / "evidence" / "nodes" / "extra.json").write_text(
            json.dumps(nodes_extra), encoding="utf-8")
        m = self.fx.root / "evidence" / "manifest.json"
        manifest = json.loads(m.read_text())
        manifest["node_sources"].append({"path": "evidence/nodes/extra.json"})
        m.write_text(json.dumps(manifest), encoding="utf-8")
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        cov = json.loads((self.fx.root / ".evidence" / "coverage-report.json").read_text())
        req_models = {row["req"]: row["models"] for row in cov["requirements"]}
        self.assertEqual(req_models["REQ-001"], req_models["REQ-002"])

    def test_03_one_transition_multiple_maps(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        extra = {"schema": eg.SCHEMA_NODES, "nodes": [
            {"id": "MAP-STOP-SERVICE", "type": "MAP",
             "source": {"path": "src/EngineBridge.kt"},
             "attributes": {"code": {"path": "src/EngineBridge.kt",
                                     "symbol": "EngineBridge"},
                            "transition": "TRANS-STOP"}}],
            "edges": [{"from": "TRANS-STOP", "rel": "IMPLEMENTED_BY",
                       "to": "MAP-STOP-SERVICE",
                       "source": {"path": "docs/model-fsm-e.md"}}]}
        (self.fx.root / "evidence" / "nodes" / "extra.json").write_text(
            json.dumps(extra), encoding="utf-8")
        m = self.fx.root / "evidence" / "manifest.json"
        manifest = json.loads(m.read_text())
        manifest["node_sources"].append({"path": "evidence/nodes/extra.json"})
        m.write_text(json.dumps(manifest), encoding="utf-8")
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_04_deferred_prop_is_not_violation(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        # PROP 改为 DEFERRED 且删掉 PROVED_BY 边场景：直接改 core.json
        core_path = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core_path.read_text())
        for n in payload["nodes"]:
            if n["id"] == "PROP-STOP":
                n["attributes"] = {"obligation_status": "DEFERRED"}
        payload["edges"] = [e for e in payload["edges"]
                            if not (e["from"] == "PROP-STOP" and e["rel"] == "PROVED_BY")]
        core_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        (self.fx.root / "evidence" / "receipts" / "lean.json").write_text(
            json.dumps({"schema": eg.SCHEMA_RECEIPTS, "receipts": []}), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        cov = json.loads((self.fx.root / ".evidence" / "coverage-report.json").read_text())
        states = {row["prop"]: row["state"] for row in cov["properties"]}
        self.assertEqual(states["PROP-STOP"], "DEFERRED")

    def test_05_unknown_execution_evidence(self):
        self.fx.write_manifest(fail_on_stale=False)
        self.fx.default_chain()
        self.fx.write_test_receipt(result="UNKNOWN", result_kind="TEST_EXECUTED",
                                   executed_at=None)
        self.fx.write_lean_receipt()
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        graph = self.fx.graph()
        ev = [e for e in graph["evidence"] if e["evidence_id"] == "EV-TEST-001"][0]
        self.assertEqual(ev["freshness"], "UNKNOWN")

    def test_06_deterministic_rebuild(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        r1 = self.fx.run("build")
        self.assertEqual(r1.returncode, 0)
        first = (self.fx.root / ".evidence" / "evidence-graph.json").read_bytes()
        first_cov = (self.fx.root / ".evidence" / "coverage-report.json").read_bytes()
        r2 = self.fx.run("build")
        self.assertEqual(r2.returncode, 0)
        self.assertEqual(first, (self.fx.root / ".evidence" / "evidence-graph.json").read_bytes())
        self.assertEqual(first_cov, (self.fx.root / ".evidence" / "coverage-report.json").read_bytes())

    def test_07_lean_manifest_compatibility(self):
        # 与 primitives 的 lean-verification.json 结构对齐：source_sha256 +
        # compiled_declarations + toolchain 字段可作为 receipt 事实来源
        self.fx.write_manifest()
        self.fx.default_chain()
        lean_manifest = {
            "schema": "primitives-lean-verification/v1",
            "lean_version": "Lean 4.19.0",
            "source_sha256": {"docs/model-fsm-e.lean": sha(self.fx.lean)},
            "compiled_declarations": {"Fixture.FSM.stop": {"kind": "theorem",
                                                           "axioms": []}},
        }
        (self.fx.root / "evidence" / "receipts" / "lean-manifest.json").write_text(
            json.dumps(lean_manifest, indent=2), encoding="utf-8")
        self.fx.write_lean_receipt(
            verifier_file="evidence/receipts/lean-manifest.json",
            verifier_revision=sha(json.dumps(lean_manifest, indent=2)))
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        graph = self.fx.graph()
        lean_ev = [e for e in graph["evidence"] if e["evidence_id"] == "EV-LEAN-001"][0]
        self.assertEqual(lean_ev["freshness"], "CURRENT")

    # ---------- 负向 ----------

    def test_n01_duplicate_id(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        payload["nodes"].append(dict(payload["nodes"][0]))  # 重复 REQ-001
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_n02_dangling_reference(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        payload["edges"].append({"from": "REQ-001", "rel": "DEFINES",
                                 "to": "MODEL-GHOST",
                                 "source": {"path": "docs/spec.md"}})
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_n03_req_without_model(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        payload["edges"] = [e for e in payload["edges"]
                            if not (e["from"] == "REQ-001" and e["rel"] == "DEFINES")]
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)

    def test_n04_prop_unproven_and_not_deferred(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        (self.fx.root / "evidence" / "receipts" / "lean.json").write_text(
            json.dumps({"schema": eg.SCHEMA_RECEIPTS, "receipts": []}),
            encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)

    def test_n05_transition_without_map(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        payload["edges"] = [e for e in payload["edges"]
                            if not (e["from"] == "TRANS-STOP"
                                    and e["rel"] == "IMPLEMENTED_BY")]
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)

    def test_n06_map_targets_missing_file(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        for n in payload["nodes"]:
            if n["id"] == "MAP-STOP-BRIDGE":
                n["attributes"]["code"]["path"] = "src/Missing.kt"
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_n07_map_targets_missing_symbol(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        for n in payload["nodes"]:
            if n["id"] == "MAP-STOP-BRIDGE":
                n["attributes"]["code"]["symbol"] = "stopEngineGone"
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("stopEngineGone", r.stdout)

    def test_n08_proof_bound_to_wrong_model_revision(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt(model_revision="rev-OLD",
                                   model_revision_current="rev-NEW")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        graph = self.fx.graph()
        lean_ev = [e for e in graph["evidence"] if e["evidence_id"] == "EV-LEAN-001"][0]
        self.assertEqual(lean_ev["freshness"], "STALE")

    def test_n09_test_bound_to_wrong_code_revision(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        # 回执记录的是旧代码 hash；当前文件内容不同 → STALE
        self.fx.write_test_receipt(code_hash=sha("OLD CODE THAT NO LONGER EXISTS"))
        self.fx.write_lean_receipt()
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        graph = self.fx.graph()
        ev = [e for e in graph["evidence"] if e["evidence_id"] == "EV-TEST-001"][0]
        self.assertEqual(ev["freshness"], "STALE")
        self.assertTrue(any("content_hash 失配" in x for x in ev["reasons"]))

    def test_n10_probe_expired(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.fx.write_probe_receipt(executed_at=old, ttl_hours=24)
        r = self.fx.run("stale")
        self.assertEqual(r.returncode, 6, r.stdout)
        self.assertIn("EV-PROBE-001", r.stdout)

    def test_n11_environment_scope_mismatch(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        self.fx.write_probe_receipt(scope={"os": "linux", "arch": "x86_64"})
        r = self.fx.run("stale")
        self.assertEqual(r.returncode, 6)
        graph = self.fx.graph()
        probe = [e for e in graph["evidence"] if e["evidence_id"] == "EV-PROBE-001"][0]
        self.assertEqual(probe["freshness"], "STALE")

    def test_n12_acceptance_points_to_wrong_req(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        for e in payload["edges"]:
            if e["from"] == "ACC-001" and e["rel"] == "ACCEPTED_BY":
                e["to"] = "REQ-GHOST"
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_n13_unparseable_input(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        core.write_text("{ not valid json !!!", encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_n14_tampered_outputs_regenerate(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        self.assertEqual(self.fx.run("build").returncode, 0)
        pristine = (self.fx.root / ".evidence" / "evidence-graph.json").read_bytes()
        # 人工篡改派生文件（模拟手动改 graph）
        out = self.fx.root / ".evidence" / "evidence-graph.json"
        tampered = json.loads(out.read_text())
        tampered["nodes"][0]["evidence_status"] = "PROVEN"  # 越权改动
        out.write_text(json.dumps(tampered), encoding="utf-8")
        self.assertNotEqual(pristine, out.read_bytes())
        # 重新 build：派生物回到确定性内容，篡改被抹除
        self.assertEqual(self.fx.run("build").returncode, 0)
        self.assertEqual(pristine, out.read_bytes())

    def test_n15_path_traversal_rejected(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        core = self.fx.root / "evidence" / "nodes" / "core.json"
        payload = json.loads(core.read_text())
        payload["nodes"][0]["source"]["path"] = "../outside/spec.md"
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        # 绝对路径同样拒绝
        payload["nodes"][0]["source"]["path"] = "/etc/passwd"
        core.write_text(json.dumps(payload), encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    # ---------- 特殊 ----------

    def test_s01_modified_compiler_invalidates_old_receipt(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        compiler_hash = sha(TOOL_DIR.joinpath("evidence_graph.py").read_text())
        # 回执声称由「当前版本编译器」验证 → 当前
        self.fx.write_lean_receipt(
            verifier_file="tools/evidence_graph.py",
            verifier_revision=compiler_hash)
        # 先把编译器复制进 fixture 项目以存在
        tools_dir = self.fx.root / "tools"
        tools_dir.mkdir()
        shutil.copy(TOOL_DIR / "evidence_graph.py", tools_dir / "evidence_graph.py")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        # 模拟编译器升级：回执仍记旧 hash，文件已是新内容
        old_compiler = compiler_hash  # 回执记录的
        mutated = (tools_dir / "evidence_graph.py").read_text() + "\n# v2 change\n"
        (tools_dir / "evidence_graph.py").write_text(mutated)
        self.fx.write_lean_receipt(
            verifier_file="tools/evidence_graph.py",
            verifier_revision=old_compiler)
        r = self.fx.run("stale")
        self.assertEqual(r.returncode, 6, r.stdout)
        graph = self.fx.graph()
        lean_ev = [e for e in graph["evidence"] if e["evidence_id"] == "EV-LEAN-001"][0]
        self.assertEqual(lean_ev["freshness"], "STALE")

    def test_s02_unrun_test_never_reports_passed(self):
        self.fx.write_manifest(fail_on_stale=False)
        self.fx.default_chain()
        # 只有 TEST_DECLARED（声明存在，从未执行）：无 receipt
        self.fx.write_lean_receipt()
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        cov = json.loads((self.fx.root / ".evidence" / "coverage-report.json").read_text())
        row = [x for x in cov["requirements"] if x["req"] == "REQ-001"][0]
        self.assertIn(row["tests"], ("MISSING", "UNKNOWN"),
                      "未运行测试不得被识别为通过")
        self.assertNotIn(row["tests"], ("CURRENT", "PASSED"))
        # TEST_EXECUTED 但 result=UNKNOWN 同样不是 PASSED
        self.fx.write_test_receipt(result="UNKNOWN", result_kind="TEST_EXECUTED",
                                   executed_at=None)
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 0)
        ev = [e for e in self.fx.graph()["evidence"]
              if e["evidence_id"] == "EV-TEST-001"][0]
        self.assertEqual(ev["freshness"], "UNKNOWN")

    def test_s03_documented_theorem_is_not_lean_theorem(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        # 无 lean receipt：THM-STOP 的源只是文档级 .lean 描述（无编译回执）
        (self.fx.root / "evidence" / "receipts" / "lean.json").write_text(
            json.dumps({"schema": eg.SCHEMA_RECEIPTS, "receipts": []}),
            encoding="utf-8")
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 5, r.stdout)  # PROP 无 CURRENT 证明
        cov = json.loads((self.fx.root / ".evidence" / "coverage-report.json").read_text())
        states = {row["prop"]: row["state"] for row in cov["properties"]}
        self.assertEqual(states["PROP-STOP"], "UNPROVEN")
        graph = self.fx.graph()
        thm = [n for n in graph["nodes"] if n["id"] == "THM-STOP"][0]
        self.assertEqual(thm["evidence_status"], "NOT_PROVEN",
                         "文档定理不得被识别为 Lean 编译定理")

    # ---------- CLI 行为 ----------

    def test_cli_coverage_command(self):
        self.fx.write_manifest()
        self.fx.default_chain()
        self.fx.write_test_receipt()
        self.fx.write_lean_receipt()
        r = self.fx.run("coverage")
        self.assertEqual(r.returncode, 0, r.stdout)
        payload = json.loads(r.stdout)
        self.assertIn("node_counts", payload)

    def test_missing_manifest_is_error(self):
        r = self.fx.run("validate")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
