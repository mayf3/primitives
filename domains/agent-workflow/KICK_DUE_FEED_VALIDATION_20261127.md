# Kick 死信后由周期扫描接回原责任

## 同一份需求与数学模型

Svc 日志必须反映 PostgreSQL 已提交的处置。提交无法确认时，应保留结算不确定性。Kick 达到失败上限停止自动推送。同一原 Dispatch Intent 只要仍满足业务资格，就继续进入原有 due-feed。Core 周期消费者按原主体接回，并且只有原 AC 的可信提交能关闭原责任。控制组关闭该消费者，在相同资格下继续保有原责任。

本次仍按既有 Svc V3 合同执行。Kick 是低延迟触发，周期查询是正确性路径。其 12 次上限针对已持久化的失败结算。正式操作与产品授权属于原项目。联合测试只使用独立 PostgreSQL、真实 Svc HTTP 与 Core 周期运行入口、本地签发的隔离测试凭据和合成工件。[既有 Svc V3 合同](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/docs/specs/SVC_WORKFLOW_EXECUTION_CONTROL_V3.md)

| 需求 | 模型与 Lean | 代码和实际验收 |
| --- | --- | --- |
| 已提交的失败才产生重试或死信日志 | `SettlementReadback` 区分提交、回滚和未确认。`dead_letter_log_requires_commit` 约束已提交的死信状态 | Svc 的 `UPDATE … RETURNING` 取实际计数和死信状态，提交成功后才生成结算日志。旧实现 RED。新用例验证第 11 次重试、第 12 次候选写入被强制回滚和第 12 次真实提交死信。已有原 payload 与键留存。进程若在提交后退出，日志可能缺席。 |
| 死信后保持原身份和可发现性 | `kickTargetFor` 绑定 Intent、instance、visit。`kick_dead_letter_preserves_due_and_identity` 保证事件键、原义务及 due/READY 投影不变 | Svc 真实 Model3 创建事务建立原 activation 和 Kick。独立测试在真实 Svc 完成 12 次失败结算。Kick 保留原键与 payload，raw due/READY HTTP 返回在死信前后完全一致。 |
| 消费者关闭时原责任仍开放 | `disabled_unclaimed_stays_open` 对任意合法有限轨迹成立，前提是尚未接纳、原有资格事实保持、没有其它完成路径 | 关闭 Core 周期消费者，同一条原 Intent 仍 READY，原 visit 为 `sv1`，开放 activation，零消费者 GET、attempt、prompt、POST、业务转移和提交。独立验收读取原 Svc 的数据。 |
| 周期路径接回并按原 AC 结算 | `trace_preserves_original_binding`、`periodic_path_can_complete_dead_lettered_intent`、`new_completion_requires_original_acceptance` 要求实际 READY、同一身份和经权威确认的原 AC | 真实 Core mount 定时取 READY，通过 Router/AgentProcess 和 WAL 接纳。隔离执行者读实际工件并核对 SHA-256，按原主体、原 visit、原边和 `sv1` 发起一次 Svc 转移。Svc 独立回读原命令回执、业务事件、同版摘要、提交、终态和 activation 关闭。 |

两条正交的结果不能由同一字段读取。Kick 保持死信时，原义务可以处于开放状态，也可以在可信业务提交之后处于终态。Lean 的正向证明给出条件可达轨迹。真实服务可访问、消费者获得运行机会、READY 分页覆盖、持久接纳、原角色执行和证据可信分别是实现义务。这次隔离实跑覆盖一条确定的原义务。

## 固定版本的联合证据

下列运行 SHA 来自隔离工作树。公开源码基线为 Svc c50ab2ac 与 Core ee4dbefb。运行回执中的本机路径已替换为通用占位符。

| 项 | 最终运行坐标 |
| --- | --- |
| Svc 日志修复 | `b73ebfe9cab8f5dbbf8d75a0b06991de44ffb130` |
| Svc 组合候选 | `787278729486381afb8e5976db912fbc190b875c`，含日志修复、隔离联合验收及网络隔离 |
| Core | `edd359fb4583d91c1832ae0d89244e53224e8fa7`，在冻结主分支基础上增加测试驱动 |
| 原 Intent / visit / instance | `9e165f6d-cfdd-43cc-8dd3-36dcba339879` / `ae672b98-8aa4-40c3-b384-1c3f162e00bd` / `ce6f87b1-1b7f-4c90-8984-6cbfbe869199` |
| 原角色 / Core attempt | `8c3a4c36-892d-40d6-8621-e303d801cdac` / `wfeat-9a4f659d048d172a874cb44d` |
| 原 AC 业务事件 / 提交 | `dc5dd954-1efe-49d3-8a06-078471948d09` / `21b960f7-4af1-4095-9be2-0b67e1394873` |
| 业务结果 | `sv1 → sv2`，进入终态并真实关闭原 activation。Core `business_commitment_observed`。4 次 READY 读取，1 个 attempt，1 次可核认的持久开始，1 次 Router prompt，1 次业务 POST。额外 Kick 为零。 |

正负控共用同一条原 Intent。为隔离实验缩短了 Kick 退避等待，12 次失败和各次事务依然实际发生。末尾将死信记录的到期时间设为当前后，自动推送仍无额外请求。只在隔离布置时启动消费者，之后由真实定时回调推进。采用真实 Broker HTTP、Router ingress、route chain、AgentProcess 与 Svc 运行路由。OAuth 签发、Agent 解析和原工作者为受约束的夹具，确定性执行器真实读取并验证工件。生产 Auth、LLM、跨多条义务公平性和正式业务上线仍需本项目验收。[冻结联合运行](evidence/kick-due-joint.txt) · [提交/回滚日志回执](evidence/kick-due-logging.txt)

## 复跑

持有上述隔离候选源码时，在固定 Svc 工作树执行。命令自行创建并清理新的独立 PostgreSQL，校验监听地址、端口、角色、数据库及数据目录。依赖本机 PostgreSQL、Node 和已缓存的 Cargo 锁定依赖。

```sh
python3 tests/run-kick-due-continuation.py "$core_checkout/packages/production-runtime/test-support/kick-dead-letter-due-feed.mjs"
```

在数学模型仓根目录运行统一 Lean 4.19.0 验证。联合层证明已提交死信之后的责任保持。Kick 失败预算的触发条件由独立 Outbox 模型和 Svc 回归核验。

```sh
python3 tools/verify_lean.py --output .lake/verification/due-feed-handoff.json
```

源码入口为 Svc `src/store/postgres/outbox.rs:242`、`src/forum_sync.rs:1069`、`tests/48_outbox_three_channels.rs:1270` 和 `tests/outbox/kick_due_continuation.rs:248`。Core 的周期入口为 `packages/production-runtime/src/workflow-execution-runtime.js:245,459`、`packages/workflow-execution/src/engine.js:459`。组合关系与性质见 [DueFeedHandoff.lean](lean/AgentWorkflow/DueFeedHandoff.lean)。

同一最终 Svc 提交的三通道回归 23 项通过，组合用例单独执行并通过。固定 Core 提交的恢复回归 57 项通过。额外的 Svc `--lib` 验证和 Core 全 composer 导入分别受既有缺失 Spec 文件与私有包影响，两项均在各自冻结基线复现。
