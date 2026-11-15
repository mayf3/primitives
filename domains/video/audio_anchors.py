"""Check declared speech-to-screen relationships; source listening remains a review task."""
from __future__ import annotations

import re


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def check_counts(event, turn, fail):
    if "coverage" not in event and "shown" not in event:
        return
    total, shown = turn.get("total"), event.get("shown")
    if type(total) is not int or type(shown) is not int or not 0 < shown <= total:
        fail("shown needs a positive count within the turn's announced total")
        return
    coverage = event.get("coverage")
    if coverage == "all" and shown == total:
        return
    if coverage == "part" and shown < total and nonempty(event.get("label")):
        return
    fail("coverage: show all announced items or label this smaller part")


def check_text_holds(presentation, number, fail):
    """Only declared reading tasks need continuous exposure of their text."""
    alignment = presentation.get("audio_alignment")
    by_id = {}
    if isinstance(alignment, dict) and alignment.get("status") in ("planned", "anchored"):
        events = alignment.get("text_events")
        for i, event in enumerate(events if isinstance(events, list) else []):
            if not isinstance(event, dict) or "id" not in event:
                continue
            key = event["id"]
            if not nonempty(key) or key in by_id:
                fail(f"audio_alignment.text_events[{i}]: expected a unique nonempty text ID")
                continue
            by_id[key] = event

    holds = presentation.get("holds")
    for i, hold in enumerate(holds if isinstance(holds, list) else []):
        if not isinstance(hold, dict) or "required_text_events" not in hold:
            continue
        field = f"presentation.holds[{i}].required_text_events"
        keys = hold["required_text_events"]
        if (not isinstance(keys, list) or not keys or not all(nonempty(k) for k in keys)
                or len(set(keys)) != len(keys)):
            fail(f"{field}: expected a nonempty list of distinct text IDs")
            continue
        for key in keys:
            if key not in by_id:
                fail(f"{field}: unknown text event {key!r}")
                continue
            event = by_id[key]
            # Invalid interval values have their own diagnostics in check_audio/check_record.
            appear, exit_at = event.get("start"), event.get("end")
            start, end = hold.get("start"), hold.get("end")
            if all(number(t) for t in (appear, exit_at, start, end)) and not appear <= start < end <= exit_at:
                fail(f"{field}: text event {key!r} does not cover the entire hold")


def check_audio(record, interval, number, fail):
    """interval() validates a plan-local interval and reports its own diagnostic."""
    presentation = record["presentation"]
    check_text_holds(presentation, number, fail)
    if "audio_alignment" not in presentation:
        version = record.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"0\.[1-3]\.(0|[1-9][0-9]*)", version):
            fail("presentation.audio_alignment: declare its status or identify a pre-0.4 plan")
        return
    alignment = presentation["audio_alignment"]
    if not isinstance(alignment, dict):
        fail("presentation.audio_alignment: expected an object")
        return
    status = alignment.get("status")
    if status in ("pending", "not-applicable"):
        if not nonempty(alignment.get("reason")):
            fail("audio_alignment: pending/not-applicable needs a reason")
        if any(alignment.get(key, []) != [] for key in ("turns", "text_events")):
            fail("audio_alignment: pending/not-applicable expects no attributed events")
        return
    if status not in ("planned", "anchored"):
        fail("audio_alignment.status: expected pending, not-applicable, planned or anchored")
        return

    source = record["source"]
    if status == "anchored" and (record.get("example_type") != "application"
            or source.get("media_accessed") is not True
            or source.get("source_status") not in ("media-inspected", "source-checked")
            or not source.get("checks")):
        fail("audio_alignment: anchored requires an application with inspected media and source checks")
    turns = alignment.get("turns")
    events = alignment.get("text_events")
    if not isinstance(turns, list) or not turns or not isinstance(events, list):
        fail("audio_alignment: planned/anchored needs nonempty turns and a text_events array")
        return
    by_id = {}
    for i, turn in enumerate(turns):
        field = f"audio_alignment.turns[{i}]"
        if not interval(turn, field):
            continue
        key = turn.get("id")
        if not nonempty(key) or key in by_id:
            fail(f"{field}: expected a unique nonempty turn ID")
            continue
        cue = turn.get("cue", turn["start"])
        if not number(cue) or not turn["start"] <= cue < turn["end"]:
            fail(f"{field}: phrase cue must lie within the turn")
            continue
        by_id[key] = turn
        if not all(nonempty(turn.get(k)) for k in ("speaker", "text", "intent")):
            fail(f"{field}: expected speaker, text and intent")
        if status == "anchored" and not nonempty(turn.get("locator")):
            fail(f"{field}: anchored turn needs a locator in the inspected source")
        if record.get("example_type") == "synthetic" and "locator" in turn:
            fail(f"{field}: a synthetic turn cannot claim a source locator")
        if "total" in turn and (type(turn["total"]) is not int or turn["total"] <= 0):
            fail(f"{field}: announced total must be a positive integer")

    for i, event in enumerate(events):
        field = f"audio_alignment.text_events[{i}]"
        if not interval(event, field):
            continue
        key = event.get("turn")
        if not nonempty(key) or key not in by_id:
            fail(f"{field}: unknown turn")
            continue
        turn = by_id[key]
        cue = turn.get("cue", turn["start"])
        role, text = event.get("role"), event.get("text")
        if not nonempty(text) or role not in ("quote", "paraphrase", "preview", "recap", "example"):
            fail(f"{field}: expected display text and a known role")
            continue
        wording = event.get("wording")
        if "wording" in event:
            if wording not in ("verbatim", "paraphrase"):
                fail(f"{field}: wording must be verbatim or paraphrase")
            elif (role == "example" or (role == "quote" and wording != "verbatim")
                    or (role == "paraphrase" and wording != "paraphrase")):
                fail(f"{field}: wording conflicts with role {role!r}")
        if role == "quote" or (role in ("preview", "recap") and wording == "verbatim"):
            if not nonempty(turn.get("text")) or text not in turn["text"]:
                fail(f"{field}: text must occur verbatim in the attributed turn")
        origin = event.get("origin")
        if role == "example" or "origin" in event:
            if origin not in ("method-example", "editorial"):
                fail(f"{field}: identify example origin as method-example or editorial")
            if origin == "method-example" and record.get("example_type") == "application":
                fail(f"{field}: material marked method-example cannot be application copy")
        if role in ("quote", "paraphrase"):
            if event["start"] < cue or event["end"] > turn["end"]:
                fail(f"{field}: current speech text precedes its cue or extends beyond its turn")
            if not nonempty(event.get("intent")) or event["intent"] != turn.get("intent"):
                fail(f"{field}: current speech and display intents differ or are missing")
        else:
            if not nonempty(event.get("label")):
                fail(f"{field}: preview, recap and editorial examples need a visible label")
            if role == "preview" and event["end"] > cue:
                fail(f"{field}: preview must finish by its referenced cue")
            if role == "recap" and event["start"] < turn["end"]:
                fail(f"{field}: recap must begin after its referenced turn finishes")
        check_counts(event, turn, lambda message: fail(f"{field}: {message}"))
