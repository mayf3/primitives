"""Exercises for the optional spoken-source contract, including old records."""
import importlib.util
import json
from pathlib import Path
import unittest

VIDEO = Path(__file__).resolve().parents[1] / "domains/video"
spec = importlib.util.spec_from_file_location("video_check", VIDEO / "check.py")
video_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_check)


class VideoAudioScenarios(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((VIDEO / "examples/theatre-entry.json").read_text())
        self.presentation = self.record["presentation"]
        self.alignment = self.presentation["audio_alignment"]
        self.events = self.alignment["text_events"]
        self.turns = self.alignment["turns"]
        self.ids = set(self.presentation["primitives"])

    def errors(self):
        return "\n".join(video_check.check_record(self.record, self.ids))

    def test_planned_turns_and_labelled_departures(self):
        self.assertEqual("", self.errors())
        self.events[1]["end"] = self.turns[1]["cue"] + 1
        self.assertIn("preview must finish", self.errors())
        self.events[4]["start"] = self.turns[0]["end"] - 1
        self.assertIn("recap must begin", self.errors())

    def test_legacy_silent_and_pending(self):
        del self.presentation["audio_alignment"]
        for version in ("0.4.0", "0.10.0", "unknown"):
            self.record["version"] = version
            self.assertIn("declare its status", self.errors())
        del self.record["version"]
        self.assertIn("declare its status", self.errors())
        self.record["version"] = "0.3.2"
        self.assertEqual("", self.errors())
        self.record["version"] = "0.4.0"
        for status in ("not-applicable", "pending"):
            self.presentation["audio_alignment"] = {"status": status, "reason": "无可核原音", "text_events": []}
            self.assertEqual("", self.errors())
            self.presentation["audio_alignment"]["turns"] = self.turns
            self.assertIn("no attributed events", self.errors())

    def test_anchored_needs_inspected_application_and_source_positions(self):
        self.alignment["status"] = "anchored"
        self.assertIn("anchored requires an application", self.errors())
        self.record["example_type"] = "application"
        self.record["source"].update(source_status="media-inspected", media_accessed=True,
                                     checks=[{"locator": "test:edit-A", "scope": "test-only source mapping"}])
        self.events.pop()  # No example copy enters this application fixture.
        self.assertIn("needs a locator", self.errors())
        # Deliberately different source and plan origins.
        self.turns[0]["locator"] = "test:edit-A@100–105s"
        self.turns[1]["locator"] = "test:edit-A@105–115s"
        self.assertEqual("", self.errors())
        self.record["example_type"] = "synthetic"
        self.assertIn("synthetic turn cannot claim", self.errors())

    def test_current_pain_and_later_answer(self):
        self.events[0]["intent"] = "解法"
        self.assertIn("intents differ", self.errors())
        # Even inside the answerer's turn the critical phrase has not begun.
        self.events[2]["start"] = self.turns[1]["cue"] - 1
        self.assertGreaterEqual(self.events[2]["start"], self.turns[1]["start"])
        self.assertIn("precedes its cue", self.errors())

    def test_stale_quote_becomes_an_attributed_recap(self):
        self.events[0]["end"] += 2
        self.assertIn("beyond its turn", self.errors())
        self.events[0].update(start=5, role="recap", label="前一位观众的疑问")
        self.assertEqual("", self.errors())

    def test_partial_count_cannot_be_presented_as_a_complete_overview(self):
        part, overview = self.events[2:4]
        overview["shown"] = 1
        self.assertIn("show all announced items", self.errors())
        overview["shown"] = 2
        del part["label"]
        self.assertIn("label this smaller part", self.errors())
        part.update(label="先给第一项", shown=3)
        self.assertIn("within the turn", self.errors())

    def test_editorial_example_and_paraphrase_are_not_quotes(self):
        sample = self.events[-1]
        del sample["label"]
        self.assertIn("need a visible label", self.errors())
        sample.update(role="quote", start=9, end=11, intent="解法")
        self.assertIn("occur verbatim", self.errors())
        sample.update(role="example", label="编辑票样")
        self.assertEqual("", self.errors())  # A labelled example may accompany speech.
        self.events[2]["role"] = "quote"
        self.assertIn("occur verbatim", self.errors())

    def test_invalid_turn_references_and_cue_types_report_diagnostics(self):
        self.turns[1]["cue"] = self.turns[1]["end"]
        self.assertIn("cue must lie within", self.errors())
        self.turns[1]["cue"] = []
        self.assertIn("cue must lie within", self.errors())
        self.events[0]["turn"] = []
        self.assertIn("unknown turn", self.errors())

    def test_narrated_actions_can_have_no_screen_text(self):
        self.alignment["text_events"] = []
        self.assertEqual("", self.errors())
        self.record["example_type"] = "application"
        self.alignment["status"] = "anchored"
        self.record["source"].update(source_status="media-inspected", media_accessed=True,
                                     checks=[{"locator": "test:edit-B", "scope": "test-only source mapping"}])
        for i, turn in enumerate(self.turns):
            turn["locator"] = f"test:edit-B:turn-{i}"
        self.assertEqual("", self.errors())
        del self.turns[0]["locator"]
        self.assertIn("needs a locator", self.errors())
        del self.alignment["text_events"]
        self.assertIn("a text_events array", self.errors())

    def test_changing_role_keeps_method_samples_out_of_applications(self):
        sample = self.events[-1]
        self.record["example_type"] = "application"
        self.assertIn("method-example cannot be application copy", self.errors())
        sample["role"] = "recap"
        self.assertIn("method-example cannot be application copy", self.errors())
        sample["role"] = "example"
        del sample["origin"]
        self.assertIn("identify example origin", self.errors())
        sample.update(origin="editorial", text="本测试专用的项目票样")
        self.assertEqual("", self.errors())


if __name__ == "__main__":
    unittest.main()
