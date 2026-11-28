#!/usr/bin/env python3
"""Compile source coordinates and observed evidence into a derived index."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from assumption_freshness import RECEIPT as PROBE_RECEIPT, assess_receipt, context_valid
from verify_lean import code_only as lean_code_only

SCHEMA = "evidence-graph/v1"
RECEIPT = "evidence-receipt/v1"
SOURCES = "evidence-sources/v1"
EVIDENCE = {"LEAN", "TEST", "TRACE", "PROBE", "ACCEPTANCE", "REFINEMENT"}
KINDS = EVIDENCE | {"REQ", "SPEC", "DEC", "MODEL", "STATE", "TRANSITION", "PROP", "THM",
                    "MAP", "CODE", "VERIFIER", "ASSUMPTION"}
SKIP = {".git", ".hg", ".svn", ".worktree", ".worktrees", ".venv", "venv", "node_modules",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".lake", "build", "dist", "target",
        ".evidence-graph"}
SUFFIXES = {".md", ".lean", ".rs", ".js", ".mjs", ".ts", ".py", ".sql", ".json", ".txt",
            ".kt", ".dart", ".swift", ".java", ".go"}
DIRECTIVE = re.compile(r"^\s*(?:<!--\s*|(?://|#|--)\s*)?@evidence-(node|link)\s+(.+?)\s*(?:-->)?\s*$")
ID = re.compile(r"[A-Z][A-Z0-9_.:-]{1,127}\Z")
REPORTS = ("evidence-graph.json", "coverage-report.json", "dangling-links.json", "stale-evidence.json")
REQUIRED_TARGETS = {
    "LEAN": {"THM", "MODEL"}, "TEST": {"CODE", "MODEL"}, "TRACE": {"CODE", "MODEL", "MAP", "VERIFIER"},
    "PROBE": {"ASSUMPTION"}, "ACCEPTANCE": {"REQ"}, "REFINEMENT": {"CODE", "MODEL", "MAP"},
}
PROBE_SOURCE_KINDS = {"spec": {"REQ", "SPEC"}, "model": {"MODEL"}, "code": {"CODE"},
                      "mapping": {"MAP"}, "verifier": {"VERIFIER"}}
PROBE_BOUND_KINDS = {"ASSUMPTION"}.union(*PROBE_SOURCE_KINDS.values())
RUNTIME_CLAIMS = {"TEST", "TRACE", "REFINEMENT"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None


def project_revision(root):
    try:
        top = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                                      text=True, stderr=subprocess.DEVNULL, timeout=3).strip()
        if Path(top).resolve() != root:
            return None
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("coordinate must be project-relative")
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symbolic link in coordinate")
    if not path.is_file():
        raise ValueError("coordinate file does not exist")
    return path


def files(root, excluded):
    for base, dirs, names in os.walk(root, followlinks=False):
        base = Path(base)
        dirs[:] = sorted(d for d in dirs if d not in SKIP and base / d != excluded
                         and not (base / d).is_symlink())
        yield from (base / name for name in sorted(names)
                    if (base / name).suffix.lower() in SUFFIXES and not (base / name).is_symlink())


def diagnostic(code, **fields):
    return {"code": code, **fields}


def load(root, excluded):
    nodes, links, errors = [], [], []

    def add(kind, value, origin):
        if isinstance(value, dict):
            if kind == "node" and isinstance(value.get("id"), str) and ID.fullmatch(value["id"]):
                if isinstance(value.get("kind"), str) and value["kind"] in KINDS:
                    nodes.append({**value, **origin})
                    return
            if kind == "link" and all(isinstance(value.get(k), str) and value[k]
                                       for k in ("from", "to", "relation")):
                links.append({**value, **origin})
                return
        errors.append(diagnostic("INVALID_" + kind.upper(), **origin))

    for path in files(root, excluded):
        source = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            errors.append(diagnostic("SOURCE_UNREADABLE", source=source))
            continue
        origin = {"source": source, "source_sha256": digest(raw)}
        if path.suffix.lower() == ".json":
            if RECEIPT not in text and not path.name.endswith(".evidence.json"):
                continue
            try:
                value = json.loads(text)
            except ValueError:
                errors.append(diagnostic("INVALID_RECEIPT", **origin))
                continue
            if not isinstance(value, dict) or value.get("schema_version") != RECEIPT:
                errors.append(diagnostic("INVALID_RECEIPT_SCHEMA", **origin))
                continue
            if "materials" in value:
                if path.name.endswith(".evidence.json"):
                    errors.append(diagnostic("UNMATERIALIZED_FIXTURE", **origin))
                continue
            for kind in ("node", "link"):
                entries = value.get(kind + "s")
                if not isinstance(entries, list):
                    errors.append(diagnostic("INVALID_RECEIPT", **origin))
                else:
                    for item in entries:
                        add(kind, item, origin)
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            match = DIRECTIVE.match(line)
            if match:
                where = {**origin, "source_line": line_no}
                try:
                    add(match[1], json.loads(match[2]), where)
                except ValueError:
                    errors.append(diagnostic("MALFORMED_DIRECTIVE", **where))
    return nodes, links, errors


def find_symbol(text, name, suffix):
    """Locate declarations, or a literal authority ID in human-readable material.

    能力边界（如实声明）：这是**文本锚点级**检查——先剥离注释（Lean 用
    verify_lean.code_only，其他语言剥离块注释与行注释）再匹配声明模式；
    不是语言 AST/符号解析。字符串字面量与宏生成的声明可能漏检/误检，
    MAP 证据等级据此为文本锚点级。
    """
    if not isinstance(name, str) or not name:
        return False
    if suffix in {".md", ".txt", ".json", ".sql"}:
        return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text) is not None
    if suffix == ".lean":
        text = lean_code_only(text)
    else:
        text = re.sub(r"/\*[\s\S]*?\*/", "", text)
        # 行注释剥离（差分实测：注释掉的声明会误导纯文本锚点）
        text = re.sub(r"(?m)^\s*(?://|#|--).*$", "", text)
    token = re.escape(name.split()[-1].rsplit(".", 1)[-1].split("::")[-1])
    if suffix == ".lean":
        names = name.split(".")
        if len(names) > 1:
            namespaces = re.findall(r"^\s*namespace\s+([\w.]+)", text, re.M)
            if ".".join(names[:-1]) not in namespaces and ".".join(names[:-1]) != ".".join(namespaces):
                return False
    declaration = (r"(?m)^\s*(?:(?:pub(?:\([^)]*\))?|export|default|private|public|async|static|"
                   r"noncomputable|unsafe|const|open|override|suspend|internal|protected|final|"
                   r"abstract)\s+)*(?:def|fn|fun|function\*?|class|struct|enum|"
                   r"inductive|structure|theorem|abbrev|const|let|var|trait|interface|type)\s+"
                   + token + r"(?![\w$])")
    if re.search(declaration, text):
        return True
    if suffix == ".lean":
        return re.search(r"(?m)^\s*\|\s*" + token + r"(?=\s|[:(]|$)", text) is not None
    if suffix in {".js", ".mjs", ".ts"}:
        method = (r"(?m)^\s*(?:(?:async|static|public|private)\s+)*" + token
                  + r"\s*\([^;]*?\)\s*\{")
        if re.search(method, text):
            return True
    if suffix in {".kt", ".dart"}:
        # Kotlin 顶层/成员函数 fun name(...)（含 private fun 等，见修饰符表）
        if re.search(r"(?m)^\s*(?:(?:private|public|internal|protected|open|override|"
                     r"suspend|static|final|abstract)\s+)*fun\s+" + token + r"(?![\w$])",
                     text):
            return True
        # Dart 顶层函数/方法（返回类型可小写）：String name(...) / void name(...)
        # 排除语句关键字开头的行（return/await/throw/new 是调用语句，
        # 不是声明——差分实测：`return compactedContinuation(...)` 会被
        # 误判为声明存在）
        dart_decl = (r"(?m)^[\t ]*(?!(?:return|await|throw|new|else|case|yield)\b)"
                     r"[A-Za-z_][\w<>,\t ?]*?[\t ]+" + token + r"[\t ]*\(")
        if suffix == ".dart" and re.search(dart_decl, text):
            return True
    return False


class Coordinates:
    def __init__(self, root, revision):
        self.root = root
        self.revision = revision
        self.cache = {}
        self.errors = []
        self.source_files = {}
        manifest = root / "fixture-sources.json"
        self.materialized = (root / "fixture.evidence.json").is_file()
        if self.materialized and not manifest.is_file():
            self.errors.append(diagnostic("SOURCE_MANIFEST_MISSING", source="fixture-sources.json"))
        if manifest.exists() or manifest.is_symlink():
            try:
                data = json.loads(safe_file(root, "fixture-sources.json").read_bytes())
                if data["schema_version"] != SOURCES or not isinstance(data["files"], dict):
                    raise ValueError("unrecognized source manifest")
                self.source_files = data["files"]
            except (ValueError, KeyError, TypeError, OSError):
                self.errors.append(diagnostic("INVALID_SOURCE_MANIFEST", source="fixture-sources.json"))

    def read(self, relative):
        if relative not in self.cache:
            p = safe_file(self.root, relative)
            self.cache[relative] = (p.read_bytes(), p.suffix.lower())
        return self.cache[relative]

    def inspect(self, node):
        coordinate = node.get("coordinate")
        if coordinate is None and node["kind"] not in {"MAP", "THM"}:
            return None, []
        if not isinstance(coordinate, dict) or not isinstance(coordinate.get("path"), str):
            return None, [diagnostic("INVALID_COORDINATE", id=node["id"])]
        path = coordinate["path"]
        try:
            raw, suffix = self.read(path)
        except (ValueError, OSError):
            return None, [diagnostic("COORDINATE_FILE_MISSING", id=node["id"], path=path)]
        actual_sha = digest(raw)
        metadata = self.source_files.get(path, {})
        if not isinstance(metadata, dict):
            return None, [diagnostic("INVALID_SOURCE_MATERIAL", id=node["id"], path=path)]
        if self.materialized and (not metadata.get("revision") or not metadata.get("sha256")):
            return None, [diagnostic("SOURCE_MATERIAL_UNBOUND", id=node["id"], path=path)]
        actual_revision = metadata.get("revision") or self.revision or coordinate.get("revision") or node.get("revision")
        result = {"path": path, "sha256": actual_sha, "revision": actual_revision}
        errors = []
        for observed in (coordinate.get("sha256"), metadata.get("sha256")):
            if observed is not None and observed != actual_sha:
                mismatch = diagnostic("SOURCE_HASH_MISMATCH", id=node["id"], path=path,
                                      expected=observed, observed=actual_sha)
                if mismatch not in errors:
                    errors.append(mismatch)
        if coordinate.get("revision") and coordinate["revision"] != actual_revision:
            errors.append(diagnostic("COORDINATE_REVISION_MISMATCH", id=node["id"], path=path,
                                     expected=actual_revision, observed=coordinate["revision"]))
        symbol = coordinate.get("symbol")
        if symbol is None and node["kind"] in {"THM", "MAP"} and "line" not in coordinate:
            errors.append(diagnostic("SYMBOL_OR_LINE_REQUIRED", id=node["id"], path=path))
        if symbol is not None or "line" in coordinate:
            try:
                text = raw.decode()
                if "line" in coordinate:
                    line = coordinate["line"]
                    lines = text.splitlines()
                    if type(line) is not int or not 1 <= line <= len(lines):
                        raise ValueError()
                    text = lines[line - 1] if symbol is not None else text
                if symbol is not None and not find_symbol(text, symbol, suffix):
                    errors.append(diagnostic("SYMBOL_NOT_FOUND", id=node["id"], path=path, symbol=symbol))
            except (ValueError, UnicodeError):
                errors.append(diagnostic("INVALID_SOURCE_LOCATION", id=node["id"], path=path))
        return result, errors


def index_graph(root, excluded):
    nodes, links, errors = load(root, excluded)
    revision = project_revision(root)
    coords = Coordinates(root, revision)
    errors.extend(coords.errors)
    by_id, out, incoming = {}, {}, {}
    if not nodes:
        errors.append(diagnostic("EMPTY_GRAPH"))
    for node in nodes:
        identifier = node["id"]
        first = by_id.setdefault(identifier, node)
        if first is not node:
            errors.append(diagnostic("DUPLICATE_ID", id=identifier, first_source=first["source"],
                                     duplicate_source=node["source"]))
        actual, issues = coords.inspect(node)
        node["resolved_coordinate"] = actual
        node["coordinate_valid"] = not issues and actual is not None
        errors.extend(issues)
        # Task 3（收敛审查）：TEST 证据必须绑定测试源文件本身——
        # 声明文件出处的 source 字段不参与失效判断，故用独立 test_source
        # 坐标（path+sha256）并纳入失效体系。
        if node["kind"] == "TEST":
            test_source = node.get("test_source")
            if isinstance(test_source, dict) and test_source.get("path"):
                ts_actual, ts_issues = coords.inspect(
                    {**node, "coordinate": test_source})
                if ts_actual is None or ts_issues:
                    errors.extend(
                        {**i, "id": node["id"], "code": i.get(
                            "code", "TEST_SOURCE_INVALID")}
                        if i.get("code") != "COORDINATE_FILE_MISSING"
                        else {"code": "TEST_SOURCE_MISSING", "id": node["id"],
                              "path": test_source["path"]}
                        for i in ts_issues)
                elif ts_actual.get("sha256") != test_source.get("sha256"):
                    errors.append(diagnostic(
                        "TEST_SOURCE_HASH_MISMATCH", id=node["id"],
                        path=test_source["path"],
                        expected=test_source.get("sha256"),
                        observed=ts_actual.get("sha256")))
            # 缺失 test_source 不作为 coordinate error（不阻断 CI）——
            # 进入 verify_evidence 作为 gap → evidence UNKNOWN
            pass
    for edge in links:
        a, b = edge["from"], edge["to"]
        if a not in by_id or b not in by_id:
            errors.append(diagnostic("DANGLING_LINK", **edge))
            continue
        out.setdefault(a, set()).add(b)
        incoming.setdefault(b, set()).add(a)
    return revision, coords, nodes, links, by_id, out, incoming, errors


def content_coordinate(node):
    return node["resolved_coordinate"] or {"revision": node.get("revision") or node["source_sha256"],
                                           "sha256": node["source_sha256"]}


def json_value(payload, reference):
    if reference.startswith("/"):
        path = [v.replace("~1", "/").replace("~0", "~") for v in reference[1:].split("/")]
        for part in path:
            payload = payload[int(part)] if isinstance(payload, list) else payload[part]
        return payload
    if reference in payload:
        return payload[reference]
    first, rest = reference.split(".", 1)
    return json_value(payload[first], rest)


def audit_result(data, actual, targets, coords):
    native = data.get("schema") == "primitives-lean-verification/v1"
    axioms = data.get("theorem_axioms" if native else "axioms")
    hashes = data.get("source_sha256")
    commands = data.get("commands")
    declarations = [n for n in targets if n["kind"] == "THM"]
    if (data.get("status") != "PASS_CONDITIONAL_MODEL_PROOFS"
            or not isinstance(axioms, dict) or not isinstance(hashes, dict) or not declarations
            or not isinstance(commands, list) or not commands
            or any(not isinstance(c, dict) or type(c.get("exit_code")) is not int
                   or c["exit_code"] != 0 for c in commands)
            or (not native and (data.get("clean_build") is not True
                                or data.get("source_hashes_frozen_before_and_after") is not True))):
        return "no successful named Lean audit"
    if data.get("repository_head_at_run", actual["revision"]) != actual["revision"]:
        return "receipt input binding mismatch: Lean execution revision"
    if not data.get("lean_version"):
        return "receipt missing lean toolchain binding"
    for target in targets:
        coordinate = target["resolved_coordinate"]
        if not coordinate or coordinate["revision"] != actual["revision"]:
            return "receipt input binding mismatch: mixed Lean source and receipt revisions"
        original = coords.source_files.get(coordinate["path"], {}).get("path", coordinate["path"])
        reported = hashes.get(original)
        if not native and reported is None:
            reported = hashes.get(Path(original).name)
        if reported != coordinate["sha256"]:
            return "receipt input binding mismatch: unaudited Lean source " + target["id"]
    allowed = {"propext", "Classical.choice", "Quot.sound"}
    for target in declarations:
        name = target["coordinate"].get("symbol")
        dependencies = axioms.get(name)
        if not isinstance(dependencies, list) or any(not isinstance(a, str) or a not in allowed
                                                    for a in dependencies):
            return "Lean audit does not attest the linked declaration"
        if native:
            compiled = data.get("compiled_declarations", {}).get(name, {})
            if compiled.get("kind") != "theorem" or compiled.get("axioms") != dependencies:
                return "named theorem is absent from the compiled audit"
    return None


def adapted_field(data, canonical, natives):
    """schema 适配：从原生回执的已固化字段映射规范字段。

    只读取原生记录中已存在的事实（如 node_version/started_at），
    不猜测、不回填当前环境值。返回 (value, source_field)。
    """
    if data.get(canonical):
        return data.get(canonical), canonical
    for native_key, native_field in natives:
        if data.get("schema_version", data.get("schema")) == native_key:
            value = data.get(native_field)
            if value:
                return value, native_field
    return None, None


TOOLCHAIN_NATIVES = (("core-model-pilot-test-run/v1", "node_version"),)
EXECUTED_AT_NATIVES = (("core-model-pilot-test-run/v1", "started_at"),)


def execution_result(data, node, targets):
    if node["kind"] == "PROBE" and data.get("schema_version") == PROBE_RECEIPT:
        return "freshness receipt requires a current probe context"
    status = data.get("status")
    if (not isinstance(status, str) or re.fullmatch(r"PASS(?:_[A-Z0-9]+)*|VERIFIED", status) is None
            or type(data.get("exit_code")) is not int or data["exit_code"] != 0):
        return "no successful execution in receipt"
    # Task 3 必填绑定作用域：TEST/TRACE（ACCEPTANCE 的独立判断制度不在此列）。
    # 原生 schema 适配：core-model-pilot-test-run/v1 的 node_version /
    # started_at 是该次执行固化的真实工具链与时间——按已记录事实采信。
    if node["kind"] in {"TEST", "TRACE"}:
        toolchain, _ = adapted_field(data, "toolchain", TOOLCHAIN_NATIVES)
        if not toolchain:
            return "receipt missing toolchain binding"
        executed, _ = adapted_field(data, "executed_at", EXECUTED_AT_NATIVES)
        if not isinstance(executed, str) or stamp(executed) is None:
            return "receipt missing valid executed_at"
    if node["kind"] == "TEST":
        summary = data.get("summary")
        if (not isinstance(summary, dict) or type(summary.get("tests")) is not int
                or summary["tests"] <= 0 or summary.get("fail") != 0
                or summary.get("pass") != summary["tests"]):
            return "no positive, all-passing test count in receipt"
    if node["kind"] == "ACCEPTANCE" and data.get("requirement_ids") != node.get("requirement_ids"):
        return "receipt input binding mismatch: original requirements"
    if node["kind"] == "PROBE" and any(
        data.get(key) != node.get(key) for key in ("executed_at", "expires_at", "ttl_seconds",
                                                   "environment_scope_hash")
    ):
        return "receipt input binding mismatch: probe environment or time"
    observed = data.get("evidence_bindings")
    if not isinstance(observed, dict):
        return "execution receipt has no observed input bindings"
    for target in targets:
        actual_target = content_coordinate(target)
        bound = observed.get(target["id"])
        if not isinstance(bound, dict):
            return "execution receipt omitted observed binding " + target["id"]
        if any(bound.get(key) != actual_target[key] for key in ("revision", "sha256")):
            return "receipt input binding mismatch: " + target["id"]
    return None


def receipt_result(node, targets, coords):
    actual = node["resolved_coordinate"]
    if not actual or not node["coordinate_valid"]:
        return "missing or invalid receipt coordinate"
    if coords.errors:
        return "source projection has no valid materialization record"
    try:
        data = json.loads(coords.read(actual["path"])[0])
        if not isinstance(data, dict):
            return "receipt must be a JSON object"
        problem = (audit_result(data, actual, targets, coords) if node["kind"] == "LEAN"
                   else execution_result(data, node, targets))
        if problem:
            return problem
        checks = node.get("receipt_checks", {})
        if not isinstance(checks, dict):
            return "invalid supplemental receipt assertions"
        if not all(type(json_value(data, k)) is type(v) and json_value(data, k) == v for k, v in checks.items()):
            return "executed receipt assertion mismatch"
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError):
        return "receipt data missing, malformed, or unreadable"
    return None


def verify_evidence(node, neighbors, coords, now, issues):
    identifier, kind = node["id"], node["kind"]
    state = node.get("evidence_state", "UNKNOWN")
    stale, gaps = [], []
    bindings = node.get("bindings", {})
    target_kinds = {other["kind"] for other in neighbors.values()}
    if state not in ("PASS", "FAIL", "UNKNOWN"):
        gaps.append("unrecognized evidence state")
    if not isinstance(bindings, dict):
        bindings = {}
        gaps.append("invalid evidence bindings")
    semantic = {i: other for i, other in neighbors.items() if other["kind"] in REQUIRED_TARGETS[kind]}
    missing = REQUIRED_TARGETS[kind] - target_kinds
    if missing:
        gaps.append("missing target types: " + ", ".join(sorted(missing)))
    if kind == "ACCEPTANCE":
        declared = node.get("requirement_ids")
        reqs = {i for i, other in neighbors.items() if other["kind"] == "REQ"}
        if not isinstance(declared, list) or not all(isinstance(v, str) for v in declared):
            gaps.append("missing original requirement IDs")
        elif set(declared) != reqs:
            stale.append(diagnostic("ACCEPTANCE_REQUIREMENT_MISMATCH", id=identifier,
                                    expected=sorted(declared), observed=sorted(reqs)))
    for i in sorted(bindings.keys() | semantic.keys()):
        expected = neighbors.get(i)
        bound = bindings.get(i)
        if expected is None:
            stale.append(diagnostic("EVIDENCE_TARGET_MISMATCH", id=identifier, target=i))
            continue
        if not isinstance(bound, dict) or not bound.get("revision") or not bound.get("sha256"):
            gaps.append("missing revision or source hash for " + i)
            continue
        if expected.get("coordinate") is not None and not expected["coordinate_valid"]:
            gaps.append("target coordinate invalid: " + i)
        actual = content_coordinate(expected)
        for field in ("revision", "sha256"):
            if bound.get(field) != actual[field]:
                stale.append(diagnostic("EVIDENCE_BINDING_MISMATCH", id=identifier, target=i, field=field,
                                        expected=actual[field], observed=bound[field]))
    for field, target_kind in (("model_revision", "MODEL"), ("code_revision", "CODE"),
                               ("mapping_revision", "MAP"), ("verifier_revision", "VERIFIER"),
                               ("spec_revision", "REQ")):
        expected = sorted({content_coordinate(n)["revision"] for n in neighbors.values()
                           if n["kind"] == target_kind and content_coordinate(n)["revision"]})
        if node.get(field) and expected and expected != [node[field]]:
            stale.append(diagnostic(field.upper() + "_MISMATCH", id=identifier,
                                    expected=expected, observed=node[field]))
    if kind == "TEST" and not node.get("test_source"):
        gaps.append("missing test_source binding (path+sha256)")
    if kind == "PROBE":
        executed = stamp(node.get("executed_at"))
        expires = stamp(node.get("expires_at"))
        ttl = node.get("ttl_seconds")
        timed = executed and type(ttl) in {float, int} and 0 <= ttl < 1e15 and math.isfinite(ttl)
        if (expires and expires <= now) or (timed and executed.timestamp() + ttl <= now.timestamp()):
            stale.append(diagnostic("PROBE_EXPIRED", id=identifier))
        if not executed or executed > now or not (expires or timed):
            gaps.append("missing or invalid probe time/TTL")
        scope, expected_scope = node.get("environment_scope_hash"), node.get("expected_environment_scope_hash")
        if expected_scope and scope != expected_scope:
            stale.append(diagnostic("PROBE_SCOPE_MISMATCH", id=identifier,
                                    expected=expected_scope, observed=scope))
        if not scope or not expected_scope:
            gaps.append("missing environment scope binding")
        if not node.get("blind_spots"):
            gaps.append("missing blind_spots declaration (probe 边界必须显式声明)")
    for detail in issues:
        if detail["id"] == identifier or detail["id"] in (semantic.keys() | bindings.keys()):
            stale.append({**detail, "evidence_id": identifier})
    if state == "PASS":
        # Any explicitly bound input also affects this result. For example a
        # test can record the raw trace as well as its required code/model pair.
        relevant = semantic if kind == "LEAN" else {i: neighbors[i]
                   for i in semantic.keys() | bindings.keys() if i in neighbors}
        problem = receipt_result(node, [relevant[i] for i in sorted(relevant)], coords)
        if problem:
            gaps.append(problem)
            if problem.startswith("receipt input binding mismatch"):
                stale.append(diagnostic("RECEIPT_BINDING_MISMATCH", id=identifier, reason=problem))
    if state != "PASS":
        gaps.append(node.get("reason") or "no executed PASS recorded")
    return ("STALE" if stale else "FAIL" if state == "FAIL" else
            "UNKNOWN" if gaps else "VERIFIED"), gaps, stale


def verify_current_probe(node, neighbors, probe_targets, coords, now, input_issues):
    context = node["probe_context"]
    identifier = node["id"]
    if not context_valid(context):
        return {"status": "UNKNOWN", "reason": "missing or invalid current probe context", "raw_status": None}
    try:
        actual = node["resolved_coordinate"]
        data = json.loads(coords.read(actual["path"])[0]) if actual else None
    except (ValueError, OSError, RecursionError):
        data = None
    result = assess_receipt(data, context, now)
    assumption = neighbors.get(context["assumption_id"], {})
    if (probe_targets != {context["assumption_id"]} or assumption.get("kind") != "ASSUMPTION"
            or assumption.get("current_probe_id") != identifier):
        return {**result, "status": "UNKNOWN", "reason": "probe is not the current directed assumption evidence"}
    sources = {i: target for i, target in neighbors.items() if target["kind"] in PROBE_BOUND_KINDS}
    input_ids = sources.keys() | {identifier}
    if any(issue["id"] in input_ids for issue in input_issues):
        return {**result, "status": "STALE", "reason": "probe or linked source coordinate is stale"}
    if (not node["coordinate_valid"] or coords.errors
            or any(not target["coordinate_valid"] for target in sources.values())):
        return {**result, "status": "UNKNOWN", "reason": "missing or invalid probe or source coordinate"}
    if sources.keys() != context["evidence_bindings"].keys():
        return {**result, "status": "STALE", "reason": "probe linked source set changed"}
    if any(any(content_coordinate(sources[key])[field] != binding[field]
               for field in ("revision", "sha256"))
           for key, binding in context["evidence_bindings"].items()):
        return {**result, "status": "STALE", "reason": "probe linked source revision or digest changed"}
    for version, kinds in PROBE_SOURCE_KINDS.items():
        revisions = {content_coordinate(source)["revision"]
                     for source in sources.values() if source["kind"] in kinds}
        if not revisions:
            return {**result, "status": "UNKNOWN", "reason": f"missing probe {version} source"}
        if context["versions"][version] not in revisions:
            return {**result, "status": "STALE", "reason": f"probe {version} version changed"}
    return result


def apply_assumption_dependencies(nodes, by_id, relations, stale):
    def current_probe(assumption_id):
        assumption = by_id.get(assumption_id, {})
        current = assumption.get("current_probe_id")
        if (assumption.get("kind") != "ASSUMPTION" or not isinstance(current, str)
                or assumption_id not in relations.get((current, "probes"), set())):
            return None
        probe = by_id.get(current, {})
        return probe if probe.get("kind") == "PROBE" and "probe_context" in probe else None

    for node in nodes:
        i = node["id"]
        if node["kind"] == "ASSUMPTION" and "current_probe_id" in node:
            probe = current_probe(i)
            if probe:
                node["assumption_coverage_status"] = probe["evidence_status"]
                node["unverified_reasons"] = probe["unverified_reasons"]
            else:
                node["assumption_coverage_status"] = "UNKNOWN"
                node["unverified_reasons"] = ["missing designated current probe"]
        if node["kind"] not in RUNTIME_CLAIMS:
            continue
        required = relations.get((i, "requires"), set())
        if "required_assumption_ids" not in node and not required:
            continue
        node["execution_evidence_status"] = node["evidence_status"]
        declared = node.get("required_assumption_ids")
        if (not isinstance(declared, list) or not declared or not all(isinstance(v, str) for v in declared)
                or len(declared) != len(set(declared)) or set(declared) != required):
            if node["evidence_status"] == "VERIFIED":
                node["evidence_status"] = "UNKNOWN"
            node["unverified_reasons"].append("runtime assumption declarations and requires links differ")
            continue
        statuses = {}
        for assumption_id in sorted(required):
            probe = current_probe(assumption_id)
            statuses[assumption_id] = probe["evidence_status"] if probe else "UNKNOWN"
        node["assumption_dependencies"] = statuses
        if node["evidence_status"] != "VERIFIED":
            continue
        unavailable = {key: status for key, status in statuses.items() if status != "VERIFIED"}
        if unavailable:
            node["evidence_status"] = "STALE" if "STALE" in unavailable.values() else "UNKNOWN"
        for assumption_id, status in unavailable.items():
            node["unverified_reasons"].append(f"required assumption {assumption_id} is {status}")
            if status == "STALE":
                stale.append(diagnostic("REQUIRED_ASSUMPTION_STALE", id=i, assumption_id=assumption_id))


def assess(root, excluded=None, now=None):
    revision, coords, nodes, links, by_id, out, incoming, errors = index_graph(root, excluded)
    generated = now or datetime.now(timezone.utc)
    input_issues = [d for d in errors if d.get("code") in {
        "SOURCE_HASH_MISMATCH", "COORDINATE_REVISION_MISMATCH", "COORDINATE_FILE_MISSING",
        "SYMBOL_NOT_FOUND", "INVALID_SOURCE_LOCATION", "SOURCE_MATERIAL_UNBOUND",
    }]
    # Resolve input invalidations before any evidence consumes them. Source
    # declaration order cannot make a stale theorem count as a valid proof.
    relations = {}
    for edge in links:
        if edge["from"] in by_id and edge["to"] in by_id:
            relations.setdefault((edge["from"], edge["relation"]), set()).add(edge["to"])
    for node in nodes:
        if node["kind"] != "THM" or not node.get("model_revision"):
            continue
        identifier = node["id"]
        neighbors = out.get(identifier, set()) | incoming.get(identifier, set())
        expected = {content_coordinate(by_id[i])["revision"]
                    for i in neighbors if by_id[i]["kind"] == "MODEL"}
        expected.discard(None)
        if expected and sorted(expected) != [node["model_revision"]]:
            input_issues.append(diagnostic("MODEL_REVISION_MISMATCH", id=identifier,
                                           expected=sorted(expected), observed=node["model_revision"]))
    stale = input_issues.copy()
    reasons = {}
    for issue in input_issues:
        reasons.setdefault(issue["id"], []).append(issue["code"])
    for node in nodes:
        identifier = node["id"]
        if node["kind"] not in EVIDENCE:
            node["evidence_status"] = "STALE" if identifier in reasons else "DECLARED"
            node["unverified_reasons"] = reasons.get(identifier, [])
            continue
        neighbors = {i: by_id[i] for i in out.get(identifier, set()) | incoming.get(identifier, set())}
        if node["kind"] == "PROBE" and "probe_context" in node:
            result = verify_current_probe(node, neighbors, relations.get((identifier, "probes"), set()),
                                          coords, generated, input_issues)
            node["probe_assessment"] = result
            node["evidence_status"] = "VERIFIED" if result["status"] == "PASS" else result["status"]
            node["unverified_reasons"] = [] if result["status"] == "PASS" else [result["reason"]]
            if result["status"] == "STALE":
                stale.append(diagnostic("PROBE_STALE", id=identifier, reason=result["reason"]))
            continue
        status, gaps, invalidations = verify_evidence(node, neighbors, coords, generated, input_issues)
        node["evidence_status"], node["unverified_reasons"] = status, gaps
        stale.extend(invalidations)
    apply_assumption_dependencies(nodes, by_id, relations, stale)
    for edge in links:
        if edge["to"] in by_id:
            origin, target = by_id.get(edge["from"]), by_id[edge["to"]]
            edge["target_revision"] = content_coordinate(target)["revision"]
            evidence = next((n for n in (origin, target) if n and n["kind"] in EVIDENCE), None)
            edge["evidence_revision"] = content_coordinate(evidence)["revision"] if evidence else None
            edge["evidence_status"] = evidence["evidence_status"] if evidence else "DECLARED"
            edge["unverified_reasons"] = evidence["unverified_reasons"] if evidence else []
    meta = {"schema_version": SCHEMA, "generated_at": generated.isoformat(),
            "project_revision": revision,
            "compiler_revision": digest(Path(__file__).read_bytes())[:32]}
    g = {**meta, "nodes": sorted(nodes, key=lambda n: (n["id"], n["source"])),
         "links": sorted(links, key=lambda e: (e["from"], e["to"], e["relation"])), "diagnostics": errors}
    cov = coverage(nodes, by_id, out, incoming)
    # 确定性构建标识（吸收 #21）：输入内容+编译器哈希派生，墙钟不入
    # build_id——同一输入的重复 build 具有相同 build_id（审计可复现）；
    # generated_at 保留墙钟（探针 TTL 判定需要真实时间），但 CI 确定性
    # 检查对比 build_id 而非字节。
    g["build_id"] = digest(json.dumps(canonical_stable(g), ensure_ascii=False,
                                  sort_keys=True).encode())[:32]
    g["compiler_revision"] = digest(Path(__file__).read_bytes())[:32]
    return {"evidence-graph.json": g, "coverage-report.json": {**meta, "build_id": g["build_id"], **cov},
            "dangling-links.json": {**meta, "build_id": g["build_id"], "items": [d for d in errors if d["code"] == "DANGLING_LINK"]},
            "stale-evidence.json": {**meta, "build_id": g["build_id"], "items": stale}}


def canonical_stable(g):
    """去除墙钟字段后的稳定视图（build_id 派生输入）。"""
    return {k: v for k, v in g.items() if k not in ("generated_at",)}


def coverage(nodes, by_id, out, incoming):
    groups = {"REQ": "requirements", "MODEL": "models", "PROP": "properties", "STATE": "transitions",
              "TRANSITION": "transitions", "MAP": "mappings", "THM": "theorems",
              "TEST": "tests", "TRACE": "traces", "ASSUMPTION": "assumptions", "PROBE": "probes",
              "REFINEMENT": "refinement", "ACCEPTANCE": "acceptance", "LEAN": "proofs"}
    rows = {group: [] for group in groups.values()}
    for node in nodes:
        i, kind = node["id"], node["kind"]
        if kind not in groups:
            continue
        forward = out.get(i, set())
        neighbors = forward | incoming.get(i, set())
        def related(kind, ids=neighbors):
            return sorted(x for x in ids if by_id[x]["kind"] == kind)
        def observed(kind):
            return any(by_id[j]["evidence_status"] == "VERIFIED" for j in related(kind))
        row = {"id": i, "critical": node.get("critical") is True,
               "status": node["evidence_status"], "unverified_reasons": node["unverified_reasons"]}
        if "execution_evidence_status" in node:
            row["execution_evidence_status"] = node["execution_evidence_status"]
            row["assumption_dependencies"] = node.get("assumption_dependencies", {})
        if kind == "REQ":
            row.update(models=related("MODEL", forward), acceptances=related("ACCEPTANCE"))
            covered = bool(row["acceptances"] and
                           any(by_id[j]["coordinate_valid"] for j in row["models"]))
            row["verified_acceptance"] = observed("ACCEPTANCE")
        elif kind == "MODEL":
            covered = node["coordinate_valid"]
        elif kind == "PROP":
            row.update(theorems=related("THM", forward),
                       deferred=bool(node.get("deferred_reason")),
                       deferred_reason=node.get("deferred_reason"))
            row["declared"] = any(by_id[j]["coordinate_valid"] for j in row["theorems"])
            covered = any(by_id[j]["coordinate_valid"] and by_id[j]["evidence_status"] != "STALE" and any(
                by_id[k]["kind"] == "LEAN" and by_id[k]["evidence_status"] == "VERIFIED"
                for k in out.get(j, set()) | incoming.get(j, set())) for j in row["theorems"])
        elif kind in {"STATE", "TRANSITION"}:
            row["mappings"] = related("MAP", forward)
            covered = bool(row["mappings"]) and all(by_id[j]["coordinate_valid"] for j in row["mappings"])
        elif kind == "MAP":
            covered = node["coordinate_valid"]
            row.update(valid=covered)
        elif kind == "THM":
            row["declared"] = node["coordinate_valid"]
            covered = row["declared"] and row["status"] != "STALE" and observed("LEAN")
        elif kind == "ASSUMPTION":
            if "current_probe_id" in node:
                row["status"] = node["assumption_coverage_status"]
                covered = row["status"] == "VERIFIED"
            else:
                covered = observed("PROBE")
            row["probes"] = related("PROBE")
        else:
            covered = row["status"] == "VERIFIED"
        row["covered"] = covered
        rows[groups[kind]].append(row)
    return {**rows, "summary": {group: {"total": len(items),
                 "covered": sum(r["covered"] for r in items),
                 "uncovered": sorted(r["id"] for r in items if not r["covered"]),
                 "critical_uncovered": sorted(r["id"] for r in items if not r["covered"] and r["critical"]),
                 "deferred": sorted(r["id"] for r in items if r.get("deferred"))}
                 for group, items in rows.items()}}


def atomic_write(path, payload):
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate", "coverage", "stale"))
    parser.add_argument("--project", default=".")
    parser.add_argument("--output", default=".evidence-graph")
    options = parser.parse_args(argv)
    root = Path(options.project).resolve()
    if not root.is_dir():
        parser.error("project directory does not exist")
    out = (root / options.output).resolve()
    if out == root or not out.is_relative_to(root):
        parser.error("output must be a subdirectory of the project")
    if out.is_dir() and any(p.name not in REPORTS for p in out.iterdir()):
        parser.error("output directory may contain only generated reports")
    for name in REPORTS:
        path = out / name
        if path.is_symlink():
            parser.error("refusing output symlink")
        if path.exists():
            try:
                prior = json.loads(path.read_bytes())
                if not isinstance(prior, dict) or prior.get("schema_version") != SCHEMA:
                    raise ValueError()
            except (OSError, ValueError):
                parser.error(f"refusing to replace existing non-report: {name}")
    reports = assess(root, out)
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in reports.items():
        atomic_write(out / name, payload)
    graph, cov, _, stale = (reports[name] for name in REPORTS)
    if options.command == "build":
        result = {"output": str(out), "nodes": len(graph["nodes"]), "links": len(graph["links"]),
                  "diagnostics": len(graph["diagnostics"])}
        rc = 0
    elif options.command == "coverage":
        result, rc = cov, 0
    elif options.command == "stale":
        result, rc = stale, int(bool(stale["items"]))
    else:
        result = {"diagnostics": graph["diagnostics"], "coverage": cov["summary"],
                  "stale": stale["items"], "output": str(out),
                  "failure_codes": {
                      "parse": sorted(c for c in ({d["code"] for d in graph["diagnostics"]}) if c in (
                          "INVALID_RECEIPT", "INVALID_RECEIPT_SCHEMA", "INVALID_NODE",
                          "INVALID_LINK", "MALFORMED_DIRECTIVE", "INVALID_SOURCE_MANIFEST",
                          "SOURCE_MANIFEST_MISSING", "UNMATERIALIZED_FIXTURE",
                          "SOURCE_UNREADABLE", "EMPTY_GRAPH", "DUPLICATE_ID")),
                      "coordinate": sorted(c for c in ({d["code"] for d in graph["diagnostics"]}) if c in (
                          "DANGLING_LINK", "SYMBOL_NOT_FOUND", "SYMBOL_OR_LINE_REQUIRED",
                          "COORDINATE_FILE_MISSING", "SOURCE_HASH_MISMATCH",
                          "COORDINATE_REVISION_MISMATCH", "INVALID_SOURCE_LOCATION",
                          "SOURCE_MATERIAL_UNBOUND")),
                      "stale": sorted({d["code"] for d in stale["items"]}),
                      "critical_uncovered": sorted(
                          rid for group in cov["summary"].values()
                          for rid in group["critical_uncovered"])},
                  }
        # 退出码保持合并仓库的布尔语义（非零=门失败，具体类别见
        # failure_codes JSON——成批改写 v1 测试断言不属于收敛轮范围）
        rc = int(bool(graph["diagnostics"] or stale["items"]
                      or any(row["critical_uncovered"] for row in cov["summary"].values())))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(run())
