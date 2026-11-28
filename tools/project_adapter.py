#!/usr/bin/env python3
"""Drive independently running implementation and model workers over JSONL."""

import argparse
import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import tempfile
import time


SUITE = "project-adapter-suite/v1"
RECEIPT = "project-adapter-receipt/v1"
REVISIONS = {"adapter_version", "mapping_version", "oracle_version", "sut_revision"}
OPTIONAL_REVISIONS = {"sut_mutation_sha256"}
DIGEST = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
MAX_FRAME = 4 * 1024 * 1024
METHODS = {"reset", "snapshot", "execute", "abstract_state", "normalize", "observe"}
OBSERVATIONS = {"PASS", "FAIL", "UNKNOWN"}
STATUS = {"TRACE_CONFORMANT", "TRACE_DRIFTED", "TRACE_INCOMPLETE", "STALE", "UNKNOWN"}


class ProtocolError(ValueError):
    """No independently observed, complete exchange for a requested step."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _read_json(data):
    def pairs(items):
        obj = dict(items)
        if len(obj) != len(items):
            raise ValueError("duplicate JSON key")
        return obj

    def constant(_):
        raise ValueError("nonfinite JSON value")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def _valid_text(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_versions(value):
    return (isinstance(value, dict) and REVISIONS <= value.keys() <= REVISIONS | OPTIONAL_REVISIONS
            and all(isinstance(v, str) and DIGEST.fullmatch(v) for v in value.values())
            and ("sut_mutation_sha256" not in value or len(value["sut_mutation_sha256"]) == 64))


def _validate_suite(suite):
    if suite.get("schema_version") != SUITE:
        raise ValueError("unsupported suite schema")
    if not _valid_versions(suite.get("versions")):
        raise ValueError("immutable SHA bindings for adapter, mapping, Oracle and implementation required")
    if type(suite.get("seed")) is not int or not 0 <= suite["seed"] < 2**53:
        raise ValueError("seed must be a nonnegative interoperable integer")
    if not all(_valid_text(suite.get(key)) for key in ("mapping_id", "observation_id")):
        raise ValueError("mapping and observation IDs are required")
    for key in ("environment_profile", "test_context"):
        if not isinstance(suite.get(key), dict):
            raise ValueError(f"{key} must be a JSON object")
    commands = suite.get("commands")
    if not isinstance(commands, list) or not commands or not all(
            isinstance(c, dict) and _valid_text(c.get("kind")) for c in commands):
        raise ValueError("nonempty command sequence with kind IDs required")
    stutters = suite.get("stutters")
    if not isinstance(stutters, dict) or not all(_valid_text(k) and _valid_text(v) for k, v in stutters.items()):
        raise ValueError("stutters require an ID and a rationale")
    for key in ("sut_argv", "oracle_argv"):
        argv = suite.get(key)
        if not isinstance(argv, list) or not argv or not all(_valid_text(arg) for arg in argv):
            raise ValueError(f"{key} must be a command argument array")
    if suite["sut_argv"] == suite["oracle_argv"]:
        raise ValueError("use distinct implementation and model worker commands")
    timeout = suite.get("timeout")
    if type(timeout) not in (float, int) or not 0 < timeout <= 300:
        raise ValueError("per-call timeout must be in (0, 300] seconds")
    _canonical(suite)


def _stream_bytes(data):
    return base64.b64encode(data).decode("ascii")


class Worker:
    def __init__(self, argv, cwd, home, timeout):
        self.argv, self.cwd, self.home, self.timeout = argv, cwd, home, timeout
        self.out = bytearray()
        self.transcript = {"argv": argv, "cwd": str(cwd), "frames": []}

    def __enter__(self):
        self.stderr = tempfile.TemporaryFile()
        try:
            environment = {"PATH": os.environ.get("PATH", os.defpath), "HOME": self.home,
                           "TMPDIR": self.home, "TZ": "UTC", "LANG": "C"}
            self.process = subprocess.Popen(self.argv, cwd=self.cwd, env=environment, start_new_session=True,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr)
        except OSError as error:
            self.stderr.close()
            raise ProtocolError(f"worker launch failed ({type(error).__name__})") from error
        self.transcript["pid"] = self.process.pid
        self.write_fd = self.process.stdin.fileno()
        self.read_fd = self.process.stdout.fileno()
        os.set_blocking(self.write_fd, False)
        os.set_blocking(self.read_fd, False)
        return self

    def __exit__(self, *_):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=5)
        try:
            while len(self.out) <= MAX_FRAME:
                data = os.read(self.read_fd, 65536)
                if not data:
                    break
                self.out.extend(data)
        except BlockingIOError:
            pass
        self.process.stdout.close()
        self.stderr.seek(0)
        tail = self.stderr.read(MAX_FRAME + 1)
        self.stderr.close()
        self.transcript["exit_code"] = self.process.returncode
        self.transcript["stderr_base64"] = _stream_bytes(tail[:MAX_FRAME])
        self.transcript["stderr_truncated"] = len(tail) > MAX_FRAME
        self.transcript["unframed_stdout_base64"] = _stream_bytes(self.out[:MAX_FRAME])
        self.transcript["stdout_truncated"] = len(self.out) > MAX_FRAME

    def call(self, method, **params):
        if method not in METHODS:
            raise ValueError("unsupported RPC method")
        identifier = len(self.transcript["frames"]) + 1
        request = _canonical({"id": identifier, "method": method, "params": params}) + b"\n"
        frame = {"request_base64": _stream_bytes(request), "response_base64": None}
        self.transcript["frames"].append(frame)
        if len(request) > MAX_FRAME:
            raise ProtocolError("request exceeds frame budget")
        deadline = time.monotonic() + self.timeout
        try:
            sent = 0
            while sent < len(request):
                _, writable, _ = select.select([], [self.write_fd], [], max(0, deadline - time.monotonic()))
                if not writable:
                    raise ProtocolError(f"{method} request timed out")
                sent += os.write(self.write_fd, request[sent:])
            while b"\n" not in self.out:
                ready, _, _ = select.select([self.read_fd], [], [], max(0, deadline - time.monotonic()))
                if not ready:
                    raise ProtocolError(f"{method} response timed out")
                data = os.read(self.read_fd, 65536)
                if not data:
                    raise ProtocolError(f"worker output closed during {method}")
                self.out.extend(data)
                if len(self.out) > MAX_FRAME and (b"\n" not in self.out or self.out.index(b"\n") >= MAX_FRAME):
                    raise ProtocolError(f"{method} response exceeds frame budget")
        except OSError as error:
            raise ProtocolError(f"{method} subprocess I/O failed ({type(error).__name__})") from error
        line, _, remaining = self.out.partition(b"\n")
        self.out = bytearray(remaining)
        frame["response_base64"] = _stream_bytes(line + b"\n")
        if remaining:
            raise ProtocolError(f"unsolicited worker output after {method}")
        try:
            response = _read_json(line)
        except (ValueError, RecursionError) as error:
            raise ProtocolError(f"invalid JSON response to {method}") from error
        if (not isinstance(response, dict) or type(response.get("id")) is not int
                or response["id"] != identifier or response.keys() != {"id", "result"}):
            raise ProtocolError(f"missing result or mismatched response to {method}")
        return response["result"]


def _observation(value):
    status = value if isinstance(value, str) else value.get("status") if isinstance(value, dict) else None
    if not isinstance(status, str) or status not in OBSERVATIONS:
        raise ProtocolError("missing or invalid observation status")
    return status


def _events(result):
    if not isinstance(result, dict) or result.get("complete") is not True or not isinstance(result.get("events"), list):
        raise ProtocolError("execution did not attest a complete event sequence")
    return result["events"]


def _project(events, stutters):
    labels, stutter_ids = [], []
    for event in events:
        if not isinstance(event, dict):
            raise ProtocolError("event mapping did not produce a JSON object")
        if _valid_text(event.get("event")) and "stutter" not in event and "unknown" not in event:
            labels.append(event["event"])
        elif event.keys() == {"stutter"} and _valid_text(event["stutter"]):
            if event["stutter"] not in stutters:
                return None, stutter_ids, "undeclared stutter"
            stutter_ids.append(event["stutter"])
        elif event.keys() == {"unknown"} and _valid_text(event["unknown"]):
            return None, stutter_ids, "event has no reviewed mapping"
        else:
            raise ProtocolError("event lacks an unambiguous mapping")
    return labels, stutter_ids, None


def _gate(evidence):
    if evidence is None:
        return None
    if not isinstance(evidence, dict):
        raise ValueError("evidence gates must be an object")
    if any(not isinstance(value, dict) for value in evidence.values()):
        raise ValueError("evidence gate values must be reports")
    if any(value.get("status") == "STALE" for value in evidence.values()):
        return "STALE", "a version or environment receipt is stale"
    if "trace" in evidence and evidence["trace"].get("status") in (None, "TRACE_INCOMPLETE"):
        return "TRACE_INCOMPLETE", "the independent trace receipt is incomplete"
    if "trace" in evidence and evidence["trace"].get("status") == "TRACE_DRIFTED":
        return "TRACE_DRIFTED", "the independent trace receipt detected drift"
    if (("probe" in evidence and evidence["probe"].get("status") != "PASS") or
            ("trace" in evidence and evidence["trace"].get("status") != "TRACE_CONFORMANT")):
        return "UNKNOWN", "an independent runtime precondition is unsupported"
    return None


def _snapshot(sut, oracle, mapping):
    concrete = sut.call("snapshot")
    abstract = sut.call("abstract_state", snapshot=concrete, mapping_id=mapping)
    expected = oracle.call("snapshot")
    return {"concrete": concrete, "abstract": abstract, "oracle": expected, "mapping_id": mapping}


def _compare_step(step, previous, sut, oracle, context, mapping, observation, stutters):
    step["sut_result"] = sut.call("execute", command=step["command"], test_context=context)
    step["oracle_result"] = oracle.call("execute", command=step["command"], test_context=context)
    step["snapshot"] = _snapshot(sut, oracle, mapping)
    observed, expected = step["sut_result"], step["oracle_result"]
    actual_events, oracle_events = _events(observed), _events(expected)
    if expected.get("supported", True) is False:
        return "UNKNOWN", "command outside bounded Oracle scope"
    step["normalized_events"] = [sut.call("normalize", event=e, mapping_id=mapping) for e in actual_events]
    step["sut_observation"] = sut.call("observe", result=observed, observation_id=observation)
    actual_status, expected_status = _observation(step["sut_observation"]), _observation(expected.get("observation"))
    states = step["snapshot"]
    if "state" not in expected or _canonical(states["oracle"]) != _canonical(expected["state"]):
        raise ProtocolError("Oracle execution result differs from independently read model state")
    if _canonical(states["abstract"]) != _canonical(states["oracle"]):
        return "TRACE_DRIFTED", "projected implementation state differs from independent model state"
    actual_labels, actual_stutters, problem = _project(step["normalized_events"], stutters)
    expected_labels, expected_stutters, oracle_problem = _project(oracle_events, stutters)
    if problem or oracle_problem:
        return "UNKNOWN", problem or oracle_problem
    step["stutters"] = [{"id": key, "justification": stutters[key]} for key in actual_stutters + expected_stutters]
    if actual_labels != expected_labels:
        return "TRACE_DRIFTED", "observed events differ from allowed model transitions"
    if not actual_labels and _canonical(states["abstract"]) != _canonical(previous["abstract"]):
        return "TRACE_DRIFTED", "stuttering step changed the abstract state"
    if not actual_labels and not step["stutters"]:
        named = [result["stutter"] for result in (observed, expected) if "stutter" in result]
        if not named or any(not _valid_text(key) or key not in stutters for key in named):
            return "UNKNOWN", "empty transition requires a declared stuttering justification"
        step["stutters"] = [{"id": key, "justification": stutters[key]} for key in named]
    if actual_status != expected_status:
        if actual_status == "UNKNOWN":
            return "UNKNOWN", "implementation observation cannot establish the assumed effect"
        return "TRACE_DRIFTED", "observation differs from the independent model expectation"
    step["transition_comparison"] = "TRACE_CONFORMANT"
    return ("UNKNOWN", "external effect remains UNKNOWN") if actual_status == "UNKNOWN" else ("TRACE_CONFORMANT", "")


def run_adapter(*, sut_argv, oracle_argv, seed, environment_profile, commands, mapping_id,
                observation_id, versions, stutters=None, evidence=None, test_context=None,
                sut_cwd=None, oracle_cwd=None, timeout=15):
    """Execute a fixed sequence and retain the audited, replayable prefix on failure."""
    suite = {"schema_version": SUITE, "sut_argv": list(sut_argv), "oracle_argv": list(oracle_argv),
             "seed": seed, "environment_profile": environment_profile, "commands": commands,
             "mapping_id": mapping_id, "observation_id": observation_id, "versions": versions,
             "stutters": {} if stutters is None else stutters, "evidence": evidence,
             "test_context": {} if test_context is None else test_context,
             "sut_cwd": str(sut_cwd) if sut_cwd is not None else None,
             "oracle_cwd": str(oracle_cwd) if oracle_cwd is not None else None, "timeout": timeout}
    _validate_suite(suite)
    suite = _read_json(_canonical(suite))
    report = {"schema_version": RECEIPT, "input": suite, "input_sha256": hashlib.sha256(_canonical(suite)).hexdigest(),
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "initial": None, "steps": [], "workers": {}, "failure": None, "unknown_steps": []}

    def finish(status, reason="", index=None):
        report["status"] = status
        if status != "TRACE_CONFORMANT":
            report["failure"] = {"reason": reason, "step": index}
        return report

    gate = _gate(evidence)
    if gate:
        return finish(*gate)
    with ExitStack() as cleanup:
        def confirm_closed():
            complete_projection = (len(report["steps"]) == len(suite["commands"])
                                   and all(step.get("transition_comparison") == "TRACE_CONFORMANT"
                                           for step in report["steps"]))
            if report.get("status") != "TRACE_CONFORMANT" and not complete_projection:
                return
            if any(worker.get("exit_code") != 0 or worker.get("unframed_stdout_base64")
                   or worker.get("stdout_truncated") for worker in report["workers"].values()):
                finish("TRACE_INCOMPLETE", "worker did not close with a complete stdout exchange")

        cleanup.callback(confirm_closed)
        try:
            workers = {}
            for role in ("sut", "oracle"):
                default = cleanup.enter_context(tempfile.TemporaryDirectory(prefix=f"adapter-{role}-"))
                worker = Worker(suite[f"{role}_argv"], suite[f"{role}_cwd"] or default, default, timeout)
                report["workers"][role] = worker.transcript
                workers[role] = cleanup.enter_context(worker)
            sut, oracle = workers["sut"], workers["oracle"]
            if Path(sut.cwd).resolve() == Path(oracle.cwd).resolve():
                raise ProtocolError("implementation and model workers require separate working directories")
            for worker in workers.values():
                worker.call("reset", seed=seed, environment_profile=environment_profile)
            report["initial"] = _snapshot(sut, oracle, mapping_id)
            if _canonical(report["initial"]["abstract"]) != _canonical(report["initial"]["oracle"]):
                return finish("TRACE_DRIFTED", "initial implementation and model states differ")
            previous = report["initial"]
            for index, command in enumerate(suite["commands"]):
                step = {"index": index, "command": command}
                report["steps"].append(step)
                context = {**suite["test_context"], "index": index, "seed": seed}
                try:
                    checked = _compare_step(step, previous, sut, oracle, context, mapping_id, observation_id,
                                            suite["stutters"])
                except ProtocolError as error:
                    checked = "TRACE_INCOMPLETE", str(error)
                step["status"], step["reason"] = checked
                if checked[0] != "TRACE_CONFORMANT" and "transition_comparison" not in step:
                    return finish(*checked, index=index)
                if checked[0] == "UNKNOWN":
                    report["unknown_steps"].append(index)
                previous = step["snapshot"]
            if report["unknown_steps"]:
                return finish("UNKNOWN", "one or more external effects remain UNKNOWN", report["unknown_steps"][0])
            return finish("TRACE_CONFORMANT")
        except ProtocolError as error:
            return finish("TRACE_INCOMPLETE", str(error))


def _launch(suite):
    _validate_suite(suite)
    return run_adapter(**{key: value for key, value in suite.items() if key != "schema_version"})


def replay_adapter(receipt, versions, evidence=None):
    """Replay the same plan using independent current bindings and optional fresh gates."""
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT or not _valid_versions(versions):
        raise ValueError("unsupported receipt or current binding")
    suite = receipt.get("input")
    if not isinstance(suite, dict) or hashlib.sha256(_canonical(suite)).hexdigest() != receipt.get("input_sha256"):
        raise ValueError("saved command input differs from recorded digest")
    if (suite["versions"] != versions or
            receipt.get("runner_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        return {"schema_version": RECEIPT, "status": "STALE", "input": suite,
                "input_sha256": receipt["input_sha256"], "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "initial": None, "steps": [], "workers": {}, "unknown_steps": [],
                "failure": {"reason": "replay revision bindings changed", "step": None}}
    if suite.get("evidence") is not None and (not isinstance(evidence, dict) or
                                              suite["evidence"].keys() != evidence.keys()):
        raise ValueError("current independent evidence must be supplied for each original replay gate")
    return _launch({**suite, "evidence": evidence})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "replay"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--versions", type=Path, help="Separately pinned versions required for replay")
    parser.add_argument("--evidence", type=Path, help="Fresh independent probe and trace gate reports for replay")
    args = parser.parse_args(argv)
    try:
        payload = _read_json(args.input.read_bytes())
        if args.mode == "replay":
            if args.versions is None:
                parser.error("replay requires --versions")
            result = replay_adapter(payload, _read_json(args.versions.read_bytes()),
                                    _read_json(args.evidence.read_bytes()) if args.evidence else None)
        else:
            result = _launch(payload)
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(result, out, ensure_ascii=False, sort_keys=True, indent=2)
            out.write("\n")
    except (OSError, TypeError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps({"status": result["status"], "receipt": str(args.output)}))
    return 0 if result["status"] == "TRACE_CONFORMANT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
