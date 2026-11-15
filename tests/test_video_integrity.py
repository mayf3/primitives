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

    def test_concurrent_events_can_share_time_with_one_primary_focus(self):
        first, second = self.record["semantic"]["objects"][:2]
        self.record["presentation"]["event_schedule"] = [
            {"id": "first", "target": first["id"], "start": 0, "end": 4},
            {"id": "second", "target": second["id"], "start": 2, "end": 5},
        ]
        self.assertEqual([], self.errors())
        self.record["presentation"]["focus_schedule"] = [
            {"target": first["id"], "start": 0, "end": 4},
            {"target": second["id"], "start": 2, "end": 5},
        ]
        self.assertTrue(any("competing primary focus" in e for e in self.errors()))

    def test_event_intervals_use_plan_time_and_traceable_ids(self):
        self.record["presentation"]["event_schedule"] = [
            {"id": "reply", "target": "unknown", "start": 1, "end": 1000},
            {"id": "reply", "target": self.record["semantic"]["objects"][0]["id"], "start": 2, "end": 4},
        ]
        errors = self.errors()
        for expected in ("interval must fit", "unknown event target", "unique nonempty ID"):
            self.assertTrue(any(expected in e for e in errors), errors)

    def test_identical_window_intervals_need_separate_lanes(self):
        record = json.loads((VIDEO / "examples/concurrent-replies.json").read_text(encoding="utf-8"))
        self.assertEqual([], self.errors(record))
        events = {e["id"]: e for e in record["presentation"]["event_schedule"]}
        events["write-04"]["lane_id"] = events["write-03"]["lane_id"]
        errors = self.errors(record)
        self.assertTrue(any("overlap in lane" in error and "write-04" in error
                            and "write-03" in error for error in errors), errors)

    def test_nested_lane_conflicts_and_touching_intervals_in_any_order(self):
        presentation = self.record["presentation"]
        target = self.record["semantic"]["objects"][0]["id"]
        presentation["event_layout"] = "lanes"
        presentation["event_schedule"] = [
            {"id": event_id, "target": target, "start": start, "end": end, "lane_id": "A"}
            for event_id, start, end in [
                ("middle", 3, 4), ("last", 5, 8), ("outer", 0, 5), ("first", 1, 2)
            ]
        ]
        errors = self.errors()
        self.assertEqual(len(errors), 2, errors)
        for event_id in ("first", "middle"):
            self.assertTrue(any(event_id in error and "outer" in error and "overlap in lane" in error
                                for error in errors), errors)
        # The short events can share B, and the two intervals on A meet at 5.
        for event in presentation["event_schedule"]:
            if event["id"] in ("first", "middle"):
                event["lane_id"] = "B"
        self.assertEqual([], self.errors())

    def test_lane_ids_are_required_only_for_lanes(self):
        record = json.loads((VIDEO / "examples/concurrent-replies.json").read_text(encoding="utf-8"))
        presentation = record["presentation"]
        for event in presentation["event_schedule"]:
            del event["lane_id"]
        for layout in ("table", "aggregate"):
            with self.subTest(layout=layout):
                record["semantic"]["event_readout"] = "aggregate"
                presentation["event_layout"] = layout
                self.assertEqual([], self.errors(record))
        presentation["event_layout"] = "lanes"
        events = presentation["event_schedule"]
        for event, invalid_id in zip(events, ("", "  ", 7, [], None)):
            event["lane_id"] = invalid_id
        errors = self.errors(record)
        self.assertEqual(len(events), sum("nonempty lane_id" in error for error in errors), errors)
        del events[0]["lane_id"]
        self.assertTrue(any("write-01" in e and "nonempty lane_id" in e for e in self.errors(record)))

    def test_invalid_event_layout_is_reported(self):
        for layout in ("lane", None, {}):
            with self.subTest(layout=layout):
                self.record["presentation"]["event_layout"] = layout
                self.assertTrue(any("presentation.event_layout" in error for error in self.errors()))

    def test_current_overlapping_events_require_independent_readout_and_layout(self):
        record = json.loads((VIDEO / "examples/concurrent-replies.json").read_text(encoding="utf-8"))
        del record["presentation"]["event_layout"]
        del record["semantic"]["event_readout"]
        for version in ("0.4.0", "0.10.0", None, "unknown"):
            with self.subTest(version=version):
                if version is None:
                    record.pop("version", None)
                else:
                    record["version"] = version
                errors = self.errors(record)
                for field in ("presentation.event_layout", "semantic.event_readout"):
                    self.assertTrue(any(field in error for error in errors), errors)

        record["version"] = "0.4.0"
        record["presentation"]["event_layout"] = "table"
        record["semantic"]["event_readout"] = "both"
        self.assertTrue(any("semantic.event_readout" in error for error in self.errors(record)))

    def test_aggregate_cannot_satisfy_individual_readout(self):
        record = json.loads((VIDEO / "examples/concurrent-replies.json").read_text(encoding="utf-8"))
        record["presentation"]["event_layout"] = "aggregate"
        self.assertTrue(any("individual event endpoints" in error for error in self.errors(record)))
        record["semantic"]["event_readout"] = "aggregate"
        notices = []
        self.assertEqual([], video_check.check_record(record, self.known, notices=notices))
        self.assertTrue(any("aggregate" in notice and "起止" in notice for notice in notices))

    def test_touching_and_disjoint_current_events_need_no_readout_or_layout(self):
        record = json.loads((VIDEO / "examples/concurrent-replies.json").read_text(encoding="utf-8"))
        presentation = record["presentation"]
        del presentation["event_layout"]
        del record["semantic"]["event_readout"]
        target = record["semantic"]["objects"][0]["id"]
        presentation["event_schedule"] = [
            {"id": name, "target": target, "start": start, "end": end}
            for name, start, end in [("later", 5, 8), ("first", 0, 2), ("next", 2, 4)]
        ]
        self.assertEqual([], self.errors(record))

    def test_legacy_concurrent_schedule_migrates_without_rewriting_events(self):
        record = json.loads((VIDEO / "examples/concurrent-replies.json").read_text(encoding="utf-8"))
        del record["semantic"]["event_readout"]
        presentation = record["presentation"]
        del presentation["event_layout"]
        del presentation["audio_alignment"]
        for event in presentation["event_schedule"]:
            del event["lane_id"]
        for version in ("0.3.0", "0.3.1", "0.3.2"):
            with self.subTest(version=version):
                record["version"] = version
                notices = []
                self.assertEqual([], video_check.check_record(record, self.known, notices=notices))
                self.assertTrue(any("迁移" in notice for notice in notices))
        record["semantic"]["event_readout"] = "individual"
        self.assertTrue(any("presentation.event_layout" in error for error in self.errors(record)))
        presentation["event_layout"] = "table"
        self.assertEqual([], self.errors(record))

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
