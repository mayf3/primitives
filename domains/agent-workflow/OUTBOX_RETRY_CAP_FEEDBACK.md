# Outbox 普通重试上限：模型反馈与实现对应

**0.3.3-pilot · 2026-11-27 · 有界模型修复**

## 定位与原验收

用户要求继续完善 SVC Workflow 的仓库审阅、数学建模和形式化证明。本子项补齐可复用 Outbox 模型，与 SVC 的 Wake 代码修复分别交付。它不声称生产问题已解决，也不修改消费项目既有合同。

- 旧模型：`mayf3/primitives@9500d8e24730fdbce334b8fdcde71830838c21f4`，`domains/agent-workflow/lean/AgentWorkflow/Outbox.lean`。
- 实现与合同基线：`mayf3/svc-workflow@c50ab2ac98decceaa26138a282c34dd92ede0ddc`。
- 原验收：已接受的 [Execution Control V3 Delta 3](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/docs/specs/SVC_WORKFLOW_EXECUTION_CONTROL_V3.md) 要求 `EXECUTION_KICK` 的任意 retryable failure 达到 12 次时死信；Forum / Owner Assistance 不因这个上限死信；死信仍保留原 payload 和诊断，人工逐行恢复另行授权。
- 分类：**模型遗漏**。SVC 的普通 retry 原本已正确传入并执行 cap；现有 UNKNOWN 模型定理没有被反驳。

旧 `Step.retry` 只有 enabled、claimed 和 owner 三项前提。因此以下旧版本命题存在构造证明：

```lean
-- 仅针对上述固定旧提交；不是当前模型允许的转换。
example :
    Step (fun _ => true) ⟨7, .executionKick, .claimed, some 3, 11⟩ (.retry 3)
      ⟨7, .executionKick, .pending, none, 12⟩ :=
  Step.retry rfl rfl rfl
```

这是“第 12 次后仍 pending”的最小反例。它先前已在 SVC 审阅包中通过原版模块编译；固定 Git 历史和此构造保留反例，不改写旧来源或旧验证回执。当前模型的 `kick_retry_at_cap_cannot_remain_pending` 排除同一结果，且第 11 次可 pending、第 12 次可 dead-letter、正常 claim 后可 delivered 都有显式正例。

## 修订与数学保证

保留现有 `Row(eventKey, channel, status, claimant, attempts)`，没有创建新调度器、账本或统一工作流运行时。

| 转换 | 前提 | 后态 |
|---|---|---|
| `retry` | enabled、claimed、owner；若为 kick 则 `attempts + 1 < 12` | pending、释放 claimant、计数加一 |
| `retryKickDeadLetter` | enabled、claimed、owner、kick、`12 ≤ attempts + 1` | deadLetter、释放 claimant、计数加一 |
| `unknownRetry` / `unknownKickDeadLetter` | 沿用相同预算分界 | 保持原有 UNKNOWN 路径 |
| `deadLetter` | kick 的永久拒绝、enabled、claimed、owner | 立即 deadLetter，计数加一 |
| `claim` / `settle` | 沿用原来的独占 claim 与 enabled 条件 | claimed / delivered |

`retry_has_successor` 证明所有合法 claimed 行都有一个 retry 后继：上限没有通过删掉所有失败路径实现。`retry_increments_attempts_once` 固定了计数口径：此处 attempts 是持久失败计数，成功 `settle` 不另加一次，符合当前 SQL；它不是 Core 的业务执行 attempt 数。

令 `KickBounded(r)` 为：kick 行的 `attempts ≤ 12`，且 pending 或 claimed 时 `attempts < 12`。从 fresh `pending / none / 0` 行证明初态成立，逐个构造器证明保持，再对任意有限 `Trace` 归纳，推出 `reachable_kick_respects_cap`。这个命题没有有限枚举深度，不以“每一步预算都成立”作为假设；它依赖轨迹每一步确实属于当前 `Step`。对初始计数已经任意偏大的行，局部 at-cap 定理仍有效，但 fresh-trace 的总体 `≤ 12` 结论不适用。

其他性质涵盖 event key / channel 不变、UNKNOWN 与 retry 不记录成功、耐久通道不死信、终态没有自动出边。`terminal_has_no_automatic_transition` 只针对自动 reconciler；人工修复后 requeue 的合同仍保留，不把它冒充自动恢复。

## 模型到实现

下表均绑定 SVC 基线提交，不随 `main` 漂移。

| 模型责任 | 实际实现 | 对应与限制 |
|---|---|---|
| `eventKey` / `channel` / `attempts` | [outbox.rs](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/outbox.rs) 的 `event_key`、`outbox_kind`、`attempt_count` | Nat 是非负整数抽象；SQL 整数溢出、输入约束和全部历史行另验 |
| claim owner | 同文件 `claim_row`：`FOR UPDATE SKIP LOCKED`，未 delivered / 未 dead-letter / 到期行 | 模型的 claimant 表示事务锁所有者，不是新增持久字段；未证明 PostgreSQL 锁调度 |
| retry 两分支 | [forum_sync.rs](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/forum_sync.rs) 的 `deliver_claimed`，`outbox::mark_attempt_failed` | kick 传 `Some(12)`；两耐久通道传 `None`；SQL 在同一 UPDATE 用 `attempt_count + 1 >= cap` 设置死信 |
| UNKNOWN | `deliver_kick` 将传输错误/超时分类为 Retryable，再走同一失败 SQL | kick 具备稳定 event key 的专属幂等投递合同；不能推广为未知业务副作用一律可重做 |
| permanent deadLetter | `deliver_kick` 的永久拒绝分类与 `mark_dead_lettered` | 模型 Command 抽象分类结果；未形式化 HTTP parser / status classifier |
| terminal 无自动出边 | due queries / `claim_row` 排除 delivered / dead-letter | 人工 requeue 单独清空 dead-letter、重置 count 与 due time；不在本模型中 |
| payload 保留 | 失败 SQL 更新计数/诊断/时间，不覆盖 payload | 当前 Row 不含 payload；这是源码映射和数据库验收义务，未宣称由 key 不变量证明 payload 不变 |

本轮证明没有覆盖事务回滚、HTTP 前后数据库崩溃、通知端幂等、背压时间、全局 Forum 顺序、配置动态切换、调度公平或无限轨迹的最终送达。真实锁和提交若不符合抽象前提，需要补实现证据或扩模型，不能引用此证明代替。

## 验证与证据状态

本次实际执行：

```bash
python3 tools/verify_lean.py --domain agent-workflow \
  --bin-dir /absolute/path/to/lean-4.19.0-linux/bin
python3 tools/primitives.py validate
python3 tools/verify_lean.py \
  --bin-dir /absolute/path/to/lean-4.19.0-linux/bin
```

单域结果：`PASS_CONDITIONAL_MODEL_PROOFS`，Agent Workflow 75 条显式定理，公共核心 6 条，共 81；编译环境审计 780 个声明及 287 个定理。Outbox 本文件由 7 条增加到 26 条，新增 19 条。确切哈希、全部依赖和工具链记录在本次统一入口生成的 `.lake/verification/agent-workflow.json`。

随后实际执行的全仓门禁同样通过：显式定理 134 条，编译声明 1196 个，编译定理 460 个；刷新本次根 `lean-verification.json`。`primitives.py validate` 通过（6 个模块、66 个条目、58 个固定来源文件、3 个桥接、3 个域检查）。本版 `Outbox.lean` SHA-256 为 `d166fc5c9d25c0afab1fd6e58752129683870987436a0069f014775819cf06f7`。

| 证据层 | 本子项状态 |
|---|---|
| 模型与证明 | 已通过上述单域 Lean 构建及传递公理审计；正例与旧缺口排除同时成立 |
| 实现对应 | 已检查指定提交的 Rust/SQL 分支与字段；这是源码映射，尚非 Rust/SQL 全程序形式精化证明 |
| 真实业务验收 | 本纯模型子项不登记生产验收；SVC 的实际 PostgreSQL 回归由消费项目记录，线上任务仍需自己的验收 |

对应数据库回归入口为 SVC `tests/48_outbox_three_channels.rs` 中的 `kick_dead_letters_at_the_retry_cap_and_recovers_via_requeue`、`kick_400_dead_letters_immediately_with_payload_retained` 与 `transport_unknown_result_schedules_retry_and_carries_stable_request_id`。UNKNOWN-at-cap 用例在审阅时属于尚未合并的 PR #141，不能写成该基线已经包含或已执行。

完成此模型补齐项不关闭任何未经真实验收的产品任务。后续若引入自动 requeue、改变 cap / 通道责任，或拟声明完整崩溃恢复与活性保证，需要重新建模并验证受影响性质。

## 独立复审与消费侧补验证

另一个未参与本模型编写的 Agent 已独立重编译当前 26 条 Outbox 定理，审计传递公理，并分别用旧版重编译原 pending-at-12 反例、用新版证明该路径不能继续 pending。结果与精确文件哈希见 [独立复审记录](evidence/OUTBOX_RETRY_CAP_REVIEW_20261127.json)；无阻断发现，所有模型边界保留。

消费侧随后在 `svc-workflow` PR #141 的精确 head `6c19d318b7aa6f03ed7bbe8cfcc2b768f8c67da6` 上实际运行 PostgreSQL 16.13 的 `48_outbox_three_channels` 测试：23 passed / 0 failed / 0 ignored，包含 UNKNOWN-at-cap。该测试 head 的运行时代码对应上述 SVC 基线，PR 增量为测试与说明。它仍是未合并 PR；这项本地数据库证据既不改变 main 的文件状态，也不登记生产验收。完整执行回执归消费项目的 Wake/Formal repair 记录所有。
