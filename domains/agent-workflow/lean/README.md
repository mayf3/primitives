# Lean 形式化切片

**Lean 4.19.0 · Agent Workflow 0.3.2-pilot · 2026-11-27**

本工程将 [后续评审说明](../FORMALIZATION.md) 中的三组命题交给 Lean 内核检查：固定策略的条件进展、历史压缩与不确定性、任意不可信报告与验收门。它不导入私有运行数据，也没有对接生产系统。

## 复现

使用 [Lean 官方安装方法](https://lean-lang.org/install/) 准备 `leanprover/lean4:v4.19.0`。从**仓库根目录**运行统一验证入口：

```bash
python3 tools/verify_lean.py --domain agent-workflow
```

需要 Python 3.11 或更新版本。若使用独立下载的 Lean 发行包：

```bash
PATH=/absolute/path/to/lean-4.19.0/bin:$PATH \
  python3 tools/verify_lean.py --domain agent-workflow
```

工具链、Lake 配置和审计由仓库根目录统一维护，本域不保留重复脚本或工具链文件。本域的 Lake 库名为 `AgentWorkflow`；开发时可以单独编译：

```bash
lake build AgentWorkflow
```

统一验证会核对编译器版本、编译证明并审计所有本地 `theorem` 的传递公理。只使用此工具链随附的 `Init` / `Std`，没有 Mathlib 或其他外部包。缺工具、编译错误、警告、未审计声明或不允许的公理都不能登记为通过。为防止静默漏审，声明使用单一显式命名空间与受限格式；新增模块或改变声明形式时，必须同步检查统一审计的覆盖。

当前本域原有 43 个定理声明保留用途。本轮试点新增两个独立 Lean 模块，覆盖同一 attempt 的恢复/写前 fence，以及三通道 outbox 的逐行状态转换。UNKNOWN 允许只读复查但不能自动重新投递；terminal 责任元数据不能重开业务投递。本轮 Agent Workflow 定理声明总数为 **56**（原有 43 个 + 本轮新增 13 个），均由 2026-11-27 workflow run `45917271049` 的 Lean 4.19.0 验证入口审计通过。数量包含辅助引理与负向性质，不等于生产保障。以统一脚本产生的当前回执为实际核验依据；回执需绑定工具链、命令、退出码、输入文件 SHA-256 及各定理依赖。审计脚本不会把跳过检查登记为 PASS。

本次增加 `DueFeedHandoff` 的 8 条定理及 `OriginalObligation` 的 11 条定理，本域共 **75** 条。前者检查已提交的日志、已死信通知与原责任的发现。后者检查同实例持久后继与原 AC 结账的因果关系，并给出运行中消费者仍可能无限停顿的反例。物理提交、接纳、核验权威与实际公平性由消费实现提供。[需求、模型与真实代码对账](../ORIGINAL_OBLIGATION_ALIGNMENT_20261127.md)

新增 `GovernanceRecovery` 的 10 条定理，本域共 **85** 条。用固定治理身份连接 Agent 发起、合法接纳、独立核验、采用、解案与原义务恢复。模型对原键恢复和权威回执路径分别给出正控，验证技术治理的权限与证据边界。[需求、证明与代码落点](../AGENT_INITIATED_GOVERNANCE.md)

新增 `GovernanceTakeover`，检查故障后的可认领租约、精确绑定、UNKNOWN 与旧 epoch 写门。[隔离可行性回执及代码对账](../GOVERNANCE_RECOVERY_FEASIBILITY.md)

单域命令把回执写入根目录下的 `.lake/verification/agent-workflow.json`；全仓命令产生根目录的 `lean-verification.json`。单域结果不会覆盖全仓回执，也不能代表其他领域已核验。

每次使用都以本次进程退出码与当前输入哈希为准；失败运行不覆盖以前的成功回执，旧文件不能充当本次通过的证据。

## 定理对应关系

| 核验内容 | 主要声明 | 条件与范围 |
|---|---|---|
| 任意允许后继的有限秩进展 | `reaches_within`、`belief_prefix_reaches_original_acceptance` | 固定策略、认证区域、全后继严格降秩；界是已完成宏步数 |
| 非目标不能死锁、目标保持 | `certified_successor`、`maximal_endpoint_is_target`、`target_persists` | 可执行性、普遍有限返回和目标闭包是证书条件 |
| 证据更新与进展观察一致 | `observed_post_iff_evidence_update` | 两片段采用同一个关系 `emits`；允许错误、相关或诱导性报告 |
| 从初态推出所有边界的真实世界包含 | `MacroRealization.possibleAtBoundary` | 只假设初态包含；逐步实际转移、报告覆盖及完整更新由实现提供 |
| 真实轨迹的条件提升 | `MacroRealization.follows_policy`、`realized_policy_reaches_original_acceptance`、`realized_internal_prefix_safe` | 需给出实际策略执行、返回、信息更新与中间状态覆盖的精化见证 |
| 进展正控 | `replayCertificate`、`replay_all_one_step_runs_finish` | 完整双世界原键恢复证书；理想化服务，不是生产幂等实现 |
| 返回合同反例 | `late_valid_return_cannot_hide_early_invalid` | 先返回非法结果、后返回合法结果的执行满足旧存在性条件，但不满足所有返回均合法的新合同 |
| 持续假报告的桥接实例与进展反例 | `deceptiveRealization`、`deceptive_reports_keep_absent_possible`、`deceptive_only_no_progress_certificate` | 真实效果始终缺失但报告全称成功；真实世界不被滤掉，且不能为不变假信念构造降秩证书 |
| 不确定性与真值保留 | `update_contains_actual`、`trace_contains_actual` | 初态包含真实世界，实际转移/报告全部被关系模型涵盖 |
| 状态摘要的精确关系表达 | `sufficient_iff_exact_relational_quotient` | enabled / 后继支持集 / 原验收兼容的充要条件；不涉及概率核 |
| 历史遗漏反例 | `no_exact_node_only_enabled_relation`、`node_only_loses_future_behavior` | 当前节点相同但在途请求不同，合法动作或未来效果不同 |
| 不可信报告不能绕过可靠门 | `reports_cannot_bypass_sound_gate` | 可信绑定、sound verifier、定义中的所有关闭路径；局部世界固定 |
| 多人共同错误的反模型 | `consensus_does_not_imply_truth`、`unsound_gate_can_close_false_goal` | 一致 PASS 不推出事实；丢失 soundness 后可假关闭 |
| 验收门正控 | `equality_evidence_is_sound`、`sound_gate_can_close_true_goal` | 合成的真值绑定门可以接受真成功，不是永远拒绝 |

源文件：[Progress.lean](AgentWorkflow/Progress.lean)、[Evidence.lean](AgentWorkflow/Evidence.lean)、[ExecutionRecovery.lean](AgentWorkflow/ExecutionRecovery.lean)、[Outbox.lean](AgentWorkflow/Outbox.lean)。本轮两个新模型是有意缩小的状态转换切片；它们尚未证明真实 Node.js / PostgreSQL 实现满足模型，也不覆盖生产环境。

## 0.3.0 消除的前提

过去 `MacroRealization` 直接要求每个边界都满足 `possibleAtBoundary`，而进展模型使用确定的 `observe` 函数。现在协议用 `emits : World → Observation → Prop` 描述所有允许报告，宏执行必须有限返回实际 `(World, Observation)` 对，且返回满足 `finish` 与 `emits`。这没有增加报告诚实或统计独立的假设。

这里的 `World` 是证明对执行结果的隐藏状态标注，不表示 Agent 或 API 响应能直接读到真实世界。策略仍只接收信息集，更新只使用实际收到的报告。

实现只需提供初态包含 `initiallyPossible`、每一步实际转移与实际报告的覆盖、以及按完整集合计算的更新。`MacroRealization.possibleAtBoundary` 调用证据模块的 `update_contains_actual` 归纳推出每个边界的包含关系。它从结构字段变成了定理，没有把旧前提换名藏回合同。

`deceptiveRealization` 是这个新接口的具体实例：真实效果一直缺失，收到的报告却一直是“已生效”，完整更新仍保留真实世界。对应反例同时证明，这个不变且未达目标的信息集不能属于任何全后继严格降秩的证书区域。因此桥接既允许假报告，也不会把重复假报告误证成进展。

## 0.3.1 加强返回合同

独立复核发现，旧 `TerminatingObservation` 对每条执行仅要求存在一个满足 `finish` 与 `emits` 的返回时刻。它允许第 0 tick 返回非法 `absent`，第 1 tick 返回合法 `applied`，然后只选择后者满足合同。这样不能保证普通接口实际消费的首次终结响应合法。

新合同同时要求：**每条允许执行在有限 tick 内有返回，而且每个 `some (World, Observation)` 返回都满足 `finish` 与 `emits`。** 它不再容许后来的合法返回掩盖先前非法返回。`late_valid_return_cannot_hide_early_invalid` 对同一反模型证明旧存在性条件成立、新合同不成立；完整原键恢复证书仍有具体实例。

这里的合法表示符合所声明的转移与报告关系，**不等于报告内容真实**：`emits` 仍可以允许错误或诱导性报告。该修订没有新增首个返回时刻、输出稳定性或墙钟时间上界的保证，也没有改变宏边界计数约定。

这修复的是返回合同过弱的问题，不是 Lean 推导错误。具体轨迹提升原本还独立要求 `realizesFinish` 与 `realizesObservation`，因此旧模型也不能把该非法首次返回当作有效边界来证明实际成功。真实程序与协议之间的精化义务仍然保留。

## 公理与可信边界

本地证明没有 `sorry`、`admit`、自定义 `axiom` 或 `native_decide`。允许的传递公理仅为 Lean 标准的 `propext`、`Classical.choice`、`Quot.sound`；无依赖的定理在回执中记为 `[]`。审计覆盖所有本地 `theorem` 声明，其引用的定义和证书会被传递检查。

`#print axioms` 的作用和限制可参考 [Lean 官方公理说明](https://lean-lang.org/doc/reference/latest/Axioms/)。此次使用的是 Lean 构建和内核类型检查，**没有另运行一套独立实现的内核校验器**。其他 Agent 对规格及证明进行了独立审阅并复编译，这与独立内核实现也分别记录。

一个定理可以没有自定义公理，却仍带有强的函数参数与合同前提。审计公理不能替代审阅这些前提是否切题、可实现或已部署。本工程明确保留：

- 初始信息集确实包含真实世界，实际转移和报告通道的覆盖完整性。
- 实际选择的动作与被证明策略一致，且角色只用合法观察。
- 所允许环境中的宏执行有限返回世界与实际收到的报告，且所有返回均符合转移与报告关系；真实调度公平性另证。
- 中间状态被 `visits` 覆盖，旧消息和迟到效果没有遗漏。
- 证据语义绑定、核验器可靠性与关闭入口完整性。
- 真实状态压缩满足关系兼容性；概率、观察分布与公平性商另证。

进展核心采用有限前缀，不要求任务完成后继续运行。具体轨迹提升的便利推论采用全 `Nat` 的 `MacroRealization`，其存在是实现必须提供的见证，并非本工程证明真实程序必有无限索引执行。双世界正控的 `safe := True` 和立即返回只是该小模型的定义。

## 独立审阅后的改动

0.2.0 审阅指出并修复了三处会使初稿解释过强的问题：有限进展定理不再要求目标产生后继；具体轨迹提升明确绑定策略执行和完整观察更新；内部安全通过实际中间状态覆盖关系接入证明。另补完整恢复证书与可接受真成功的验收门正控。0.3.0 在此基础上统一关系观察接口，并消除逐边界真值包含的直接假设。

集成审计还修正了源哈希在构建后才计算的时间差，以及声明发现可能遗漏修饰声明或带点限定名的问题。保留的边界见 [FORMALIZATION.md](../FORMALIZATION.md)：这是可复查的条件定理、正控和反模型，生产采用、概率重试界及完整较新模型同步仍分别待验。
