#!/usr/bin/env python3
"""Run a trusted isolated assumption probe, or assess a receipt against a current context."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


CONTEXT = "assumption-probe-context/v1"
RECEIPT = "assumption-probe-receipt/v1"
REVISIONS = {"spec", "model", "code", "mapping", "verifier", "probe"}
RESULT_CODES = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verifier_revision():
    return digest(Path(__file__).read_bytes())


def scope_hash(scope):
    return digest(json.dumps(scope, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode())


def timestamp(value):
    if isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value)
            if stamp.tzinfo is not None:
                return stamp.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            pass
    return None


def text(value):
    return isinstance(value, str) and bool(value.strip())


def sha(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def context_valid(value):
    if not isinstance(value, dict) or value.get("schema_version") != CONTEXT:
        return False
    versions, ttl = value.get("versions"), value.get("ttl_seconds")
    failure, blind, bindings = (value.get("failure_behavior"), value.get("blind_spots"),
                                value.get("evidence_bindings"))
    return (all(text(value.get(key)) for key in ("assumption_id", "proposition", "owner", "probe_id"))
            and isinstance(versions, dict) and versions.keys() == REVISIONS
            and all(text(v) for v in versions.values()) and sha(versions["probe"])
            and type(ttl) is int and 0 < ttl <= 31_536_000
            and sha(value.get("environment_scope_hash"))
            and isinstance(failure, dict) and failure.keys() == {"condition_false", "timeout"}
            and all(v in ("FAIL", "UNKNOWN") for v in failure.values())
            and isinstance(blind, list) and bool(blind) and all(text(v) for v in blind)
            and isinstance(bindings, dict) and bool(bindings)
            and all(text(k) and isinstance(v, dict) and v.keys() == {"revision", "sha256"}
                    and text(v["revision"]) and sha(v["sha256"]) for k, v in bindings.items()))


def safe_evidence(value):
    return isinstance(value, dict) and 0 < len(value) <= 32 and all(
        isinstance(k, str) and re.fullmatch(r"[a-z][a-z_0-9]{0,47}", k)
        and (type(v) is bool or type(v) is int and 0 <= v < 2**53 or sha(v))
        for k, v in value.items()
    )


def reported_status(kind, observed, exit_code, evidence, failure):
    if kind == "timeout" and observed is None and exit_code is None and evidence == {}:
        return failure["timeout"]
    if kind == "observed" and isinstance(observed, str) and observed in RESULT_CODES:
        if type(exit_code) is int and exit_code == RESULT_CODES[observed] and safe_evidence(evidence):
            return failure["condition_false"] if observed == "FAIL" else observed
    return "UNKNOWN"


def assess_receipt(receipt, context, now):
    """Judge historical execution independently of the current policy, scope and clock."""
    raw = receipt.get("status") if isinstance(receipt, dict) else None

    def result(status, reason):
        return {"status": status, "reason": reason,
                "raw_status": raw if isinstance(raw, str) and raw in RESULT_CODES else None}

    if not context_valid(context) or not isinstance(now, datetime) or now.utcoffset() is None:
        return result("UNKNOWN", "invalid current probe context or clock")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT:
        return result("UNKNOWN", "no supported execution receipt")
    prior = {**receipt, "schema_version": CONTEXT}
    if not context_valid(prior):
        return result("UNKNOWN", "malformed execution context")
    fields = ("assumption_id", "probe_id", "proposition", "owner", "versions", "ttl_seconds",
              "environment_scope_hash", "failure_behavior", "blind_spots", "evidence_bindings")
    changed = [key for key in fields if receipt[key] != context[key]]
    if changed:
        return result("STALE", "changed binding: " + ", ".join(changed))
    if context["versions"]["verifier"] != verifier_revision():
        return result("STALE", "running verifier differs from expected version")
    ran, expiry = timestamp(receipt.get("executed_at")), timestamp(receipt.get("expires_at"))
    if not ran or not expiry or ran > now or expiry - ran != timedelta(seconds=context["ttl_seconds"]):
        return result("UNKNOWN", "invalid execution or expiry time")
    if expiry <= now:
        return result("STALE", "probe TTL expired")
    cmd, inputs, scope = (receipt.get("command"), receipt.get("input_hashes"),
                          receipt.get("environment_snapshot"))
    if (not isinstance(cmd, list) or not cmd or not all(text(v) for v in cmd)
            or not isinstance(inputs, dict) or not all(text(k) and sha(v) for k, v in inputs.items())
            or inputs.get("probe") != context["versions"]["probe"]
            or inputs.get("runner") != context["versions"]["verifier"]
            or not isinstance(scope, dict) or not scope):
        return result("UNKNOWN", "missing command, input digests, or environment snapshot")
    try:
        if scope_hash(scope) != context["environment_scope_hash"]:
            return result("STALE", "recorded environment bytes do not match expected scope")
    except (ValueError, TypeError):
        return result("UNKNOWN", "invalid environment snapshot")
    reconstructed = reported_status(receipt.get("execution_kind"), receipt.get("observed_result"),
                                   receipt.get("exit_code"), receipt.get("evidence"), context["failure_behavior"])
    if not isinstance(raw, str) or raw != reconstructed:
        return result("UNKNOWN", "recorded result conflicts with invocation evidence")
    return result(raw, "current execution observation")


def hash_inputs(paths):
    return {key: digest(Path(path).read_bytes()) for key, path in paths.items()}


def run_probe(context, scope, inputs, argv, *, cwd, timeout=30):
    """Run only a reviewed no-secret command in a caller-selected isolated workspace."""
    if not context_valid(context) or not isinstance(scope, dict) or scope_hash(scope) != context["environment_scope_hash"]:
        raise ValueError("invalid probe context or scope hash")
    if not argv or not all(text(arg) for arg in argv) or not 0 < timeout <= 300:
        raise ValueError("invalid probe command or timeout")
    probe = Path(inputs["probe"]).resolve()
    if str(probe) not in argv or not Path(argv[0]).is_absolute():
        raise ValueError("use the absolute executable and include the exact probe input path in the command")
    inputs = {**inputs, "runner": Path(__file__)}
    before = hash_inputs(inputs)
    if before["probe"] != context["versions"]["probe"]:
        raise ValueError("probe file differs from pinned version")
    if before["runner"] != context["versions"]["verifier"]:
        raise ValueError("probe runner differs from pinned version")
    kind, observed, exit_code, evidence = "unavailable", None, None, {}
    with tempfile.TemporaryDirectory(prefix="assumption-probe-env-") as home:
        env = {"HOME": home, "TMPDIR": home, "PATH": os.defpath, "TZ": "UTC", "LANG": "C"}
        with tempfile.TemporaryFile() as stdout:
            try:
                run = subprocess.run(argv, cwd=cwd, timeout=timeout, env=env, stdout=stdout,
                                     stderr=subprocess.DEVNULL)
                exit_code = run.returncode
                stdout.seek(0)
                data = stdout.read(8193)
                payload = json.loads(data) if len(data) <= 8192 else None
                if (isinstance(payload, dict) and payload.keys() == {"result", "evidence"}
                        and isinstance(payload["result"], str) and RESULT_CODES.get(payload["result"]) == exit_code
                        and safe_evidence(payload["evidence"])):
                    kind, observed, evidence = "observed", payload["result"], payload["evidence"]
                else:
                    kind = "invalid-output"
            except subprocess.TimeoutExpired:
                kind = "timeout"
            except (ValueError, RecursionError):
                kind = "invalid-output"
            except OSError:
                pass
    try:
        unchanged = before == hash_inputs(inputs)
    except OSError:
        unchanged = False
    if not unchanged:
        kind, observed, evidence = "inputs-changed", None, {}
    ran = datetime.now(timezone.utc)
    status = reported_status(kind, observed, exit_code, evidence, context["failure_behavior"])
    return {**context, "schema_version": RECEIPT, "status": status, "execution_kind": kind,
            "observed_result": observed, "exit_code": exit_code, "evidence": evidence,
            "executed_at": ran.isoformat(), "expires_at": (ran + timedelta(seconds=context["ttl_seconds"])).isoformat(),
            "command": list(argv), "input_hashes": before, "environment_snapshot": scope}


def read_json(path):
    return json.loads(Path(path).read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    check = commands.add_parser("check")
    check.add_argument("--context", required=True)
    check.add_argument("--receipt")
    check.add_argument("--at", help="Explicit observation time for replay")
    run = commands.add_parser("run")
    for flag in ("context", "scope", "output"):
        run.add_argument(f"--{flag}", required=True)
    run.add_argument("--cwd", default=".")
    run.add_argument("--input", action="append", required=True, help="name=absolute path, including probe")
    run.add_argument("--timeout", type=float, default=30)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        context = read_json(args.context)
        if args.action == "check":
            now = timestamp(args.at) if args.at is not None else datetime.now(timezone.utc)
            report = assess_receipt(read_json(args.receipt) if args.receipt else None, context, now)
        else:
            pairs = [item.split("=", 1) for item in args.input]
            inputs = dict(pairs)
            if len(inputs) != len(pairs) or "runner" in inputs or "probe" not in inputs:
                raise ValueError("invalid or duplicate named inputs")
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            with Path(args.output).open("x", encoding="utf-8") as out:
                receipt = run_probe(context, read_json(args.scope), inputs, command, cwd=args.cwd, timeout=args.timeout)
                json.dump(receipt, out, ensure_ascii=False, sort_keys=True, indent=2)
                out.write("\n")
            report = assess_receipt(receipt, context, datetime.now(timezone.utc))
    except (OSError, ValueError, TypeError) as error:
        # Subprocess output and argument values are intentionally excluded.
        parser.error(f"invalid probe input or unavailable file ({type(error).__name__})")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
