# Spec → Model → Proof → Code：研究沉淀与架构判断

**研究基线：2026-11-27 · 状态：研究综合，不是完整实现证明**

本文件沉淀本轮国际研究报告中的稳定认识，并将研究事实、工程推论和本仓库建议分开。它是后续方法设计的参考依据，不替代任何消费项目的 Product Spec、Product Authority 或真实验收。

## 1. 核心架构判断

目前没有发现一套被广泛采用、能够对任意应用自动机械完成以下全部环节的通用工业系统：

`Product Spec fidelity → mathematical model → theorem proof → arbitrary-language implementation refinement → environment assumption freshness → original acceptance`

已有成熟实践通常把其中若干段做到很强。我们的目标不应是宣称发明了新的形式化方法，而是把已有方法连接成可维护、可追溯、可失效、可对抗验证的 Agent-assisted engineering lifecycle。

核心分工：

- **Spec 是意图与产品义务的权威来源。** 证明层不得自行改写用户目标。
- **数学模型是共同语义中心。** 它把需求转化为对象、状态、事件、转移、性质、观察和环境前提。
- **形式化证明验证精确命题。** Lean 等工具证明模型性质在声明的假设下成立，不证明自然语言翻译一定忠实。
- **实现精化建立模型与具体代码的关系。** 关系可以由机器证明、代码级验证、模型驱动测试和真实轨迹等不同强度的证据支持。
- **环境证据和原始验收独立。** 运行前提失效时，依赖这些前提的系统保证必须降级；产品是否完成仍由原始 Spec 的验收决定。

## 2. 必须分开的正确性维度

| 维度 | 问题 | 合适证据 | 不能冒充它的证据 |
|---|---|---|---|
| Requirement correctness | 需求是否完整、一致并代表用户意图？ | Owner/Stakeholder 审查、场景、正反例、验收追溯 | Lean 通过 |
| Model fidelity | 模型是否忠实表达需求及允许/禁止行为？ | 双向追溯、覆盖检查、可满足性、成功路径和反例审查 | 模型没有找到反例 |
| Proof correctness | 定理是否由声明定义和前提推出？ | proof assistant kernel、axiom/TCB audit、固定工具链 | 测试通过 |
| Implementation conformance | 具体代码是否符合抽象模型？ | Refinement proof、程序验证、MBT、Trace Validation | 模型正确 |
| Verifier trustworthiness | checker、adapter、normalizer、CI 是否可靠？ | 独立负控、变异测试、权限隔离、版本绑定 | checker 自己报告 PASS |
| Product acceptance | 真实产品是否满足原始 Spec？ | 原始 Acceptance 在目标环境中的执行证据 | 前五项任一 PASS |

任何一层的 UNKNOWN、STALE、INCOMPLETE、DEFERRED 都必须保持可见。不得聚合成没有类型的绿色 VERIFIED。

## 3. 研究案例及可借鉴边界

| 案例 | 成熟能力 | 适合借鉴 | 不应夸大之处 |
|---|---|---|---|
| seL4 | Isabelle/HOL 分层 refinement：抽象规格、可执行规格到 C 实现 | 初态对应、gluing/refinement relation、分层证明和可信边界 | 高投入、特定系统；不是所有应用代码都应全量证明 |
| IronFleet | 分布式系统的状态机精化、Hoare-style 验证、安全性与活性 | Safety/Liveness 同时考虑、分布式实现证明 | 证明架构和实现成本较高 |
| AWS TLA+ | 关键分布式设计的状态空间探索 | 在实现前发现并发、故障和协议设计问题 | 设计模型检查不等于生产代码已证明 |
| AWS Cedar VGD | Lean 可执行语义、模型性质证明、Rust 生产实现差分随机测试 | 让形式化模型与生产实现保持持续比较 | 差分随机测试不是一般性 Rust refinement theorem |
| Microsoft CCF | TLA+ 协议模型与真实执行轨迹/测试连接 | 将规格与真实运行验证纳入 CI | Trace 只覆盖已记录执行 |
| Quint / Quint Connect | Quint 模型检查、生成执行轨迹、Rust 实现回放 | 最接近日常 model-to-code MBT 的工具路线 | Quint Connect 目前以 Rust 集成为中心；其他语言需要 adapter |
| TLA+ Trace Validation | 将实现状态映射到规格状态，验证记录轨迹 | 生产 Trace 的模型一致性检查 | 不穷尽未执行路径，完整性需额外协议 |
| FoundationDB | 确定性模拟、故障注入、精确重放 | 时序、故障、恢复和并发问题的可复现测试 | Simulation 不等于数学证明 |
| Dafny / Verus / F* | 在程序语言/受限语言中表达规格并验证实现 | 小型、高价值、稳定的纯核心 | 不宜直接替代整个 Dart/Kotlin 应用栈 |
| Alloy / Event-B | 有限结构探索、可满足性、状态/事件 refinement | 需求早期发现矛盾、空模型、错误抽象 | 有界检查的结论受 scope/工具语义约束 |
| GSN | 组织 Claim、Context、Assumption、Strategy、Evidence | 解释为何异构证据足以支持工程保证 | Assurance argument 不是定理证明 |

## 4. 数学模型必须检查可行性

安全不变量本身不足以说明模型有用。空模型、不可达成功态、永远停留在初始态的系统，都可能让某些安全定理平凡成立。

对模型 `M=(S,E,I,T,O,A)`，至少区分：

- **Initial non-emptiness**：`∃ s, s ∈ I`。
- **Safety**：所有可达状态满足不变量。
- **Reachability**：需求指定的状态/事件是否可达。
- **Success-path existence**：是否存在到达目标状态的有限路径。
- **Liveness**：在明确环境和公平性前提下，必要进展是否最终发生。
- **Termination**：操作是否在声明条件下结束。

可达集合：

`Reach(M) = μX. I ∪ {s' | ∃s∈X, e∈E, T(s,e,s')}`

安全性质：

`∀s∈Reach(M), P(s)`

成功路径存在性：

`∃s₀…sₙ,e₀…eₙ₋₁. s₀∈I ∧ (∀i<n, T(sᵢ,eᵢ,sᵢ₊₁)) ∧ Goal(sₙ)`

公平性必须作为显式假设审查，不能为了证明进展而把“调度器最终一定执行”直接塞进前提。Safety refinement 也不能自动推出 Liveness refinement：具体实现可能无限执行抽象不可见的 stuttering 步骤。

## 5. Refinement 的工程含义

对具体实现状态 `C`、抽象模型状态 `S`，建立关系：

`R ⊆ C × S`

至少审查：

1. Initial correspondence：具体初态对应允许的抽象初态。
2. Step simulation：具体一步可由抽象零步或有限步模拟，并保持 R。
3. Observation mapping：返回值、持久化状态、事件、UI 投影如何映射到模型观察。
4. Stuttering justification：每个被归类为抽象不可见的具体事件都必须有理由。
5. Liveness preservation：若产品要求最终推进，排除无限不可见 stuttering，并声明 fairness 条件。
6. Boundary/TCB：线程调度、OS、编译器、FFI、网络、数据库等未证明边界必须显式列出。

零步/多步模拟适用于内部实现步骤、异步刷新和 reconciliation，但不能把业务进展伪装成内部步骤。

## 6. Trace 完整性与因果关系

逐行检查 `from/event/to` 合法，只能说明已观察记录可被模型解释。它不能证明日志完整。

正确性 Trace 应额外保留：

- trace/run ID、producer ID、producer epoch；
- 每个 producer 的单调 sequence；
- event ID、transition ID；
- parent/cause IDs；fan-out/batch 使用多个 links；
- model/code/mapping/verifier revision；
- segment close / watermark / completeness marker；
- 原始数据哈希与 normalization version。

跨 producer 只保证因果偏序，不要假装所有事件都有全局墙钟顺序。丢事件、缺失 segment close、sequence gap、采集器失败或不完整查询必须返回 INCOMPLETE/UNKNOWN。OpenTelemetry 的 Span/Trace/Links 可复用作关联和因果传播，但其文档明确指出采样、导出失败和查询裁剪会造成 partial traces；它不是 correctness completeness protocol。

## 7. Evidence Graph：派生索引，不是新事实源

建议追溯关系：

```text
REQ → DEC → MODEL → STATE / TRANSITION
                  ↓
                PROP → THM → LEAN
                  ↓
                MAP → CODE → TEST
                  ↓
CODE → TRACE → OBSERVATION
MODEL → ASSUMPTION → PROBE → OBSERVATION
REQ → ACCEPTANCE ← MODEL / THM / MAP / TRACE / PROBE
```

各权威源保留自己的语义：
- Spec 保存 REQ/DEC/ACC；
- 项目模型保存 MODEL/STATE/TRANSITION/PROP/ASSUMPTION；
- Lean declaration 保存 THM；
- adapter/source annotation 保存 MAP；
- 运行时生成 TRACE/OBS；
- Acceptance 保存原始任务结果。

CI 从这些来源生成 canonical JSON graph、reverse index 和 dangling-link/coverage report。Canonical graph 是派生物，不允许人工编辑，不得变成第四份事实源。

机械 checker 能检查 ID 唯一性、引用存在、版本一致、必需边缺失、映射符号不存在和证据过期；它不能自行判断某个需求是否代表用户真实意图。

## 8. AI Agent 的可信边界

Agent 可承担需求拆解、模型草拟、Lean proof engineering、adapter 生成、反例调查和修复建议；但不得独立控制权威需求、被测实现、验证器和最终验收标准。

对关键保证：
- Spec 意义变更必须经过原 Product Authority。
- code-only 变更不得静默弱化模型/不变量。
- model/assumption 变更必须列出影响的定理、mapping、测试、反例和旧证据失效范围。
- verifier/adapter/normalizer 变更必须触发独立负控与权限审查。
- 关键最终验证由独立 CI 身份执行，不能依赖 coding Agent 自己的本地 PASS。
- 原始故障反例不可删除；修复后必须证明旧反例被区分，同时保留正向成功路径。

## 9. 对本仓库与治理仓库的分工

**primitives** 负责可复用数学定义、Lean theorem kernel、模型/Trace/Evidence 数据语义、工具链参考实现和技术边界。

**agent-development-governance** 负责 Product Authority、变更路由、责任分离、独立审查、CI gate、证据版本绑定与失效规则。

**consumer repository** 负责自己的 Spec、业务模型、实现映射、测试适配器、真实环境证据和产品验收。不得把所有项目业务状态机搬进共享原语仓库。

## 10. 下一步

先完成一个小而真实的端到端试点（建议 codex-go FSM-E/FSM-UI）：冻结原始 Spec、真实故障、代码 commit 和验收；建 6–10 个状态、10–20 个关键转移；执行模型可满足性/成功路径检查；证明关键 Lean 性质；实现代码 adapter、Trace 完整性校验、PBT 和环境探针；注入非法转移、丢事件、过期 assumption 三种负控；最终仍执行原始 Acceptance。

P0 成功只说明一个试点切片闭环，不代表整个项目或其他消费者已经形式化验证。

## 参考来源（原始/官方资料优先）

- seL4: https://sel4.systems/Info/FAQ/proof.pml
- IronFleet: https://www.microsoft.com/en-us/research/publication/ironfleet-proving-practical-distributed-systems-correct/
- AWS formal methods: https://www.amazon.science/publications/how-amazon-web-services-uses-formal-methods
- AWS Cedar verification-guided development: https://aws.amazon.com/blogs/opensource/lean-into-verified-software-development/
- Quint Connect: https://github.com/quint-co/quint-connect
- Quint MBT: https://quint.sh/docs/model-based-testing
- Apalache: https://apalache-mc.org/docs/apalache/index.html
- Alloy 6: https://alloytools.org/documentation.html
- TLA+ Trace Validation: https://docs.tlapl.us/using:tlc:trace_validation
- Microsoft CCF: https://www.usenix.org/conference/nsdi25/presentation/howard
- FoundationDB simulation: https://github.com/apple/foundationdb/blob/main/documentation/sphinx/source/testing.rst
- OpenTelemetry trace data model: https://opentelemetry.io/docs/specs/otel/trace/data-model/
- Lean axiom audit: https://lean-lang.org/doc/reference/latest/Axioms/
- Hypothesis stateful testing: https://hypothesis.readthedocs.io/en/latest/stateful.html
- Kotest: https://kotest.io/docs/quickstart/
- fast-check model-based testing: https://fast-check.dev/docs/advanced/model-based-testing/
- Dart property-testing candidates: https://pub.dev/packages/property_testing and https://pub.dev/packages/kiri_check

研究日期、论文/工具版本和具体部署状态应在真正采用时重新核验。报告中的 2026 年论文线索属于研究输入；在没有取得并逐篇核验原始论文前，不把其摘要性描述当成已复核结论。
