#!/usr/bin/env python3
"""Evidence Graph Compiler — Batch 1 (primitives).

把分散在权威源里的 Spec / Model / Proof / Code / Test / Trace / Probe
事实编译成一张可检查的追溯图（Evidence Graph）。

设计铁律（docs/EVIDENCE_GRAPH.md 同步维护）：
  1. Graph 是派生索引，不是事实源。权威事实只存在于各仓库的原始文件。
  2. 不运行任何验证器：编译器只读取已有 receipt（执行回执）并核对其
     版本绑定。没有 receipt 的测试/证明/探针一律 UNKNOWN / DECLARED，
     绝不伪装成通过。
  3. 版本与新鲜度是核心：节点/边/证据绑定来源 revision 与 content hash；
     绑定不匹配 → STALE；探针有 TTL与环境 scope；验证器自身变化 →
     旧回执不得冒充新结论。
  4. 确定性输出：同一输入重复 build 得到字节一致的产物。
  5. 纯 Python 标准库、离线、无数据库、无图数据库、无第三方包。

CLI:
  python3 tools/evidence_graph.py build    --project <dir>
  python3 tools/evidence_graph.py validate --project <dir>
  python3 tools/evidence_graph.py coverage --project <dir>
  python3 tools/evidence_graph.py stale    --project <dir>

退出码（validate/build）：
  0 正常；2 输入解析/清单非法/路径穿越；3 重复 ID；4 悬空必需引用或
  悬空代码映射；5 策略缺口（REQ 无 MODEL / PROP 未证明且未 DEFERRED /
  TRANSITION 无 MAP）；6 存在 STALE 证据且策略要求失败；7 用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_MANIFEST = "evidence-graph-manifest/v1"
SCHEMA_NODES = "evidence-nodes/v1"
SCHEMA_RECEIPTS = "evidence-receipts/v1"

NODE_TYPES = {
    "REQ", "DEC", "MODEL", "STATE", "TRANSITION", "PROP", "THM", "LEAN",
    "MAP", "CODE", "TEST", "TRACE", "OBSERVATION", "ASSUMPTION", "PROBE",
    "ACCEPTANCE", "EVIDENCE",
}

RELATIONS = {
    "REQUIRES", "DERIVED_FROM", "DEFINES", "TRANSITIONS_TO", "GUARDED_BY",
    "PROVED_BY", "IMPLEMENTED_BY", "TESTED_BY", "OBSERVED_BY", "ASSUMED_BY",
    "VERIFIED_BY", "ACCEPTED_BY",
}

EVIDENCE_STATUSES = {
    "CURRENT", "STALE", "UNKNOWN", "FAILED", "DEFERRED", "NOT_APPLICABLE",
}

# 证据可信层级（不得互相伪装；本编译器只在 receipt 明确声明时采信）
EVIDENCE_KINDS = {
    "DOCUMENTED", "DOCUMENTED_CLAIM", "NOT_PROVEN",
    "TEST_DECLARED", "TEST_EXECUTED", "TEST_PASSED", "TEST_FAILED",
    "MODEL_CHECKED_BOUNDED", "PROVEN",
    "IMPLEMENTATION_CONFORMANT", "ASSUMPTIONS_VERIFIED",
    "PRODUCT_ACCEPTED", "UNKNOWN", "STALE", "DEFERRED",
}


class CompileError(Exception):
    """带退出码的编译失败。"""

    def __init__(self, code: int, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


# ---------------------------------------------------------------- utilities

def canonical_json(obj) -> str:
    """确定性序列化（用于 hash 与输出一致性）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_rel_path(project_root: Path, raw: str) -> Path:
    """路径安全：拒绝绝对路径、路径穿越与 ~ 展开。"""
    if not isinstance(raw, str) or raw == "":
        raise CompileError(2, f"非法路径: {raw!r}（空或非字符串）")
    p = Path(raw)
    if p.is_absolute() or raw.startswith("~"):
        raise CompileError(2, f"非法路径（绝对路径/~/网络路径）: {raw}")
    parts = p.parts
    if ".." in parts:
        raise CompileError(2, f"非法路径（含 .. 穿越段）: {raw}")
    resolved = (project_root / p).resolve()
    root_resolved = project_root.resolve()
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise CompileError(2, f"非法路径（穿越出项目根）: {raw}")
    return project_root / p


def read_json_file(path: Path):
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CompileError(2, f"JSON 解析失败: {path}: {exc}") from exc
    except OSError as exc:
        raise CompileError(2, f"文件读取失败: {path}: {exc}") from exc


def git_file_revision(project_root: Path, rel: Path) -> dict:
    """取文件级版本：最近一次触及提交 + 工作区是否偏离该提交。"""
    info = {"git_revision": None, "worktree": "clean"}
    try:
        out = subprocess.run(
            ["git", "log", "-n", "1", "--format=%H", "--", str(rel)],
            cwd=str(project_root), capture_output=True, text=True, timeout=10)
        rev = out.stdout.strip()
        if out.returncode == 0 and rev:
            info["git_revision"] = rev
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        head = subprocess.run(
            ["git", "show", f"HEAD:{rel.as_posix()}"],
            cwd=str(project_root), capture_output=True, timeout=10)
        current = path_bytes(project_root / rel)
        if head.returncode == 0 and head.stdout != current:
            info["worktree"] = "dirty"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return info


def path_bytes(path: Path) -> bytes:
    with path.open("rb") as fh:
        return fh.read()


def check_anchor(text: str, anchor: dict, path: str) -> None:
    """校验 locator 锚点确实存在于权威源文件中（防止引用漂移）。"""
    if not anchor:
        return
    kind = anchor.get("kind")
    value = anchor.get("value")
    if kind == "heading":
        for line in text.splitlines():
            if line.strip().startswith(str(value)):
                return
        raise CompileError(2, f"锚点缺失（heading）: {path}: {value!r}")
    if kind == "contains":
        if str(value) not in text:
            raise CompileError(2, f"锚点缺失（contains）: {path}: {value!r}")
        return
    if kind == "regex":
        if not re.search(str(value), text):
            raise CompileError(2, f"锚点缺失（regex）: {path}: {value!r}")
        return
    raise CompileError(2, f"未知锚点类型: {kind}（{path}）")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


# ---------------------------------------------------------------- loading

class Project:
    """一次编译的项目上下文。"""

    def __init__(self, root: Path):
        self.root = root
        manifest_path = (root / "evidence" / "manifest.json")
        if not manifest_path.is_file():
            # 允许 manifest 在根目录的兼容位置
            alt = root / "evidence-graph.manifest.json"
            if alt.is_file():
                manifest_path = alt
            else:
                raise CompileError(
                    2, f"缺少 evidence/manifest.json: {root}")
        self.manifest_path = manifest_path
        self.manifest = read_json_file(manifest_path)
        if self.manifest.get("schema") != SCHEMA_MANIFEST:
            raise CompileError(2, f"manifest schema 不支持: "
                                 f"{self.manifest.get('schema')!r}")
        self.name = self.manifest.get("project") or root.name
        self.repository = self.manifest.get("repository", "")
        self.outputs_rel = Path(self.manifest.get("outputs", ".evidence"))
        self.policy = self.manifest.get("policy", {}) or {}
        self.fail_on = set(self.policy.get("fail_on", [
            "duplicate_id", "dangling_required_ref", "req_without_model",
            "prop_unproven_and_not_deferred", "transition_without_map",
            "dangling_code_mapping",
        ]))
        self.fail_on_stale = bool(self.policy.get("fail_on_stale", True))
        self.environment_scope = self.manifest.get("environment_scope", {}) or {}
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.receipts: list[dict] = []
        # 来源文件缓存：path -> {content, sha256, git_revision, worktree}
        self.file_cache: dict[str, dict] = {}

    # ---- source files ----

    def load_source(self, rel: Path, anchor=None) -> dict:
        key = rel.as_posix()
        if key not in self.file_cache:
            full = safe_rel_path(self.root, key)
            if not full.is_file():
                raise CompileError(2, f"权威源文件不存在: {key}")
            data = path_bytes(full)
            text = data.decode("utf-8", errors="replace")
            git = git_file_revision(self.root, rel)
            self.file_cache[key] = {
                "path": key,
                "content": text,
                "sha256": sha256_bytes(data),
                "git_revision": git["git_revision"],
                "worktree": git["worktree"],
            }
        entry = dict(self.file_cache[key])
        if anchor:
            check_anchor(entry["content"], anchor, key)
        return entry

    def load_source_or_none(self, rel_str: str, anchor=None):
        try:
            full = safe_rel_path(self.root, rel_str)
        except CompileError:
            return None
        if not full.is_file():
            return None
        return self.load_source(Path(rel_str), anchor)

    # ---- declaration sets (nodes/edges) ----

    def load_declarations(self) -> None:
        sources = self.manifest.get("node_sources", []) or []
        if not sources:
            raise CompileError(2, "manifest.node_sources 为空：没有可编译的声明源")
        for src in sources:
            rel_str = src.get("path")
            anchor = src.get("anchor")
            entry = self.load_source(Path(rel_str), anchor)
            data = read_json_file(safe_rel_path(self.root, rel_str))
            if data.get("schema") != SCHEMA_NODES:
                raise CompileError(2, f"nodes schema 不支持: {rel_str}: "
                                     f"{data.get('schema')!r}")
            for node in data.get("nodes", []) or []:
                self._add_node(node, src, entry)
            for edge in data.get("edges", []) or []:
                self._add_edge(edge, src)

    def _add_node(self, node: dict, src: dict, source_entry: dict) -> None:
        nid = node.get("id")
        if not nid or not isinstance(nid, str):
            raise CompileError(2, f"节点缺少 id: {json.dumps(node, ensure_ascii=False)[:120]}")
        if nid in self.nodes:
            raise CompileError(3, f"重复 ID: {nid}")
        ntype = node.get("type")
        if ntype not in NODE_TYPES:
            raise CompileError(2, f"未知节点类型: {ntype}（{nid}）")
        source = dict(node.get("source", {}) or {})
        # 声明文件自身也是来源的一部分
        source.setdefault("declaration_file", src.get("path"))
        source.setdefault("declaration_sha256", source_entry["sha256"])
        spath = source.get("path")
        if spath:
            entry = self.load_source(Path(spath), source.get("anchor"))
            source["sha256"] = entry["sha256"]
            source["git_revision"] = entry["git_revision"]
            source["worktree"] = entry["worktree"]
        evidence_status = node.get("evidence_status", "DOCUMENTED")
        if evidence_status not in EVIDENCE_KINDS:
            raise CompileError(2, f"非法 evidence_status: {evidence_status}（{nid}）")
        self.nodes[nid] = {
            "id": nid,
            "type": ntype,
            "source": source,
            "attributes": node.get("attributes", {}) or {},
            "evidence_status": evidence_status,
        }

    def _add_edge(self, edge: dict, src: dict) -> None:
        frm = edge.get("from")
        to = edge.get("to")
        rel = edge.get("rel")
        if not frm or not to or rel not in RELATIONS:
            raise CompileError(2, f"非法边（from/to/rel）: "
                                 f"{json.dumps(edge, ensure_ascii=False)[:140]}")
        source = dict(edge.get("source", {}) or {})
        source.setdefault("declaration_file", src.get("path"))
        spath = source.get("path")
        if spath:
            entry = self.load_source(Path(spath), source.get("anchor"))
            source["sha256"] = entry["sha256"]
            source["git_revision"] = entry["git_revision"]
        self.edges.append({"from": frm, "rel": rel, "to": to, "source": source})

    # ---- receipts ----

    def load_receipts(self) -> None:
        for src in self.manifest.get("receipt_sources", []) or []:
            rel_str = src.get("path")
            full = safe_rel_path(self.root, rel_str)
            if not full.is_file():
                # receipt 属于运行期产物：缺失不是解析错误，是 UNKNOWN
                continue
            data = read_json_file(full)
            items = data.get("receipts", []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                raise CompileError(2, f"receipt 文件结构非法: {rel_str}")
            for item in items:
                if item.get("schema") not in (None, SCHEMA_RECEIPTS):
                    raise CompileError(2, f"receipt schema 不支持: {rel_str}")
                if not item.get("evidence_id"):
                    raise CompileError(2, f"receipt 缺 evidence_id: {rel_str}")
                item = dict(item)
                item["_file"] = rel_str
                self.receipts.append(item)


# ---------------------------------------------------------------- freshness

def evaluate_receipt(proj: Project, receipt: dict) -> dict:
    """核对一份执行回执的版本绑定与时效，产出证据记录。

    不运行任何验证器；只做版本一致性、TTL、环境 scope 的核对。
    """
    out = {
        "evidence_id": receipt.get("evidence_id"),
        "evidence_type": receipt.get("evidence_type", "UNKNOWN"),
        "targets": receipt.get("targets", []) or [],
        "executed_at": receipt.get("executed_at"),
        "result": receipt.get("result", "UNKNOWN"),
        "freshness": "UNKNOWN",
        "reasons": [],
        "limitations": receipt.get("limitations", ""),
        "file": receipt.get("_file"),
    }
    reasons = []

    # 1. verifier 自身身份：verifier_file 的当前 hash 必须与回执一致，
    #    否则旧回执不得冒充新版本验证结果（§3.5-6）
    verifier_file = receipt.get("verifier_file")
    if verifier_file:
        entry = proj.load_source_or_none(verifier_file)
        if entry is None:
            reasons.append(f"verifier_file 不存在: {verifier_file}")
        else:
            claimed = receipt.get("verifier_revision")
            if claimed and claimed != entry["sha256"]:
                reasons.append(
                    f"verifier 已变化: 回执={claimed[:12]} 当前={entry['sha256'][:12]}")

    # 2. 版本绑定：bindings[].path 的当前 revision/hash 必须与回执一致
    for binding in receipt.get("bindings", []) or []:
        bpath = binding.get("path")
        entry = proj.load_source_or_none(bpath) if bpath else None
        if entry is None:
            reasons.append(f"绑定文件不存在: {bpath}")
            continue
        claimed_rev = binding.get("revision")
        claimed_hash = binding.get("content_hash")
        if claimed_rev and entry["git_revision"] and claimed_rev != entry["git_revision"]:
            reasons.append(
                f"revision 失配: {bpath} 回执={claimed_rev[:12]} "
                f"当前={entry['git_revision'][:12]}")
        if claimed_hash and claimed_hash != entry["sha256"]:
            reasons.append(
                f"content_hash 失配: {bpath} 回执={claimed_hash[:12]} "
                f"当前={entry['sha256'][:12]}")

    # 3. 显式 model/mapping revision 失配（引用外部仓库版本时使用）
    for key in ("model_revision", "mapping_revision", "target_revision",
                "source_revision"):
        claimed = receipt.get(key)
        current = receipt.get(f"{key}_current")
        if claimed and current and claimed != current:
            reasons.append(f"{key} 失配: 回执={claimed} 当前={current}")

    # 4. TTL（探针等时效性证据）
    executed_at = receipt.get("executed_at")
    ttl_hours = receipt.get("ttl_hours")
    if executed_at and ttl_hours is not None:
        try:
            executed = parse_utc(executed_at)
            age_h = (datetime.now(timezone.utc) - executed).total_seconds() / 3600.0
            if age_h > float(ttl_hours):
                reasons.append(
                    f"TTL 过期: executed_at={executed_at} ttl={ttl_hours}h "
                    f"已过 {age_h:.1f}h")
        except (ValueError, KeyError):
            reasons.append(f"executed_at 格式非法: {executed_at}")

    # 5. 环境 scope 一致性（§3.5-7：只约束 Probe 类证据——环境假设的
    #    有效性与执行环境绑定；Lean 证明等机器无关证据不受 scope 失配影响）
    etype = receipt.get("evidence_type", "UNKNOWN")
    scope = receipt.get("environment_scope")
    if (etype.startswith("PROBE") and scope is not None
            and scope != proj.environment_scope):
        reasons.append(
            "environment_scope 失配: "
            f"回执={canonical_json(scope)[:80]} 当前={canonical_json(proj.environment_scope)[:80]}")

    # 6. 执行结果
    result = receipt.get("result", "UNKNOWN")
    if result == "FAIL" or receipt.get("exit_code") not in (None, 0):
        out["freshness"] = "FAILED"
        if result != "FAIL":
            reasons.append(f"exit_code={receipt.get('exit_code')}")
        out["reasons"] = reasons
        return out

    out["reasons"] = reasons
    if result == "UNKNOWN" or not executed_at:
        out["freshness"] = "UNKNOWN"
        if not executed_at:
            reasons.append("缺 executed_at")
        return out
    out["freshness"] = "STALE" if reasons else "CURRENT"
    return out


# ---------------------------------------------------------------- compile

REQUIRED_REL = {
    # 节点类型 -> 必需的出边关系（策略 prop_unproven 等单独处理）
    "REQ": ("DEFINES",),
    "TRANSITION": ("IMPLEMENTED_BY",),
}


def compile_graph(proj: Project) -> dict:
    """组装图 + 应用校验策略。返回 graph dict；策略缺口记入 proj.violations。"""
    proj.load_declarations()
    proj.load_receipts()

    # 证据评估先于策略检查：PROP 证明判定依赖回执新鲜度
    proj.evaluations = [evaluate_receipt(proj, r) for r in proj.receipts]

    violations = []
    dangling = []

    # 1. 边引用完整性
    for edge in proj.edges:
        for side in ("from", "to"):
            if edge[side] not in proj.nodes:
                dangling.append({
                    "kind": "dangling_reference",
                    "edge": edge,
                    "missing": edge[side],
                })

    # 2. 节点级策略：必需出边
    out_rels: dict[str, set] = {}
    for edge in proj.edges:
        if edge["from"] in proj.nodes:
            out_rels.setdefault(edge["from"], set()).add(edge["rel"])

    for nid, node in proj.nodes.items():
        for req_rel in REQUIRED_REL.get(node["type"], ()):
            if req_rel not in out_rels.get(nid, set()):
                key = ("req_without_model" if node["type"] == "REQ"
                       else "transition_without_map")
                violations.append({
                    "kind": key, "node": nid,
                    "detail": f"{node['type']} 缺少必需关系 {req_rel}",
                })

    # 3. PROP 证明策略：有 PROVED_BY→THM/LEAN（带 CURRENT 证明回执）
    #    或 attributes.obligation_status=DEFERRED，否则缺口
    receipts_by_target: dict[str, list[dict]] = {}
    for ev in proj.evaluations:
        for t in ev["targets"]:
            receipts_by_target.setdefault(t.get("node"), []).append(ev)

    def has_current_proof(nid: str) -> bool:
        for edge in proj.edges:
            if (edge["from"] == nid and edge["rel"] == "PROVED_BY"
                    and edge["to"] in proj.nodes):
                for ev in receipts_by_target.get(edge["to"], []):
                    if ev["freshness"] == "CURRENT":
                        return True
        return False

    for nid, node in proj.nodes.items():
        if node["type"] != "PROP":
            continue
        deferred = (node.get("attributes", {}).get("obligation_status") == "DEFERRED")
        if deferred or has_current_proof(nid):
            continue
        # 有证明回执但全部非 CURRENT → 证据失效类（stale 策略管）；
        # 完全没有（或全 UNKNOWN）→ 未证明义务类
        has_any_proof_receipt = any(
            ev["targets"] and any(t.get("node") == e["to"] for t in ev["targets"])
            for e in proj.edges if e["from"] == nid and e["rel"] == "PROVED_BY"
            and e["to"] in proj.nodes
            for ev in proj.evaluations)
        if has_any_proof_receipt:
            violations.append({
                "kind": "prop_proof_stale", "node": nid,
                "detail": "PROP 的证明回执存在但已 STALE/FAILED/UNKNOWN——需重新验证",
            })
        else:
            violations.append({
                "kind": "prop_unproven_and_not_deferred", "node": nid,
                "detail": "PROP 无 CURRENT 证明回执且未声明 DEFERRED",
            })

    # 4. MAP 目标代码存在性 + 符号锚点（dangling_code_mapping）
    for nid, node in proj.nodes.items():
        if node["type"] != "MAP":
            continue
        target = node.get("attributes", {}).get("code") or {}
        cpath = target.get("path")
        symbol = target.get("symbol")
        if not cpath:
            violations.append({"kind": "dangling_code_mapping", "node": nid,
                               "detail": "MAP 缺少 attributes.code.path"})
            continue
        try:
            entry = proj.load_source(Path(cpath))
        except CompileError as exc:
            violations.append({"kind": "dangling_code_mapping", "node": nid,
                               "detail": f"代码文件不存在: {exc}"})
            continue
        if symbol:
            if not re.search(rf"\b{re.escape(symbol)}\b", entry["content"]):
                violations.append({
                    "kind": "dangling_code_mapping", "node": nid,
                    "detail": f"符号不存在: {cpath}::{symbol}",
                })

    # 5. ACCEPTANCE 必须指向存在的 REQ
    for edge in proj.edges:
        if (edge["rel"] == "ACCEPTED_BY" and edge["to"] not in proj.nodes):
            dangling.append({"kind": "acceptance_missing_req", "edge": edge,
                             "missing": edge["to"]})

    proj.violations = violations
    proj.dangling = dangling

    # ---- 图对象（确定性排序）----
    sorted_nodes = [proj.nodes[k] for k in sorted(proj.nodes)]
    sorted_edges = sorted(
        proj.edges, key=lambda e: (e["from"], e["rel"], e["to"],
                                   canonical_json(e.get("source", {}))))
    sorted_evals = sorted(
        proj.evaluations, key=lambda e: (e["evidence_id"] or "",
                                         canonical_json(e["targets"])))
    graph = {
        "schema": "evidence-graph/v1",
        # 确定性构建标识（输入集+编译器哈希派生）：同一输入重复 build
        # 产物字节一致（§3.6 可复现）；墙钟时间不入图，时间戳以
        # receipt.executed_at 为准
        "build_id": "",
        "compiler_revision": compiler_revision(),
        "project": proj.name,
        "repository": proj.repository,
        "inputs": {
            path: {
                "sha256": v["sha256"],
                "git_revision": v["git_revision"],
                "worktree": v["worktree"],
            }
            for path, v in sorted(proj.file_cache.items())
        },
        "nodes": sorted_nodes,
        "edges": sorted_edges,
        "evidence": sorted_evals,
        "violations": sorted(violations, key=lambda v: canonical_json(v)),
        "dangling": sorted(dangling, key=lambda d: canonical_json(d)),
    }
    graph["build_id"] = sha256_text(canonical_json(
        {k: graph[k] for k in ("schema", "compiler_revision", "project",
                                "repository", "inputs", "nodes", "edges",
                                "evidence", "violations", "dangling")}))[:16]
    return graph


# ---------------------------------------------------------------- reports

def coverage_report(proj: Project, graph: dict) -> dict:
    by_type: dict[str, int] = {}
    for node in graph["nodes"]:
        by_type[node["type"]] = by_type.get(node["type"], 0) + 1

    receipts_by_target: dict[str, list[dict]] = {}
    for ev in graph["evidence"]:
        for t in ev["targets"]:
            receipts_by_target.setdefault(t.get("node"), []).append(ev)

    def chain_status(nid: str, rel: str) -> str:
        """沿关系找到目标节点，汇总其证据新鲜度。"""
        targets = [e["to"] for e in graph["edges"]
                   if e["from"] == nid and e["rel"] == rel]
        if not targets:
            return "MISSING"
        states = set()
        for t in targets:
            evs = receipts_by_target.get(t, [])
            if not evs:
                states.add("UNKNOWN")
            else:
                states |= {ev["freshness"] for ev in evs}
        for bad in ("FAILED", "STALE", "UNKNOWN"):
            if bad in states:
                return bad
        return "CURRENT"

    req_rows = []
    for node in graph["nodes"]:
        if node["type"] != "REQ":
            continue
        models = [e["to"] for e in graph["edges"]
                  if e["from"] == node["id"] and e["rel"] == "DEFINES"]
        req_rows.append({
            "req": node["id"],
            "models": models,
            "model": "COVERED" if models else "MISSING",
            "proof": chain_status(node["id"], "PROVED_BY"),
            "implementation": chain_status(node["id"], "IMPLEMENTED_BY"),
            "tests": chain_status(node["id"], "TESTED_BY"),
            "acceptance": chain_status(node["id"], "ACCEPTED_BY"),
        })

    prop_rows = []
    for node in graph["nodes"]:
        if node["type"] != "PROP":
            continue
        deferred = node.get("attributes", {}).get("obligation_status") == "DEFERRED"
        proof_edges = [e["to"] for e in graph["edges"]
                       if e["from"] == node["id"] and e["rel"] == "PROVED_BY"]
        states = set()
        for t in proof_edges:
            evs = receipts_by_target.get(t, [])
            states |= {ev["freshness"] for ev in evs} if evs else {"UNKNOWN"}
        if deferred:
            state = "DEFERRED"
        elif "CURRENT" in states:
            state = "PROVEN_EVIDENCE_CURRENT"
        elif "STALE" in states:
            state = "STALE"
        elif "FAILED" in states:
            state = "FAILED"
        else:
            state = "UNPROVEN"
        prop_rows.append({"prop": node["id"], "state": state,
                          "obligation_status":
                              node.get("attributes", {}).get("obligation_status", "")})

    stale_list = [ev for ev in graph["evidence"] if ev["freshness"] == "STALE"]
    return {
        "schema": "evidence-coverage/v1",
        "build_id": graph["build_id"],
        "compiler_revision": graph["compiler_revision"],
        "project": graph["project"],
        "node_counts": dict(sorted(by_type.items())),
        "edge_count": len(graph["edges"]),
        "evidence_count": len(graph["evidence"]),
        "evidence_freshness": {
            s: sum(1 for ev in graph["evidence"] if ev["freshness"] == s)
            for s in ("CURRENT", "STALE", "UNKNOWN", "FAILED")
        },
        "requirements": sorted(req_rows, key=lambda r: r["req"]),
        "properties": sorted(prop_rows, key=lambda r: r["prop"]),
        "stale_evidence_ids": sorted(ev["evidence_id"] or "" for ev in stale_list),
        "violations": graph["violations"],
        "dangling": graph["dangling"],
    }


def stale_report(proj: Project, graph: dict) -> dict:
    stale = []
    for ev in graph["evidence"]:
        if ev["freshness"] in ("STALE", "FAILED"):
            stale.append(ev)
        elif ev["freshness"] == "UNKNOWN":
            stale.append(ev)
    return {
        "schema": "evidence-stale/v1",
        "build_id": graph["build_id"],
        "compiler_revision": graph["compiler_revision"],
        "project": graph["project"],
        "policy_fail_on_stale": proj.fail_on_stale,
        "items": sorted(stale, key=lambda e: e["evidence_id"] or ""),
    }


# ---------------------------------------------------------------- outputs

def compiler_revision() -> str:
    return sha256_bytes(Path(__file__).read_bytes())


def write_outputs(proj: Project, graph: dict) -> dict:
    out_dir = safe_rel_path(proj.root, proj.outputs_rel.as_posix())
    out_dir.mkdir(parents=True, exist_ok=True)
    coverage = coverage_report(proj, graph)
    stale = stale_report(proj, graph)
    dangling = {
        "schema": "evidence-dangling/v1",
        "build_id": graph["build_id"],
        "compiler_revision": graph["compiler_revision"],
        "project": graph["project"],
        "items": graph["dangling"] + [
            {"kind": v["kind"], "node": v.get("node"), "detail": v["detail"]}
            for v in graph["violations"]
        ],
    }
    files = {
        "evidence-graph.json": graph,
        "coverage-report.json": coverage,
        "dangling-links.json": dangling,
        "stale-evidence.json": stale,
    }
    for name, payload in files.items():
        (out_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n", encoding="utf-8")
    return files


# ---------------------------------------------------------------- commands

def load_project(args) -> Project:
    root = Path(args.project).resolve()
    if not root.is_dir():
        raise CompileError(7, f"项目目录不存在: {root}")
    return Project(root)


def cmd_build(args) -> int:
    proj = load_project(args)
    graph = compile_graph(proj)
    write_outputs(proj, graph)
    print(f"build: nodes={len(graph['nodes'])} edges={len(graph['edges'])} "
          f"evidence={len(graph['evidence'])} violations={len(graph['violations'])} "
          f"dangling={len(graph['dangling'])} -> {proj.outputs_rel}")
    violations = graph["violations"] + graph["dangling"]
    for v in violations:
        print(f"  VIOLATION {v.get('kind')}: "
              f"{v.get('node') or v.get('missing') or ''} {v.get('detail', '')}")
    if any(v["kind"] in proj.fail_on for v in graph["dangling"]):
        return 4
    for d in graph["dangling"]:
        if d["kind"] in ("dangling_reference", "acceptance_missing_req"):
            return 4
    codes = {
        "duplicate_id": 3,
        "dangling_required_ref": 4,
        "dangling_code_mapping": 4,
        "req_without_model": 5,
        "prop_unproven_and_not_deferred": 5,
        "transition_without_map": 5,
        "prop_proof_stale": 6,
    }
    for v in graph["violations"]:
        if v["kind"] in proj.fail_on:
            if v["kind"] == "prop_proof_stale" and not proj.fail_on_stale:
                continue
            return codes.get(v["kind"], 5)
    return 0


def cmd_validate(args) -> int:
    proj = load_project(args)
    graph = compile_graph(proj)
    write_outputs(proj, graph)  # validate 同样落盘派生物，便于审计
    stale = [ev for ev in graph["evidence"] if ev["freshness"] == "STALE"]
    print(f"validate: nodes={len(graph['nodes'])} evidence={len(graph['evidence'])} "
          f"stale={len(stale)} violations={len(graph['violations'])} "
          f"dangling={len(graph['dangling'])}")
    for ev in stale:
        print(f"  STALE {ev['evidence_id']}: {'; '.join(ev['reasons'])[:160]}")
    for v in graph["violations"] + graph["dangling"]:
        print(f"  VIOLATION {v.get('kind')}: "
              f"{v.get('node') or v.get('missing') or ''} {v.get('detail', '')}")
    for d in graph["dangling"]:
        if d["kind"] in ("dangling_reference", "acceptance_missing_req"):
            return 4
    if any(d["kind"] in proj.fail_on for d in graph["dangling"]):
        return 4
    codes = {"duplicate_id": 3, "dangling_required_ref": 4,
             "dangling_code_mapping": 4, "req_without_model": 5,
             "prop_unproven_and_not_deferred": 5, "transition_without_map": 5,
             "prop_proof_stale": 6}
    for v in graph["violations"]:
        if v["kind"] in proj.fail_on:
            if v["kind"] == "prop_proof_stale" and not proj.fail_on_stale:
                continue
            return codes.get(v["kind"], 5)
    if proj.fail_on_stale and stale:
        return 6
    return 0


def cmd_coverage(args) -> int:
    proj = load_project(args)
    graph = compile_graph(proj)
    write_outputs(proj, graph)
    cov = coverage_report(proj, graph)
    print(canonical_json({
        "node_counts": cov["node_counts"],
        "evidence_freshness": cov["evidence_freshness"],
        "requirements": len(cov["requirements"]),
        "properties": len(cov["properties"]),
    }))
    return 0


def cmd_stale(args) -> int:
    proj = load_project(args)
    graph = compile_graph(proj)
    write_outputs(proj, graph)
    stale = [ev for ev in graph["evidence"] if ev["freshness"] == "STALE"]
    for ev in stale:
        print(f"STALE {ev['evidence_id']}: {'; '.join(ev['reasons'])[:200]}")
    if proj.fail_on_stale and stale:
        return 6
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence_graph.py",
        description="Evidence Graph Compiler (Batch 1) — 派生追溯图，非事实源")
    sub = parser.add_subparsers(dest="command")
    for name in ("build", "validate", "coverage", "stale"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True, help="项目根目录")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 7
    handlers = {"build": cmd_build, "validate": cmd_validate,
                "coverage": cmd_coverage, "stale": cmd_stale}
    try:
        return handlers[args.command](args)
    except CompileError as exc:
        print(f"ERROR({exc.code}): {exc.message}", file=sys.stderr)
        for d in exc.details:
            print(f"  {d}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
