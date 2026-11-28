#!/usr/bin/env python3
"""Bridge the Project Adapter JSONL interface to an isolated native Core checkout."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/evidence-graph-fixtures/core/batch4_mutations/core-adapter-driver.mjs"
DESTINATION = "packages/workflow-execution/test/observation-cas/batch4-project-adapter-driver.mjs"
MAPPING_ID = "CORE.MAP.SAME-ATTEMPT-PROJECTION"
OBSERVATION_ID = "CORE.OBS.ROUTER-ORIGINAL"
PHASE = {"planned": "planned", "resolution_blocked": "resolutionBlocked",
         "delivery_started": "deliveryStarted", "run_delivered": "runDelivered",
         "recovery_refused": "needsReview", "delivery_failed": "needsReview"}
METADATA = {"recovery_authorized", "recovery_checked", "readback_checked"}
FAULTS = {"sigkillBeforeWal", "sigkillAfterWal", "sigkillAckLost"}
NO_WRITE = {"recoverAfterStart", "queryOriginal", "restart", "staleGeneration", "reconcileAfterStart",
            "sigkillBeforeWal", "sigkillAfterWal"}
AFTER_FENCE_CHECK = {"queryOriginal", "restart", "recoverAfterStart", "reconcileAfterStart"}
STUTTERS = {"restart": "restart_replay", "queryOriginal": "readonly_original_query",
            "staleGeneration": "stale_identity_refused", "recoverAfterStart": "post_wal_recovery_refused",
            "sigkillBeforeWal": "pre_wal_process_exit"}


def attempt(snapshot):
    rows = snapshot["attempts"]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("expected one native attempt in the bounded fixture")
    return rows[0]


def abstract_state(snapshot):
    item = attempt(snapshot)
    phase = "settled" if item["phase"] == "reconciled" and item["state"] == "SETTLED" else (
        "needsReview" if item["phase"] == "reconciled" else PHASE.get(item["phase"]))
    if phase is None:
        raise ValueError("native phase has no bounded abstraction")
    return {"identity": {"nodeVisitId": item["nodeVisitId"], "attemptId": item["attemptId"],
                         "generation": item.get("generation", 1)},
            "phase": phase, "deliveryStarted": "deliveryStartedAtMs" in item}


def normalize(event):
    kind = event["kind"]
    prior = event["observed_prior_phase"]
    if kind == "router_post":
        if not event["fence"]:
            return {"event": "routerWriteBeforeDurableFence"}
        if event["index"] != 1:
            return {"event": "duplicateRouterWrite"}
        if event["command_kind"] in NO_WRITE:
            return {"event": "prohibitedRouterWrite"}
        if event["requestId"] != event["observed_attempt_id"]:
            return {"event": "routerRequestIdentityMismatch"}
        return {"stutter": "router_transport_observation"}
    if kind in METADATA or kind == "resolution_blocked" and prior == "resolutionBlocked":
        return {"stutter": "recovery_observation_metadata"}
    symbols = {"resolution_blocked": "blockResolution", "delivery_started": "beginDelivery",
               "run_delivered": "confirmDelivery"}
    if kind in symbols:
        return {"event": symbols[kind]}
    if kind in {"delivery_failed", "reconciled"}:
        if prior == "deliveryStarted":
            return {"event": "rejectAfterStart"}
        if prior == "runDelivered":
            return {"event": "reconcileSettled" if event.get("verdict") == "SETTLED" else "reconcileNeedsReview"}
    return {"unknown": f"unmapped native ledger event: {kind}"}


def event_delta(result, command):
    prior = abstract_state(result["before"])
    phase = prior["phase"]
    for event in result["events"]:
        item = {**event, "observed_prior_phase": phase, "command_kind": command,
                "observed_attempt_id": prior["identity"]["attemptId"]}
        yield item
        if event["kind"] in PHASE:
            phase = PHASE[event["kind"]]
        elif event["kind"] == "reconciled":
            phase = "settled" if event["verdict"] == "SETTLED" else "needsReview"


def bound_router_receipt(observed, durable):
    if not isinstance(observed, dict):
        return False
    receipt = observed.get("snapshot")
    if not isinstance(receipt, dict) or observed.get("state") not in {"pending", "recovering", "settled"}:
        return False
    link = receipt.get("callerCorrelation")
    if not isinstance(link, dict) or link.get("requestId") != durable["attemptId"]:
        return False
    handle, message = observed.get("handle"), receipt.get("messageId")
    if (not isinstance(handle, str) or not handle or handle != receipt.get("handle")
            or not isinstance(message, str) or not message):
        return False
    delivered = durable.get("delivered")
    return not delivered or (delivered.get("requestId") == durable["attemptId"]
                             and delivered.get("reconciliationHandle") == handle
                             and delivered.get("messageId") == message)


def query_observation(outcome, correlation, durable, unresolved):
    if not isinstance(outcome, dict):
        return "UNKNOWN"
    if outcome != correlation:
        return "FAIL"
    if outcome == {"state": "never_existed"}:
        return "UNKNOWN" if unresolved or durable.get("delivered") else "PASS"
    if not bound_router_receipt(outcome, durable):
        return "UNKNOWN"
    if not durable.get("delivered") and not unresolved:
        return "FAIL"  # An attributable admission exists without a durable fence.
    return "UNKNOWN" if unresolved else "PASS"


def witnessed_observation(result, command):
    before, after = result["before"], result["after"]
    durable = attempt(after)
    unresolved = "deliveryStartedAtMs" in durable and not durable.get("delivered")
    effect = "UNKNOWN" if unresolved else "NOT_ESTABLISHED"
    if durable.get("delivered"):
        effect = "ROUTER_ADMISSION_OBSERVED" if bound_router_receipt(after.get("correlation"), durable) else "CORE_DELIVERY_RECORDED"
    if not result["appendOnly"] or (command in FAULTS and result.get("faultWitness", {}).get("signal") != "SIGKILL"):
        return "UNKNOWN", effect, False
    if not after["ledgerBytes"].endswith("\n"):
        return "UNKNOWN", effect, False
    outcome = result.get("outcome", {})
    if command == "staleGeneration" and (not isinstance(outcome, dict)
                                         or outcome.get("action") != "stale_observation"
                                         or outcome.get("committed") is not False):
        return "FAIL", effect, True
    if command == "recoverAfterStart" and (not isinstance(outcome, dict) or outcome.get("outcome") not in
                                           {"RECOVERY_INAPPLICABLE", "NO_OP_TERMINAL"}):
        return "FAIL", effect, True
    if command in {"restart", "queryOriginal"} and (before["ledgerBytes"] != after["ledgerBytes"]
                                                     or before["routerBytes"] != after["routerBytes"]):
        return "FAIL", effect, True
    if command == "queryOriginal":
        return query_observation(outcome, after.get("correlation"), durable, unresolved), effect, True
    if command in AFTER_FENCE_CHECK and unresolved:
        return "UNKNOWN", effect, True
    if command in {"sigkillAckLost", "sigkillAfterWal"}:
        return "UNKNOWN", effect, True
    return "PASS", effect, True


class NativeCore:
    def __init__(self, core):
        self.core = core
        self.driver = core / DESTINATION
        self.process = None

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="batch4-adapter-env-")
        try:
            with self.driver.open("xb") as file:
                file.write(SOURCE.read_bytes())
        except BaseException:
            self.temp.cleanup()
            raise
        try:
            node = shutil.which("node")
            if node is None:
                raise ValueError("Node is unavailable")
            env = {"PATH": os.defpath, "HOME": self.temp.name, "TMPDIR": self.temp.name, "TZ": "UTC"}
            self.process = subprocess.Popen([node, str(self.driver)], cwd=self.core, env=env,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=sys.stderr, text=True)
        except BaseException:
            self.driver.unlink()
            self.temp.cleanup()
            raise
        return self

    def __exit__(self, *_):
        try:
            self.process.stdin.close()
            try:
                status = self.process.wait(timeout=12)
            except subprocess.TimeoutExpired as error:
                self.process.kill()
                self.process.wait(timeout=5)
                raise ValueError("native Core worker did not finish its observation stream") from error
            if self.process.stdout.read(1) or status != 0:
                raise ValueError("native Core worker exited unsuccessfully or emitted unframed trailing output")
        finally:
            self.process.stdout.close()
            self.driver.unlink()
            self.temp.cleanup()

    def rpc(self, method, params):
        request = {"id": 1, "method": method, "params": params}
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        if reply.get("id") != request["id"] or "result" not in reply:
            raise ValueError(reply.get("error", "unreadable native Core response"))
        return reply["result"]

    def call(self, method, params):
        if method == "reset":
            if type(params.get("seed")) is not int:
                raise ValueError("seed must be an integer")
            profile = params.get("environment_profile")
            profile = profile.get("id") if isinstance(profile, dict) else profile
            if profile not in {"core-recovery", "core-generation-two"}:
                raise ValueError("use an isolated Core fixture environment")
            return self.rpc("reset", {"profile": profile})
        if method == "snapshot":
            return self.rpc("snapshot", {})
        if method == "abstract_state":
            if params.get("mapping_id") != MAPPING_ID:
                raise ValueError("unknown Core Recovery mapping")
            return abstract_state(params["snapshot"])
        if method == "normalize":
            if params.get("mapping_id") != MAPPING_ID:
                raise ValueError("unknown Core Recovery mapping")
            return normalize(params["event"])
        if method == "observe":
            if params.get("observation_id") != OBSERVATION_ID:
                raise ValueError("unknown Core Recovery observation")
            return params["result"]["observation"]
        if method == "execute":
            command = params["command"]
            kind = command["kind"]
            result = self.rpc("execute", {"command": command})
            observation, effect, complete = witnessed_observation(result, kind)
            observed_events = list(event_delta(result, kind))
            result["native_events"] = result["events"]
            result.update(events=observed_events, observation=observation, effect=effect,
                          business_effect="UNKNOWN", complete=complete)
            if kind in STUTTERS:
                result["stutter"] = STUTTERS[kind]
            elif result.get("rejected"):
                result["stutter"] = "refused_invalid_event"
            return result
        raise ValueError("unknown Core Adapter method")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True, help="isolated Core source checkout")
    args = parser.parse_args(argv)
    core = args.core.resolve(strict=True)
    with NativeCore(core) as adapter:
        for line in sys.stdin:
            identifier = None
            try:
                request = json.loads(line)
                identifier = request["id"]
                result = adapter.call(request["method"], request.get("params", {}))
                reply = {"id": identifier, "result": result}
            except (OSError, TypeError, KeyError, ValueError) as error:
                reply = {"id": identifier, "error": {"kind": "CORE_OBSERVATION_UNAVAILABLE", "message": str(error)}}
            print(json.dumps(reply, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
