# Evidence Graph Compiler 使用指南

> Graph 是**派生索引**，不是事实源。权威事实只存在于各仓库的原始文件
> （Spec、模型、Lean 源、代码、测试、执行回执）。编译器只做三件事：
> 读取权威源 → 校验引用与版本绑定 → 生成可检查的追溯图与报告。

## 1. 接入一个新项目（三步）

```text
<project>/
  evidence/
    manifest.json          # 编译入口：声明项目、来源、策略
    nodes/*.json           # 节点/边声明（引用权威源，不复制权威源）
    receipts/*.json        # 执行回执（测试/Lean/探针的真实运行记录）
```

```bash
python3 tools/evidence_graph.py build    --project <project>
python3 tools/evidence_graph.py validate --project <project>
python3 tools/evidence_graph.py coverage --project <project>
python3 tools/evidence_graph.py stale    --project <project>
```

输出（全部派生物，写入 `evidence/manifest.json` 的 `outputs`，默认 `.evidence/`）：

| 文件 | 内容 |
|---|---|
| `evidence-graph.json` | 全量节点/边/证据/违规 |
| `coverage-report.json` | REQ 覆盖矩阵 + PROP 状态 |
| `dangling-links.json` | 悬空引用与策略缺口 |
| `stale-evidence.json` | STALE/FAILED/UNKNOWN 证据清单 |

## 2. manifest（编译入口，不含业务事实）

```json
{
  "schema": "evidence-graph-manifest/v1",
  "project": "codex-go",
  "repository": "mayf3/codex-go",
  "outputs": ".evidence",
  "environment_scope": {"os": "android", "arch": "arm64", "device": "honor"},
  "policy": {
    "fail_on": ["duplicate_id", "dangling_required_ref", "req_without_model",
                 "prop_unproven_and_not_deferred", "transition_without_map",
                 "dangling_code_mapping"],
    "fail_on_stale": true
  },
  "node_sources":    [{"path": "evidence/nodes/core.json"}],
  "receipt_sources": [{"path": "evidence/receipts/tests.json"}]
}
```

- `environment_scope`：Probe 类证据的有效环境。回执的 scope 与它不一致 → 该
  Probe 证据 STALE（Lean 等机器无关证据不受 scope 约束）。
- `policy.fail_on`：哪些缺口算失败（退出码见 §8）。可选层缺失用 UNKNOWN
  如实报告，不伪装 PASS，也不强制失败。

## 3. 节点与边声明（evidence/nodes/*.json）

**只声明引用和关系，不复制 Spec / 不重定义业务状态机。** 每个节点/边的
`source` 必须指向权威源文件；`anchor` 让编译器核对锚点确实存在（防漂移）。

```json
{
  "schema": "evidence-nodes/v1",
  "nodes": [
    {"id": "REQ-ENGINE-001", "type": "REQ",
     "source": {"path": "docs/formal-model.md",
                "anchor": {"kind": "contains", "value": "FSM-E"}},
     "evidence_status": "DOCUMENTED"},
    {"id": "PROP-FSM-E-LIVENESS", "type": "PROP",
     "source": {"path": "docs/formal-model.md",
                "anchor": {"kind": "contains", "value": "定理"}},
     "attributes": {"obligation_status": "DEFERRED"}},
    {"id": "MAP-STOP-BRIDGE", "type": "MAP",
     "source": {"path": "android/app/src/main/kotlin/com/codexgo/app/engine/EngineBridge.kt"},
     "attributes": {"code": {"path": "android/.../EngineBridge.kt",
                             "symbol": "stopEngine"}}}
  ],
  "edges": [
    {"from": "REQ-ENGINE-001", "rel": "DEFINES", "to": "MODEL-FSM-E",
     "source": {"path": "docs/formal-model.md"}}
  ]
}
```

锚点类型：`contains` / `heading`（以行首匹配）/ `regex`。

### 稳定 ID 约定

- 前缀即类型：`REQ-` `DEC-` `MODEL-` `STATE-` `TRANS-` `PROP-` `THM-`
  `LEAN-` `MAP-` `CODE-` `TEST-` `TRACE-` `PROBE-` `ACC-`。
- ID 一经引用不得改名；重命名 = 悬空引用（编译器退出码 4）。
- 跨项目引用用完整 ID + `source.repository` 区分。

### 节点类型与关系

节点：REQ DEC MODEL STATE TRANSITION PROP THM LEAN MAP CODE TEST TRACE
OBSERVATION ASSUMPTION PROBE ACCEPTANCE EVIDENCE。
关系：REQUIRES DERIVED_FROM DEFINES TRANSITIONS_TO GUARDED_BY PROVED_BY
IMPLEMENTED_BY TESTED_BY OBSERVED_BY ASSUMED_BY VERIFIED_BY ACCEPTED_BY。
策略默认：REQ 必须有 `DEFINES`→MODEL；TRANSITION 必须有 `IMPLEMENTED_BY`；
PROP 必须有 CURRENT 证明回执或 `attributes.obligation_status=DEFERRED`。

### MAP（代码映射）

`attributes.code.path` 必须存在（退出码 4），`symbol` 必须能在该文件中
找到（同一检查）。映射变化 = 代码坐标变化 → 相关证据重新评估。

## 4. 执行回执（evidence/receipts/*.json）

**回执 = 一次真实执行的记录。编译器不运行任何验证器**——它只核对回执的
版本绑定。没有回执 = 没有证据。

```json
{"schema": "evidence-receipts/v1", "receipts": [
  {"schema": "evidence-receipts/v1",
   "evidence_id": "EV-TEST-001",
   "evidence_type": "TEST_PASSED",
   "targets": [{"node": "TEST-ENGINE-STOP", "rel": "VERIFIED_BY"}],
   "bindings": [{"kind": "code", "path": "android/.../EngineBridge.kt",
                 "content_hash": "<sha256 of file>"},
                {"kind": "model", "path": "docs/formal-model.md",
                 "revision": "<git sha>"}],
   "verifier_file": "tools/run_tests.sh",
   "verifier_revision": "<sha256 of verifier script>",
   "toolchain": "gradle-8.14/jdk21",
   "command": "gradle :app:testDebugUnitTest",
   "exit_code": 0,
   "executed_at": "2026-11-28T00:00:00Z",
   "result": "PASS",
   "ttl_hours": null,
   "environment_scope": {"os": "android", "arch": "arm64"},
   "limitations": "有界单测，非一般性证明"}
]}
```

### 新鲜度判定（编译器自动执行）

| 条件 | freshness |
|---|---|
| 所有绑定 hash/revision 一致、无 TTL、scope 一致 | `CURRENT` |
| 任一绑定失配 / 显式 model_revision 失配 / verifier 已变化 | `STALE` |
| `exit_code != 0` 或 `result=FAIL` | `FAILED` |
| 缺 `executed_at` 或 `result=UNKNOWN` | `UNKNOWN` |
| Probe 且 `executed_at + ttl_hours` 已过 | `STALE` |
| Probe 且 environment_scope 与 manifest 不一致 | `STALE` |

### 可信边界（禁止互相伪装）

| 标记 | 含义 |
|---|---|
| `DOCUMENTED` | 权威文档记载（非执行证据） |
| `DOCUMENTED_CLAIM` | 文档声称的性质（如 formal-model.md 的定理描述）——**不是** Lean 证明 |
| `NOT_PROVEN` | 无 Lean 编译回执 |
| `TEST_DECLARED` | 测试源存在，从未执行 |
| `TEST_EXECUTED` | 有执行记录但结果未知 |
| `TEST_PASSED` | 有 exit=0 的真实回执 |
| `MODEL_CHECKED_BOUNDED` | 有界模型检查回执 |
| `PROVEN` | Lean 编译审计回执（CURRENT） |
| `UNKNOWN` / `STALE` / `DEFERRED` | 如实报告，不压缩为 PASS |

## 5. 关联 Lean 定理

1. THM 节点：文档级定理描述，`evidence_status: NOT_PROVEN`（直到有编译回执）。
2. LEAN 节点：Lean 源码中的 declaration，source 指向 `.lean` 文件。
3. PROP `PROVED_BY` LEAN 节点。
4. 回执：`bindings[].path` 指向 `.lean` 文件 + `content_hash`；或直接绑定
   primitives 的 `lean-verification.json`（其 `source_sha256` 即逐文件哈希）；
   `verifier_file: tools/verify_lean.py` + 其哈希——**验证器被修改后旧回执
   自动 STALE**。

## 6. Trace / Probe（Batch 2 预留接口）

- TRACE 节点：`source.path` 指向 trace 原始记录 + `locator`；回执由未来的
  Trace Validator 生成，schema 同 `evidence-receipts/v1`，`evidence_type`
  建议 `TRACE_VERIFIED`。
- PROBE 节点 + 回执：`evidence_type` 以 `PROBE` 开头、`ttl_hours` 必填、
  `environment_scope` 必须与 manifest 一致——否则自动 STALE。
- 无需改编译器：新输入类型只是新的节点声明 + 回执文件。

## 7. 退出码（build / validate）

| 码 | 含义 |
|---|---|
| 0 | 通过（UNKNOWN/DEFERRED 存在不算失败，如实报告） |
| 2 | 权威输入解析失败 / manifest 非法 / 路径穿越 |
| 3 | 重复 ID |
| 4 | 悬空必需引用 / 悬空代码映射（文件或符号不存在）/ Acceptance 指错 REQ |
| 5 | 策略缺口：REQ 无 MODEL / PROP 未证明且未 DEFERRED / TRANSITION 无 MAP |
| 6 | 存在 STALE 证据且 `policy.fail_on_stale=true`（或 prop_proof_stale） |
| 7 | CLI 用法错误 |

`coverage` / `stale` 命令只报告不设策略门（`stale` 在 `fail_on_stale` 时
返回 6）。

## 8. 最小可运行示例

```bash
mkdir -p demo/evidence/nodes demo/evidence/receipts demo/docs demo/src
cat > demo/docs/spec.md <<'EOF'
# SPEC-1 计数器需求
计数器必须可递增且不可越过上限。
EOF
cat > demo/src/counter.py <<'EOF'
class Counter:
    def inc(self): ...
EOF
cat > demo/evidence/nodes/core.json <<'EOF'
{"schema": "evidence-nodes/v1",
 "nodes": [
   {"id": "REQ-1", "type": "REQ",
    "source": {"path": "docs/spec.md", "anchor": {"kind": "contains", "value": "SPEC-1"}}},
   {"id": "MODEL-COUNTER", "type": "MODEL",
    "source": {"path": "docs/spec.md", "anchor": {"kind": "contains", "value": "上限"}}},
   {"id": "MAP-INC", "type": "MAP",
    "source": {"path": "src/counter.py"},
    "attributes": {"code": {"path": "src/counter.py", "symbol": "inc"}}}],
 "edges": [
   {"from": "REQ-1", "rel": "DEFINES", "to": "MODEL-COUNTER",
    "source": {"path": "docs/spec.md"}}]}
EOF
cat > demo/evidence/manifest.json <<'EOF'
{"schema": "evidence-graph-manifest/v1", "project": "demo",
 "node_sources": [{"path": "evidence/nodes/core.json"}],
 "receipt_sources": []}
EOF
python3 tools/evidence_graph.py validate --project demo   # exit 0（无 REQ 违规）
```

真实接入以 codex-go 试点（`feat/evidence-graph-pilot` 分支）为准。

## 9. 确定性与审计

- 重复 build：输出字节一致（`build_id` 由输入集+编译器哈希派生，墙钟不入图）。
- 图内 `inputs` 记录每个权威文件的 `sha256 / git_revision / worktree(dirty)`。
- `compiler_revision` = 编译器自身 sha256——编译器升级后，旧回执若绑定旧
  编译器哈希即 STALE，不得冒充新版本验证结果。
- 人工篡改 `.evidence/` 下任何文件，重新 build 即恢复（派生物可随时再生）。
