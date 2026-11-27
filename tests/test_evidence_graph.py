from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "evidence_graph.py"


def node(**value):
    return "@evidence-node " + json.dumps(value, separators=(",", ":"))


def link(source, target, relation="supports"):
    return "@evidence-link " + json.dumps({"from": source, "to": target, "relation": relation}, separators=(",", ":"))


class EvidenceGraphCompilerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "spec").mkdir()

    def put(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def run_cli(self, command="validate"):
        return subprocess.run([sys.executable, str(SCRIPT), command, "--project", str(self.root)],
                              text=True, capture_output=True, timeout=10)

    def coordinate(self, name, text, revision):
        return {"path": name, "revision": revision,
                "sha256": hashlib.sha256(self.put(name, text).read_bytes()).hexdigest()}

    @staticmethod
    def binding(coordinate):
        return {k: coordinate[k] for k in ("revision", "sha256")}

    def valid_fixture(self):
        req = self.coordinate("spec.md", "# REQ-001", "spec-r1")
        model = self.coordinate("Model.lean", "namespace Model\ntheorem t : True := trivial\nend Model",
                                "model-r1")
        code = self.coordinate("src/service.py", "def apply_transition(state, event):\n    return state\n",
                               "code-r1")
        audit = {"schema": "primitives-lean-verification/v1", "status": "PASS_CONDITIONAL_MODEL_PROOFS",
                 "commands": [{"exit_code": 0}], "theorem_axioms": {"Model.t": []},
                 "compiled_declarations": {"Model.t": {"kind": "theorem", "axioms": []}},
                 "source_sha256": {"Model.lean": model["sha256"]}}
        lean = self.coordinate("lean-receipt.json", json.dumps(audit), "model-r1")
        inputs = {"MODEL-001": self.binding(model), "CODE-001": self.binding(code)}
        executed = {"status": "PASS", "exit_code": 0, "summary": {"tests": 1, "pass": 1, "fail": 0},
                    "evidence_bindings": inputs}
        tested = self.coordinate("test-run.json", json.dumps(executed), "code-r1")
        acceptance = {"status": "PASS", "exit_code": 0, "requirement_ids": ["REQ-001"],
                      "evidence_bindings": {"REQ-001": self.binding(req)}}
        accepted = self.coordinate("acceptance.json", json.dumps(acceptance), "spec-r1")
        self.put("spec/requirements.md", "\n".join([
            node(id="REQ-001", kind="REQ", critical=True, coordinate=req),
            node(id="MODEL-001", kind="MODEL", coordinate=model),
            node(id="PROP-001", kind="PROP", critical=True),
            node(id="THM-001", kind="THM", coordinate={**model, "symbol": "Model.t"}),
            node(id="LEAN-001", kind="LEAN", coordinate=lean, evidence_state="PASS",
                 bindings={"MODEL-001": self.binding(model), "THM-001": self.binding(model)}),
            node(id="TRANS-001", kind="TRANSITION", critical=True),
            node(id="CODE-001", kind="CODE", coordinate=code),
            node(id="MAP-001", kind="MAP", coordinate={**code, "symbol": "apply_transition"}),
            node(id="TEST-001", kind="TEST", critical=True, coordinate=tested, evidence_state="PASS",
                 bindings=inputs),
            node(id="ACC-001", kind="ACCEPTANCE", critical=True, coordinate=accepted,
                 requirement_ids=["REQ-001"], evidence_state="PASS",
                 bindings={"REQ-001": self.binding(req)}),
            link("REQ-001", "MODEL-001"), link("REQ-001", "ACC-001"), link("PROP-001", "THM-001"),
            link("LEAN-001", "THM-001"), link("LEAN-001", "MODEL-001"), link("TRANS-001", "MAP-001"),
            link("TEST-001", "MODEL-001"), link("TEST-001", "CODE-001"),
        ]))

    def graph_nodes(self):
        graph = json.loads((self.root / ".evidence-graph/evidence-graph.json").read_text())
        return {n["id"]: n for n in graph["nodes"]}

    def stale_codes(self):
        stale = json.loads((self.root / ".evidence-graph/stale-evidence.json").read_text())
        return {d["code"] for d in stale["items"]}

    def test_valid_graph_builds_four_derived_reports(self):
        self.valid_fixture()
        result = self.run_cli("validate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = self.root / ".evidence-graph"
        for name in ("evidence-graph.json","coverage-report.json","dangling-links.json","stale-evidence.json"):
            self.assertTrue((out/name).is_file(), name)
        graph = json.loads((out/"evidence-graph.json").read_text())
        self.assertEqual(graph["schema_version"], "evidence-graph/v1")
        self.assertEqual(len(graph["nodes"]), 10)
        for identifier in ("LEAN-001", "TEST-001", "ACC-001"):
            self.assertEqual(self.graph_nodes()[identifier]["evidence_status"], "VERIFIED")

    def test_duplicate_ids_are_rejected_not_silently_overwritten(self):
        self.put("a.md", node(id="REQ-001",kind="REQ") )
        self.put("b.md", node(id="REQ-001",kind="REQ") )
        result=self.run_cli()
        self.assertNotEqual(result.returncode,0)
        graph=json.loads((self.root/".evidence-graph/evidence-graph.json").read_text())
        self.assertTrue(any(x["code"]=="DUPLICATE_ID" for x in graph["diagnostics"]))

    def test_dangling_reference_is_reported(self):
        self.put("spec/a.md", node(id="REQ-001",kind="REQ")+ "\n"+link("REQ-001","MODEL-MISSING"))
        result=self.run_cli()
        self.assertNotEqual(result.returncode,0)
        data=json.loads((self.root/".evidence-graph/dangling-links.json").read_text())
        self.assertEqual(data["items"][0]["to"],"MODEL-MISSING")

    def test_critical_requirement_without_model_or_acceptance_is_uncovered(self):
        self.put("spec/a.md", node(id="REQ-001",kind="REQ",critical=True))
        result=self.run_cli()
        self.assertNotEqual(result.returncode,0)
        data=json.loads((self.root/".evidence-graph/coverage-report.json").read_text())
        self.assertEqual(data["summary"]["requirements"]["uncovered"],["REQ-001"])

    def test_explicit_deferred_property_is_visible_but_not_called_proven(self):
        self.put("spec/a.md", node(id="PROP-001",kind="PROP",critical=True,deferred_reason="No sound abstraction yet"))
        self.assertEqual(self.run_cli().returncode,1)
        data=json.loads((self.root/".evidence-graph/coverage-report.json").read_text())
        row=data["properties"][0]
        self.assertTrue(row["deferred"])
        self.assertFalse(row["covered"])
        self.assertFalse(bool(row["theorems"]))

    def test_mapping_requires_real_file_and_declared_symbol(self):
        self.put("spec/a.md", node(id="MAP-001",kind="MAP",coordinate={"path":"src/missing.py","symbol":"run"}))
        self.assertNotEqual(self.run_cli().returncode,0)
        data=json.loads((self.root/".evidence-graph/coverage-report.json").read_text())
        self.assertFalse(data["mappings"][0]["valid"])

    def test_model_revision_mismatch_and_expired_probe_are_stale(self):
        self.put("spec/a.md", "\n".join([
            node(id="MODEL-001",kind="MODEL",revision="model-new"),
            node(id="THM-001",kind="THM",model_revision="model-old"),
            node(id="PROBE-001",kind="PROBE",executed_at="2020-01-01T00:00:00Z",ttl_seconds=1),
            link("THM-001","MODEL-001")
        ]))
        self.run_cli("build")
        data=json.loads((self.root/".evidence-graph/stale-evidence.json").read_text())
        codes={row["code"] for row in data["items"]}
        self.assertIn("MODEL_REVISION_MISMATCH",codes)
        self.assertIn("PROBE_EXPIRED",codes)

    def test_receipt_schema_is_consumed_as_derived_input(self):
        payload={"schema_version":"evidence-receipt/v1","nodes":[{"id":"TRACE-001","kind":"TRACE"}],
                 "links":[]}
        self.put("receipts/run.json",json.dumps(payload))
        self.assertEqual(self.run_cli("build").returncode,0)
        graph=json.loads((self.root/".evidence-graph/evidence-graph.json").read_text())
        self.assertIn("TRACE-001",{n["id"] for n in graph["nodes"]})

    def test_symbol_reference_in_a_comment_is_not_an_implementation(self):
        self.valid_fixture()
        self.put("src/service.py", "# def apply_transition(state, event): return state")
        self.assertEqual(self.run_cli("stale").returncode, 1)
        self.assertIn("SYMBOL_NOT_FOUND", self.stale_codes())

    def test_weakened_same_name_theorem_invalidates_proof(self):
        self.valid_fixture()
        self.put("Model.lean", "namespace Model\ntheorem t : True := True.intro\nend Model")
        self.assertEqual(self.run_cli("stale").returncode, 1)
        self.assertEqual(self.graph_nodes()["LEAN-001"]["evidence_status"], "STALE")

    def test_code_and_receipt_deletion_are_invalidations(self):
        self.valid_fixture()
        (self.root / "src/service.py").unlink()
        (self.root / "test-run.json").unlink()
        self.assertEqual(self.run_cli("stale").returncode, 1)
        self.assertIn("COORDINATE_FILE_MISSING", self.stale_codes())
        self.assertEqual(self.graph_nodes()["TEST-001"]["evidence_status"], "STALE")

    def test_wrong_original_requirement_is_not_reusable(self):
        self.valid_fixture()
        authority = self.root / "spec/requirements.md"
        text = authority.read_text().replace(link("REQ-001", "ACC-001"), link("REQ-002", "ACC-001"))
        authority.write_text(text + "\n" + node(id="REQ-002", kind="REQ"))
        self.assertEqual(self.run_cli("stale").returncode, 1)
        self.assertIn("ACCEPTANCE_REQUIREMENT_MISMATCH", self.stale_codes())

    def test_unknown_execution_stays_unknown_even_with_a_pass_artifact(self):
        self.valid_fixture()
        authority = self.root / "spec/requirements.md"
        authority.write_text(authority.read_text().replace(
            '"evidence_state":"PASS","bindings":{"MODEL-001"',
            '"evidence_state":"UNKNOWN","bindings":{"MODEL-001"'))
        self.assertEqual(self.run_cli("validate").returncode, 1)
        self.assertEqual(self.graph_nodes()["TEST-001"]["evidence_status"], "UNKNOWN")

    def test_failed_test_cannot_be_promoted_by_selecting_a_true_field(self):
        self.valid_fixture()
        path = self.root / "test-run.json"
        previous = hashlib.sha256(path.read_bytes()).hexdigest()
        raw = json.loads(path.read_text())
        raw.update(exit_code=1)
        replacement = self.coordinate("test-run.json", json.dumps(raw), "code-r1")
        authority = self.root / "spec/requirements.md"
        authority.write_text(authority.read_text().replace(previous, replacement["sha256"]))
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertEqual(self.graph_nodes()["TEST-001"]["evidence_status"], "UNKNOWN")

    def test_rebinding_only_descriptor_to_new_revision_does_not_rebind_native_test(self):
        self.valid_fixture()
        authority = self.root / "spec/requirements.md"
        authority.write_text(authority.read_text().replace("code-r1", "code-r2"))
        self.assertEqual(self.run_cli("stale").returncode, 1)
        self.assertIn("RECEIPT_BINDING_MISMATCH", self.stale_codes())

    def test_generic_observation_is_not_a_lean_audit(self):
        self.valid_fixture()
        path = self.root / "lean-receipt.json"
        previous = hashlib.sha256(path.read_bytes()).hexdigest()
        replacement = self.coordinate("lean-receipt.json", '{"status":"PASS"}', "model-r1")
        authority = self.root / "spec/requirements.md"
        authority.write_text(authority.read_text().replace(previous, replacement["sha256"]))
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertEqual(self.graph_nodes()["LEAN-001"]["evidence_status"], "UNKNOWN")

    def test_materialized_fixture_without_source_map_is_invalid(self):
        self.valid_fixture()
        self.put("fixture.evidence.json", json.dumps(
            {"schema_version":"evidence-receipt/v1", "nodes":[], "links":[]}))
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertEqual(self.graph_nodes()["LEAN-001"]["evidence_status"], "STALE")

    def test_removed_single_material_entry_invalidates_dependent_evidence(self):
        self.valid_fixture()
        self.put("fixture.evidence.json", json.dumps(
            {"schema_version":"evidence-receipt/v1", "nodes":[], "links":[]}))
        files = {}
        for n in self.graph_fixture_nodes():
            coordinate = n.get("coordinate")
            if coordinate and coordinate["path"] != "src/service.py":
                files[coordinate["path"]] = self.binding(coordinate)
        self.put("fixture-sources.json", json.dumps({"schema_version":"evidence-sources/v1", "files":files}))
        self.assertEqual(self.run_cli("stale").returncode, 1)
        self.assertEqual(self.graph_nodes()["TEST-001"]["evidence_status"], "STALE")
        self.assertIn("SOURCE_MATERIAL_UNBOUND", self.stale_codes())

    def graph_fixture_nodes(self):
        prefix = "@evidence-node "
        return [json.loads(line[len(prefix):]) for line in
                (self.root / "spec/requirements.md").read_text().splitlines()
                if line.startswith(prefix)]


if __name__=="__main__":
    unittest.main()
