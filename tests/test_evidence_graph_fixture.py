from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "evidence_graph_fixture.py"


class EvidenceGraphFixtureMaterializerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repository = self.root / "consumer"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Evidence test")
        self.original = self.repository / "src.rs"
        self.original.write_text("fn original() {}\n", encoding="utf-8")
        (self.repository / "alias.rs").symlink_to("src.rs")
        self.git("add", ".")
        self.git("commit", "-qm", "fixed original")
        self.revision = self.git("rev-parse", "HEAD").strip()
        self.original.write_text("fn worktree_only() {}\n", encoding="utf-8")
        self.fixture = self.root / "fixture.json"
        self.target = self.root / "snapshot"
        self.material = {
            "repo": "consumer", "revision": self.revision,
            "path": "src.rs", "target": "materials/src.rs",
        }
        self.descriptor = {
            "schema_version": "evidence-receipt/v1", "materials": [self.material],
            "nodes": [], "links": [],
        }

    def git(self, *args):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        return subprocess.check_output(
            ["git", "-C", str(self.repository), *args], text=True, env=env
        )

    def run_cli(self, *more):
        self.fixture.write_text(json.dumps(self.descriptor), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--fixture", str(self.fixture),
             "--repositories", str(self.root), "--destination", str(self.target), *more],
            text=True, capture_output=True, timeout=15,
        )

    def test_exact_git_blob_and_designated_local_receipt_are_recorded(self):
        self.target.mkdir()
        self.descriptor["files"] = ["one-receipt.jsonl"]
        evidence_path = self.root / "one-receipt.jsonl"
        evidence_path.write_bytes(b'{"exit_code":0}\n')
        self.descriptor["nodes"] = [
            {"coordinate": {"path": "one-receipt.jsonl", "revision": self.revision}}
        ]
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = b"fn original() {}\n"
        self.assertEqual((self.target / "materials/src.rs").read_bytes(), expected)
        self.assertEqual(self.original.read_text(encoding="utf-8"), "fn worktree_only() {}\n")
        self.assertEqual((self.target / evidence_path.name).read_bytes(), evidence_path.read_bytes())
        receipt = json.loads((self.target / "fixture.evidence.json").read_bytes())
        self.assertNotIn("materials", receipt)
        self.assertNotIn("files", receipt)
        source = json.loads((self.target / "fixture-sources.json").read_bytes())["files"]
        self.assertEqual(source["materials/src.rs"], {
            "repo": "consumer", "revision": self.revision, "path": "src.rs",
            "sha256": hashlib.sha256(expected).hexdigest(),
        })
        self.assertEqual(source["one-receipt.jsonl"]["revision"], self.revision)

    def test_floating_commit_reference_fails_without_creating_output(self):
        self.material["revision"] = "HEAD"
        self.assertIn("exact 40-hex Git commit", self.run_cli().stderr)
        self.assertFalse(self.target.exists())

    def test_pinned_symlink_is_not_a_regular_git_source(self):
        self.material["path"] = "alias.rs"
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a regular Git file", result.stderr)
        self.assertFalse(self.target.exists())

    def test_missing_authority_fails_without_creating_output(self):
        self.material["path"] = "missing.rs"
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or ambiguous", result.stderr)
        self.assertFalse(self.target.exists())

    def test_targets_cannot_escape_or_replace_generated_files(self):
        for name in ("../sentinel", "nested/evidence-graph.json"):
            with self.subTest(name=name):
                self.material["target"] = name
                self.assertNotEqual(self.run_cli().returncode, 0)
                self.assertFalse(self.target.exists())
                self.assertFalse((self.root / "sentinel").exists())

    def test_nonempty_destination_remains_untouched(self):
        self.target.mkdir()
        sentinel = self.target / "sentinel"
        sentinel.write_bytes(b"preserve this")
        self.assertIn("nonexistent or empty", self.run_cli().stderr)
        self.assertEqual(list(self.target.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"preserve this")

    def test_duplicate_target_fails_without_partially_copying_output(self):
        self.descriptor["materials"].append(dict(self.material))
        self.assertIn("duplicate fixture target", self.run_cli().stderr)
        self.assertFalse(self.target.exists())

    def test_local_symlink_fails_without_creating_output(self):
        alias = self.root / "pointer.json"
        alias.symlink_to(self.original)
        self.descriptor["files"] = [alias.name]
        self.assertIn("cannot use a symlink", self.run_cli().stderr)
        self.assertFalse(self.target.exists())

    def test_named_repository_override_selects_local_checkout(self):
        self.material["repo"] = "alternate"
        result = self.run_cli("--repo", f"alternate={self.repository}")
        self.assertEqual(result.returncode, 0, result.stderr)
        source = json.loads((self.target / "fixture-sources.json").read_bytes())["files"]
        self.assertEqual(source["materials/src.rs"]["repo"], "alternate")


if __name__ == "__main__":
    unittest.main()
