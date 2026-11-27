from __future__ import annotations
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

    def valid_fixture(self):
        self.put("spec/requirements.md", "\n".join([
            node(id="REQ-001", kind="REQ", critical=True, revision="spec-r1"),
            node(id="MODEL-001", kind="MODEL", revision="model-r1"),
            node(id="PROP-001", kind="PROP", critical=True),
            node(id="THM-001", kind="THM", model_revision="model-r1"),
            node(id="TRANS-001", kind="TRANSITION", critical=True),
            node(id="MAP-001", kind="MAP", coordinate={"path":"src/service.py","symbol":"def apply_transition"}),
            node(id="ACC-001", kind="ACCEPTANCE", spec_revision="spec-r1"),
            link("REQ-001","MODEL-001"), link("REQ-001","ACC-001"),
            link("PROP-001","THM-001"), link("TRANS-001","MAP-001")
        ]))
        self.put("src/service.py", "def apply_transition(state, event):\n    return state\n")

    def test_valid_graph_builds_four_derived_reports(self):
        self.valid_fixture()
        result = self.run_cli("validate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = self.root / ".evidence-graph"
        for name in ("evidence-graph.json","coverage-report.json","dangling-links.json","stale-evidence.json"):
            self.assertTrue((out/name).is_file(), name)
        graph = json.loads((out/"evidence-graph.json").read_text())
        self.assertEqual(graph["schema_version"], "evidence-graph/v1")
        self.assertEqual(len(graph["nodes"]), 7)

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
        self.assertEqual(self.run_cli().returncode,0)
        data=json.loads((self.root/".evidence-graph/coverage-report.json").read_text())
        row=data["properties"][0]
        self.assertTrue(row["deferred"])
        self.assertTrue(row["covered"])
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


if __name__=="__main__":
    unittest.main()
