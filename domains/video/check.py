#!/usr/bin/env python3
"""Validate video plans and evidence boundaries; never infer viewer outcomes."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from runpy import run_path
import sys

MODULE_ROOT = Path(__file__).resolve().parent
# The repository checker and standalone tests also load this file by path.
check_audio = run_path(str(MODULE_ROOT / "audio_anchors.py"))["check_audio"]


def number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def evidence_records(value):
    """A checklist or a success flag is not a traceable review record."""
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, dict)
        and isinstance(item.get("locator"), str) and item["locator"].strip()
        and isinstance(item.get("scope"), str) and item["scope"].strip()
        for item in value
    )


def check_record(record, known_ids, location="record", *, notices=None):
    errors = []

    def fail(message):
        errors.append(f"{location}: {message}")

    if not isinstance(record, dict):
        return [f"{location}: expected a video plan object"]
    for field in ("source", "semantic", "presentation", "render", "validation"):
        if not isinstance(record.get(field), dict):
            fail(f"{field}: expected an object")
    if errors:
        return errors
    if not isinstance(record.get("id"), str) or not record["id"].startswith("video.example."):
        fail("id: expected a video.example.* identifier")
    if record.get("example_type") not in {"synthetic", "application"}:
        fail("example_type: expected synthetic or application")
    if type(record.get("selected")) is not bool:
        fail("selected: expected a boolean; selection does not imply implementation")
    synthetic = record.get("example_type") == "synthetic"
    source, semantic, presentation, render, validation = (
        record[name] for name in ("source", "semantic", "presentation", "render", "validation")
    )

    # Source positions belong to inspected material, never to a planned timeline.
    status = source.get("source_status")
    if status not in {"report-only", "media-inspected", "source-checked"}:
        fail("source.source_status: unknown source state")
    if type(source.get("media_accessed")) is not bool:
        fail("source.media_accessed: expected a boolean")
    if status in {"media-inspected", "source-checked"} and not evidence_records(source.get("checks")):
        fail("source.checks: inspected or checked claims need locator and scope records")
    if status == "media-inspected" and source.get("media_accessed") is not True:
        fail("source.media_accessed: media-inspected requires access to the media")
    source_range = source.get("source_range_seconds")
    if source_range is not None:
        if not (isinstance(source_range, list) and len(source_range) == 2
                and all(number(t) for t in source_range) and 0 <= source_range[0] < source_range[1]):
            fail("source.source_range_seconds: expected null or [start, end] in seconds")
        if source.get("media_accessed") is not True or not evidence_records(source.get("checks")):
            fail("source.source_range_seconds: a verified range requires inspected media and source checks")
    anchor = source.get("transcript_anchor")
    if anchor is not None and (not isinstance(anchor, str) or not anchor.strip()
                               or not evidence_records(source.get("checks"))):
        fail("source.transcript_anchor: an anchor requires traceable source checks")
    if not isinstance(source.get("evidence_assets"), list):
        fail("source.evidence_assets: expected an array, empty when unavailable")
    if synthetic and (status != "report-only" or source.get("media_accessed") is not False
                      or source_range is not None or anchor is not None or source.get("checks")):
        fail("source: a synthetic proposal cannot claim inspected media or verified source anchors")

    # Retain explicit entity identities and directed relation meanings.
    objects = semantic.get("objects")
    object_ids = []
    if not isinstance(objects, list) or not objects:
        fail("semantic.objects: expected a nonempty array")
    else:
        for item in objects:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                fail("semantic.objects: each object needs an ID")
            else:
                object_ids.append(item["id"])
    if len(object_ids) != len(set(object_ids)):
        fail("semantic.objects: duplicate identity; copies need distinct IDs")
    relations = semantic.get("relations")
    if not isinstance(relations, list):
        fail("semantic.relations: expected an array")
    else:
        for relation in relations:
            if not isinstance(relation, dict):
                fail("semantic.relations: expected relation objects")
                continue
            if relation.get("from") not in object_ids or relation.get("to") not in object_ids:
                fail("semantic.relations: unknown object endpoint")
            if not relation.get("type") or not relation.get("label"):
                fail("semantic.relations: an arrow needs a type and a meaning")
    for field in ("understanding_goal", "feeling_goal"):
        if not isinstance(semantic.get(field), str) or not semantic[field].strip():
            fail(f"semantic.{field}: expected an independent goal")

    primitives = presentation.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        fail("presentation.primitives: expected selected method IDs")
        primitives = []
    for primitive in primitives:
        if not isinstance(primitive, str) or primitive not in known_ids:
            fail(f"presentation.primitives: unknown primitive {primitive!r}")
    duration = presentation.get("planned_duration_seconds")
    valid_duration = number(duration) and duration > 0
    if not valid_duration:
        fail("presentation.planned_duration_seconds: expected a positive finite duration")

    def interval(item, label):
        if not isinstance(item, dict):
            fail(f"{label}: expected an interval object")
            return False
        start, end = item.get("start"), item.get("end")
        valid = (valid_duration and number(start) and number(end)
                 and 0 <= start < end <= duration)
        if not valid:
            fail(f"{label}: interval must fit planned_duration_seconds")
        return valid

    # Overlapping events can share a clock, but not an individual display lane.
    separate_axis = "event_axis_unit" in presentation
    axis_unit = presentation.get("event_axis_unit")
    if separate_axis and (not isinstance(axis_unit, str) or not axis_unit.strip()):
        fail("presentation.event_axis_unit: expected a nonempty unit for the depicted intervals")
    layout = presentation.get("event_layout")
    if "event_layout" in presentation and layout not in ("lanes", "table", "aggregate"):
        fail("presentation.event_layout: expected lanes, table or aggregate")
    readout = semantic.get("event_readout")
    if "event_readout" in semantic and readout not in ("individual", "aggregate"):
        fail("semantic.event_readout: expected individual or aggregate")
    if layout == "aggregate" and readout == "individual":
        fail("presentation.event_layout: aggregate cannot show individual event endpoints; choose lanes or table")
    elif layout == "aggregate" and notices is not None:
        notices.append(f"{location}: aggregate 只呈现汇总量；从末帧恢复单个事件起止须用 lanes 或 table。")
    events = presentation.get("event_schedule", [])
    if not isinstance(events, list):
        fail("presentation.event_schedule: expected an array")
    else:
        event_ids = set()
        lanes = {}
        spans = []
        for event in events:
            valid_screen_interval = interval(event, "presentation.event_schedule")
            if not isinstance(event, dict):
                continue
            event_id = event.get("id")
            span = None
            if separate_axis:
                start, end = event.get("axis_start"), event.get("axis_end")
                if number(start) and number(end) and start < end:
                    span = (start, end)
                else:
                    fail(f"presentation.event_schedule: event {event_id!r} needs finite axis_start < axis_end")
            elif "axis_start" in event or "axis_end" in event:
                fail(f"presentation.event_schedule: event {event_id!r} needs event_axis_unit for axis endpoints")
            elif valid_screen_interval:
                span = (event["start"], event["end"])
            if span is not None:
                spans.append(span)
            if not isinstance(event_id, str) or not event_id.strip() or event_id in event_ids:
                fail("presentation.event_schedule: each event needs a unique nonempty ID")
            else:
                event_ids.add(event_id)
            if event.get("target") not in object_ids:
                fail("presentation.event_schedule: unknown event target")
            if layout == "lanes":
                lane = event.get("lane_id")
                if not isinstance(lane, str) or not lane.strip():
                    fail(f"presentation.event_schedule: event {event_id!r} needs a nonempty lane_id")
                elif span is not None and isinstance(event_id, str):
                    lanes.setdefault(lane.strip(), []).append((*span, event_id))

        for lane, intervals in lanes.items():
            last_end = -math.inf
            last_event = None
            for start, end, event_id in sorted(intervals):
                if start < last_end:
                    fail(f"presentation.event_schedule: events {last_event!r} and {event_id!r} overlap in lane {lane!r}")
                if end > last_end:
                    last_end, last_event = end, event_id

        spans.sort()
        if any(second[0] < first[1] for first, second in zip(spans, spans[1:])):
            version = record.get("version")
            legacy = (isinstance(version, str) and re.fullmatch(r"0\.3\.(0|[1-9][0-9]*)", version)
                      and "event_readout" not in semantic and not separate_axis)
            if legacy:
                if notices is not None:
                    notices.append(f"{location}: 兼容 {version} 并发排程。迁移时按观看任务填写 semantic.event_readout "
                                   "与 presentation.event_layout，再将 version 更新为 0.4.0。")
            else:
                if "event_layout" not in presentation:
                    fail("presentation.event_layout: overlapping events require lanes, table or aggregate")
                if "event_readout" not in semantic:
                    fail("semantic.event_readout: overlapping events require individual or aggregate")

    focus = presentation.get("focus_schedule")
    previous_end = 0
    if not isinstance(focus, list) or not focus:
        fail("presentation.focus_schedule: expected a nonempty array")
    else:
        for item in focus:
            if interval(item, "presentation.focus_schedule"):
                if item["start"] < previous_end:
                    fail("presentation.focus_schedule: competing primary focus intervals")
                previous_end = item["end"]
            if isinstance(item, dict) and item.get("target") not in object_ids:
                fail("presentation.focus_schedule: unknown focus target")
    holds = presentation.get("holds")
    if not isinstance(holds, list):
        fail("presentation.holds: expected an array")
    else:
        if "video.hold" in primitives and not holds:
            fail("presentation.holds: video.hold needs an explicit hold interval")
        for item in holds:
            interval(item, "presentation.holds")
            if isinstance(item, dict):
                visible = item.get("visible")
                if not isinstance(visible, list) or not visible or any(x not in object_ids for x in visible):
                    fail("presentation.holds: unknown or empty visible objects")

    check_audio(record, interval, number, fail)

    if render.get("status") not in {"proposed", "implemented", "regressed", "retired"}:
        fail("render.status: unknown implementation state")
    if type(render.get("implemented")) is not bool:
        fail("render.implemented: expected a boolean")
    if render.get("status") == "implemented" and render.get("implemented") is not True:
        fail("render: implemented status conflicts with implemented flag")
    if render.get("implemented") is True and not evidence_records(render.get("artifacts")):
        fail("render.artifacts: implementation requires traceable artifacts")
    if synthetic and (render.get("status") != "proposed" or render.get("implemented") is not False
                      or render.get("artifacts")):
        fail("render: a synthetic proposal cannot claim implementation")

    for axis, states, success in (
        ("factual", {"pending", "checked", "failed"}, "checked"),
        ("accessibility", {"pending", "passed", "failed"}, "passed"),
    ):
        check = validation.get(axis)
        if not isinstance(check, dict) or check.get("status") not in states:
            fail(f"validation.{axis}: invalid review state")
            continue
        if check["status"] != "pending" and not evidence_records(check.get("records")):
            fail(f"validation.{axis}.records: review results need locator and scope records")
        if synthetic and (check["status"] != "pending" or check.get("records")):
            fail(f"validation.{axis}: synthetic plans retain pending review, not claimed results")
        if axis == "factual" and check["status"] == success and "video.evidence-ground" in primitives:
            if not evidence_records(source.get("evidence_assets")):
                fail("video.evidence-ground: checked factual claims require evidence assets")

    viewer = validation.get("viewer")
    if not isinstance(viewer, dict) or viewer.get("status") not in {"untested", "observed", "mixed", "contradicted"}:
        fail("validation.viewer: invalid viewer state")
    else:
        observations = viewer.get("observations")
        if not isinstance(observations, list):
            fail("validation.viewer.observations: expected an array")
        if (synthetic or viewer["status"] == "untested") and observations:
            fail("validation.viewer: synthetic or untested plans cannot contain actual observations")
        if synthetic and viewer["status"] != "untested":
            fail("validation.viewer: a synthetic plan must remain untested")
        if viewer["status"] != "untested" and not evidence_records(observations):
            fail("validation.viewer.observations: actual results need locator and scope records")
        for field in ("understanding_tasks", "feeling_questions"):
            if not isinstance(viewer.get(field), list) or not viewer[field]:
                fail(f"validation.viewer.{field}: keep understanding and feelings separately testable")
    return errors


def main():
    errors = []
    notices = []
    paths = sorted((MODULE_ROOT / "examples").glob("*.json"))
    try:
        catalog = json.loads((MODULE_ROOT / "catalog.json").read_text(encoding="utf-8"))
        entries = catalog["entries"]
        known_ids = {entry["id"] for entry in entries}
        action_ids = {entry["id"] for entry in entries if entry["kind"] == "action"}
        for entry in entries:
            if entry["kind"] == "composite":
                components = entry.get("components")
                if not isinstance(components, list) or not components or not all(
                    isinstance(part, str) and part in action_ids for part in components
                ):
                    errors.append(f"{entry['id']}: expand components into known action IDs")
        if not paths:
            errors.append("video: no example plans found")
        seen = set()
        for path in paths:
            record = json.loads(path.read_text(encoding="utf-8"))
            errors.extend(check_record(record, known_ids, str(path.relative_to(MODULE_ROOT)), notices=notices))
            identifier = record.get("id") if isinstance(record, dict) else None
            if isinstance(identifier, str):
                if identifier in seen:
                    errors.append(f"{path.name}: duplicate example ID")
                seen.add(identifier)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"video: cannot read catalog/examples: {exc}")
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    for notice in notices:
        print(f"NOTE {notice}")
    print(f"PASS video: {len(paths)} plans; IDs, timing and evidence-state consistency only, not viewer validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
