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

    def test_quote_characters_cannot_hide_axioms_or_kernel_options(self):
        path = self.root / "domains/video/lean/Video/Temporal.lean"
        original = path.read_text()
        for hidden in ("axiom reviewHiddenFalse : False\n"
                       "theorem review_hidden_false : False := reviewHiddenFalse",
                       "set_option debug.skipKernelTC true"):
            with self.subTest(hidden=hidden):
                payload = "def firstQuote : Char := '\"'\n" + hidden + "\n" + \
                    "def lastQuote : Char := '\"'\n"
                path.write_text(original.replace("end Video.Temporal", payload + "end Video.Temporal"))
                with self.assertRaisesRegex(ValueError, "proof escape"):
                    verify.read_layout(self.root)

    def test_theorem_between_character_literals_is_in_inventory(self):
        path = self.root / "domains/video/lean/Video/Temporal.lean"
        payload = "def firstQuote : Char := '\"'\n" + \
            "theorem formerly_hidden : True := True.intro\n" + \
            "def lastQuote : Char := '\"'\n"
        path.write_text(path.read_text().replace("end Video.Temporal", payload + "end Video.Temporal"))
        _, names, _ = verify.read_layout(self.root)
        self.assertIn("Video.Temporal.formerly_hidden", names["video"])

    def test_literals_and_escaped_identifiers_do_not_change_code_boundaries(self):
        source = r'''def x' : Char := '"'
def x'' : Char := '\''
def α' : Char := '\\'
def hexQuote : Char := '\x22'
def unicodeQuote : Char := '\u0022'
def slash : Char := '/'
def dash : Char := '-'
def escaped : String := "\" /- -- theorem axiom"
def «quoted " /- -- identifier'» : Nat := 0
/- comment /- nested -/ " ' -/
theorem visible : True := True.intro
'''
        masked = verify.code_only(source)
        self.assertEqual(len(source), len(masked))
        self.assertEqual([i for i, c in enumerate(source) if c == "\n"],
                         [i for i, c in enumerate(masked) if c == "\n"])
        for name in ("x'", "x''", "α'"):
            self.assertIn(f"def {name} : Char", masked)
        self.assertEqual(1, masked.count("theorem"))
        self.assertNotIn("axiom", masked)
        self.assertIn("theorem visible : True", masked)

    def test_unsupported_raw_strings_fail_closed(self):
        for source in ('def x := r"\\"', 'def x := r#"a " quotation"#'):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "Raw Lean strings"):
                    verify.code_only(source)

    def test_malformed_literals_and_identifier_escapes_fail_closed(self):
        for source in ("def x := '\\q'", "def x := '\\x2'", "def x := 'a",
                       'def x := "unfinished', "def «unfinished := 0"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    verify.code_only(source)

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


class CompiledEnvironmentTests(unittest.TestCase):
    projects = [{"modules": ["Example", "Example.Proof"]}]

    def output(self, declarations=None, **changes):
        payload = {"schema": "primitives-compiled-audit/v1",
                   "modules": ["Example", "Example.Proof"], "excluded_unsafe": [],
                   "excluded_partial": [],
                   "declarations": declarations if declarations is not None else [
                       self.record("Example.result"), self.record("_private.Example.helper")]}
        payload.update(changes)
        return verify.COMPILED_AUDIT_PREFIX + json.dumps(payload)

    def record(self, name, kind="theorem", axioms=None):
        return {"name": name, "module": "Example.Proof", "kind": kind,
                "axioms": axioms or []}

    def test_compiled_private_helper_is_checked_without_a_source_name(self):
        audited, unsafe, partial = verify.parse_compiled_audit(self.output(), self.projects, ["Example.result"])
        self.assertIn("_private.Example.helper", audited)
        self.assertEqual([], unsafe)
        self.assertEqual([], partial)
        for kind in ("theorem", "definition"):
            output = self.output([self.record("Example.result"),
                                  self.record("_private.Example.helper", kind, ["sorryAx"])])
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "Unapproved compiled"):
                    verify.parse_compiled_audit(output, self.projects, ["Example.result"])

    def test_compiled_unused_axiom_cannot_escape_source_inventory(self):
        # The source inventory can omit this axiom and its dependent theorem;
        # the independent environment enumeration still has to reject it.
        output = self.output([self.record("Example.result"),
                              self.record("Example.hiddenFalse", "axiom", ["Example.hiddenFalse"])])
        with self.assertRaisesRegex(ValueError, "Repository-defined compiled axiom"):
            verify.parse_compiled_audit(output, self.projects, ["Example.result"])

    def test_excluded_unsafe_name_cannot_replace_an_audited_theorem(self):
        output = self.output([], excluded_unsafe=["Example.result"])
        with self.assertRaisesRegex(ValueError, "Explicit theorems missing"):
            verify.parse_compiled_audit(output, self.projects, ["Example.result"])
        output = self.output(excluded_unsafe=["Example.result"])
        with self.assertRaisesRegex(ValueError, "unsafe compiler-declaration inventory"):
            verify.parse_compiled_audit(output, self.projects, ["Example.result"])

    def test_missing_modules_duplicate_records_and_unknown_kinds_fail_closed(self):
        outputs = [self.output(modules=["Example"]),
                   self.output([self.record("Example.result"), self.record("Example.result")]),
                   self.output([self.record("Example.result", "unreviewed")])]
        for output in outputs:
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    verify.parse_compiled_audit(output, self.projects, ["Example.result"])
        for output in ("", self.output() + "\n" + self.output()):
            with self.subTest(output=output):
                with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
                    verify.parse_compiled_audit(output, self.projects, ["Example.result"])


if __name__ == "__main__":
    unittest.main()
