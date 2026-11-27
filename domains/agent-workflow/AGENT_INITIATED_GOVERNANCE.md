# Agent 主动发起治理并恢复原工作流

本规格增补 [ZERO-OPS 总模型](FORMAL_MODEL.md) 和 [原义务验收切片](ORIGINAL_OBLIGATION_ALIGNMENT_20261127.md)。Agent 在执行节点发现自身不能解决的阻塞时，可以依据既有权限发起一次可持久接管的 Debug 或治理义务。授权、独立核验、采用、解案和恢复原任务由各自的权威入口执行。

## 需求与模型

| 需求 | 可检核的数学和实现条件 |
| --- | --- |
| 自己发起 Debug | 原节点、Case 分类及有权请求者绑定。先持久建立或认回同一技术责任，再通知和实际接纳。重复发现、进程重启和重发使用原逻辑身份。 |
| 治理真的改变阻塞 | Debug 产生可执行诊断。有权修复者接纳并产出工件。独立核验绑定同一修复身份和内容。采用者读回生效事实；只有有权者能解除准确的 Case。 |
| 必要时重建执行 | 重建的是可丢失的执行或治理子尝试。原任务、原 Definition、原 AC 和原操作身份仍可追溯。新 attempt 必须有可接受的安全证据和当前版本。Definition 修订及存量迁移需要各自授权与独立验证。 |
| 回到原任务并完成 | 修复通过、解案、原角色实际接回、父业务通过原 AC 是分别可查的事实。原命令已经生效时，对账并将权威回执送回原流程。没有可靠效果信息时，保留 UNKNOWN 并继续走对账责任。 |
| 减少人工请求 | 已获授权的诊断、补材料、隔离测试和安全恢复可以由系统执行。技术故障、缺材料和重试耗尽不自动创建人类决策。确需本人表达偏好、确认事实或授权时，系统维护准确问题及恢复条件。 |

记原义务为 q，当前节点为 v，原操作键为 k。单次治理逻辑身份 g = (q, v, caseId, generation, k)。诊断、修复、采用、回接都绑定 g。同一 g 的重复请求只认回已建立工作。任何阶段都保留父业务义务；父任务结清继续由原 AC 门定义。

本切片覆盖一条技术治理责任及其结果。合法入口依次为：具备权限的请求持久登记 Debug → 有权消费者接纳 → 诊断产出 → 修复义务持久建立并接纳 → 同版独立核验 → 有权采用并读回 → 有权解案 → 原角色或原命令对账消费者实际接回。可用同一权威提交实现相邻事件，也可让恢复者消费持久的前一阶段。租约和通知不构成实际接纳。

恢复原执行须持有安全凭证。可以凭权威未生效证据恢复原键，也可以在服务端原键幂等和回执覆盖完整操作期限时重放原键。如果确认已生效，读取原命令回执并回交原流程。没有这些证据，就保留待对账责任。超时、尝试预算归零、Case 关闭都不给出安全凭证。

治理执行者自身失败时，由独立于该执行者的恢复入口读回同一个治理责任。自动创建后一层治理需有明确范围、有限预算和严格下降的故障依赖秩，耗尽后持久保留前一义务与接收者。本切片仅表达单次治理的安全因果关系，调度公平、通道可用、独立的控制面恢复和多代收敛属于后续实现与证明义务。

## 真实代码落点与首轮验收

固定 Svc `c50ab2ac` 和 Core `ee4dbefb` 可复用下列入口。表中的代码事实来自固定源码，尚未验收生产运行组合。

| 连接 | 可复用行为与缺口 |
| --- | --- |
| Agent → 正式治理 | Core 指示原受派 Agent 使用自身主体、当前 visit/版本调用 Assistance。Svc 在同一事务保存请求、Case 和符合已批准策略的 INTAKE。后台生产器还需要配置合法 Policy Actor，并检查当前 visit 和 OWNER_PENDING。 [Core 请求契约](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/instruction.js#L41) · [Svc 请求事务](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/assistance_transaction/write.rs#L34) · [INTAKE](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/owner_obligation/intents.rs#L8) |
| 治理执行者退出 | 已受管子流再次发起同类 Assistance 会产生 `NESTED_ASSISTANCE_UNSUPPORTED`。复用 Case 和治理记录，通过独立、已有授权的恢复入口认回同一责任。当前扫描处理到持续返回 5xx 的旧 PENDING 时可提前结束本轮；应实跑一笔故障旧义务和一笔健康后继，检验隔离与公平性。 [受管停止](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/owner_obligation/intents.rs#L19) · [生产扫描](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/owner_obligation/reconcile.rs#L74) |
| 解案与原任务恢复 | Svc 的受管子流检查终态、提交及绑定验收；无子流绑定的旧 Case 缺少这项自动证据门。原恢复证明查询使用原 Dispatch Intent、visit、当前状态及 request/resolve 权威记录。Core 仍需产生符合当前状态的实际恢复接纳。 [受管终态](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/assistance_transaction/governance_child/terminal.rs#L152) · [Svc 恢复证据](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/query_owner_assistance_resume_evidence.rs#L53) · [Core 恢复接纳](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/owner-assistance-resume-engine.js#L118) |
| 存量承接与重建 | 当前 materializer 要求 OWNER_PENDING，存量 HUMAN_REQUIRED 需要正式有权承接。Svc 的 `REBUILD_PROJECTION` 是管理员从不可变事实修复投影的原语。业务重试、投影修复、Definition 迁移分别核验原权威和追溯。 [状态门](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/owner_obligation/reconcile.rs#L105) · [投影重建](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/admin_recovery_repository/rebuild_transaction.rs#L128) |

首轮验收使用一张已批准策略覆盖的真实技术 Case。原受派 Agent 主动发现，原请求与治理身份分别可回查。中断发起者以及 Debug 或修复消费者，再看同一治理义务是否被接纳，修复是否独立通过并合法采用，原角色是否自动接回并按原 AC 提交。健康任务应继续推进。另做三项负控：真正的本人决定仍等权威输入；效果不明且无安全重放凭证时无新执行；关闭独立恢复消费者时义务仍开放。人工协调和发现机制实际发起分别记账。

## Lean

[GovernanceRecovery.lean](lean/AgentWorkflow/GovernanceRecovery.lean) 使用固定绑定的单次治理状态机。机检覆盖持久登记、同版独立核验、授权采用、持久且实际消费的恢复交接、同键与同节点责任。权威已提交回执可用时，选择读回；两条安全路径都缺失时，保留等待。模型分别给出原键重试和读回提交的正控，及换键、作者自审、无权威效果和无实际接纳的负控。实际租约分配、跨进程唯一约束、权限和预算由消费实现提供。

```sh
python3 tools/verify_lean.py
```

治理执行中断的新增租约模型、隔离进程实跑与可复现的实现缺口见 [治理接管可行性](GOVERNANCE_RECOVERY_FEASIBILITY.md)。
