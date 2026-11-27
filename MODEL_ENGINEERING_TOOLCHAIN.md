# Model Engineering Toolchain：从研究结论到可运行工程

**版本：v0.1.0 · 2026-11-27 · 定位：参考实施架构，不是所有项目的强制工具清单**

本文回答“工程上具体用什么、怎么连、CI 产出什么”。它补充 [以数学模型为中心的开发规范](MODEL_CENTERED_DEVELOPMENT.md)、[模型—实现精化与环境前提验证](MODEL_IMPLEMENTATION_CONFORMANCE.md) 和 [研究沉淀](RESEARCH_SPEC_MODEL_PROOF_CODE_2026-11.md)。工具应按问题选择，不应为了工具覆盖率把每个项目都变成形式化项目。

## 1. 推荐的分层工具链

| 层 | 首选工具/格式 | 作用 | 适用边界 |
|---|---|---|---|
| Product Spec / Authority | 项目现有 Spec + 稳定 ID + Markdown/YAML frontmatter | 保存目标、约束、正反例、验收和权威版本 | 语义仍由 Owner/Reviewer 决定 |
| 结构/可满足性探索 | Alloy 6 | 查找有限范围实例、矛盾和结构反例 | scope 有限；不是代码验证 |
| 状态机规格 | Quint；已有 TLA+ 项目继续用 TLA+ | 表达状态、事件、动作、不变量、活性和假设 | 不强制所有项目迁移语言 |
| 显式状态模型检查 | TLC | 有限状态空间穷举与反例 | 状态空间需可枚举 |
| 符号/有界模型检查 | Apalache | SMT-based bounded checking、inductiveness 检查 | 有限参数/有限结构；bounded 结果必须标记边界 |
| 数学定理 | Lean 4（共享参数化核心 + 项目实例） | 证明关键模型性质、抽象 refinement lemma | 不自动证明 Dart/Kotlin 生产代码 |
| Model-Based Testing | Quint Connect（Rust）；其他语言用同一模型协议写 adapter | 模型生成事件序列并执行真实实现 | Quint Connect 官方集成聚焦 Rust |
| 语言原生 PBT | Python Hypothesis；Kotlin Kotest；Rust proptest；TypeScript fast-check；Dart package:test + 受控 stateful harness，评估 property_testing/kiri_check | 生成命令序列、比较模型与 SUT、缩减反例 | 各库的状态机能力、异步调度和成熟度不同，需试点 |
| Runtime Trace | JSONL correctness events + OpenTelemetry context/links | 记录状态转移、版本、因果和观察 | OTel 不保证采集完整；correctness ledger 另行设计 |
| Evidence Graph | Python compiler + JSON Schema + graph checks | 从源注释/manifest 派生 canonical graph | 不引入手工维护的中央事实源 |
| CI / 独立验证 | GitHub Actions 或项目已有 CI，固定工具链和 verifier identity | 绑定精确 revision，执行 build/check/test/negative controls | 需要保护验证器、权限与 required checks |

### 为什么不是只选一个工具？

- Quint/TLA+/Alloy 擅长模型探索和反例发现。
- Lean 擅长证明精确数学命题。
- Verus/Dafny/F* 适合在特定语言/核心实现上做程序验证。
- Quint Connect、PBT 和 Trace Validator 把抽象模型连接到真实实现。
- OpenTelemetry 解决跨服务关联，不解决完整性证明。
- Evidence Graph 解决追溯和失效计算，不决定语义正确性。

## 2. 可立即使用的工具

### 2.1 Quint CLI + Apalache/TLC

安装（npm）：

```bash
npm install --global @informalsystems/quint
quint --version
quint typecheck path/to/model.qnt
```

常用工作流：

```bash
# 随机模拟并检查不变量
quint run path/to/model.qnt --invariant SafetyInvariant --max-steps 100

# 符号/模型检查（后端按安装版本与 CLI help 选择 Apalache/TLC）
quint verify path/to/model.qnt --invariant SafetyInvariant

# 查看本机支持的准确选项，避免复制过时 CLI 参数
quint verify --help
quint run --help
```

Quint 的 MBT 文档有旧版 ITF trace generation 教程；官方文档已提示 Rust 项目优先迁移到 Quint Connect。不要把旧教程里的 adapter API 直接当成当前稳定接口。

### 2.2 Quint Connect（Rust 首选连接器）

仓库： https://github.com/quint-co/quint-connect

用于从 Quint 模型生成 traces，并将其回放到 Rust 实现，检查实现状态是否与模型预期相符。先在 Rust 试点中采用官方示例；不要宣称它已为 Dart/Kotlin 提供同等级官方 adapter。其他语言应实现本仓库定义的 adapter contract，而不是伪造已有兼容性。

### 2.3 Apalache 与 TLC 的选择

- TLC：适合有限、可枚举状态空间；明确记录状态数、参数域、约束和穷举范围。
- Apalache：把模型转成 SMT 约束，适合 bounded exploration 和 inductiveness 检查；必须记录 bound 和 solver/tool version。
- 两者均不能自动证明自然语言 Spec 忠实性。
- 对 bounded check，输出状态必须是 `MODEL_CHECKED_BOUNDED`，不得写 `PROVEN`。

### 2.4 Alloy 6

官网：https://alloytools.org/documentation.html

适合在需求和模型早期探索关系结构、约束可满足性、非法组合和小范围反例。把 `run` 的实例存在性与 `check` 的反例搜索分开记录。每份结果绑定 scope；scope 外不做一般性结论。

### 2.5 语言原生状态属性测试

| 语言 | 工具 | 推荐用途 |
|---|---|---|
| Python | Hypothesis RuleBasedStateMachine | 命令序列、状态化操作、自动缩减反例 |
| Kotlin | Kotest property testing；必要时自建 command model runner | 属性生成；异步/并发需额外 scheduler/fault harness |
| Rust | proptest；与 Quint Connect 组合 | 状态化生成、shrinking、模型轨迹回放 |
| TypeScript | fast-check model-based testing，必要时 asyncModelRun / scheduledModelRun | 同时运行 model 与 real system，重放 seed/path |
| Dart/Flutter | 先用 package:test 实现确定性 command runner；再评估 property_testing 或 kiri_check | 适配当前应用状态核；第三方库先做小型 API/维护活跃度验证 |

这些工具不是跨语言统一标准。最重要的是统一事件/命令/观察协议和回执格式，而不是要求所有语言使用同一测试库。

### 2.6 Lean 4

沿用仓库现有固定 Lean toolchain、`lake build` 和 `tools/verify_lean.py`。每个关键 theorem 必须记录：
- theorem ID 和对应 PROP/REQ；
- 模型 revision；
- Lean source revision 与 toolchain；
- transitive axiom audit（如 `#print axioms theoremName`）；
- 是否有 `sorryAx` / 未批准 axiom；
- 未覆盖前提和非形式化边界。

Lean 通过只说明形式命题在当前定义和前提下成立，不代表 Model Fidelity 或 Product Acceptance 自动通过。

## 3. 项目统一 Adapter Contract

每个消费项目实现一个很薄的 adapter，将项目具体实现暴露给公共测试 runner：

```text
snapshot() -> ConcreteSnapshot
abstractState(snapshot, MAP_ID) -> AbstractState
execute(command, TEST_CONTEXT) -> ExecutionResult
normalize(event, MAP_ID) -> ModelEvent | Invisible
observe(result, OBSERVATION_ID) -> Observation
reset(seed, environmentProfile) -> ResetReceipt
```

最低要求：

- adapter 不能读取测试模型的内部状态来伪造 SUT observation；
- model oracle 和真实实现必须独立运行；
- 每个命令保留 seed、序列、transition ID、code/model/map revisions；
- `Invisible` 必须有 stuttering justification；
- reset 必须验证环境真的回到声明初态；
- 外部副作用结果未知时保留 UNKNOWN，不得伪装成功或安全重试。

## 4. Correctness Trace Protocol

OpenTelemetry 用于 TraceId/SpanId/parent/links 的跨进程关联；业务正确性日志另有 schema。建议 JSONL 至少包含：

```json
{
  "schema_version": "model-trace/v1",
  "trace_id": "TRACE-opaque",
  "event_id": "opaque-event-id",
  "producer_id": "engine",
  "producer_epoch": 3,
  "seq": 42,
  "span_id": "otel-span-id",
  "causal_parent_ids": ["event-41"],
  "transition_id": "TR-ENGINE-PROCESS-DIED",
  "from_observed": "RUNNING",
  "event": "PROCESS_DIED",
  "to_observed": "DEGRADED",
  "code_revision": "git-sha",
  "model_revision": "git-sha",
  "mapping_revision": "git-sha",
  "verifier_revision": "git-sha",
  "environment_profile": "sanitized-profile",
  "segment_complete": false,
  "payload_hash": "sha256"
}
```

完整性协议：

1. 同一 producer 按 `(producer_epoch, seq)` 建立顺序。
2. 不同 producer 只要求 causal partial order；fan-out/batch 允许多个 cause links。
3. event_id 去重；重复事件必须确定性处理。
4. segment close/watermark 明确采集区间已经封闭。
5. sequence gap、parent 缺失、producer epoch 未闭合、watermark 未关闭或采集失败 → `TRACE_INCOMPLETE` / `UNKNOWN`。
6. transition 不允许、状态映射失败、revision 不匹配 → `TRACE_DRIFTED` / `STALE`。
7. 保存原始 trace、归一化 trace、normalizer revision、hash 和重放入口。

注意：OpenTelemetry 的 trace 数据模型明确承认 sampling、drop、export delay、query slicing 会造成 partial trace；存在全部已知 parent 也不能证明所有预期 child 都采集到了。因此 OTel trace 不能直接充当完整性证明。

## 5. Evidence Graph Compiler（建议自研的最小工具）

当前没有发现一个通用现成工具，能够自动完成我们需要的 REQ→MODEL→THM→MAP→CODE→TRACE→PROBE→ACC 语义追溯与失效计算。不要强行拼接一个现成 graph UI 代替它。

建议从 Python 标准库实现一个小型 compiler：

输入：
- Spec frontmatter / stable IDs；
- 模型 source annotations；
- Lean theorem manifest；
- adapter mapping manifest；
- test/trace receipts；
- assumption/probe receipts；
- acceptance receipt。

输出：
- `evidence-graph.json`（只读派生物）；
- `dangling-links.json`；
- `coverage-report.json`；
- `stale-evidence.json`；
- HTML/SVG visualization（后续再做）。

首批机械检查：
- ID 重复、引用悬空；
- 关键 REQ 无 MODEL/ACC；
- 关键 PROP 无 THM 或显式 defer；
- required transition 无 MAP；
- MAP 指向不存在的 code symbol；
- evidence 引用错误 revision；
- required assumption 无 probe 或过期；
- success path 缺失；
- negative control 被模型接受、positive witness 被模型拒绝。

Compiler 只检查声明关系和确定性规则，不判断 Spec 是否符合用户真实意图。语义审查仍归 Owner/Reviewer。

## 6. 推荐 CI Pipeline

```text
0. Freeze coordinates
   Spec / Model / Lean / Code / Mapping / Verifier / Toolchain / Environment
       ↓
1. Spec & graph integrity
   duplicate IDs / dangling links / bidirectional coverage / authority hash
       ↓
2. Model sanity
   typecheck / satisfiable initial state / success witness / negative scenarios
       ↓
3. Model exploration
   TLC exhaustive finite scope OR Apalache bounded/inductive checks
       ↓
4. Lean proof
   clean lake build / theorem IDs / #print axioms / sorryAx audit
       ↓
5. Adapter + model-based tests
   legal traces / illegal traces / PBT / replayable seeds / shrinking
       ↓
6. Runtime trace validation
   schema / transition legality / causal order / completeness / exact revisions
       ↓
7. Assumption probes
   PASS / FAIL / UNKNOWN / expiry / scope hash / failure-state behavior
       ↓
8. Independent negative controls
   illegal transition -> FAIL
   missing trace event -> UNKNOWN
   stale model/code/verifier -> STALE
   expired assumption -> guarantee withdrawn
       ↓
9. Original acceptance
   execute original ACC in target environment
```

每个 stage 输出 typed receipt；不允许一个 aggregate green badge 抹平不同保证等级。

## 7. 工具和证据状态词汇

至少区分：

- `PROVEN`：精确 theorem 在指定 Lean/kernel/axioms 下通过。
- `MODEL_CHECKED_EXHAUSTIVE_WITHIN_SCOPE`：已穷举声明的有限模型范围。
- `MODEL_CHECKED_BOUNDED`：只检查到明确 bound。
- `PROGRAM_VERIFIED`：指定程序片段通过代码级验证。
- `TRACE_CONFORMANT`：完整性已确认的记录轨迹符合模型。
- `TRACE_INCOMPLETE`：轨迹完整性不足。
- `TRACE_DRIFTED`：轨迹中出现模型不允许的行为。
- `TESTED` / `SIMULATED`：有限测试/模拟范围通过。
- `ASSUMPTIONS_VALID`：声明环境快照和有效期内的前提有证据。
- `ACCEPTED`：原始需求验收完成。
- `UNKNOWN` / `STALE`：没有足够当前证据。

这些是独立 claim 类型，不是从低到高自动升级的状态机。

## 8. codex-go P0 试点建议

第一轮只选择 FSM-E / FSM-UI 的关键生命周期切片：
- 6–10 个状态；
- 10–20 个关键转移；
- 至少一条正常完成路径；
- 至少一条历史故障/恢复路径；
- 关键 safety properties；
- liveness 暂时只在前提明确时声明。

必须有三个验证器负控：
1. 注入非法状态转移 → `TRACE_DRIFTED`。
2. 删除一个关键中间事件 → `TRACE_INCOMPLETE`，不能 PASS。
3. 让关键环境探针过期/失败 → 相关保证降级为 `STALE/UNKNOWN` 或项目定义的 `DEGRADED/BLOCKED`。

最后使用原始 REQ/ACC 验收。P0 通过仅证明这条样板路径闭环，不宣称整个 app 或全部生产行为已被形式化证明。

## 9. 实施顺序

- **P0：一个真实切片。** 先冻结 Spec/故障/代码版本，接通模型、Lean、adapter、trace、probe、负控和验收。
- **P1：通用连接工具。** Evidence Graph Compiler、adapter SDK、Trace Validator、assumption freshness engine、theorem/mapping invalidation。
- **P2：跨项目复用。** 共享 schema、runner、CI action 和数学原语；各项目保留自己的业务模型与验收。

## 10. 官方工具入口

- Quint CLI / MBT: https://quint.sh/docs/quint
- Quint Connect: https://github.com/quint-co/quint-connect
- Apalache: https://apalache-mc.org/docs/apalache/index.html
- Alloy 6: https://alloytools.org/documentation.html
- TLA+ Trace Validation: https://docs.tlapl.us/using:tlc:trace_validation
- Hypothesis stateful testing: https://hypothesis.readthedocs.io/en/latest/stateful.html
- Kotest: https://kotest.io/docs/quickstart/
- fast-check MBT: https://fast-check.dev/docs/advanced/model-based-testing/
- Dart property_testing candidate: https://pub.dev/packages/property_testing
- Dart kiri_check candidate: https://pub.dev/packages/kiri_check
- OpenTelemetry trace data model: https://opentelemetry.io/docs/specs/otel/trace/data-model/
- Lean axiom dependencies: https://lean-lang.org/doc/reference/latest/Axioms/

在项目真正采用前固定 tool versions、容器/安装来源、CLI 输出和官方 API；工具链接不等于已通过本项目的技术评估。
