"""Material negative cases for the proof inventory and transitive axiom gate."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_lean", ROOT / "tools/verify_lean.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class LeanInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(ROOT, self.root,
                        ignore=shutil.ignore_patterns(".git", ".lake", "__pycache__"))

    def test_new_module_cannot_silently_escape_audit(self):
        path = self.root / "domains/life/lean/Life/Unlisted.lean"
        path.write_text("theorem hidden : True := True.intro\n")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            verify.read_layout(self.root)

    def test_source_named_subdirectory_cannot_hide_unaudited_code(self):
        path = self.root / "domains/video/lean/sources/Hidden.lean"
        path.parent.mkdir()
        path.write_text("axiom hidden : False\n")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            verify.read_layout(self.root)

    def test_removing_adapter_manifest_does_not_silently_skip_data(self):
        path = self.root / "lean-projects.json"
        spec = json.loads(path.read_text())
        next(p for p in spec["projects"] if p["domain"] == "video")["checks"] = []
        path.write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError, "adapter inventory mismatch"):
            verify.read_layout(self.root)

    def test_parent_path_cannot_escape_adapter_domain(self):
        path = self.root / "lean-projects.json"
        spec = json.loads(path.read_text())
        video = next(p for p in spec["projects"] if p["domain"] == "video")
        video["checks"][0]["inputs"] = ["domains/video/../life/GUIDE.md"]
        path.write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError, "canonical"):
            verify.read_layout(self.root)

    def test_same_line_commands_cannot_forge_audit_output(self):
        path = self.root / "domains/life/lean/Life/Commitments.lean"
        path.write_text(path.read_text().replace("end Life.Commitments", "end Life.Commitments #check Nat"))
        with self.assertRaisesRegex(ValueError, "proof escape"):
            verify.read_layout(self.root)

    def test_partial_run_cannot_overwrite_full_receipt(self):
        with self.assertRaisesRegex(ValueError, "partial domain run"):
            verify.report_path("video", self.root / "lean-verification.json", self.root)

    def test_actual_sorry_is_rejected_but_nested_comment_is_not_code(self):
        path = self.root / "domains/life/lean/Life/Commitments.lean"
        original = path.read_text()
        path.write_text(original + "\n/- comment /- sorry -/ remains comment -/\n")
        verify.read_layout(self.root)
        path.write_text(original + "\ntheorem unproved : False := by sorry\n")
        with self.assertRaisesRegex(ValueError, "proof escape"):
            verify.read_layout(self.root)

    def test_domain_cannot_import_sibling_business_semantics(self):
        path = self.root / "domains/life/lean/Life/Commitments.lean"
        path.write_text("import Writing.Revision\n" + path.read_text())
        with self.assertRaisesRegex(ValueError, "cross-domain import"):
            verify.read_layout(self.root)

    def test_unreviewed_compiler_options_are_rejected(self):
        path = self.root / "lakefile.toml"
        path.write_text('moreLeanArgs = ["-Ddebug.skipKernelTC=true"]\n' + path.read_text())
        with self.assertRaisesRegex(ValueError, "Unexpected Lake configuration"):
            verify.read_layout(self.root)

    def test_local_toolchain_override_is_rejected(self):
        (self.root / "domains/life/lean/lean-toolchain").write_text("leanprover/lean4:nightly\n")
        with self.assertRaisesRegex(ValueError, "Duplicate build"):
            verify.read_layout(self.root)

    def test_video_input_is_bound_to_verification_hashes(self):
        _, _, inputs = verify.read_layout(self.root)
        before = verify.source_hashes(inputs, self.root)
        path = self.root / "domains/video/examples/concurrent-replies.json"
        path.write_text(path.read_text().replace('"final_unfinished": 4', '"final_unfinished": 5'))
        after = verify.source_hashes(inputs, self.root)
        key = "domains/video/examples/concurrent-replies.json"
        self.assertIn(key, before)
        self.assertNotEqual(before[key], after[key])

    def test_transitive_sorry_and_custom_axioms_are_rejected(self):
        for axiom in ("sorryAx", "invented_soundness", "Lean.ofReduceBool"):
            with self.subTest(axiom=axiom):
                with self.assertRaisesRegex(ValueError, "Unapproved transitive"):
                    verify.parse_axioms(f"'Example.result' depends on axioms: [{axiom}]", ["Example.result"])

    def test_incomplete_or_duplicate_axiom_output_is_rejected(self):
        good = "'Example.result' does not depend on any axioms\n"
        self.assertEqual({"Example.result": []}, verify.parse_axioms(good, ["Example.result"]))
        for output in ("", good + good):
            with self.assertRaisesRegex(ValueError, "Incomplete, duplicate"):
                verify.parse_axioms(output, ["Example.result"])


if __name__ == "__main__":
    unittest.main()
