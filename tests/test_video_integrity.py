"""Reject material video-plan failures without modifying the repository."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "domains/video"
spec = importlib.util.spec_from_file_location("video_check", VIDEO / "check.py")
video_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_check)


class VideoIntegrityScenarios(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((VIDEO / "examples/decision-gate.json").read_text(encoding="utf-8"))
        catalog = json.loads((VIDEO / "catalog.json").read_text(encoding="utf-8"))
        self.known = {entry["id"] for entry in catalog["entries"]}

    def errors(self, record=None):
        return video_check.check_record(record or self.record, self.known)

    def test_unknown_primitive_cannot_be_used(self):
        self.record["presentation"]["primitives"].append("video.invented-action")
        self.assertTrue(any("unknown primitive" in e for e in self.errors()))

    def test_source_duration_cannot_replace_planned_duration(self):
        self.record["presentation"]["planned_duration_seconds"] = 45
        self.assertTrue(any("interval must fit" in e for e in self.errors()))

    def test_claimed_source_anchors_require_inspection(self):
        self.record["source"]["source_range_seconds"] = [1005, 1050]
        self.record["source"]["transcript_anchor"] = "transcript:ep03:L412-L438"
        self.record["source"]["source_status"] = "source-checked"
        errors = self.errors()
        self.assertTrue(any("source.checks" in e for e in errors), errors)
        self.assertTrue(any("synthetic proposal" in e for e in errors), errors)

    def test_synthetic_results_cannot_be_upgraded(self):
        mutations = [
            ("render", {"status": "implemented", "implemented": True,
                        "artifacts": [{"locator": "render.mp4", "scope": "simulated"}]}),
            ("factual", {"status": "checked", "records": [{"locator": "review", "scope": "simulated"}]}),
            ("accessibility", {"status": "passed", "records": [{"locator": "review", "scope": "simulated"}]}),
            ("viewer", {"status": "observed", "observations": [{"locator": "feedback", "scope": "simulated"}]}),
        ]
        for axis, mutation in mutations:
            with self.subTest(axis=axis):
                record = copy.deepcopy(self.record)
                target = record["render"] if axis == "render" else record["validation"][axis]
                target.update(mutation)
                self.assertTrue(any("synthetic" in e for e in self.errors(record)))

    def test_evidence_ground_needs_actual_evidence_assets(self):
        self.record["example_type"] = "application"
        self.record["presentation"]["primitives"].append("video.evidence-ground")
        self.record["validation"]["factual"].update(
            status="checked", records=[{"locator": "review-note", "scope": "claimed result"}]
        )
        self.assertTrue(any("require evidence assets" in e for e in self.errors()))

    def test_checklist_is_not_review_evidence(self):
        self.record["example_type"] = "application"
        self.record["validation"]["accessibility"].update(status="passed", records=["检查字幕同步"])
        self.assertTrue(any("review results need" in e for e in self.errors()))

    def test_empty_plan_is_not_a_pass(self):
        errors = video_check.check_record({}, self.known)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
