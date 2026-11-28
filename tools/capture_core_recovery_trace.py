#!/usr/bin/env python3
"""Capture the pinned Core recovery tests and the native ledger bytes they read."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile


CORE_REVISION = "ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e"
TEST_ROOT = "packages/workflow-execution/test/observation-cas"
RESTART_TEST = f"{TEST_ROOT}/blocked-recovery-restart.test.js"
CAS_TEST = f"{TEST_ROOT}/blocked-recovery.test.js"
NATIVE_WITNESS = "events: events(fx.dir), ...extra"
LEDGER_WITNESS = "events: events(fx.dir), ledgerBytes: bytes(join(fx.dir, 'attempts.jsonl')), ...extra"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def tap_receipts(tap):
    receipts = []
    for line in tap.decode("utf-8").splitlines():
        if line.startswith("# {"):
            # Undo TAP's directive and backslash escaping before decoding JSON.
            diagnostic = json.loads(line[2:].replace(r"\#", "#").replace("\\\\", "\\"))
            if isinstance(diagnostic, dict) and "testName" in diagnostic:
                receipts.append(diagnostic)
    return receipts


def run_test(repo, output_file, test, environment, *options):
    command = ["node", "--test", "--test-reporter=tap", *options, test]
    completed = subprocess.run(command, cwd=repo, env=environment, capture_output=True, timeout=90)
    output_file.write_bytes(completed.stdout)
    output_file.with_suffix(".stderr").write_bytes(completed.stderr)
    if completed.returncode:
        raise ValueError(f"Core test exited {completed.returncode}, see {output_file}")
    return completed.stdout, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New receipt directory")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archive = subprocess.check_output(["git", "-C", str(args.core_repo), "archive", CORE_REVISION], timeout=45)
    with tempfile.TemporaryDirectory(prefix="core-recovery-trace-") as temporary:
        root = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
            # The pinned tree has a developer-specific node_modules symlink.
            # These two node:test suites use Node built-ins and local Core source.
            tree.extractall(root, members=(item for item in tree if item.name != "node_modules"), filter="data")
        fixture = root / RESTART_TEST
        original = fixture.read_text(encoding="utf-8")
        if original.count(NATIVE_WITNESS) != 1:
            raise ValueError("Pinned Core receipt insertion point changed")
        instrumented = original.replace(NATIVE_WITNESS, LEDGER_WITNESS)
        fixture.write_text(instrumented, encoding="utf-8")
        (output / "original-restart.test.js").write_text(original, encoding="utf-8")
        (output / "instrumented-restart.test.js").write_text(instrumented, encoding="utf-8")
        temp = root / "trace-runtime"
        temp.mkdir()
        environment = {"PATH": os.environ["PATH"], "HOME": str(temp), "TMPDIR": str(temp),
                       "EKR_SOURCE_SHA": CORE_REVISION}
        tap, command = run_test(root, output / "core-restart.tap", RESTART_TEST, environment)
        receipts = tap_receipts(tap)
        names = {item["testName"] for item in receipts}
        if len(receipts) != 6 or len(names) != 6 or any(
            item["sourceSha"] != CORE_REVISION or not item["rawReceipt"].get("ledgerBytes")
            for item in receipts
        ):
            raise ValueError("Core run did not supply six distinct native ledger receipts")
        late_test = "B2 an old automatic scan cannot authorize or modify a later blocked generation"
        late, late_command = run_test(root, output / "core-stale-attempt.tap", CAS_TEST, environment,
                                     "--test-name-pattern", f"^{late_test}$")
        if not re.search(rb"(?m)^# pass 1$", late) or f" - {late_test}".encode() not in late:
            raise ValueError("The stale-attempt negative control did not run")
        result = {
            "schema_version": "core-recovery-capture/v1", "code_revision": CORE_REVISION,
            "environment": "isolated-core-loopback", "test_exit": 0,
            "harness_sha256": sha256(Path(__file__).read_bytes()),
            "fixture_sha256": sha256(original.encode()),
            "instrumented_fixture_sha256": sha256(instrumented.encode()),
            "tap_sha256": sha256(tap), "stale_attempt_tap_sha256": sha256(late),
            "node_version": subprocess.check_output(["node", "--version"], env=environment, text=True).strip(),
            "commands": [command, late_command], "scenarios": receipts,
        }
        (output / "core-recovery-capture.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(output / "core-recovery-capture.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        sys.exit(f"CORE_TRACE_CAPTURE_FAILED: {error}")
