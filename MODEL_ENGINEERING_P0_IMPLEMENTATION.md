# P0 实施手册：把一个真实状态机接成 Spec → Model → Proof → Code 闭环

**版本：v0.1.0 · 2026-11-27 · 定位：可执行试点配方，不是所有项目的强制项**

本文把 Model Engineering Toolchain 收敛为一个可执行切片。首选试点为 codex-go 的 FSM-E / FSM-UI，但必须先读取并冻结真实仓库、真实故障和原始验收；本文件中的状态名、目录和命令只是建议，不是对 codex-go 现状的事实陈述。

## 1. P0 工具选择

| 任务 | 首选 | 作用 | 边界 |
|---|---|---|---|
| Spec/需求权威 | 项目现有 accepted Spec + 稳定 ID | 保存目标、约束、正反例、验收 | 语义仍由 Owner/Reviewer 决定 |
| 状态机模型 | Quint；已有 TLA+ 项目继续使用 TLA+ | 状态、事件、转移、性质和假设 | 模型可执行不等于代码符合 |
| 有限模型探索 | TLC 或 Apalache | 找不可达状态、非法转移和有限范围反例 | bounded 结果不是无界证明 |
| 结构约束探索 | Alloy 6（按需） | 找关系矛盾、空实例和非法组合 | 不替代时序状态机验证 |
| 关键数学性质 | Lean 4 | 证明精确模型性质和 refinement lemma | 通用定理不自动证明项目代码 |
| Rust 模型测试 | Quint Connect + proptest | 模型轨迹回放、性质测试 | Quint Connect 官方集成聚焦 Rust |
| TypeScript | fast-check | command model testing、异步和调度测试 | 模型必须独立于 SUT |
| Python | Hypothesis RuleBasedStateMachine | 状态化命令序列、反例缩减 | 保存可复现 seed/replay |
| Kotlin | Kotest property testing | 生成命令和状态性质 | 并发调度需额外 harness |
| Dart/Flutter | package:test；评估 kiri_check | 确定性 command runner、stateful PBT | 先做小型 spike，不默认第三方库已满足需求 |
| 正确性轨迹 | 自有 JSONL + OpenTelemetry context/links | 状态转移、版本、因果和观察 | OTel 不保证采集完整 |
| 追溯索引 | Python compiler + JSON Schema | 生成 graph、coverage、stale report | 派生索引不是新事实源 |

## 2. 消费项目最小目录

在消费者项目内创建项目自己的目录，不把业务模型放进共享 primitives：

```text
formal/
  authority/source-lock.json
  model/lifecycle.qnt
  model/model-lock.json
  model/scenarios/positive-paths.json
  model/scenarios/historical-counterexamples.json
  proof/Lifecycle.lean
  proof/proof-lock.json
  mapping/implementation-map.json
  trace/schema.json
  trace/fixtures/valid-normal.jsonl
  trace/fixtures/invalid-transition.jsonl
  trace/fixtures/incomplete-segment.jsonl
  probes/assumptions.json
  tests/model_adapter_test.dart
  receipts/model-check.json
  receipts/lean-proof.json
  receipts/mbt.json
  receipts/trace-validation.json
  receipts/assumption-probes.json
  receipts/acceptance.json
```

这是建议布局。若项目已有 Specs、Lean、tests 和 CI 结构，应映射现有目录，不为遵守示例而搬迁权威文件。

## 3. 冻结需求和真实故障

建模前固定 consumer repository、base/head commit、dirty state、原始 Spec/Decision/Acceptance、历史 bug/Issue/日志哈希、运行环境、设备/OS/运行时版本、当前实现和测试入口。

每条关键需求引用现有 REQ ID；不要复制一份内容相似的新 Spec。历史反例沿用现有 ID 或建立 BUG ID。需求权威变化走项目原有 Product Authority 流程。

## 4. 模型 sanity：先证明模型不是空的

明确状态变量、初态谓词 Init、事件集合、转移关系 Next、正向场景、负向场景、失败/迟到/重复/乱序/重启/未知外部结果，以及环境假设和公平性前提。

至少检查：
1. Init 有实例；
2. 正常成功路径存在；
3. 历史故障路径仍能在模型中表达；
4. 关键禁止转移确实不可发生；
5. 关键 safety 性质在声明范围内成立；
6. bounded/exhaustive 范围写入 receipt。

Quint 示例命令（按锁定版本的 help 核验参数）：

```bash
npm install --global @informalsystems/quint
quint --version
quint typecheck formal/model/lifecycle.qnt
quint run formal/model/lifecycle.qnt --invariant SafetyInvariant --max-steps 100 --seed 42
quint verify formal/model/lifecycle.qnt --invariant SafetyInvariant --backend tlc
```

Apalache 使用时记录有限参数、bound、solver 和版本。bounded check 只能标记为 MODEL_CHECKED_BOUNDED。需要关系结构可满足性时再单独加入 Alloy。

## 5. Lean 只证明明确的关键义务

将模型性质映射为 PROP ID，Lean declaration 映射为 THM ID。P0 优先证明关键 safety invariant、完成状态所需证据、身份/版本/责任关系，以及项目已经给出真实 relation 和 transition 时的有限轨迹模拟。

还应独立给出成功路径 witness 或 reachability 检查。不能只证明所有可达状态满足不变量。

在仓库现有 Lean 工具链下执行：

```bash
lake build
python3 tools/verify_lean.py
```

实际参数以仓库 LEAN.md 为准。Receipt 绑定 Lean commit、toolchain、命令、theorem IDs、传递公理审计、未证明义务和退出码。

## 6. Adapter：同一命令序列分别驱动模型与真实实现

最小接口：

```text
reset(seed, environmentProfile) -> ResetReceipt
snapshot() -> ConcreteSnapshot
execute(command, testContext) -> ExecutionResult
abstractState(snapshot, MAP_ID) -> AbstractState
normalize(runtimeEvent, MAP_ID) -> ModelEvent | Invisible
observe(result, OBSERVATION_ID) -> Observation
```

必须保证：
- model oracle 和 SUT 独立运行；
- adapter 不能从模型内部状态伪造真实实现 observation；
- Invisible 必须有逐项 stuttering rationale；
- reset 后读取真实状态；
- 失败保留 seed、命令序列、shrunk counterexample、代码/模型/mapping revision；
- 外部操作 UNKNOWN 时禁止伪造成功或盲目重试。

语言选择：
- Rust：先评估 Quint Connect；一般 PBT 用 proptest。
- TypeScript：fast-check 的 commands、asyncModelRun、scheduledModelRun。
- Python：Hypothesis RuleBasedStateMachine。
- Kotlin：Kotest property testing；并发另建 scheduler/fault harness。
- Dart/Flutter：先用 package:test 写确定性 command runner；小试 kiri_check stateful API，再决定采用。property_testing 可作为备选，需核验维护、shrinking、seed replay 和 Flutter 兼容性。

## 7. Trace completeness

每条事件至少绑定 trace_id、event_id、producer_id、producer_epoch、seq、transition_id、from/event/to、code_revision、model_revision、mapping_revision、verifier_revision。跨进程因果使用 parent/cause IDs 或 OpenTelemetry links；OTel 只提供关联上下文，不证明 correctness event 没有丢失。

必须设计显式 segment close/watermark。只有采集范围关闭、sequence 连续性和必要因果引用均可核验，才允许 TRACE_CONFORMANT。sequence gap、关键 parent 缺失、segment 未关闭、collector 失败、查询不完整或 revision 不匹配不得 PASS。

P0 先实现单 producer 或有限 producer 的明确协议，不声称解决任意分布式全局因果排序。

## 8. Assumption Probe

每个 ASM 记录精确命题、责任边界、PROBE 实现与版本、执行时机、TTL、环境 scope hash、PASS/FAIL/UNKNOWN、失败行为和探针盲区。

例如“网络可用”不能只测 DNS；必须说明具体端点、TLS/认证、代理环境和请求语义。探针 PASS 只对被观察环境快照和有效期负责。

## 9. 三类独立负控

| 负控 | 注入方式 | 预期结果 |
|---|---|---|
| 非法转移 | 强制 SUT 发出模型禁止的 from/event/to | TRACE_DRIFTED / CI fail |
| 轨迹缺失 | 删除关键中间事件、制造 seq gap 或不关闭 segment | TRACE_INCOMPLETE / UNKNOWN，不得 PASS |
| 环境失效 | 探针失败、超时、过期或 scope hash 改变 | 相关保证 STALE/UNKNOWN，系统按合同降级 |

另加合法正向控制，确保验证器不是永远 FAIL。验证器、normalizer、adapter 和负控 corpus 应由独立保护的 CI 身份执行。

## 10. P0 CI 顺序与完成标准

```text
freeze exact coordinates
  -> validate source/ID links
  -> Quint typecheck + model sanity
  -> TLC/Apalache check (record scope/bound)
  -> Lean clean build + theorem/axiom audit
  -> PBT/MBT against real SUT
  -> correctness trace completeness + model validation
  -> assumption probe freshness
  -> positive + negative controls
  -> original acceptance in target environment
```

P0 只有在需求/故障坐标冻结、模型有非空初态/成功 witness/历史故障 witness、关键性质有证明或有界检查、关键转移有代码映射、真实 SUT 被模型命令驱动、Trace 能拒绝缺失记录、三类负控及正控通过、探针过期会撤销保证、原始 Acceptance 实际执行、独立 Reviewer 可重现结论时才算完成。

P0 不要求证明整个 app、OS 或所有并发调度。未覆盖范围必须列明，不得升级为全系统 PROGRAM_VERIFIED。
