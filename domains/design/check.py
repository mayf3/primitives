#!/usr/bin/env python3
"""Check design use-record structure and state consistency, not user outcomes."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


MODULE_ROOT = Path(__file__).resolve().parent
ALLOWED_STATES = {
    "source_status": {"cited", "source-checked", "source-limited"},
    "implementation_status": {"proposed", "implemented", "regressed", "retired"},
    "user_validation_status": {"untested", "observed", "contradicted", "mixed"},
}
OBSERVATION_STATES = {"observed", "contradicted", "mixed"}


def read_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: cannot read JSON: {exc}")
        return None


def check_record(
    record: dict[str, Any],
    location: str,
    primitive_ids: set[str],
    synthetic: bool,
    errors: list[str],
) -> None:
    primitive_id = record.get("primitive_id")
    if not isinstance(primitive_id, str) or primitive_id not in primitive_ids:
        errors.append(
            f"{location}.primitive_id: expected an ID in this module's catalog; "
            f"got {primitive_id!r}"
        )

    for field, allowed in ALLOWED_STATES.items():
        value = record.get(field)
        if not isinstance(value, str) or value not in allowed:
            errors.append(
                f"{location}.{field}: expected one of {sorted(allowed)!r}; "
                f"got {value!r}"
            )

    validation_status = record.get("user_validation_status")
    observations = record.get("user_observations", [])
    if not isinstance(observations, list):
        errors.append(f"{location}.user_observations: expected an array")
        observations = []

    if synthetic and validation_status != "untested":
        errors.append(
            f"{location}.user_validation_status: a synthetic example must stay "
            "untested; simulated outcomes are not real user observations"
        )

    if (synthetic or validation_status == "untested") and observations:
        errors.append(
            f"{location}.user_observations: synthetic or untested records cannot "
            "contain claimed real user observations"
        )

    if isinstance(validation_status, str) and validation_status in OBSERVATION_STATES:
        if not observations:
            errors.append(
                f"{location}.user_observations: {validation_status!r} requires "
                "a nonempty array of actual observation records"
            )
        scope = record.get("validation_scope")
        if not isinstance(scope, str) or not scope.strip():
            errors.append(
                f"{location}.validation_scope: {validation_status!r} requires "
                "a nonempty text describing the task, target version and observation scope"
            )


def inspect_records(
    value: Any,
    location: str,
    primitive_ids: set[str],
    errors: list[str],
    inherited_synthetic: bool = False,
) -> int:
    """Find nested use records; synthetic containers also constrain their children."""
    count = 0
    if isinstance(value, dict):
        synthetic = inherited_synthetic or value.get("example_type") == "synthetic"
        if "primitive_id" in value or any(field in value for field in ALLOWED_STATES):
            check_record(value, location, primitive_ids, synthetic, errors)
            count += 1
        for key, child in value.items():
            count += inspect_records(
                child, f"{location}.{key}", primitive_ids, errors, synthetic
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            count += inspect_records(
                child,
                f"{location}[{index}]",
                primitive_ids,
                errors,
                inherited_synthetic,
            )
    return count


def main() -> int:
    errors: list[str] = []
    catalog_path = MODULE_ROOT / "catalog.json"
    catalog = read_json(catalog_path, errors)
    primitive_ids: set[str] = set()

    if not isinstance(catalog, dict) or not isinstance(catalog.get("entries"), list):
        errors.append(f"{catalog_path}: expected an object with an entries array")
    else:
        for index, entry in enumerate(catalog["entries"]):
            primitive_id = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(primitive_id, str) or not primitive_id.startswith("design."):
                errors.append(f"{catalog_path}: $.entries[{index}].id: invalid design ID")
            elif primitive_id in primitive_ids:
                errors.append(
                    f"{catalog_path}: $.entries[{index}].id: duplicate {primitive_id!r}"
                )
            else:
                primitive_ids.add(primitive_id)

    example_paths = sorted((MODULE_ROOT / "examples").rglob("*.json"))
    record_count = 0
    for path in example_paths:
        value = read_json(path, errors)
        file_count = inspect_records(value, f"{path}: $", primitive_ids, errors)
        if file_count == 0:
            errors.append(f"{path}: expected at least one design use record")
        record_count += file_count

    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1

    print(
        f"PASS design: {record_count} use records in {len(example_paths)} JSON files; "
        "structure and state consistency only, not verification of user outcomes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
