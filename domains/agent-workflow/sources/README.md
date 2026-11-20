# 来源说明与公开边界

## 直接构造来源

- 本模块的直接概念底稿是一份**私有的独立架构审阅稿**：《无人值守工作流的数学模型与历史检验》，v1.1，2026-11-15。其讨论了 \(M=(X,X_0,U,E,\Delta,obs,Acc,Env)\)、\(X=(G,P,D,A,K,W)\)、S1–S3、L1–L2、有限可达性博弈与 H1–H11。
- 0.2.0 追加核对了 2026-11-18 v2.4 与 2026-11-20 后续复验的抽象语义：信息集、全后继进展、状态充分性、可信证据和概率前提。公开 [修订说明](../FORMALIZATION.md) 是去敏重写；新 [Lean 文件](../lean/README.md) 是本次构造的可复查证明，不是源稿原有的形式化结果。完整较新源稿及大型检查器尚未迁入。
- 本公开版本是**重新概括、去除实际运行轨迹与私人标识、重新定义可检验原语**后的工作稿；**没有逐字导入原稿，也未向公开仓库发布私有 Issue、会话、实例、原始证据包、访问凭据或本地路径**。
- 因原始审阅稿不在公开仓库，它的历史结论不能当作外部读者可核实的生产证明。公开 H1–H11 只有**合成反例类型**，不冒充原真实历史的复核结果。本模块的 `sources/manifest.json` 因此没有登记不实际包含的源文快照（`imports: []`）。
- 本仓库包含数学概念整理、原语候选、有限示例和明确范围的 Lean 条件证明；没有正式安装新版执行器，也没有更改任何私有工作流任务状态。

## 可以公开复核的参考

| 资料 | 用于支持什么 | 不支持什么 |
|---|---|---|
| [Turing 1936 原论文](https://cs.stanford.edu/people/trevisan/cs172-07/turing36.pdf) | 构形、状态和单步的形式化方法动机 | 不证明现代 Agent 工作流可无人值守 |
| [Lamport：行动的时序逻辑](https://lamport.azurewebsites.net/pubs/lamport-actions.pdf) | 安全、活性及行为轨迹的表述参考 | 不证明这里列出的不变量已经满足 |
| [可达性/对抗博弈讲义](https://finkbeiner.groups.cispa.de/teaching/automata-games-verification-15/downloads/notes.pdf) | 有限获胜区域与策略构造的基础形式 | 不覆盖真实并发、无限环境和模型错误 |
| [Lean 公理与依赖检查](https://lean-lang.org/doc/reference/latest/Axioms/) | 解释 `#print axioms` 与传递依赖 | 不验证定理前提在真实系统中成立；本工程工具链另固定为 4.19.0 |
| [AWS 事务发件箱设计模式](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) | 业务状态与事件发送一致性的一种工程手段 | 不意味着任何具体 Outbox 已正确安装或端到端工作 |
| [Svc Workflow 执行控制规范 V3](https://github.com/mayf3/svc-workflow/blob/main/docs/specs/SVC_WORKFLOW_EXECUTION_CONTROL_V3.md) | 现有实现家族对 outbox 通道与启用条件的公开合同例子 | accepted 规范不等于生产启用 |
| [Svc Workflow 治理义务规范 V3](https://github.com/mayf3/svc-workflow/blob/main/docs/specs/SVC_WORKFLOW_OWNER_OBLIGATION_WORKFLOWS_V3.md) | 原任务、治理与工作流义务交接的具体设计例子 | accepted 设计不等于实际业务完成 |

## 本版证据等级

- **术语与模型**：作者衍生的抽象定义，待独立审核与反例检验。
- **例子**：纯合成，未声称来自真实观察。
- **有限检查**：本仓库代码在明确状态与故障范围内的检验；结果以实际运行输出为准。
- **Lean 证明**：本轮新构造的条件命题、正控及反模型，命题、公理与运行回执公开；没有概率重试界或生产精化证明。
- **生产、权限、业务效果**：本模块均未验证，也不应含真实运行证据。

下次修订时必须清楚说明：改变了哪个可观察区别、加入了什么反例、适用假设如何变化，以及当前实际通过的测试是什么。
