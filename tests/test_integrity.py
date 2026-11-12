"""Exercise material failure modes without modifying the working repository."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("primitives", ROOT / "tools/primitives.py")
primitives = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primitives)


class IntegrityScenarios(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", "__pycache__"))

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, relative, value):
        (self.root / relative).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_source_edit_is_not_silently_accepted(self):
        manifest = primitives.read_json(self.root / "domains/design/sources/manifest.json")
        relative = manifest["imports"][0]["files"][0]["path"]
        path = self.root / "domains/design" / relative
        path.write_bytes(path.read_bytes() + b"\nchanged\n")
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("immutable source SHA-256 mismatch" in e for e in errors), errors)

    def test_domain_cannot_depend_on_sibling_document(self):
        path = self.root / "domains/writing/GUIDE.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n[隐式依赖](../life/GUIDE.md)\n", encoding="utf-8")
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("reference leaves allowed directory" in e for e in errors), errors)

    def test_bridge_cannot_use_invented_method(self):
        path = "bridges/explain-and-guide.json"
        record = primitives.read_json(self.root / path)
        record["steps"][0]["uses"] = ["life.invented-method"]
        self.write_json(path, record)
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("unknown method reference" in e for e in errors), errors)

    def test_module_version_change_requires_bridge_review(self):
        path = "domains/life/module.json"
        module = primitives.read_json(self.root / path)
        module["version"] = "0.2.0"
        self.write_json(path, module)
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("review composition" in e for e in errors), errors)

    def test_historical_source_is_not_a_default_search_result(self):
        source = self.root / "domains/writing/sources/search-only-fixture.txt"
        source.write_text("historical-only-unique-needle", encoding="utf-8")
        _, _, entries = primitives.load_index(self.root)
        self.assertEqual([], primitives.find_entries(entries, "historical-only-unique-needle"))
        self.assertTrue(any(e["id"] == "design.entry-outcome" for e in primitives.find_entries(entries, "预告入口结果")))

    def test_catalog_cannot_point_to_a_directory(self):
        path = "domains/writing/catalog.json"
        catalog = primitives.read_json(self.root / path)
        catalog["entries"][0]["path"] = "."
        self.write_json(path, catalog)
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("expected a file" in e for e in errors), errors)

    def test_design_record_missing_id_does_not_disappear_from_checks(self):
        path = "domains/design/examples/entry-outcome.json"
        record = primitives.read_json(self.root / path)
        del record["primitive_id"]
        self.write_json(path, record)
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("primitive_id" in e and "Domain check" in e for e in errors), errors)

    def test_empty_design_example_does_not_count_as_validation(self):
        path = "domains/design/examples/entry-outcome.json"
        self.write_json(path, {})
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any("expected at least one design use record" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
