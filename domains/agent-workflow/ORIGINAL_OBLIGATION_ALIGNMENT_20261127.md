# ZERO-OPS 原义务、节点交接与原验收对齐

本切片覆盖同一个 model 3 实例内由 Agent 接续的一条原业务义务。[ZERO-OPS 总模型](FORMAL_MODEL.md) 继续约束安全性、条件活性及外部效果。[原联合试验](KICK_DUE_FEED_VALIDATION_20261127.md) 覆盖 Kick 死信、Core 定期 READY 接纳以及一条终态提交。

## 1. 先冻结需求

| 需求 | 数学条件 | 最小失败情形 |
| --- | --- | --- |
| R1 原责任持续有效 | 通知失败、死信、READY 不可见、物理尝试结算、停止及 UNKNOWN 保留原义务。可见性和消费者状态独立于义务状态。系统仍须提供可执行的发现或恢复路径，见 R3。 | READY 空页或消费者停止后，原义务从未结清集合消失。 |
| R2 当前节点结束后有后继，原合同负责最终验收 | 普通交接要求同一原义务的当前 visit、受派主体、状态版本及权威命令回执，并已持久建立原图确定的后继。终态提交留下待验收责任，唯有对应原合同及同一终态事件的可信验收关闭原义务。 | 仅凭节点离开、Svc 终态、异版报告或缺少后继的回执，便记作完成。 |
| R3 无人值守是条件活性 | 有权消费者持续运行、可执行责任公平获服务、可恢复阻塞有合法出路、所需证据可取得、原合同可满足时，才讨论最终完成。 | 消费者处于启用且 READY 始终可见，实际执行却一直没有发生。 |
| R4 观察、接纳与效果各有权威 | READY 是候选视图，持久接纳是执行者事实，正式提交来自权威命令，原 AC 来自合同认可的证据。外部写入的 UNKNOWN 继续遵守原键及对账约束。 | 仅凭历史视图、CAS 冲突或响应超时推定已发生效果，或推定无效果而重发。 |

审批门保留原合同和有权主体。技术等待保留原恢复责任。合法取消是独立的授权动作，保留显式历史。本切片只建模成功、等待与交接三者。真实人工节点、跨实例父子图、并行分支、回退预算和外部效果继续由总规约约束。联合试验的关闭负控从未启动 Core 消费者，也无在飞工作。运行中的停止与 drain 有不同语义。

## 2. 数学语义

原义务身份 q = (obligation, instance, definitionVersion, originalAC)。节点责任 v = (intent, instance, visit, principal, stateVersion)。开放状态为 Working(q,v,visibility) 或 AwaitingAC(q,event)。通过状态为 Accepted(q,event,evidence)。visibility 取 ready、held、unavailable，只决定 READY 投影。物理执行可发生或重试，改变原义务的动作必须有权威证据。

| 动作 | 前置与结果 |
| --- | --- |
| 观察、停机、无结果、重试待对账 | 对原义务而言允许停留原状态。可见性变化只更新 Working 的读投影。 |
| 非终态交接 | 读取绑定原义务、当前 visit、事件及后继的权威回执。在来源及已持久建立的精确后继都属同一实例、visit 更新、版本前进时进入 Working(q,next,unavailable)，等待重新确定 READY。版本可前进多位。 |
| 终态提交 | 读取绑定原义务、同实例的当前 visit 与终态事件的权威回执，进入 AwaitingAC(q,event)。无执行后继须由原图和权威终态事件判定。Svc 终态也可有目标 visit，READY 空页也可能有被阻塞的后继。 |
| 通过原 AC | 从 AwaitingAC(q,event) 消费绑定原义务、原合同、相同终态事件和具体验收证据的可信结论，进入 Accepted。 |

三项待核的物理前提是真实提交回执、同图后继的持久存在、绑定原 AC 的可信验收。原 AC 的工件身份与内容适用性由授权验证者判断。权威命令检查身份、当前状态 CAS 和开放 Case。Lean 切片的范围为身份及开放性保持、交接及验收的必要证据约束，以及原有限模型的一条合法无限停顿反例。正向全程完成保证仍须满足总规约的宏步实现和公平性前提。

## 3. 从数学判据到代码取证

源码链接使用两个固定公开基线。所引用的实现文件与联合试验的隔离候选逐文件一致。试验坐标详见原联合回执。

| 判据 | 真实落点 | 仍待证实的精化 |
| --- | --- | --- |
| R1 开放义务独立于 Kick | Raw due 读 activation、阻塞与到期，READY 再加域和前置筛选，Core 周期消费者读取 READY。联合试验关闭消费者时保持 READY/open、sv1，启用后按原 intent 提交。 [Svc raw due](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/query_dispatch_intents.rs#L170) · [Svc READY](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/query_ready_intents.rs#L26) | 关闭负控只覆盖无在飞的情形。 |
| R2 同实例后继 | Svc 同一事务关闭来源 activation 并建立后继 visit 和适用的 activation。事务内验证版本、主体、Case 与边。联合试验使用独立 Svc 读回绑定原试点的业务 AC。 [Svc 提交校验](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/transition_transaction.rs#L151) · [关闭及后继](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/transition_transaction.rs#L750) | 真实非终态转给不同受派人的自动接纳，以及通用终态后 AC 落账，需要各自闭合。 |
| R3 服务可达 | Core 正常入口重读原意图、当前 visit 与受派主体，再持久接纳。 [Core 准入](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/owner-assistance-resume-engine.js#L37) | 有一条成功轨迹与长期无饥饿是两个谓词。技术 Case 的恢复和存量合法承接需要实际消费者。 |
| R4 证据具备权威 | Core 尝试可标为 business_commitment_observed，同时业务投影仍为 UNKNOWN / UNPROVEN。历史视图也会触发前一分类。 [Core 尝试结算](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/judgment.js#L53) · [Core 业务投影](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/business-result.js#L139) | Svc 身份继任可保留原 visit 并改变原受派主体的可见性。历史视图应等待权威事件对账。 [Svc 可见性](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/query_visibility.rs#L326) |

后续代码验收使用两个负载明确的样本。真实非终态交接须按原图自动接纳同一义务的新 visit。历史视图或 visit 已移动时，缺权威事件和原 AC 的结果不得被记为原义务完成。上游提交和后继 READY 各自如实记录，直到取得后继的持久接纳和实际结果。

## 4. Lean 对应与复跑

| 需求 | 证明或反例 | 范围 |
| --- | --- | --- |
| R1 | `trace_preserves_original`、`held_is_open_without_ready` | 原任务、实例、Definition 与 AC 标识在有限轨迹保持。开放与已验收可产生同一 READY 空结果。 |
| R2 | `changed_visit_has_durable_successor`、`stage_final_keeps_open_with_receipt`、`acceptance_from_working_has_original_ac_and_commit`、`accepted_is_stable` | 同一义务换 visit 必须有确切提交和持久后继。原 AC 通过需要因果上先出现可信同实例终态提交，并消费同事件验收。 |
| R3 | `ready_dead_lettered_admission_can_idle_forever` | 在旧模型中，启用消费者、Kick 已死信、已接纳且 READY 保持可见，仍有一条合法无限停顿轨迹。真实执行、调度公平和核验返回需要另外落实。 |
| R4 | `new_acceptance_requires_matching_pending_event` 与 Lean 示例 | 缺后继持久证据、错来源或后继实例、异终态事件、异 AC、拿错工件和跳过终态提交均有负控。合成正控覆盖跨角色、版本间隔大于 1 的后继，再提交并验收。 |

Lean 的权威参数由实现提供。即使核验方信任异事件回执，模型也拒绝给当前终态结账。独审曾构造实例 99 的来源 visit 结清实例 17 原义务的轨迹，现把两条提交路径的来源实例绑定移入规则并保留负控。合成正控预先给出合法回执，后继的定期发现和真实接纳仍需隔离运行验收。[Lean 源码](lean/AgentWorkflow/OriginalObligation.lean)

```sh
python3 tools/verify_lean.py
node domains/agent-workflow/evidence/core-attempt-vs-business-acceptance.mjs /absolute/path/to/pinned-core
```

Core 探针接受公开基线 ee4dbefb 及隔离候选 edd359fb，调用真实模块，注入构造的详情与空时间线。三项结果如下。

| 输入 | 尝试分类 | 原业务输出 |
| --- | --- | --- |
| 完整详情显示 visit 已移动、实例已终结，缺确切事件 | SETTLED，visitLeft=true | UNKNOWN / UNPROVEN |
| 历史参与者视图、实例非终态 | SETTLED，visitLeft=null | UNKNOWN / UNPROVEN |
| 完整详情显示原 visit 仍在、缺提交 | RUN_ENDED_NO_TRANSITION，visitLeft=false | UNKNOWN / UNPROVEN |

第二项的源代码时序可由合法身份继任产生：Svc 的当前有效身份决定完整视图，历史视图仍可由原始受派关系授予。合法继任入口可保留当前 visit。探针复现 Core 分类，跨服务生产事件仍待证实。Core 对同一标签的 Forum 投影也需核查。相关下一步是用权威回执验证业务提交及后继，保留执行尝试自身的结算语义。[身份继任写入](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/bin/identity_repair_v1.rs#L803) · [Forum 投影](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/forum-projection.js#L52) · [可复跑探针](evidence/core-attempt-vs-business-acceptance.mjs)

正常 READY 接纳和预调用的原尝试恢复也是两条入口。后者在 READY 为空时仍可恢复确认从未调用的同一尝试。正式业务变更继续受 Svc 的当前实例与 Case 门约束。这样可以保留技术修复的执行路径，同时防止把恢复尝试误作已解除 Case 或通过原 AC。[Core 自动恢复](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/recovery/operation.js#L80)
