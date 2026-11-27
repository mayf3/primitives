#!/usr/bin/env python3
"""Exercise the Batch 1 CLI on pinned consumer evidence and deliberate input drift."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


TOOLS = Path(__file__).resolve().parent
FIXTURES = TOOLS.parent / "docs" / "evidence-graph-fixtures"
COMPILER = TOOLS / "evidence_graph.py"
MATERIALIZER = TOOLS / "evidence_graph_fixture.py"
REPORTS = ("evidence-graph.json", "coverage-report.json", "dangling-links.json", "stale-evidence.json")
VERIFIED = {
    "wake": {"WAKE-PR142-LEAN-AUDIT"},
    "outbox": {"OUTBOX.MAIN.LEAN.AUDIT", "OUTBOX.DRAFT.LEAN.AUDIT"},
    "core": {"CORE.LEAN.KERNEL-CI", "CORE.TEST.RECOVERY"},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def run(command: list[str], directory: Path, label: str, expected: tuple[int, ...]) -> dict:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, text=True, timeout=120)
    (directory / f"{label}.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (directory / f"{label}.stderr.txt").write_text(result.stderr, encoding="utf-8")
    record = {"command": command, "exit_code": result.returncode}
    (directory / f"{label}.command.json").write_text(json.dumps(record, indent=2) + "\n",
                                                    encoding="utf-8")
    check(result.returncode in expected, f"{label} exit {result.returncode}; see {directory}")
    return record


def compile_project(project: Path, receipt_dir: Path, expected: dict[str, tuple[int, ...]]):
    results = {}
    receipt_dir.mkdir(parents=True)
    for action, codes in expected.items():
        command = [sys.executable, str(COMPILER), action, "--project", str(project)]
        results[action] = run(command, receipt_dir, action, codes)
    for report in REPORTS:
        shutil.copyfile(project / ".evidence-graph" / report, receipt_dir / report)
    return results


def diagnose(receipt_dir: Path) -> set[str]:
    graph = read_json(receipt_dir / REPORTS[0])
    stale = read_json(receipt_dir / REPORTS[3])
    records = [*graph["diagnostics"], *stale["items"]]
    return {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in records}


def weaken_theorem(path: Path):
    text = path.read_text(encoding="utf-8")
    weaker = "theorem step_preserves_event_key : True := True.intro\n\n"
    modified, count = re.subn(r"^theorem step_preserves_event_key\b[\s\S]*?(?=^/--)",
                              weaker, text, count=1, flags=re.MULTILINE)
    check(count == 1, "Real Outbox theorem was unavailable for the negative control")
    path.write_text(modified, encoding="utf-8")


def replace_once(path: Path, original: str, replacement: str):
    text = path.read_text(encoding="utf-8")
    check(original in text, f"{path}: mutation anchor is absent")
    path.write_text(text.replace(original, replacement, 1), encoding="utf-8")


def reassign_acceptance(path: Path):
    receipt = read_json(path)
    for link in receipt["links"]:
        if link["from"] == "OUTBOX.MAIN.REQ.004" and link["to"] == "OUTBOX.MAIN.AC.004":
            link["from"] = "OUTBOX.MAIN.REQ.005"
            path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return
    raise ValueError("Outbox acceptance link is absent")


def adversarial_checks(outbox: Path, baseline: Path, temporary: Path, receipts: Path):
    pristine = diagnose(baseline)
    mutations = (
        ("symbol", "materials/main/outbox.rs", "OUTBOX.MAIN.CODE.CLAIM",
         "SYMBOL_NOT_FOUND", lambda path: replace_once(path, "fn claim_row(", "fn claim_row_changed(")),
        ("spec", "materials/main/spec.md", "OUTBOX.MAIN.SPEC",
         "SOURCE_HASH_MISMATCH", lambda path: replace_once(
             path, "EXECUTION_KICK_MAX_ATTEMPTS = 12", "EXECUTION_KICK_MAX_ATTEMPTS = 13")),
        ("theorem", "materials/main/Outbox.lean", "OUTBOX.MAIN.THM.KEY",
         "SOURCE_HASH_MISMATCH", weaken_theorem),
        ("test-deletion", "materials/pr141-pr13-draft/48_outbox_three_channels.rs",
         "OUTBOX.DRAFT.CODE.TEST-UNKNOWN-CAP", "COORDINATE_FILE_MISSING", Path.unlink),
        ("receipt-deletion", "materials/pg/regression-receipt.json",
         "OUTBOX.DRAFT.TEST.PG", "COORDINATE_FILE_MISSING", Path.unlink),
        ("acceptance-binding", "fixture.evidence.json", "OUTBOX.MAIN.AC.004",
         "ACCEPTANCE_REQUIREMENT_MISMATCH", reassign_acceptance),
    )
    results = {}
    for case, relative, node_id, expected_code, mutate in mutations:
        mutated = temporary / ("outbox-" + case)
        shutil.copytree(outbox, mutated, ignore=shutil.ignore_patterns(".evidence-graph"))
        source = mutated / relative
        before = sha256(source)
        mutate(source)
        after = sha256(source) if source.exists() else None
        check(after != before, f"{case} left the input unchanged")
        report = receipts / case
        commands = compile_project(mutated, report, {"validate": (1,), "stale": (1,)})
        new_records = [json.loads(item) for item in sorted(diagnose(report) - pristine)]
        check(any(item.get("id") == node_id and item.get("code") == expected_code
                  for item in new_records),
              f"{case} did not report {expected_code} at {node_id}: {new_records}")
        results[case] = {"path": relative, "target": node_id, "before_sha256": before,
                         "after_sha256": after, "commands": commands,
                         "new_diagnostic_count": len(new_records),
                         "expected_diagnostics": [item for item in new_records if item.get("id") == node_id]}
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories", required=True, type=Path, help="Parent of consumer Git repos")
    parser.add_argument("--repo", action="append", default=[], help="Repository override name=path")
    parser.add_argument("--output", required=True, type=Path, help="New directory for generated evidence")
    parser.add_argument("--expected-compiler-sha256", help="Externally reviewed compiler digest")
    args = parser.parse_args()
    compiler_sha = sha256(COMPILER)
    if args.expected_compiler_sha256 is not None:
        check(compiler_sha == args.expected_compiler_sha256, "Compiler differs from reviewed digest")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": "evidence-graph-fixture-validation/v1",
               "compiler_sha256": compiler_sha, "python_version": sys.version,
               "fixtures": {}}
    with tempfile.TemporaryDirectory(prefix="evidence-graph-fixtures-") as scratch:
        temporary = Path(scratch)
        for name, expected_verified in VERIFIED.items():
            fixture = FIXTURES / name / "fixture.json"
            project = temporary / name
            receipt = output / name
            setup = output / "materialization"
            setup.mkdir(exist_ok=True)
            command = [sys.executable, str(MATERIALIZER), "--fixture", str(fixture),
                       "--repositories", str(args.repositories.resolve()), "--destination", str(project)]
            for override in args.repo:
                command.extend(("--repo", override))
            run(command, setup, name, (0,))
            commands = compile_project(project, receipt, {
                "build": (0,), "validate": (1,), "coverage": (0,), "stale": (0,),
            })
            graph = read_json(receipt / REPORTS[0])
            check(not graph["diagnostics"], f"{name} has diagnostics: {graph['diagnostics']}")
            check(not read_json(receipt / REPORTS[2])["items"], f"{name} has dangling links")
            check(not read_json(receipt / REPORTS[3])["items"], f"{name} has stale pinned inputs")
            verified = {node["id"] for node in graph["nodes"] if node["evidence_status"] == "VERIFIED"}
            unknown = {node["id"] for node in graph["nodes"] if node.get("evidence_state") == "UNKNOWN"}
            check(verified == expected_verified,
                  f"{name} verified evidence differs from the scoped expectation: {sorted(verified)}")
            check(unknown and not unknown & verified, f"{name} hid or promoted its UNKNOWN statements")
            summary["fixtures"][name] = {
                "commands": commands, "fixture_sha256": sha256(fixture),
                "source_manifest_sha256": sha256(project / "fixture-sources.json"),
                "report_sha256": {file: sha256(receipt / file) for file in REPORTS},
                "nodes": len(graph["nodes"]), "links": len(graph["links"]),
                "verified_evidence": sorted(verified), "unknown": sorted(unknown),
                "coverage": read_json(receipt / REPORTS[1])["summary"],
            }
        summary["negative_controls"] = adversarial_checks(
            temporary / "outbox", output / "outbox", temporary, output / "negative-controls",
        )
    check(sha256(COMPILER) == summary["compiler_sha256"], "Compiler changed during fixture checks")
    (output / "fixture-validation.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "FIXTURE_CHECKS_PASS",
        "output": str(output),
        "fixtures": list(summary["fixtures"]),
        "detected_negative_controls": list(summary["negative_controls"]),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"FIXTURE_CHECKS_FAILED: {error}", file=sys.stderr)
        sys.exit(1)
