import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from core_recovery_adapter import NativeCore, query_observation


class CoreAdapterObservationTests(unittest.TestCase):
    def test_read_only_query_requires_the_observed_original_receipt(self):
        attempt = {"attemptId": "original", "delivered": {"requestId": "original", "reconciliationHandle": "handle",
                                                         "messageId": "message"}}
        receipt = {"state": "recovering", "handle": "handle", "snapshot": {
            "handle": "handle", "messageId": "message", "callerCorrelation": {"requestId": "original"}}}
        absence = {"state": "never_existed"}
        self.assertEqual(query_observation(receipt, receipt, attempt, False), "PASS")
        self.assertEqual(query_observation(absence, receipt, attempt, False), "FAIL")
        self.assertEqual(query_observation(absence, absence, attempt, False), "UNKNOWN")
        other = {**receipt, "snapshot": {**receipt["snapshot"], "callerCorrelation": {"requestId": "other"}}}
        self.assertEqual(query_observation(other, other, attempt, False), "UNKNOWN")
        self.assertEqual(query_observation(receipt, receipt, {"attemptId": "original"}, True), "UNKNOWN")

    def test_nested_worker_requires_clean_exit_and_no_unframed_tail(self):
        for code, trailing, valid in [(0, "", True), (9, "", False), (0, "garbage\n", False)]:
            with self.subTest(code=code, trailing=trailing), tempfile.TemporaryDirectory() as temporary:
                bridge = NativeCore(Path(temporary))
                bridge.driver.parent.mkdir(parents=True)
                bridge.driver.touch()
                bridge.temp = SimpleNamespace(cleanup=lambda: None)
                bridge.process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(trailing), wait=lambda timeout: code)
                if valid:
                    bridge.__exit__(None, None, None)
                else:
                    with self.assertRaisesRegex(ValueError, "native Core worker exited unsuccessfully"):
                        bridge.__exit__(None, None, None)
                self.assertFalse(bridge.driver.exists())
