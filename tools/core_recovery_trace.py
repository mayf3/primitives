"""Bind captured Core Recovery ledgers to the single-attempt model profile."""

import json
from pathlib import Path
import re

from capture_core_recovery_trace import LEDGER_WITNESS, NATIVE_WITNESS, sha256, tap_receipts
from trace_validate import load_json, verifier_revision


CAPTURE = "core-recovery-capture/v1"
PROFILE = "core-recovery-trace-profile/v1"
NORMALIZER = Path(__file__)
PROFILE_SHA256 = "d03c411e6f79efb7ee28212cf6c4a43287ef0436348d4e87909f1fcb84b73010"
IDENTITY_FIELDS = ("attemptId", "workflowInstanceId", "nodeVisitId", "dispatchIntentId", "ownerPrincipalId")
NORMAL = "B2-503-restart-automatic-first-admission"
BEFORE = "B2-SIGKILL-before-wal"
AFTER = "B2-SIGKILL-after-wal"
LOST = "B2-accepted-ACK-lost-SIGKILL"
RACE = "B2-automatic-manual-real-process-race"
REFUSED = "B2-world-drift-refusal-SIGKILL-read-only-duty-restarts"
SCENARIOS = {NORMAL, BEFORE, AFTER, LOST, RACE, REFUSED}
STALE_ATTEMPT = "B2 an old automatic scan cannot authorize or modify a later blocked generation"
AUTOMATIC_RULE = "accepted:AGENT_CORE_WORKFLOW_RECOVERY_LIVENESS_V1#CTR-EKRWAE-005"
NATIVE_PHASES = {"planned": "planned", "resolution_blocked": "resolutionBlocked",
                 "delivery_started": "deliveryStarted", "run_delivered": "runDelivered",
                 "reconciled": "needsReview", "recovery_refused": "needsReview"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_lines(values):
    return b"".join((json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                    for value in values)


def parse_ledger(raw):
    require(raw.endswith(b"\n"), "native ledger has a torn or unsealed tail")
    events = [load_json(line) for line in raw.split(b"\n")[:-1]]
    require(all(isinstance(event, dict) for event in events), "native JSONL entries must be objects")
    return events


def resolved_bindings(graph, profile, descriptor):
    require(graph.get("schema_version") == "evidence-graph/v1", "a compiled Evidence Graph is required")
    nodes = graph["nodes"]
    pins = {node["id"]: node for node in descriptor["nodes"]}
    bindings = {}
    for identifier in profile["binding_ids"]:
        matches = [node for node in nodes if node["id"] == identifier]
        require(len(matches) == 1, f"missing or ambiguous graph binding {identifier}")
        node, = matches
        pinned = pins[identifier]
        require(node.get("coordinate_valid") is True and node.get("evidence_status") != "STALE",
                f"invalid or stale graph binding {identifier}")
        actual = node["resolved_coordinate"]
        require(node["kind"] == pinned["kind"] and node["coordinate"] == pinned["coordinate"]
                and all(actual[key] == pinned["coordinate"][key] for key in ("path", "revision", "sha256")),
                f"compiled graph binding differs from the canonical fixture for {identifier}")
        bindings[identifier] = {"id": identifier, **{
            key: node["resolved_coordinate"][key] for key in ("revision", "sha256")
        }}
    return bindings


def verify_tap(tap, expected_name, count):
    for label, expected in (("tests", count), ("pass", count), ("fail", 0), ("cancelled", 0),
                            ("skipped", 0), ("todo", 0)):
        entries = re.findall(rf"(?m)^# {label} (\d+)$", tap.decode())
        require(entries == [str(expected)], f"{expected_name} TAP lacks complete {label} summary")


def load_capture(path, bindings, code_revision, environment):
    capture = load_json(path.read_bytes())
    require(capture.get("schema_version") == CAPTURE and capture.get("code_revision") == code_revision
            and capture.get("environment") == environment and type(capture.get("test_exit")) is int
            and capture["test_exit"] == 0, "capture revision, environment or test exit mismatch")
    harness = NORMALIZER.with_name("capture_core_recovery_trace.py")
    require(capture.get("harness_sha256") == sha256(harness.read_bytes()), "capture harness digest mismatch")
    original = path.with_name("original-restart.test.js").read_bytes()
    patched = path.with_name("instrumented-restart.test.js").read_bytes()
    needle = NATIVE_WITNESS.encode()
    require(sha256(original) == capture.get("fixture_sha256") == bindings["CORE.CODE.TEST-RESTART"]["sha256"]
            and original.count(needle) == 1
            and patched == original.replace(needle, LEDGER_WITNESS.encode())
            and sha256(patched) == capture.get("instrumented_fixture_sha256"),
            "instrumented test differs from the pinned test plus its recorder")
    tap = path.with_name("core-restart.tap").read_bytes()
    require(sha256(tap) == capture.get("tap_sha256"), "restart TAP digest mismatch")
    verify_tap(tap, "restart", 6)
    receipts = tap_receipts(tap)
    require(receipts == capture["scenarios"], "capture diagnostics differ from full TAP")
    stale_tap = path.with_name("core-stale-attempt.tap").read_bytes()
    require(sha256(stale_tap) == capture.get("stale_attempt_tap_sha256")
            and f"ok 1 - {STALE_ATTEMPT}".encode() in stale_tap, "stale-attempt TAP binding mismatch")
    verify_tap(stale_tap, "late generation", 1)
    return receipts, {"test": STALE_ATTEMPT, "status": "EXECUTABLE_TEST_PASSED",
                      "source_binding": bindings["CORE.CODE.TEST-BLOCKED"], "tap_sha256": sha256(stale_tap)}


def initial_identity(first):
    require(first["kind"] == "attempt_planned", "first event does not establish a planned attempt")
    identity = {key: first[key] for key in IDENTITY_FIELDS}
    require(all(isinstance(value, str) and value for value in identity.values()),
            "attempt identity is empty or malformed")
    identity["generation"] = first.get("generation", 1)
    require(type(identity["generation"]) is int and identity["generation"] == 1,
            "capture does not start with native generation one")
    return identity


def check_identity(actual, identity, required=False):
    for key, value in identity.items():
        if required or key in actual:
            require_identity_value(key, actual.get(key, 1 if key == "generation" else None), value)


def require_identity_value(field, value, expected):
    require(type(value) is type(expected) and value == expected, f"same-attempt identity mismatch on {field}")


def check_native_event_identity(event, identity):
    check_identity(event, identity)
    for field in ("nodeVisitId", "workflowInstanceId"):
        require_identity_value(field, event.get(field), identity[field])
    aliases = {"expectedAttemptId": "attemptId", "expectedGeneration": "generation", "requestId": "attemptId"}
    required = {}
    if event["kind"] in {"recovery_checked", "readback_checked"}:
        required = aliases
    elif event["kind"] == "run_delivered":
        required = {"requestId": "attemptId"}
    for alias, key in aliases.items():
        if alias in event or alias in required:
            require_identity_value(alias, event.get(alias), identity[key])
    if "authorization" in event:
        authorization = event["authorization"]
        check_identity(authorization, identity, required=True)
        require_identity_value("authorization.requestId", authorization.get("requestId"), identity["attemptId"])
        require_identity_value("authorization.gateEvidence.requestId",
                               authorization["gateEvidence"].get("requestId"), identity["attemptId"])


def project_phase(event, phase):
    kind = event["kind"]
    if kind in ("recovery_checked", "recovery_authorized", "readback_checked", "attempt_planned"):
        return phase
    if kind == "reconciled":
        require(event.get("verdict") == "NEEDS_REVIEW" and event.get("judgment") == "delivery_unverified",
                "post-WAL witness does not carry the expected unverified verdict")
        return "needsReview"
    if kind == "recovery_refused":
        return "needsReview"
    return NATIVE_PHASES.get(kind)


def check_recovery_authority(name, events, outputs):
    authorizations = [(index, event) for index, event in enumerate(events)
                      if event["kind"] == "recovery_authorized"]
    if name == REFUSED:
        require(not authorizations and events[-1]["kind"] == "recovery_refused",
                "world-drift fixture requires a native refusal and no authorization")
        return
    start = next(index for index, event in enumerate(events) if event["kind"] == "delivery_started")
    minimum = 2 if name == BEFORE else 1
    require(len(authorizations) >= minimum and all(index < start for index, _ in authorizations),
            "recovery needs its original authorization before the delivery WAL")
    require(all(item["attempt"].get("recoveryAuthorizations") == len(authorizations) for item in outputs),
            "native authorization count disagrees with reloaded attempt")
    for _, event in authorizations:
        reference = event.get("authorityRef")
        audit = event.get("authorization")
        if name == RACE and reference == "B2_PROCESS_TEST_OWNER":
            continue
        require(reference == AUTOMATIC_RULE and isinstance(audit, dict)
                and audit.get("kind") == "automatic" and audit.get("ruleRef") == reference
                and audit.get("triggerId"), "automatic recovery lacks its exact authority witness")


def restart_witness(record, events, identity):
    name, raw = record["testName"], record["rawReceipt"]
    initial = record["initialState"]["attempt"]
    check_identity(initial, identity, required=True)
    require(initial["phase"] == "resolution_blocked" and "deliveryStartedAtMs" not in initial,
            "seed snapshot is outside the pre-WAL blocked fixture")
    last = record["actualResult"]
    if name == RACE:
        outputs = [last["autoResult"], last["manualResult"]]
        require(raw["childExits"] == [[0, None], [0, None]], "competing fixture children did not exit")
    elif name == REFUSED:
        outputs = [item["actual"] for item in last]
        require([item["childExit"] for item in last] == [[0, None], [0, None]],
                "refusal fixture did not have two clean descendants")
    else:
        outputs = [last]
        require(raw.get("childExit", raw.get("restartedExit")) == [0, None],
                "recovery fixture did not exit")
    for actual in outputs:
        check_identity(actual["attempt"], identity, required=True)
        require(not actual["errors"], "fixture child reported errors")
    deliveries = raw["deliveries"]
    require(len([r for r in raw["requests"] if r["path"] == "/deliver"]) == len(deliveries),
            "loopback HTTP request and delivery counts disagree")
    for delivery in deliveries:
        origin = delivery["messageOrigin"]
        require(delivery["requestId"] == identity["attemptId"] and
                all(origin[key] == identity[key] for key in ("attemptId", "nodeVisitId", "workflowInstanceId")),
                "loopback delivery belongs to a different attempt")
    if name not in {NORMAL, RACE}:
        require(raw["crashedExit"] == [None, "SIGKILL"], "missing real child SIGKILL witness")
    if name in {BEFORE, AFTER, REFUSED}:
        phase = {BEFORE: "recoveryAuthorized", AFTER: "deliveryStarted", REFUSED: "recoveryRefused"}[name]
        require(raw["boundary"]["point"] == phase, "child exit is not at its declared durable boundary")
    correlation = outputs[0].get("correlation", {})
    if name == LOST:
        accepted = raw["accepted"]
        pending = accepted["receipt"]["snapshot"]
        observed = correlation["snapshot"]
        require(deliveries == [accepted["request"]] and accepted["receipt"]["state"] == "pending"
                and pending["callerCorrelation"]["requestId"] == identity["attemptId"]
                and pending["handle"] == observed["handle"] == correlation["handle"]
                and pending["messageId"] == observed["messageId"]
                and observed["initialOutcome"] == "outcome_unknown" and observed["fenceState"] == "active"
                and observed["outcome"] is None and observed["terminationEvidence"] is None
                and outputs[0]["routerBytes"] == raw["loaded"]["routerBytes"],
                "Router ACK-loss witness does not bind a single acceptance to UNKNOWN and an active fence")
    elif name == AFTER:
        require(correlation["state"] == "never_existed" and not deliveries,
                "post-WAL pre-delivery fixture has an unexpected Router effect")
    expected_deliveries = 0 if name in {AFTER, REFUSED} else 1
    require(len(deliveries) == expected_deliveries, "duplicate or missing loopback Router request")
    starts = sum(event["kind"] == "delivery_started" for event in events)
    completed = sum(event["kind"] == "run_delivered" for event in events)
    require(starts == (0 if name == REFUSED else 1)
            and completed == (1 if name in {NORMAL, BEFORE, RACE} else 0),
            "unexpected native WAL or delivery confirmation count")
    check_recovery_authority(name, events, outputs)
    observations = {
        "router_deliveries": len(deliveries), "wal_starts": starts, "core_delivery_confirmations": completed,
        "observed_core_phases": [item["attempt"]["phase"] for item in outputs],
        "router_outcome": "UNKNOWN" if name == LOST else "NO_LOOPBACK_REQUEST" if not deliveries else "ADMITTED",
        "business_acceptance": "UNKNOWN",
    }
    return outputs, observations


def normalize(record, profile, bindings, revisions, closed, late):
    name, raw = record["testName"], record["rawReceipt"]
    require(record["sourceSha"] == revisions["code_revision"] and record["faultInjection"] == name
            and type(record["productionWrites"]) is int and record["productionWrites"] == 0,
            "Core scenario revision, fault or isolation marker mismatch")
    legacy_raw = raw.get("terminalBytes")
    actual = record["actualResult"]
    if isinstance(actual, dict) and "terminalSnapshot" in actual:
        legacy_raw = actual["terminalSnapshot"]["ledgerBytes"]
    native = raw["ledgerBytes"] if closed else legacy_raw
    raw_bytes = native.encode() if native is not None else json_lines(raw["events"])
    events = parse_ledger(raw_bytes)
    require(events and events == raw["events"], "exact native ledger disagrees with parsed events")
    if closed and legacy_raw is not None:
        require(native == legacy_raw, "closing ledger changed after native terminal snapshot")
    identity = initial_identity(events[0])
    outputs, observations = restart_witness(record, events, identity)
    trace_id = f"core-ledger:{name}"
    # Only this sealed file observer has a complete bounded order. Core's
    # native ledger carries no per-process producer identity or sequence.
    producer_id = "isolated-ledger-file-observer"
    environment = profile["environment_profile"]
    phase = "planned"
    rows = []
    for line, (event, raw_line) in enumerate(zip(events, raw_bytes.split(b"\n")[:-1], strict=True), 1):
        check_native_event_identity(event, identity)
        kind = event["kind"]
        require(kind != "attempt_planned" or line == 1, "attempt changed within the single-attempt capture")
        observed = project_phase(event, phase)
        transition = next((item["transition_id"] for item in profile["transitions"] if
                           (item["from_observed"], item["event"], item["to_observed"]) == (phase, kind, observed)), None)
        stutter = next((item["mapping_id"] for item in profile["stutters"] if
                        item["event"] == kind and phase == observed and phase in item["states"]), None)
        event_id = f"file-line:{line}"
        row = {
            "schema_version": "model-trace/v1", "trace_id": trace_id, "event_id": event_id,
            "producer_id": producer_id, "producer_epoch": 0, "seq": line, "raw_line": line,
            "sequence_source": "observed_raw_line", "causal_parent_ids": [rows[-1]["event_id"]] if rows else [],
            "transition_id": transition, "from_observed": phase, "event": kind, "to_observed": observed,
            "subject_id": identity["nodeVisitId"], "identity": identity, **revisions,
            "environment_profile": environment, "segment_complete": closed, "payload_hash": sha256(raw_line),
        }
        if stutter is not None:
            row["stutter_mapping_id"] = stutter
        rows.append(row)
        phase = observed
    require(all(NATIVE_PHASES.get(item["attempt"]["phase"]) == phase for item in outputs),
            "last normalized phase disagrees with reloaded native snapshot")
    normalized = json_lines(rows)
    contract = {"schema_version": "model-trace-contract/v1", "trace_id": trace_id,
                "environment_profile": environment, "revisions": revisions,
                "bindings": list(bindings.values()), "transitions": profile["transitions"],
                "stutters": profile["stutters"], "profile_sha256": PROFILE_SHA256}
    manifest = {
        "schema_version": "model-trace-segment/v1", "trace_id": trace_id, "environment_profile": environment,
        "revisions": revisions, "closed": closed, "collector_status": "complete" if closed else "partial",
        "raw_sha256": sha256(raw_bytes), "normalized_sha256": sha256(normalized),
        "streams": [{"producer_id": producer_id, "producer_epoch": 0, "first_seq": 1, "last_seq": len(rows)}],
        "initial": {identity["nodeVisitId"]: {"state": "planned", "identity": identity}},
    }
    if not closed:
        manifest["coverage_reason"] = "Batch 1 observations do not independently seal every native ledger segment"
    observations.update({"raw_origin": "native-ledger-bytes" if native is not None else "decoded-receipt-events",
                         "byte_count": len(raw_bytes), "native_lines": len(rows), "stale_attempt_test": late,
                         "scope": profile["scope"]})
    return {"id": name, "contract": contract, "manifest": manifest, "normalized_bytes": normalized,
            "raw_bytes": raw_bytes, "observations": observations}


def load_core_traces(graph_path, contract_path, capture_path=None):
    """Return evidence-bound inputs for the shared trace verifier, one per fixture."""
    graph = load_json(Path(graph_path).read_bytes())
    contract_path = Path(contract_path)
    profile_bytes = contract_path.read_bytes()
    require(sha256(profile_bytes) == PROFILE_SHA256, "unreviewed Core trace model profile")
    profile = load_json(profile_bytes)
    require(profile.get("schema_version") == PROFILE, "missing Core trace model profile schema")
    descriptor = NORMALIZER.parents[1] / "docs/evidence-graph-fixtures/core/fixture.json"
    bindings = resolved_bindings(graph, profile, load_json(descriptor.read_bytes()))
    core_revision = bindings["CORE.CODE.EVENTS"]["revision"]
    revisions = {"code_revision": core_revision,
                 "model_revision": bindings[profile["model_node"]]["revision"],
                 "mapping_revision": bindings["CORE.MAP.SAME-ATTEMPT-PROJECTION"]["revision"],
                 "verifier_revision": verifier_revision(),
                 "normalizer_revision": sha256(NORMALIZER.read_bytes())}
    if capture_path is not None:
        receipts, late = load_capture(Path(capture_path), bindings, core_revision, profile["environment_profile"])
    else:
        historical = contract_path.with_name("core-restart-observations.jsonl").read_bytes()
        require(sha256(historical) == bindings[profile["trace_node"]]["sha256"],
                "historical trace digest differs from compiled graph")
        receipts, late = parse_ledger(historical), None
    require(len(receipts) == len(SCENARIOS) and {item["testName"] for item in receipts} == SCENARIOS,
            "Core scenario set is incomplete or ambiguous")
    return [normalize(record, profile, bindings, revisions, capture_path is not None, late) for record in receipts]
