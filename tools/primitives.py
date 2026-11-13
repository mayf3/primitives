#!/usr/bin/env python3
"""Offline discovery and structural validation for the primitives repository."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def anchors(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    found = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', text))
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        number = counts.get(slug, 0)
        counts[slug] = number + 1
        found.add(slug if number == 0 else f"{slug}-{number}")
    return found


def check_ref(base: Path, reference: str, boundary: Path, errors: list[str], label: str,
              allow_directory: bool = False):
    if not isinstance(reference, str) or not reference:
        errors.append(f"{label}: missing file reference")
        return None
    raw, anchor = urldefrag(reference)
    if urlparse(raw).scheme or raw.startswith("//"):
        errors.append(f"{label}: expected a local file: {reference}")
        return None
    target = (base / unquote(raw)).resolve()
    if not inside(target, boundary):
        errors.append(f"{label}: reference leaves allowed directory: {reference}")
        return None
    if not target.exists():
        errors.append(f"{label}: missing target: {reference}")
        return None
    if not target.is_file() and not (allow_directory and target.is_dir()):
        errors.append(f"{label}: expected a file: {reference}")
        return None
    if anchor and target.is_file() and unquote(anchor) not in anchors(target):
        errors.append(f"{label}: missing anchor: {reference}")
    return target


def load_index(root: Path):
    registry = read_json(root / "registry.json")
    modules = []
    entries = []
    for module in registry["modules"]:
        directory = root / module["path"]
        if not inside(directory, root / "domains"):
            raise ValueError(f"Invalid module path: {module['path']}")
        metadata = read_json(directory / "module.json")
        catalog_path = directory / metadata["catalog"]
        if not inside(catalog_path, directory):
            raise ValueError("Catalog escapes its module")
        catalog = read_json(catalog_path)
        modules.append({**metadata, "directory": directory})
        for entry in catalog["entries"]:
            entries.append({**entry, "scope": module["id"], "domain": module["id"], "directory": directory})
    meta = registry.get("meta")
    if meta is not None:
        if not isinstance(meta, dict) or meta.get("path") != "meta":
            raise ValueError("Invalid meta path: expected meta")
        directory = root / meta["path"]
        if not inside(directory, root):
            raise ValueError("Meta directory escapes repository")
        catalog_path = directory / meta["catalog"]
        if not inside(catalog_path, directory):
            raise ValueError("Catalog escapes meta directory")
        catalog = read_json(catalog_path)
        for entry in catalog["entries"]:
            entries.append({**entry, "scope": "meta", "domain": None, "directory": directory})
    return registry, modules, entries


def entry_body(entry: dict) -> str:
    relative, fragment = urldefrag(entry["path"])
    target = (entry["directory"] / relative).resolve()
    if not inside(target, entry["directory"]):
        raise ValueError(f"Entry escapes scope: {entry['id']}")
    text = target.read_text(encoding="utf-8")
    if not fragment:
        return text.strip()
    marker = re.search(r'<a\s+(?:id|name)=["\']' + re.escape(fragment) + r'["\'][^>]*>\s*</a>', text)
    if marker:
        remainder = text[marker.end():]
        following = re.search(r'<a\s+(?:id|name)=["\']', remainder)
        return (remainder[:following.start()] if following else remainder).strip()
    # Explicit anchors are the recommended stable addresses. This fallback
    # supports a regular heading without inventing a new index representation.
    return text.strip()


def find_entries(entries: list[dict], query: str) -> list[dict]:
    query = query.casefold().strip()
    if not query:
        return []
    scored = []
    for entry in entries:
        head = " ".join([entry["id"], entry["title"], entry["summary"], *entry["tags"]]).casefold()
        body = entry_body(entry).casefold()
        score = (4 if query in head else 0) + (1 if query in body else 0)
        if score:
            scored.append((score, entry))
    return [entry for _, entry in sorted(scored, key=lambda item: (-item[0], item[1]["id"]))]


def validate(root: Path) -> tuple[list[str], dict]:
    root = root.resolve()
    errors: list[str] = []
    counts = {"modules": 0, "entries": 0, "source_files": 0, "bridges": 0, "domain_checks": 0}
    try:
        registry, modules, entries = load_index(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"Registry/index: {exc}"], counts
    if registry.get("schema_version") != "1.0":
        errors.append("Unsupported registry schema_version")
    module_ids = [m["id"] for m in modules]
    if len(module_ids) != len(set(module_ids)):
        errors.append("Duplicate module ID")
    if "meta" in module_ids:
        errors.append("meta is a separate scope, not a domain module")
    entry_ids = [e["id"] for e in entries]
    if len(entry_ids) != len(set(entry_ids)):
        errors.append("Duplicate catalog ID")
    known_domain_methods = {entry["id"] for entry in entries if entry["domain"] is not None}
    versions = {m["id"]: m.get("version") for m in modules}
    immutable: set[Path] = set()
    import_ids: set[str] = set()
    validators: list[Path] = []

    meta = registry.get("meta")
    if meta is not None:
        directory = root / meta["path"]
        if meta.get("id") != "meta":
            errors.append("meta: ID must be meta")
        for field in ("id", "title", "version", "path", "entrypoint", "catalog"):
            if field not in meta:
                errors.append(f"meta: missing metadata field {field}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(meta.get("version", ""))):
            errors.append("meta: use an explicit version")
        for field in ("entrypoint", "catalog"):
            check_ref(directory, meta.get(field), directory, errors, f"meta.{field}")
        catalog = read_json(directory / meta["catalog"])
        if catalog.get("namespace") != "meta":
            errors.append("meta: catalog namespace mismatch")

    for module in modules:
        directory = module["directory"]
        name = module["id"]
        if directory.name != name or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            errors.append(f"{name}: module ID and directory do not match")
        for field in ("title", "version", "description", "entrypoint", "guide", "catalog", "depends_on"):
            if field not in module:
                errors.append(f"{name}: missing module field {field}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(module.get("version", ""))):
            errors.append(f"{name}: use an explicit module version")
        if module.get("depends_on") != []:
            errors.append(f"{name}: domain dependencies must be empty; put composition in bridges")
        for field in ("entrypoint", "guide", "catalog"):
            check_ref(directory, module.get(field), directory, errors, f"{name}.{field}")
        try:
            catalog = read_json(directory / module["catalog"])
            if catalog.get("domain") != name:
                errors.append(f"{name}: catalog namespace mismatch")
            manifest = read_json(directory / "sources/manifest.json")
            for imported in manifest["imports"]:
                source_id = imported["id"]
                if source_id in import_ids:
                    errors.append(f"Duplicate source ID: {source_id}")
                import_ids.add(source_id)
                if imported.get("kind") == "git" and not re.fullmatch(r"[0-9a-f]{40}", imported.get("revision", "")):
                    errors.append(f"{source_id}: git source must pin a full commit SHA")
                for source in imported["files"]:
                    path = check_ref(directory, source["path"], directory / "sources", errors, source_id)
                    if path is None or not path.is_file():
                        continue
                    if path in immutable:
                        errors.append(f"Source path listed more than once: {source['path']}")
                    immutable.add(path)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != source["sha256"]:
                        errors.append(f"{source_id}: immutable source SHA-256 mismatch: {source['path']}")
                    if not source.get("upstream_path"):
                        errors.append(f"{source_id}: missing original source path")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{name}: invalid catalog/source manifest: {exc}")
        for validator in module.get("validators", []):
            path = check_ref(directory, validator, directory, errors, f"{name}.validator")
            if path and path.suffix == ".py":
                validators.append(path)
            else:
                errors.append(f"{name}: validator must be a local Python file")

    for entry in entries:
        label = entry.get("id", "unknown entry")
        for field in ("id", "title", "kind", "summary", "tags", "path"):
            if field not in entry:
                errors.append(f"{label}: missing catalog field {field}")
        if not isinstance(label, str) or not label.startswith(entry["scope"] + "."):
            errors.append(f"{label}: wrong catalog namespace")
        if not isinstance(entry.get("tags"), list) or not all(isinstance(t, str) for t in entry.get("tags", [])):
            errors.append(f"{label}: tags must be strings")
        check_ref(entry["directory"], entry.get("path"), entry["directory"], errors, label)

    # Check authored working documents. Imported snapshots retain upstream links
    # and are checked for byte identity instead of silently rewriting them.
    for doc in root.rglob("*.md"):
        if ".git" in doc.parts or doc.resolve() in immutable:
            continue
        boundary = root
        for module in modules:
            if inside(doc, module["directory"]):
                boundary = module["directory"]
                break
        content = re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1\s*$", "", doc.read_text(encoding="utf-8"))
        for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", content):
            reference = match.group(1).strip()
            reference = re.sub(r'\s+"[^\"]*"$', "", reference).strip("<>")
            if urlparse(reference).scheme or reference.startswith("//"):
                continue
            if reference.startswith("#"):
                reference = doc.name + reference
            check_ref(doc.parent, reference, boundary, errors, str(doc.relative_to(root)), allow_directory=True)

    for bridge in registry.get("bridges", []):
        label = bridge.get("id", "bridge")
        check_ref(root, bridge.get("path"), root / "bridges", errors, label)
        path = check_ref(root, bridge.get("record"), root / "bridges", errors, label)
        if path is None:
            continue
        try:
            record = read_json(path)
            if record["id"] != label:
                errors.append(f"{label}: bridge record ID mismatch")
            for name, version in record["module_versions"].items():
                if name not in versions:
                    errors.append(f"{label}: unknown bridge domain {name}")
                elif versions[name] != version:
                    errors.append(f"{label}: review composition after {name} version changes")
            step_ids = [s["id"] for s in record["steps"]]
            if len(step_ids) != len(set(step_ids)):
                errors.append(f"{label}: duplicate step ID")
            for step in record["steps"]:
                if step["domain"] not in versions:
                    errors.append(f"{label}: step domain is not a registered domain: {step['domain']}")
                if step["domain"] not in record["module_versions"]:
                    errors.append(f"{label}: step domain version is not pinned")
                for used in step["uses"]:
                    if used not in known_domain_methods:
                        errors.append(f"{label}: unknown method reference {used}")
                    if not used.startswith(step["domain"] + "."):
                        errors.append(f"{label}: method reference belongs to another step domain")
            for handoff in record["handoffs"]:
                if handoff["from"] not in step_ids or handoff["to"] not in step_ids:
                    errors.append(f"{label}: dangling handoff endpoint")
                if handoff["relation"] not in {"uses", "informs", "derived_from", "evaluates"}:
                    errors.append(f"{label}: unsupported handoff relation")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{label}: malformed bridge: {exc}")

    # Domain code owns domain state semantics; the shared checker only invokes
    # the explicitly registered, local and version-controlled extension.
    for validator in validators:
        try:
            result = subprocess.run([sys.executable, str(validator)], cwd=root, capture_output=True, text=True, timeout=15)
            if result.returncode:
                errors.append(f"Domain check {validator.relative_to(root)}: {(result.stdout + result.stderr).strip()}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"Domain check {validator.relative_to(root)}: {exc}")
    counts.update(modules=len(modules), entries=len(entries), source_files=len(immutable), bridges=len(registry.get("bridges", [])), domain_checks=len(validators))
    return errors, counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="查找领域原语与元层方法，并检查结构和来源。")
    parser.add_argument("--root", type=Path, default=ROOT, help="另一个原语仓库根目录")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="列出可调用条目")
    searching = sub.add_parser("find", help="搜索工作索引与定义，忽略历史来源")
    searching.add_argument("query")
    for command in (listing, searching):
        filters = command.add_mutually_exclusive_group()
        filters.add_argument("--domain", help="仅查指定领域，不含元层")
        filters.add_argument("--scope", help="查 meta 元层或指定领域 ID")
    showing = sub.add_parser("show", help="显示一个条目的工作定义")
    showing.add_argument("id")
    sub.add_parser("validate", help="检查结构、来源和显式组合；不验证效果")
    args = parser.parse_args(argv)
    if args.command == "validate":
        errors, counts = validate(args.root)
        if errors:
            for error in errors:
                print("ERROR:", error)
            return 1
        print("PASS:", json.dumps(counts, ensure_ascii=False))
        print("仅通过结构与来源一致性检查；不代表真人、创作或人生判断验证。")
        return 0
    try:
        registry, modules, entries = load_index(args.root)
        domain = getattr(args, "domain", None)
        scope = getattr(args, "scope", None)
        domain_ids = {module["id"] for module in modules}
        if domain and domain not in domain_ids:
            parser.error(f"未知领域：{domain}")
        scopes = domain_ids | ({"meta"} if registry.get("meta") is not None else set())
        if scope and scope not in scopes:
            parser.error(f"未知检索范围：{scope}")
        if domain:
            entries = [entry for entry in entries if entry["domain"] == domain]
        if scope:
            entries = [entry for entry in entries if entry["scope"] == scope]
        if args.command == "find":
            entries = find_entries(entries, args.query)
        if args.command == "show":
            entry = next((entry for entry in entries if entry["id"] == args.id), None)
            if entry is None:
                print(f"找不到条目：{args.id}", file=sys.stderr)
                return 1
            directory = entry["directory"].resolve().relative_to(args.root.resolve()).as_posix()
            print(f"{entry['id']} · {entry['title']}\n来源位置：{directory}/{entry['path']}\n")
            print(entry_body(entry))
            return 0
        for entry in entries:
            print(f"{entry['id']} | {entry['title']} | {entry['summary']}")
        if not entries:
            print("没有匹配条目。请从元层 README.md 或相应领域 GUIDE.md 查找适用方法。")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"无法读取索引：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
