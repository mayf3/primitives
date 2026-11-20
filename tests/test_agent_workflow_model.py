"""Bounded synthetic Agent Workflow model checks.

Do not treat these as proof of production safety/liveness.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "domains/agent-workflow/model_check.py"


class AgentWorkflowBoundedModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [sys.executable, str(MODEL)], cwd=ROOT,
            text=True, capture_output=True, timeout=15,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.report = json.loads(result.stdout)

    def test_safe_model_has_a_reachable_completed_goal(self):
        r = self.report["baseline"]
        self.assertTrue(r["ok"])
        self.assertGreater(r["states"], 0)
        self.assertGreater(r["accepted_states"], 0)

    def test_missing_successor_is_caught(self):
        self.assertEqual(
            self.report["mutations"]["drop-successor"]["violation"],
            "S1_MISSING_REQUIRED_SUCCESSOR",
        )

    def test_self_reported_completion_is_caught(self):
        self.assertEqual(
            self.report["mutations"]["false-pass"]["violation"],
            "S2_UNVERIFIED_CLOSURE",
        )

    def test_blind_replay_is_caught(self):
        self.assertEqual(
            self.report["mutations"]["blind-replay"]["violation"],
            "S3_EFFECT_AT_MOST_ONCE",
        )

    def test_missing_consumer_or_reconcile_causes_progress_failure(self):
        for key in ("orphan-successor", "no-readback"):
            r = self.report["mutations"][key]
            self.assertFalse(r["ok"])
            self.assertEqual(
                r["violation"], "L1_NO_ENABLED_CONSUMER_OR_READBACK",
            )
            self.assertGreater(len(r["trace"]), 0)

    def test_scope_does_not_claim_production_proof(self):
        self.assertTrue(self.report["passed"])
        limitations = " ".join(self.report["does_not_prove"])
        self.assertIn("production", limitations)
        self.assertIn("unbounded concurrency", limitations)


if __name__ == "__main__":
    unittest.main()
