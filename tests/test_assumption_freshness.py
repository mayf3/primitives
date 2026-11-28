from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from assumption_freshness import (CONTEXT, assess_receipt, digest, run_probe, scope_hash)
import assumption_freshness


class AssumptionFreshnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.probe = self.root / "probe.py"
        self.scope = {"profile": "unit-fixture", "instance": "one"}
        self.verifier = digest(Path(assumption_freshness.__file__).read_bytes())

    def run_sample(self, text, *, timeout=3):
        self.probe.write_text(text, encoding="utf-8")
        self.context = {"schema_version": CONTEXT, "assumption_id": "ASM.TEST", "proposition": "Test condition",
                        "owner": "unit-tests", "probe_id": "PROBE.TEST", "ttl_seconds": 60,
                        "versions": {"spec": "s", "model": "m", "code": "c", "mapping": "map",
                                     "verifier": self.verifier, "probe": digest(self.probe.read_bytes())},
                        "environment_scope_hash": scope_hash(self.scope),
                        "failure_behavior": {"condition_false": "FAIL", "timeout": "UNKNOWN"},
                        "blind_spots": ["This is a unit fixture."],
                        "evidence_bindings": {"MODEL": {"revision": "m", "sha256": "0" * 64}}}
        receipt = run_probe(self.context, self.scope, {"probe": self.probe},
                            [sys.executable, str(self.probe)], cwd=self.root, timeout=timeout)
        self.now = datetime.now(timezone.utc)
        return receipt

    def test_observation_and_exact_expiry(self):
        receipt = self.run_sample('print(\'{"result":"PASS","evidence":{"loaded":true}}\')')
        self.assertEqual(assess_receipt(receipt, self.context, self.now)["status"], "PASS")
        expire = datetime.fromisoformat(receipt["expires_at"])
        self.assertEqual(assess_receipt(receipt, self.context, expire)["status"], "STALE")
        self.assertEqual(assess_receipt(receipt, self.context, self.now - timedelta(days=1))["status"], "UNKNOWN")
        self.assertEqual(receipt["status"], "PASS")

    def test_not_executed_timeout_and_arbitrary_output_are_unknown(self):
        receipt = self.run_sample("import time; time.sleep(15)", timeout=0.1)
        self.assertEqual(receipt["execution_kind"], "timeout")
        self.assertIsNone(receipt["exit_code"])
        self.assertEqual(assess_receipt(receipt, self.context, self.now)["status"], "UNKNOWN")
        self.assertEqual(assess_receipt(None, self.context, self.now)["status"], "UNKNOWN")
        extra = 'print(\'{"result":"PASS","evidence":{"loaded":true}}\' + " "*9000)'
        receipt = self.run_sample(extra)
        self.assertEqual(receipt["evidence"], {})
        self.assertEqual(assess_receipt(receipt, self.context, self.now)["status"], "UNKNOWN")

    def test_scope_and_all_revision_changes_retire_the_old_observation(self):
        receipt = self.run_sample('print(\'{"result":"PASS","evidence":{"loaded":true}}\')')
        for key in self.context["versions"]:
            with self.subTest(key=key):
                changed = deepcopy(self.context)
                changed["versions"][key] = "1" * 64
                self.assertEqual(assess_receipt(receipt, changed, self.now)["status"], "STALE")
        changed = {**self.context, "environment_scope_hash": scope_hash({**self.scope, "instance": "two"})}
        self.assertEqual(assess_receipt(receipt, changed, self.now)["status"], "STALE")

    def test_failure_and_malformed_status_are_distinct(self):
        receipt = self.run_sample('print(\'{"result":"FAIL","evidence":{"loaded":false}}\')\nraise SystemExit(1)')
        self.assertEqual(assess_receipt(receipt, self.context, self.now)["status"], "FAIL")
        self.assertEqual(assess_receipt({**receipt, "status": []}, self.context, self.now)["status"], "UNKNOWN")
        self.assertEqual(assess_receipt({**receipt, "exit_code": 0}, self.context, self.now)["status"], "UNKNOWN")
