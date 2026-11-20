# Lean 形式化切片

**Lean 4.19.0 · Agent Workflow 0.3.0 · 2026-11-20**

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

当前本域有 **42 个定理声明**：原有 37 个声明保留用途，新增更新等价、边界真值归纳和三个错误报告检查。数量包含辅助引理、正控与反例，不等于 42 项生产保障。以统一脚本产生的当前回执为实际核验依据；回执需绑定工具链、命令、退出码、输入文件 SHA-256 及各定理依赖。审计脚本不会把跳过检查登记为 PASS。

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
| 持续假报告的桥接实例与进展反例 | `deceptiveRealization`、`deceptive_reports_keep_absent_possible`、`deceptive_only_no_progress_certificate` | 真实效果始终缺失但报告全称成功；真实世界不被滤掉，且不能为不变假信念构造降秩证书 |
| 不确定性与真值保留 | `update_contains_actual`、`trace_contains_actual` | 初态包含真实世界，实际转移/报告全部被关系模型涵盖 |
| 状态摘要的精确关系表达 | `sufficient_iff_exact_relational_quotient` | enabled / 后继支持集 / 原验收兼容的充要条件；不涉及概率核 |
| 历史遗漏反例 | `no_exact_node_only_enabled_relation`、`node_only_loses_future_behavior` | 当前节点相同但在途请求不同，合法动作或未来效果不同 |
| 不可信报告不能绕过可靠门 | `reports_cannot_bypass_sound_gate` | 可信绑定、sound verifier、定义中的所有关闭路径；局部世界固定 |
| 多人共同错误的反模型 | `consensus_does_not_imply_truth`、`unsound_gate_can_close_false_goal` | 一致 PASS 不推出事实；丢失 soundness 后可假关闭 |
| 验收门正控 | `equality_evidence_is_sound`、`sound_gate_can_close_true_goal` | 合成的真值绑定门可以接受真成功，不是永远拒绝 |

源文件：[Progress.lean](AgentWorkflow/Progress.lean)、[Evidence.lean](AgentWorkflow/Evidence.lean)。两片段的关系观察更新现已连接；验收门仍是独立的局部切片。本工程尚未证明这些模型与真实服务组成完整的端到端精化关系。

## 0.3.0 消除的前提

过去 `MacroRealization` 直接要求每个边界都满足 `possibleAtBoundary`，而进展模型使用确定的 `observe` 函数。现在协议用 `emits : World → Observation → Prop` 描述所有允许报告，宏执行必须有限返回实际 `(World, Observation)` 对，且返回满足 `finish` 与 `emits`。这没有增加报告诚实或统计独立的假设。

这里的 `World` 是证明对执行结果的隐藏状态标注，不表示 Agent 或 API 响应能直接读到真实世界。策略仍只接收信息集，更新只使用实际收到的报告。

实现只需提供初态包含 `initiallyPossible`、每一步实际转移与实际报告的覆盖、以及按完整集合计算的更新。`MacroRealization.possibleAtBoundary` 调用证据模块的 `update_contains_actual` 归纳推出每个边界的包含关系。它从结构字段变成了定理，没有把旧前提换名藏回合同。

`deceptiveRealization` 是这个新接口的具体实例：真实效果一直缺失，收到的报告却一直是“已生效”，完整更新仍保留真实世界。对应反例同时证明，这个不变且未达目标的信息集不能属于任何全后继严格降秩的证书区域。因此桥接既允许假报告，也不会把重复假报告误证成进展。

## 公理与可信边界

本地证明没有 `sorry`、`admit`、自定义 `axiom` 或 `native_decide`。允许的传递公理仅为 Lean 标准的 `propext`、`Classical.choice`、`Quot.sound`；无依赖的定理在回执中记为 `[]`。审计覆盖所有本地 `theorem` 声明，其引用的定义和证书会被传递检查。

`#print axioms` 的作用和限制可参考 [Lean 官方公理说明](https://lean-lang.org/doc/reference/latest/Axioms/)。此次使用的是 Lean 构建和内核类型检查，**没有另运行一套独立实现的内核校验器**。其他 Agent 对规格及证明进行了独立审阅并复编译，这与独立内核实现也分别记录。

一个定理可以没有自定义公理，却仍带有强的函数参数与合同前提。审计公理不能替代审阅这些前提是否切题、可实现或已部署。本工程明确保留：

- 初始信息集确实包含真实世界，实际转移和报告通道的覆盖完整性。
- 实际选择的动作与被证明策略一致，且角色只用合法观察。
- 所允许环境中的宏执行有限返回世界与实际收到的报告；真实调度公平性另证。
- 中间状态被 `visits` 覆盖，旧消息和迟到效果没有遗漏。
- 证据语义绑定、核验器可靠性与关闭入口完整性。
- 真实状态压缩满足关系兼容性；概率、观察分布与公平性商另证。

进展核心采用有限前缀，不要求任务完成后继续运行。具体轨迹提升的便利推论采用全 `Nat` 的 `MacroRealization`，其存在是实现必须提供的见证，并非本工程证明真实程序必有无限索引执行。双世界正控的 `safe := True` 和立即返回只是该小模型的定义。

## 独立审阅后的改动

0.2.0 审阅指出并修复了三处会使初稿解释过强的问题：有限进展定理不再要求目标产生后继；具体轨迹提升明确绑定策略执行和完整观察更新；内部安全通过实际中间状态覆盖关系接入证明。另补完整恢复证书与可接受真成功的验收门正控。0.3.0 在此基础上统一关系观察接口，并消除逐边界真值包含的直接假设。

集成审计还修正了源哈希在构建后才计算的时间差，以及声明发现可能遗漏修饰声明或带点限定名的问题。保留的边界见 [FORMALIZATION.md](../FORMALIZATION.md)：这是可复查的条件定理、正控和反模型，生产采用、概率重试界及完整较新模型同步仍分别待验。
