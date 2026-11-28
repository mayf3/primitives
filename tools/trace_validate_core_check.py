#!/usr/bin/env python3
"""Run the first Batch 2 checks on a fresh isolated Core ledger capture."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from core_recovery_trace import load_core_traces
from trace_validate import load_json, sha256, validate_trace


CONTRACT = Path(__file__).resolve().parents[1] / "docs/evidence-graph-fixtures/core/recovery-trace-contract.json"
NORMAL = "B2-503-restart-automatic-first-admission"
BEFORE = "B2-SIGKILL-before-wal"
AFTER = "B2-SIGKILL-after-wal"
ACK_LOST = "B2-accepted-ACK-lost-SIGKILL"
RACE = "B2-automatic-manual-real-process-race"
REFUSAL = "B2-world-drift-refusal-SIGKILL-read-only-duty-restarts"


def evaluate(graph, case):
    return validate_trace(graph, case["contract"], case["manifest"], case["normalized_bytes"], case["raw_bytes"])


def assert_status(result, expected, label):
    if result["status"] != expected:
        raise ValueError(f"{label}: expected {expected}, got {result['status']} {result['issues']}")


def encode_rows(rows):
    return b"".join(json.dumps(row, sort_keys=True).encode("utf-8") + b"\n" for row in rows)


def score_edited(graph, case, rows, raw=None):
    edited = deepcopy(case)
    edited["normalized_bytes"] = encode_rows(rows)
    edited["manifest"]["normalized_sha256"] = sha256(edited["normalized_bytes"])
    if raw is not None:
        edited["raw_bytes"] = raw
        edited["manifest"]["raw_sha256"] = sha256(raw)
    return evaluate(graph, edited)


def controls(graph, positive):
    rows = [load_json(line) for line in positive["normalized_bytes"].split(b"\n") if line]
    missing = score_edited(graph, positive, rows[:1] + rows[2:])
    truncated = b"".join(positive["raw_bytes"].splitlines(keepends=True)[:-1])
    tail = score_edited(graph, positive, rows[:-1], raw=truncated)
    opened = deepcopy(positive)
    opened["manifest"]["closed"] = False
    illegal_rows = deepcopy(rows)
    illegal_rows[-1]["to_observed"] = "settled"
    stale_model = deepcopy(rows)
    stale_model[-1]["model_revision"] = "0" * 40
    stale_attempt = deepcopy(rows)
    stale_attempt[-1]["identity"]["attemptId"] = "outdated-attempt-id"
    gap_rows = deepcopy(rows)
    gap_rows[-1]["seq"] += 1
    parent_rows = deepcopy(rows)
    parent_rows[-1]["causal_parent_ids"].append("missing-causal-parent")
    other_graph = deepcopy(graph)
    model_node = next(node for node in other_graph["nodes"] if node["id"] == "CORE.MODEL.EXECUTION-RECOVERY")
    model_node["resolved_coordinate"]["revision"] = "0" * 40
    result = {
        "removed-middle-row": (missing, "TRACE_INCOMPLETE"),
        "removed-tail-with-recomputed-hashes": (tail, "TRACE_INCOMPLETE"),
        "unsealed-capture": (evaluate(graph, opened), "TRACE_INCOMPLETE"),
        "sequence-gap": (score_edited(graph, positive, gap_rows), "TRACE_INCOMPLETE"),
        "missing-parent": (score_edited(graph, positive, parent_rows), "TRACE_INCOMPLETE"),
        "illegal-step": (score_edited(graph, positive, illegal_rows), "TRACE_DRIFTED"),
        "stale-attempt": (score_edited(graph, positive, stale_attempt), "TRACE_DRIFTED"),
        "stale-model": (score_edited(graph, positive, stale_model), "STALE"),
        "stale-graph-model": (evaluate(other_graph, positive), "STALE"),
    }
    for key, (report, expected) in result.items():
        assert_status(report, expected, key)
    return {key: report for key, (report, _) in result.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    graph_bytes = args.graph.read_bytes()
    graph = load_json(graph_bytes)
    cases = load_core_traces(args.graph, CONTRACT, args.capture)
    expected = {NORMAL: "TRACE_CONFORMANT", BEFORE: "TRACE_CONFORMANT",
                AFTER: "TRACE_CONFORMANT", ACK_LOST: "TRACE_CONFORMANT",
                RACE: "TRACE_CONFORMANT", REFUSAL: "UNKNOWN"}
    if len(cases) != len(expected) or {case["id"] for case in cases} != set(expected):
        raise ValueError("Fresh capture did not contain the expected pilot scenarios")
    segment_dir = args.output.with_suffix(".segments")
    segment_dir.mkdir(exist_ok=False)
    receipts = {}
    for case in cases:
        report = evaluate(graph, case)
        assert_status(report, expected[case["id"]], case["id"])
        receipts[case["id"]] = {"trace": report, "observations": case["observations"]}
        segment = segment_dir / case["id"]
        segment.mkdir()
        (segment / "native.jsonl").write_bytes(case["raw_bytes"])
        (segment / "normalized.jsonl").write_bytes(case["normalized_bytes"])
        (segment / "manifest.json").write_text(json.dumps(case["manifest"], indent=2) + "\n", encoding="utf-8")
        (segment / "contract.json").write_text(json.dumps(case["contract"], indent=2) + "\n", encoding="utf-8")
    positive = next(case for case in cases if case["id"] == NORMAL)
    historical = {}
    for case in load_core_traces(args.graph, CONTRACT):
        report = evaluate(graph, case)
        assert_status(report, "TRACE_INCOMPLETE", f"historical {case['id']}")
        historical[case["id"]] = report
    report = {
        "schema_version": "core-recovery-trace-check/v1",
        "graph_sha256": sha256(graph_bytes), "capture_sha256": sha256(args.capture.read_bytes()),
        "scenarios": receipts, "historical_unsealed": historical,
        "negative_controls": controls(graph, positive),
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f"CORE_TRACE_CHECK_FAILED: {error}")
