#!/usr/bin/env python3
"""Evidence Graph 统一收敛层的新增负控/正控（收敛审查 Task 3/5）。

在 v1 基础上锁定的增量语义：
  1. Kotlin `fun` / Dart 顶层函数符号识别（差分实测：v1 原 SUFFIXES 与
     关键词表不含 Kotlin/Dart——codex-go 试点无法接入的真实缺口）。
  2. 行注释剥离：注释掉的声明不得充当符号证据。
  3. build_id 确定性（吸收 #21）：同一输入重复 build → 相同 build_id；
     输入变化 → build_id 变化；墙钟不入 build_id。
  4. compiler_revision 入图元数据（消费端固定依赖与失效判定依据）。
  5. TEST 回执必填绑定：缺 toolchain / executed_at → UNKNOWN（state=PASS
     也不得 VERIFIED）。
  6. PROBE 必填 blind_spots：缺失 → UNKNOWN。
  7. failure_codes JSON：validate 输出按 parse/coordinate/stale/
     critical_uncovered 分类（退出码保持 v1 布尔语义）。
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import evidence_graph as eg  # noqa: E402
from test_evidence_graph import EvidenceGraphCompilerTests as Base  # noqa: E402
from test_evidence_graph import node, link  # noqa: E402


class UnifiedSymbolTest(Base):
    """符号识别扩展：Kotlin fun / Dart 顶层函数 / 行注释剥离。"""

    def test_kotlin_fun_symbol_is_found(self):
        code = self.coordinate(
            "src/Bridge.kt",
            "class EngineBridge {\n"
            "    private fun stopEngine(): Boolean {\n"
            "        return true\n"
            "    }\n"
            "}\n", "code-r1")
        spec = self.coordinate("spec.md", "# REQ-001\n", "spec-r1")
        # v1 分布式 annotation：@evidence-node/@evidence-link 指令嵌在权威源内
        self.put("spec/pilot.md",
                 node(id="REQ-1", kind="REQ", coordinate=spec) + "\n" +
                 node(id="MAP-STOP", kind="MAP",
                      coordinate={"path": "src/Bridge.kt", "symbol": "stopEngine",
                                  "sha256": code["sha256"]}) + "\n" +
                 link("REQ-1", "MAP-STOP"))
        result = self.run_cli("validate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                           .read_text())
        map_node = [n for n in graph["nodes"] if n["id"] == "MAP-STOP"][0]
        self.assertTrue(map_node["coordinate_valid"], "Kotlin fun 符号必须可识别")

    def test_dart_top_level_function_is_found(self):
        code = self.coordinate(
            "src/compactor.dart",
            "String compactedContinuation(\n"
            "  List entries, {\n"
            "  int maxChars = 1000,\n"
            "}) {\n"
            "  return '';\n"
            "}\n", "code-r1")
        self.put("spec/pilot.md",
                 node(id="MAP-COMPACT", kind="MAP",
                      coordinate={"path": "src/compactor.dart",
                                  "symbol": "compactedContinuation",
                                  "sha256": code["sha256"]}))
        result = self.run_cli("validate")
        graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                           .read_text())
        map_node = [n for n in graph["nodes"] if n["id"] == "MAP-COMPACT"][0]
        self.assertTrue(map_node["coordinate_valid"],
                        "Dart 顶层函数必须可识别")
        self.assertEqual(result.returncode, 0)

    def test_commented_out_symbol_does_not_count(self):
        code = self.coordinate(
            "src/gone.py",
            "# def stopEngineGone():\n"
            "#     return True\n", "code-r1")
        self.put("spec/pilot.md",
                 node(id="MAP-GONE", kind="MAP",
                      coordinate={"path": "src/gone.py", "symbol": "stopEngineGone",
                                  "sha256": code["sha256"]}))
        self.run_cli("validate")
        graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                           .read_text())
        codes = {d["code"] for d in graph["diagnostics"]}
        self.assertIn("SYMBOL_NOT_FOUND", codes,
                      "行注释内的声明不得充当符号证据")

    def test_call_without_declaration_does_not_count(self):
        for suffix in (".dart", ".kt"):
            for statement in ("return missing()", "yield missing()", "throw missing()"):
                with self.subTest(suffix=suffix, statement=statement):
                    self.assertFalse(eg.find_symbol(f"  {statement};\n", "missing", suffix))


class UnifiedDeterminismTest(Base):
    """build_id 确定性（墙钟不入 build_id）+ compiler_revision 元数据。"""

    def _valid(self):
        self.valid_fixture()
        self.assertEqual(self.run_cli("validate").returncode, 0)
        return json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                          .read_text())

    def test_build_id_stable_across_rebuilds(self):
        g1 = self._valid()
        import time
        time.sleep(1.1)  # generated_at 必然变化
        g2 = self._valid()
        self.assertEqual(g1["build_id"], g2["build_id"],
                         "同一输入重复 build 的 build_id 必须一致")
        self.assertNotEqual(g1["generated_at"], g2["generated_at"],
                            "generated_at 为墙钟——build_id 不得包含它")

    def test_build_id_changes_when_input_changes(self):
        g1 = self._valid()
        # 只改输入并重跑 validate（不重新物化原始输入）
        self.put("src/service.py",
                 "def apply_transition(state, event):\n    return 'changed'\n")
        self.run_cli("validate")
        g2 = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                        .read_text())
        self.assertNotEqual(g1["build_id"], g2["build_id"],
                            "输入变化必须改变 build_id")

    def test_compiler_revision_recorded(self):
        g = self._valid()
        self.assertTrue(g.get("compiler_revision"))
        self.assertEqual(len(g["compiler_revision"]), 32)


class UnifiedReceiptBindingTest(Base):
    """Task 3 必填绑定：缺失即 UNKNOWN，PASS 不得自动升 CURRENT。"""

    def _test_node_receipt(self, receipt_overrides):
        code = self.coordinate(
            "src/service.py", "def apply_transition(state, event):\n    return state\n",
            "code-r1")
        model = self.coordinate("Model.lean",
                                "namespace Model\nend Model", "model-r1")
        test_src = self.coordinate("test/test_x.py", "def test_x():\n    pass\n",
                                   "test-r1")
        executed = {
            "status": "PASS", "exit_code": 0,
            "summary": {"tests": 1, "pass": 1, "fail": 0},
            "evidence_bindings": {"CODE-001": {"revision": "code-r1",
                                               "sha256": code["sha256"]},
                                  "MODEL-001": {"revision": "model-r1",
                                                "sha256": model["sha256"]}},
        }
        executed.update(receipt_overrides)
        tested = self.coordinate("test-run.json", json.dumps(executed), "code-r1")
        payload = {
            "schema_version": "evidence-receipt/v1",
            "nodes": [
                {"id": "MODEL-001", "kind": "MODEL", "source": "receipt",
                 "coordinate": model},
                {"id": "CODE-001", "kind": "CODE", "source": "receipt",
                 "coordinate": code},
                {"id": "TEST-001", "kind": "TEST", "source": "receipt",
                 "coordinate": tested, "evidence_state": "PASS",
                 "test_source": {"path": test_src["path"],
                                 "sha256": test_src["sha256"]},
                 "bindings": {"CODE-001": {"revision": "code-r1",
                                           "sha256": code["sha256"]},
                              "MODEL-001": {"revision": "model-r1",
                                            "sha256": model["sha256"]}}},
            ],
            "links": [
                {"from": "TEST-001", "to": "CODE-001", "relation": "verifies"},
                {"from": "TEST-001", "to": "MODEL-001", "relation": "verifies"},
            ],
        }
        (self.root / "evidence").mkdir(exist_ok=True)
        (self.root / "evidence" / "pilot.evidence.json").write_text(
            json.dumps(payload), encoding="utf-8")

    def _status_of(self, nid="TEST-001"):
        self.run_cli("validate")
        graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                           .read_text())
        return [n for n in graph["nodes"] if n["id"] == nid][0]["evidence_status"]

    def test_missing_toolchain_yields_unknown_despite_pass(self):
        self._test_node_receipt({})  # 无 toolchain / executed_at
        self.assertEqual(self._status_of(), "UNKNOWN",
                         "缺 toolchain/executed_at → UNKNOWN（PASS 不自动升 CURRENT）")

    def test_missing_test_source_yields_unknown(self):
        """缺 test_source 绑定 → UNKNOWN（如实报告，不阻断 CI 不伪装 PASS）"""
        code = self.coordinate(
            "src/service.py", "def apply_transition(state, event):\n    return state\n",
            "code-r1")
        model = self.coordinate("Model.lean",
                                "namespace Model\nend Model", "model-r1")
        tested = self.coordinate("test-run.json", json.dumps({
            "status": "PASS", "exit_code": 0,
            "toolchain": "gradle-8.14/jdk21",
            "executed_at": "2026-11-28T00:00:00Z",
            "summary": {"tests": 1, "pass": 1, "fail": 0},
            "evidence_bindings": {"CODE-001": {"revision": "code-r1",
                                               "sha256": code["sha256"]},
                                  "MODEL-001": {"revision": "model-r1",
                                                "sha256": model["sha256"]}},
        }), "code-r1")
        payload = {
            "schema_version": "evidence-receipt/v1",
            "nodes": [
                {"id": "MODEL-001", "kind": "MODEL", "source": "receipt",
                 "coordinate": model},
                {"id": "CODE-001", "kind": "CODE", "source": "receipt",
                 "coordinate": code},
                {"id": "TEST-001", "kind": "TEST", "source": "receipt",
                 "coordinate": tested, "evidence_state": "PASS",
                 "bindings": {"CODE-001": {"revision": "code-r1",
                                           "sha256": code["sha256"]},
                              "MODEL-001": {"revision": "model-r1",
                                            "sha256": model["sha256"]}}},
            ],
            "links": [
                {"from": "TEST-001", "to": "CODE-001", "relation": "verifies"},
                {"from": "TEST-001", "to": "MODEL-001", "relation": "verifies"},
            ],
        }
        (self.root / "evidence").mkdir(exist_ok=True)
        (self.root / "evidence" / "pilot.evidence.json").write_text(
            json.dumps(payload), encoding="utf-8")
        result = self.run_cli("validate")
        # 走 v1 语义：缺 test_source → gap → UNKNOWN → rc 0（不阻断 CI）
        # 但 coverage 如实报告 TEST 未覆盖
        self.assertEqual(result.returncode, 0, result.stdout)
        graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                           .read_text())
        test_node = [n for n in graph["nodes"] if n["id"] == "TEST-001"][0]
        self.assertEqual(test_node["evidence_status"], "UNKNOWN")
        self.assertTrue(any("test_source" in r
                            for r in test_node.get("unverified_reasons", [])))

    def test_full_bindings_yield_verified(self):
        self._test_node_receipt({"toolchain": "gradle-8.14/jdk21",
                                 "executed_at": "2026-11-28T00:00:00Z"})
        self.assertEqual(self._status_of(), "VERIFIED")

    def test_core_native_schema_field_binds_toolchain_and_execution_time(self):
        self._test_node_receipt({"schema": "core-model-pilot-test-run/v1", "node_version": "v26.7.0",
                                 "started_at": "2026-11-27T23:34:13Z"})
        self.assertEqual(self._status_of(), "VERIFIED")

    def test_missing_observed_targets_produce_stable_build_id_across_hash_seeds(self):
        self._test_node_receipt({"toolchain": "gradle-8.14/jdk21", "executed_at": "2026-11-28T00:00:00Z",
                                 "evidence_bindings": {}})
        outcomes = []
        for seed in ("1", "3", "7", "12", "82"):
            result = subprocess.run([sys.executable, eg.__file__, "validate", "--project", str(self.root)],
                                    env={**os.environ, "PYTHONHASHSEED": seed}, text=True,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json").read_bytes())
            reasons = next(n["unverified_reasons"] for n in graph["nodes"] if n["id"] == "TEST-001")
            outcomes.append((graph["build_id"], reasons))
        self.assertTrue(all(item == outcomes[0] for item in outcomes))
        self.assertIn("execution receipt omitted observed binding CODE-001", outcomes[0][1])


class ProbeBlindSpotsTest(Base):
    """PROBE 必填 blind_spots：缺失 → UNKNOWN。"""

    def _probe(self, extra):
        assumption = self.coordinate("docs/assumption.md", "# A-1\n", "a-r1")
        probe = {"status": "PASS", "exit_code": 0,
                 "executed_at": "2026-11-28T00:00:00Z",
                 "expires_at": "2026-12-28T00:00:00Z", "ttl_seconds": 2592000,
                 "environment_scope_hash": "scope-1",
                 "expected_environment_scope_hash": "scope-1"}
        probe.update(extra)
        # PROBE 节点为指令行；probe.json 是其执行回执（coordinate 指向它）
        (self.root / "evidence").mkdir(exist_ok=True)
        probe_doc = {"schema_version": "evidence-receipt/v1", **probe,
                     "toolchain": "probe-runner",
                     "evidence_bindings": {"ASSUMPTION-1": {
                         "revision": "a-r1", "sha256": assumption["sha256"]}},
                     "nodes": [], "links": []}
        (self.root / "evidence" / "probe.json").write_text(
            json.dumps(probe_doc), encoding="utf-8")
        probe_coord = self.coordinate("evidence/probe.json",
                                      json.dumps(probe_doc), "probe-r1")
        self.put("spec/pilot.md",
                 node(id="ASSUMPTION-1", kind="ASSUMPTION",
                      coordinate=assumption) + "\n" +
                 node(id="PROBE-1", kind="PROBE", evidence_state="PASS",
                      coordinate=probe_coord, blind_spots=extra.get("blind_spots"),
                      executed_at=probe["executed_at"],
                      expires_at=probe["expires_at"],
                      ttl_seconds=probe["ttl_seconds"],
                      environment_scope_hash="scope-1",
                      expected_environment_scope_hash="scope-1",
                      bindings={"ASSUMPTION-1": {"revision": "a-r1",
                                                 "sha256": assumption["sha256"]}}) + "\n" +
                 link("PROBE-1", "ASSUMPTION-1"))

    def _probe_status(self):
        self.run_cli("validate")
        graph = json.loads((self.root / ".evidence-graph" / "evidence-graph.json")
                           .read_text())
        return [n for n in graph["nodes"] if n["id"] == "PROBE-1"][0]

    def test_missing_blind_spots_yields_unknown(self):
        self._probe({})
        node = self._probe_status()
        self.assertEqual(node["evidence_status"], "UNKNOWN",
                         "缺 blind_spots 声明 → UNKNOWN")
        self.assertTrue(any("blind_spots" in r for r in node["unverified_reasons"]))

    def test_declared_blind_spots_allows_verified(self):
        self._probe({"blind_spots": "仅覆盖 proot 内 userns 可用性，不含 SELinux"})
        node = self._probe_status()
        self.assertEqual(node["evidence_status"], "VERIFIED")

    def test_scope_drift_appears_in_cli_failure_codes(self):
        self._probe({"blind_spots": "fixture only"})
        declaration = self.root / "spec/pilot.md"
        declaration.write_text(declaration.read_text().replace(
            '"expected_environment_scope_hash":"scope-1"', '"expected_environment_scope_hash":"scope-2"'
        ))
        result = self.run_cli("validate")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("PROBE_SCOPE_MISMATCH", json.loads(result.stdout)["failure_codes"]["stale"])


class FailureCodesTest(Base):
    """failure_codes JSON：退出码保持布尔，类别由输出承载。"""

    def test_failure_codes_classify(self):
        self.valid_fixture()
        # 注入悬空链接 + 重复 ID 双缺陷（分布式 annotation 形式）
        req_md = self.root / "spec" / "requirements.md"
        req_md.write_text(req_md.read_text() + "\n" +
            node(id="REQ-001", kind="REQ", critical=True) + "\n" +
            link("REQ-001", "MODEL-GHOST"))
        result = self.run_cli("validate")
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        codes = set(sum(out["failure_codes"].values(), []))
        self.assertIn("DUPLICATE_ID", codes)
        self.assertIn("DANGLING_LINK", codes)


if __name__ == "__main__":
    unittest.main()
