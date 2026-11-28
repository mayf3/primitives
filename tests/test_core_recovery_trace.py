import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from core_recovery_trace import (
    check_native_event_identity, check_recovery_authority, initial_identity, parse_ledger, resolved_bindings,
)


FIXTURES = ROOT / "docs/evidence-graph-fixtures/core"


class CoreRecoveryTraceTests(unittest.TestCase):
    def setUp(self):
        with (FIXTURES / "core-restart-observations.jsonl").open() as stream:
            self.record = json.loads(next(stream))
        self.events = self.record["rawReceipt"]["events"]
        self.identity = initial_identity(self.events[0])

    def test_native_stale_generation_and_request_cannot_inherit_current_identity(self):
        readback = next(event for event in self.events if event["kind"] == "readback_checked")
        check_native_event_identity(readback, self.identity)
        for field, mistake in (("expectedGeneration", 2), ("expectedGeneration", True),
                               ("expectedAttemptId", "stale-attempt"), ("requestId", "other-request")):
            with self.subTest(field=field, mistake=mistake), self.assertRaisesRegex(ValueError, field):
                check_native_event_identity({**readback, field: mistake}, self.identity)

    def test_native_nested_authorization_identity_is_checked(self):
        event = next(event for event in self.events if event["kind"] == "recovery_authorized")
        check_native_event_identity(event, self.identity)
        replaced = {**event["authorization"], "generation": 2}
        with self.assertRaisesRegex(ValueError, "generation"):
            check_native_event_identity({**event, "authorization": replaced}, self.identity)

    def test_native_duplicate_fields_and_torn_tail_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_ledger(b'{"kind":"delivery_started","kind":"run_delivered"}\n')
        with self.assertRaisesRegex(ValueError, "torn"):
            parse_ledger(b'{"kind":"delivery_started"}')

    def test_graph_cannot_supply_its_own_revision_pin(self):
        descriptor = json.loads((FIXTURES / "fixture.json").read_bytes())
        profile = json.loads((FIXTURES / "recovery-trace-contract.json").read_bytes())
        graph = {"schema_version": "evidence-graph/v1",
                 "nodes": [{**item, "coordinate_valid": True, "resolved_coordinate": dict(item["coordinate"])}
                           for item in descriptor["nodes"] if item["id"] in profile["binding_ids"]]}
        resolved_bindings(graph, profile, descriptor)
        model = next(node for node in graph["nodes"] if node["id"] == profile["model_node"])
        model["resolved_coordinate"]["revision"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "canonical fixture"):
            resolved_bindings(graph, profile, descriptor)

    def test_original_authorization_is_required_before_wal(self):
        outputs = [self.record["actualResult"]]
        check_recovery_authority(self.record["testName"], self.events, outputs)
        missing = [event for event in self.events if event["kind"] != "recovery_authorized"]
        with self.assertRaisesRegex(ValueError, "authorization before"):
            check_recovery_authority(self.record["testName"], missing, outputs)
