#!/usr/bin/env python3
"""Materialize declared, immutable fixture inputs without changing source repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


REVISION = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
DESCRIPTOR_SCHEMA = "evidence-receipt/v1"
SOURCES_SCHEMA = "evidence-sources/v1"
OUTPUT_NAMES = {
    "fixture.evidence.json",
    "fixture-sources.json",
    "evidence-graph.json",
    "coverage-report.json",
    "dangling-links.json",
    "stale-evidence.json",
    ".evidence-graph",
    ".git",
}


def relative_path(value, label):
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError(f"{label} must be a nonempty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{label} must be a normalized relative path: {value!r}")
    return path


def exact_revision(value, label):
    if not isinstance(value, str) or REVISION.fullmatch(value) is None:
        raise ValueError(f"{label} must be an exact 40-hex Git commit")
    return value


def git(repo, *args):
    env = {
        **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    command = ["git", "--no-replace-objects", "-C", str(repo), *args]
    result = subprocess.run(command, capture_output=True, env=env, timeout=20)
    if result.returncode:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"cannot read Git object in {repo}: {error}")
    return result.stdout


def git_file(repo, revision, path):
    if git(repo, "cat-file", "-t", revision).strip() != b"commit":
        raise ValueError(f"{repo}: {revision} is not a commit")
    tree_line = git(repo, "ls-tree", "-z", revision, "--", path.as_posix())
    records = tree_line.split(b"\0")[:-1]
    if len(records) != 1:
        raise ValueError(f"{repo}: {revision}:{path} is missing or ambiguous")
    header, separator, name = records[0].partition(b"\t")
    mode, kind, _ = header.split()
    if not separator or name != path.as_posix().encode("utf-8") or kind != b"blob" or mode not in {
        b"100644",
        b"100755",
    }:
        raise ValueError(f"{repo}: {revision}:{path} is not a regular Git file")
    return git(repo, "show", f"{revision}:{path.as_posix()}")


def local_file(root, path):
    checked = root
    for part in path.parts:
        checked /= part
        if checked.is_symlink():
            raise ValueError(f"local fixture file cannot use a symlink: {path}")
    if not checked.is_file():
        raise ValueError(f"local fixture file is missing or not regular: {path}")
    return checked.read_bytes()


def check_destination(destination):
    if destination.is_symlink() or (
        destination.exists() and (not destination.is_dir() or any(destination.iterdir()))
    ):
        raise ValueError(f"destination must be a nonexistent or empty directory: {destination}")


def store_copy(stage, target, data, source, index):
    if any(part in OUTPUT_NAMES for part in target.parts):
        raise ValueError(f"target collides with generated or repository files: {target}")
    name = target.as_posix()
    if name in index:
        raise ValueError(f"duplicate fixture target: {target}")
    path = stage.joinpath(*target.parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    index[name] = {**source, "sha256": hashlib.sha256(data).hexdigest()}


def node_revisions(descriptor, target):
    revisions = set()
    for node in descriptor.get("nodes", []):
        coordinate = node.get("coordinate") if isinstance(node, dict) else None
        if isinstance(coordinate, dict) and coordinate.get("path") == target:
            revision = coordinate.get("revision")
            if revision is not None:
                revisions.add(exact_revision(revision, "fixture node revision"))
    if len(revisions) > 1:
        raise ValueError(f"local receipt {target} declares different source revisions")
    return next(iter(revisions), None)


def materialize(fixture, repositories, destination, overrides):
    descriptor = json.loads(fixture.read_bytes())
    if not isinstance(descriptor, dict) or descriptor.get("schema_version") != DESCRIPTOR_SCHEMA:
        raise ValueError(f"fixture must declare {DESCRIPTOR_SCHEMA}")
    materials = descriptor.pop("materials", [])
    local = descriptor.pop("files", [])
    if not isinstance(materials, list) or not isinstance(local, list):
        raise ValueError("fixture materials and files must be arrays")
    if not isinstance(descriptor.get("nodes", []), list):
        raise ValueError("fixture nodes must be an array")
    check_destination(destination)

    index = {}
    with tempfile.TemporaryDirectory(prefix=".evidence-fixture-", dir=destination.parent) as temp:
        stage = Path(temp) / "project"
        stage.mkdir()
        for item in materials:
            if not isinstance(item, dict):
                raise ValueError("each imported material must be an object")
            repository = item.get("repo")
            if not isinstance(repository, str) or REPOSITORY.fullmatch(repository) is None:
                raise ValueError(f"invalid material repository name: {repository!r}")
            revision = exact_revision(item.get("revision"), "material revision")
            source = relative_path(item.get("path"), "material source")
            target = relative_path(item.get("target"), "material target")
            repo = overrides.get(repository, repositories / repository)
            payload = git_file(repo, revision, source)
            store_copy(stage, target, payload, {
                "repo": repository,
                "path": source.as_posix(),
                "revision": revision,
            }, index)

        for entry in local:
            item = {"path": entry, "target": entry} if isinstance(entry, str) else entry
            if not isinstance(item, dict):
                raise ValueError("each local fixture file must be a path or object")
            source = relative_path(item.get("path"), "local fixture source")
            target = relative_path(item.get("target", source.as_posix()), "local fixture target")
            revision = node_revisions(descriptor, target.as_posix())
            if item.get("revision") is not None:
                declared = exact_revision(item["revision"], "local fixture revision")
                if revision is not None and revision != declared:
                    raise ValueError(f"local fixture revision disagrees with its nodes: {target}")
                revision = declared
            payload = local_file(fixture.parent, source)
            store_copy(stage, target, payload, {
                "repo": "fixture",
                "path": source.as_posix(),
                "revision": revision,
            }, index)

        (stage / "fixture.evidence.json").write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (stage / "fixture-sources.json").write_text(
            json.dumps({"schema_version": SOURCES_SCHEMA, "files": index},
                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        check_destination(destination)
        stage.rename(destination)
    return len(index)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--repositories", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--repo", action="append", default=[], metavar="NAME=PATH")
    args = parser.parse_args(argv)
    try:
        overrides = {}
        for value in args.repo:
            name, separator, path = value.partition("=")
            if not separator or REPOSITORY.fullmatch(name) is None or not path or name in overrides:
                raise ValueError(f"invalid or duplicate repository override: {value!r}")
            overrides[name] = Path(path).expanduser().resolve(strict=True)
        fixture = args.fixture.expanduser().resolve(strict=True)
        repositories = args.repositories.expanduser().resolve(strict=True)
        requested = args.destination.expanduser()
        if requested.name in {"", ".", ".."}:
            raise ValueError("destination must name a separate output directory")
        destination = requested.parent.resolve(strict=True) / requested.name
        count = materialize(fixture, repositories, destination, overrides)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps({"destination": str(destination), "files": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
