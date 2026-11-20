#!/usr/bin/env python3
"""Bind the current synthetic four-window JSON example to the Video proofs.

The adapter parses data; it does not prove that the parser, JSON fields, source
media, renderer, or audience observations are correct. Only checked integers
are emitted into a temporary Lean module, which is then kernel checked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXAMPLE = ROOT / "domains/video/examples/concurrent-replies.json"
WRITERS = ("write-01", "write-02", "write-03", "write-04")
READERS = ("read-initial",)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def integer(value, label, *, natural=False):
    if type(value) is not int:
        raise ValueError(f"{label}: this exact-tick model requires a JSON integer")
    if natural and value < 0:
        raise ValueError(f"{label}: expected a nonnegative count")
    return value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def lean_input(record):
    require(record["id"] == "video.example.concurrent-replies", "wrong example ID")
    require(record["example_type"] == "synthetic", "this proof binding is for a synthetic example")
    source = record["source"]
    require(source["source_status"] == "report-only", "do not relabel this proof as source verification")
    require(source["media_accessed"] is False and source["source_range_seconds"] is None,
            "source media/time claims require a separate model binding")
    presentation = record["presentation"]
    require(not presentation.get("event_axis_unit"), "separate diagram axes need an explicit adapter")
    require(presentation["event_layout"] == "lanes", "reference example uses named lanes")
    require(record["semantic"]["event_readout"] == "individual", "reference example reads individual events")
    require("video.temporal-relations" in presentation["primitives"], "temporal primitive is missing")
    events = presentation["event_schedule"]
    require(isinstance(events, list), "event_schedule must be a list")
    indexed = {}
    for event in events:
        event_id = event["id"]
        require(event_id not in indexed, f"duplicate event ID: {event_id!r}")
        require("axis_start" not in event and "axis_end" not in event,
                "axis times must not be silently replaced by presentation times")
        indexed[event_id] = event
    require(set(indexed) == set(WRITERS + READERS), "expected exactly four writers and one reader")
    for number, event_id in enumerate(WRITERS, start=1):
        target = f"window-{number:02d}"
        require(indexed[event_id]["target"] == target and indexed[event_id]["lane_id"] == target,
                f"{event_id}: identity/lane binding changed")
    require(indexed["read-initial"]["target"] == "reader" and
            indexed["read-initial"]["lane_id"] == "reader", "reader identity/lane binding changed")

    def intervals(ids):
        values = []
        for event_id in ids:
            event = indexed[event_id]
            start = integer(event["start"], f"{event_id}.start")
            finish = integer(event["end"], f"{event_id}.end")
            values.append(f"⟨({start} : Int), ({finish} : Int)⟩")
        return "[" + ", ".join(values) + "]"

    window = record["semantic"]["observation_window"]
    require(window["counting_rule"] == "统计完成时刻 t 满足 start < t ≤ end 的事件",
            "completion-window convention changed; update the model explicitly")
    require(window["unit"] == "段", "work-unit convention changed")
    lo = integer(window["start"], "observation_window.start")
    hi = integer(window["end"], "observation_window.end")
    initial, produced, consumed, final = (
        integer(window[field], f"observation_window.{field}", natural=True)
        for field in ("initial_unfinished", "produced", "read", "final_unfinished")
    )
    planned = integer(presentation["planned_duration_seconds"], "planned_duration_seconds")
    return f'''import Video

namespace Video.ExampleCheck

open Video.Temporal

def parsedWriters : List (Interval .schematic) := {intervals(WRITERS)}
def parsedReaders : List (Interval .schematic) := {intervals(READERS)}

theorem writers_match_reference : parsedWriters = fourWriters := by decide
theorem readers_match_reference : parsedReaders = firstReader := by decide

theorem window_matches_reference :
    ({lo} : Int) = 2 ∧ ({hi} : Int) = 8 ∧ ({initial} : Nat) = 1 := by decide

theorem parsed_common_interval (t : Int) :
    (∀ i ∈ parsedWriters, contains i t) ↔ (4 ≤ t ∧ t < 5) := by
  rw [writers_match_reference]
  exact four_writers_common_interval t

theorem parsed_completion_counts :
    completedCount ({lo} : Int) ({hi} : Int) parsedWriters = {produced} ∧
    completedCount ({lo} : Int) ({hi} : Int) parsedReaders = {consumed} := by decide

theorem parsed_budget : ({consumed} : Nat) ≤ {initial} + {produced} := by decide

theorem parsed_balance :
    remaining {initial} {produced} {consumed} + {consumed} = {initial} + {produced} :=
  queue_balance {initial} {produced} {consumed} parsed_budget

theorem parsed_final_remaining :
    remaining {initial} (completedCount ({lo} : Int) ({hi} : Int) parsedWriters)
      (completedCount ({lo} : Int) ({hi} : Int) parsedReaders) = {final} := by decide

theorem parsed_intervals_fit :
    ∀ i ∈ parsedWriters ++ parsedReaders, valid i ∧ 0 ≤ i.start ∧ i.finish ≤ {planned} := by
  simp [parsedWriters, parsedReaders, valid] <;> omega

end Video.ExampleCheck
'''


def run(args):
    record = json.loads(args.example.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    code = lean_input(record)
    # Rebuild the imported module so a standalone invocation cannot silently
    # use a previous Video.olean after the proof source has changed.
    build = subprocess.run([args.lake, "build", "Video"], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
    if build.returncode:
        sys.stderr.write(build.stdout + build.stderr)
        return build.returncode
    scratch = ROOT / ".lake/verification"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="video-example-", dir=scratch) as temporary:
        generated = Path(temporary) / "VideoExample.lean"
        generated.write_text(code, encoding="utf-8")
        checked = subprocess.run([args.lake, "env", "lean", "-DwarningAsError=true", str(generated)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60)
        if checked.returncode:
            sys.stderr.write(checked.stdout + checked.stderr)
            return checked.returncode
    print("PASS video example: current JSON checked by Lean; five named synthetic events, "
          "common interval [4,5), counts 4/1, remaining 4. No source-media or viewer claim.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", default="lake", help="Lake executable from the pinned Lean toolchain")
    parser.add_argument("--example", type=Path, default=DEFAULT_EXAMPLE,
                        help="JSON input; override only for an explicit conformance/negative check")
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL video example: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
