"""Keep meta discovery separate from domain semantics and directory ownership."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("primitives_meta", ROOT / "tools/primitives.py")
primitives = importlib.util.module_from_spec(spec)
spec.loader.exec_module(primitives)


class MetaIntegrityScenarios(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.domain_ids = ("life", "writing", "design", "video")
        self.registry = {
            "schema_version": "1.0", "version": "0.3.0",
            "modules": [{"id": name, "path": f"domains/{name}"} for name in self.domain_ids],
            "meta": {
                "id": "meta", "title": "元层", "version": "0.1.0", "path": "meta",
                "entrypoint": "README.md", "catalog": "catalog.json",
            },
            "bridges": [],
        }
        self.write_json("registry.json", self.registry)
        for name in self.domain_ids:
            base = f"domains/{name}"
            self.write_json(f"{base}/module.json", {
                "id": name, "title": name, "version": "0.1.0", "description": "fixture",
                "entrypoint": "GUIDE.md", "guide": "GUIDE.md", "catalog": "catalog.json",
                "depends_on": [],
            })
            self.write_json(f"{base}/catalog.json", {
                "domain": name, "entries": [self.entry(f"{name}.example", "GUIDE.md#example")],
            })
            self.write_json(f"{base}/sources/manifest.json", {"imports": []})
            self.write_text(f"{base}/GUIDE.md", '<a id="example"></a>\n# 示例\n共享检索词\n')
        self.catalog = {"namespace": "meta", "entries": [self.entry("meta.review", "README.md#review")]}
        self.write_json("meta/catalog.json", self.catalog)
        self.write_text("meta/README.md", '<a id="review"></a>\n# 元层\n共享检索词 元层独有词\n')

    @staticmethod
    def entry(identifier, path):
        return {"id": identifier, "title": identifier, "kind": "method", "summary": "fixture",
                "tags": [], "path": path}

    def write_text(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_json(self, relative, value):
        self.write_text(relative, json.dumps(value, ensure_ascii=False))

    def cli(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = primitives.main(["--root", str(self.root), *arguments])
        return result, output.getvalue()

    def assert_error(self, expected):
        errors, _ = primitives.validate(self.root)
        self.assertTrue(any(expected in error for error in errors), errors)

    def test_meta_is_searchable_without_becoming_a_fifth_domain(self):
        _, modules, entries = primitives.load_index(self.root)
        self.assertEqual(set(self.domain_ids), {module["id"] for module in modules})
        meta = primitives.find_entries(entries, "元层独有词")
        self.assertEqual(["meta.review"], [entry["id"] for entry in meta])
        self.assertEqual("meta", meta[0]["scope"])
        self.assertIsNone(meta[0]["domain"])
        self.assertEqual(self.root / "meta", meta[0]["directory"])
        self.assertTrue(all(entry["scope"] == entry["domain"] for entry in entries if entry["domain"]))
        errors, counts = primitives.validate(self.root)
        self.assertEqual([], errors)
        self.assertEqual(4, counts["modules"])
        self.assertIn("meta.review", self.cli("list")[1])
        self.assertIn("meta/README.md#review", self.cli("show", "meta.review")[1])
        self.assertIn("domains/writing/GUIDE.md#example", self.cli("show", "writing.example")[1])

    def test_domain_and_scope_filters_keep_distinct_meanings(self):
        result, output = self.cli("find", "共享检索词", "--domain", "writing")
        self.assertEqual(0, result)
        self.assertIn("writing.example", output)
        self.assertNotIn("meta.review", output)
        self.assertNotIn("life.example", output)
        self.assertEqual(output, self.cli("find", "共享检索词", "--scope", "writing")[1])
        result, output = self.cli("find", "共享检索词", "--scope", "meta")
        self.assertEqual(0, result)
        self.assertIn("meta.review", output)
        self.assertNotIn("writing.example", output)
        for arguments in (("list", "--domain", "meta"),
                          ("list", "--domain", "writing", "--scope", "meta")):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as raised:
                self.cli(*arguments)
            self.assertEqual(2, raised.exception.code)

    def test_meta_directory_and_catalog_cannot_escape(self):
        for field, value, message in (
            ("path", "domains/life", "Invalid meta path"),
            ("path", "../outside", "Invalid meta path"),
            ("catalog", "../domains/life/catalog.json", "Catalog escapes meta directory"),
        ):
            with self.subTest(field=field, value=value):
                original = self.registry["meta"][field]
                self.registry["meta"][field] = value
                self.write_json("registry.json", self.registry)
                self.assert_error(message)
                self.registry["meta"][field] = original

    def test_meta_entries_stay_local_and_require_existing_anchors(self):
        for path, message in (
            ("../domains/life/GUIDE.md#example", "reference leaves allowed directory"),
            ("README.md#missing", "missing anchor"),
        ):
            with self.subTest(path=path):
                self.catalog["entries"][0]["path"] = path
                self.write_json("meta/catalog.json", self.catalog)
                self.assert_error(message)

    def test_meta_namespace_and_duplicate_ids_are_checked(self):
        self.catalog["namespace"] = "writing"
        self.write_json("meta/catalog.json", self.catalog)
        self.assert_error("meta: catalog namespace mismatch")
        self.catalog["namespace"] = "meta"
        self.catalog["entries"][0]["id"] = "writing.review"
        self.write_json("meta/catalog.json", self.catalog)
        self.assert_error("wrong catalog namespace")
        self.catalog["entries"] = [self.entry("meta.review", "README.md#review")] * 2
        self.write_json("meta/catalog.json", self.catalog)
        self.assert_error("Duplicate catalog ID")

    def test_meta_version_and_entrypoint_are_checked(self):
        self.registry["meta"]["version"] = "latest"
        self.registry["meta"]["entrypoint"] = "../domains/life/GUIDE.md"
        self.write_json("registry.json", self.registry)
        self.assert_error("meta: use an explicit version")
        self.assert_error("meta.entrypoint: reference leaves allowed directory")

    def test_meta_cannot_become_a_bridge_domain_with_a_null_version(self):
        self.registry["bridges"] = [{"id": "bridge.fixture", "path": "bridges/fixture.md",
                                     "record": "bridges/fixture.json"}]
        self.write_json("registry.json", self.registry)
        self.write_text("bridges/fixture.md", "# Fixture\n")
        record = {"id": "bridge.fixture", "module_versions": {"life": "0.1.0"},
                  "steps": [{"id": "step", "domain": "life", "uses": ["life.example"]}],
                  "handoffs": []}
        self.write_json("bridges/fixture.json", record)
        self.assertEqual([], primitives.validate(self.root)[0])
        record["module_versions"] = {"meta": None}
        record["steps"][0].update(domain="meta", uses=["meta.review"])
        self.write_json("bridges/fixture.json", record)
        errors, _ = primitives.validate(self.root)
        for expected in ("unknown bridge domain meta", "step domain is not a registered domain: meta",
                         "unknown method reference meta.review"):
            self.assertTrue(any(expected in error for error in errors), errors)
        record["module_versions"] = {"life": None}
        record["steps"][0].update(domain="life", uses=["life.example"])
        self.write_json("bridges/fixture.json", record)
        self.assert_error("review composition after life version changes")

    def test_only_meta_can_refer_across_domain_boundary(self):
        self.write_text("meta/README.md", '<a id="review"></a>\n[领域案例](../domains/life/GUIDE.md#example)\n')
        errors, _ = primitives.validate(self.root)
        self.assertEqual([], errors)
        self.write_text("domains/life/GUIDE.md", '<a id="example"></a>\n[元层](../../meta/README.md#review)\n')
        self.assert_error("domains/life/GUIDE.md: reference leaves allowed directory")


if __name__ == "__main__":
    unittest.main()
