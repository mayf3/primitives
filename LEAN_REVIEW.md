# Lean 模型与验证入口独立复核

**2026-11-20 · 注册表 0.6.1 · 复核基准 `13cebbea8d6260d464466af3dddff473195e74e7`**

## 结论与范围

本次逐项检查公共核心与六域的定义、命题、假设、证明和说明，先在干净副本复跑基准的 101 条显式定理、70 项测试与结构检查，再独立构造反例。结果不是“零问题”：确认 **1 个验收入口漏洞、1 个协议规格缺口、1 处需澄清的前提说明**。

没有找到推翻现有条件定理的 Lean 逻辑错误。验收入口漏洞影响“所有声明都已审计”的保证；协议缺口表明一个合同比其通常解释更弱。两者分别修复，不能因为内核编译通过就忽略。

修复仍使用同一 Lean 4.19.0 工具链，没有引入独立内核实现。其他 Agent 的独立审阅与反模型构造有助于检查规格，但不能替代工具链可信性或实际系统的精化证明。

## R1 · P1：字符字面量使未审计声明逃过验收

位置：`tools/verify_lean.py` 的 `code_only` 和声明发现。

旧扫描器识别注释与字符串，却没有识别 Lean 的字符字面量。两个合法的双引号字符之间，源码会被扫描器误当作字符串。临时副本中加入以下内容，旧验证器仍完成 clean、build、显式定理公理审计和 JSON 适配器，并报告 101 条定理通过：

```lean
def openingQuote : Char := '"'
axiom reviewHiddenFalse : False
theorem review_hidden_false : False := reviewHiddenFalse
def closingQuote : Char := '"'
```

这里的 `False` 来自新加入的公理，Lean 按其规则允许推导；错误在于仓库验收入口没有发现该公理和额外定理。基准源码没有这段写法，不能据此声称原有 101 条命题已被反驳。

修复分为两层：字符、转义和标识符按受限约定正确处理；同时从编译后的 Lean 环境按清单中的模块枚举实际声明，检查每个安全逻辑声明的传递公理以及显式定理覆盖。所有 theorem、私有逻辑声明和自动生成的安全逻辑声明均纳入检查。Lean 标记为 unsafe/partial 的编译辅助单列，不作为逻辑定理审计，不按名称猜测排除；安全证明仍不能依赖未获准公理。额外编译声明不计为新增原语定理。

回归检查要求上述输入被拒绝；编译环境检查还单独拒绝未审计的自定义公理、缺失模块、缺失或错误种类的显式命题、不允许的传递依赖。源扫描不再独自承担公理覆盖保证。

## R2 · P2：一次较晚的合法返回掩盖先前的非法返回

位置：`domains/agent-workflow/lean/AgentWorkflow/Progress.lean` 的 `TerminatingObservation`。

旧条件为“每个允许执行都存在某个 tick，返回值满足 `finish` 和 `emits`”。独立反模型在 tick 0 返回 `absent`，在 tick 1 返回 `applied`，而 `finish` 只允许 `applied`。旧条件可以只选 tick 1；甚至可以构造区域包含初态的完整 `BeliefCertificate`。

这没有反驳具体轨迹提升定理：`MacroRealization.realizesFinish` 仍单独要求所选实际边界的完成合法。因此这是合同过弱、容易被调用方误用的规格问题。

新合同要求：

```text
每条允许执行：
  有限时刻存在 some 返回
  并且每一个 some 返回都满足 finish 与 emits
```

新增定理 `late_valid_return_cannot_hide_early_invalid` 对同一个模型同时证明旧存在性条件成立、新合同不成立。理想化恢复协议与完整正控证书同步加强，仍可实例化。持续错误报告的原反模型保留：符合 `emits` 不等于报告真实。

没有把宏边界改为首次返回时刻，也没有增加返回值稳定性、墙钟时限、真实服务终结或调度公平性的保证。

## R3 · P3：写作必要信息必须由调用者正确表达

位置：`domains/writing/lean/README.md` 与 `Writing/Revision.lean` 的说明。

`Faithful evidence required draft` 表示 `evidence ⇒ draft` 且 `draft ⇒ required`。如果 `required=True`，即使 evidence 可满足，删空为恒真草稿也能通过。第二个条件只保护实际编码进去的要求。

说明已明确：调用者负责写出必要信息，并针对具体编辑证明 `Revision` 的两个蕴含。有限组合定理组合已有契约，不自动判断任意自然语言编辑是否合格。数学定义与定理保持原状。

## 其他已复核的边界

| 范围 | 独立检查 | 判断 |
|---|---|---|
| 公共抽象 | 解码只定义在观测像集；碰撞反例；经典选择的使用 | 没有额外空类型缺口；数学解码器存在不产生可执行算法 |
| 公共契约 | 空关系、零步轨迹、组合的前提 | 仅部分正确性；文档没有将其升级为终止 |
| Agent Workflow | 非空信念、同一信息集同一策略、全后继降秩、可接受真成功的正控 | 排除了空信念与仅挑幸运路径；证书仍需实际提供 |
| Agent Workflow | 全 `Nat` 的具体轨迹见证 | 便利推论要求无限索引见证，文档已披露；有限前缀核心不需要任务完成后继续运行 |
| Design | 更换任务查询，使被隐藏 detail 变为关键 | 原保证仅针对既定 `nextAction`；不能推出真实页面可读或任意任务信息充分 |
| Learning | `[3,4]` 已区分原三个模型；加入第四种记忆策略击穿 `[2,3,4]` | 三题是指定模型空间内充分性，不是最小题数或真实掌握 |
| Life | 构造非空决策轨迹；记录新版本后仍可引用旧历史承诺 | 非真空不变量；模型不实现撤销或当前执行权限，文档已披露 |
| Writing | 可满足且非恒等的合格弱化；不一致证据；恒真 required | 条件契约可组合；证据真值、可满足性和必要信息由外部提供 |
| Video | 共同仿射映射、整数比例、区间端点、计数余额与 JSON 字段绑定 | 未发现与声明范围冲突的错误；有理倍速、舍入、实际并行和渲染效果均不在结论内 |

## 复现与记录

在仓库根运行：

```bash
python3 tools/primitives.py validate
python3 -m unittest discover -s tests -v
python3 tools/verify_lean.py
```

`lean-verification.json` 绑定修复后的源码、工具链、命令、显式定理与编译环境公理依赖。回执只说明记录哈希对应的版本；以本次退出码为准，失败不刷新旧成功回执。

本次修复后的实跑结果：

| 检查 | 结果 |
|---|---|
| 仓库结构与来源 | 6 域、66 条登记项、58 份固定来源、3 份桥接、3 个领域校验器通过；固定来源无改动 |
| Python 回归测试 | 79/79 通过；其中验证器测试从 13 项增加到 22 项 |
| 原合并版本的补充审计 | 保持基准源码不变，干净重编译后用新环境审计检查：原 101 条显式定理、865 个安全逻辑声明、其中 324 个编译 theorem 均通过；没有发现 R1 已在基准源码中发生 |
| 干净 Lean 构建与显式定理审计 | 102 条通过；新增的 1 条是 R2 的协议负控 |
| 编译环境公理审计 | 868 个安全逻辑声明通过，其中 325 个为 theorem，包含原 102 条及自动生成证明；这些数不能相加 |
| 编译辅助 | 699 个 unsafe、3 个 partial 声明按 Lean 安全元数据单列；不声称完成逻辑依赖白名单审计 |
| R1 反例重放 | 新词法检查拒绝源码；绕过源码扫描、直接审计原反例编译产物时，也拒绝隐藏的公理依赖 |
| 独立语义探针 | 四域 10 项，返回合同修复后另 4 项，均通过 Lean 编译；见下方附录 |

原有显式 `#print axioms` 结果与编译环境收集的同名定理依赖逐项一致。实际基准与修复版本中均未观察到未获准的逻辑公理；R1 是通过独立注入反例确认的验收漏洞。

下方额外 10 个正反例是本次独立复核证据，不注册为领域 API，也不增加产品定理计数。将代码保存到仓库外的 `ModelBoundaryProbes.lean`，先完成上述构建，再运行：

```bash
lake env lean /absolute/path/to/ModelBoundaryProbes.lean
```

这些例子只使用合成模型。它们支持表中的适用范围判断，没有引入真实个人记录、运行日志或用户效果证据。

## 附录：独立语义探针

```lean
import Design.Disclosure
import Learning.Identifiability
import Life.Commitments
import Writing.Revision

namespace HumanDomainReview

-- Design: the original guarantee is satisfiable for every actual page, but a
-- new task query may make the field previously declared auxiliary essential.
open Design.Disclosure in
example : ∃ page : PageState,
    page.expanded = false ∧ nextAction page = .repairOutput ∧
    visibleAction (render page) = .repairOutput := by
  exact ⟨⟨true, false, 7, false⟩, rfl, rfl, rfl⟩

def priceSensitiveAction (page : Design.Disclosure.PageState) :
    Design.Disclosure.NextAction :=
  if page.supportingDetail = 0 then .proceed else .repairOutput

example : ∃ first second : Design.Disclosure.PageState,
    Design.Disclosure.render first = Design.Disclosure.render second ∧
    priceSensitiveAction first ≠ priceSensitiveAction second := by
  exact ⟨⟨true, true, 0, false⟩, ⟨true, true, 1, false⟩,
    rfl, by decide⟩

-- Learning: [2, 3, 4] is a sufficient question set, not a minimal one.
open Learning.Identifiability in
example : Distinguishes frameResponse [3, 4] := by
  intro first second same
  have atThree := same 3 (by decide)
  have atFour := same 4 (by decide)
  cases first <;> cases second <;> simp_all [frameResponse]

-- One additional deterministic model defeats the prior three-question test.
-- false computes on all questions; true memorizes those three only.
def expandedResponse (memorizes : Bool) (seconds : Nat) : Nat :=
  if memorizes then
    if seconds = 2 ∨ seconds = 3 ∨ seconds = 4 then 30 * seconds else 0
  else 30 * seconds

open Learning.Identifiability in
example : ¬ Distinguishes expandedResponse [2, 3, 4] := by
  apply same_answers_prevent_identification expandedResponse [2, 3, 4]
    false true (by decide)
  intro question member
  have choices : question = 2 ∨ question = 3 ∨ question = 4 := by
    simpa using member
  rcases choices with rfl | rfl | rfl <;> decide

example : expandedResponse false 5 ≠ expandedResponse true 5 := by decide

-- Life: real nonempty decisions are reachable, not only vacuous invariants.
open Life.Commitments in
example : ∃ events : List Event,
    (run empty events).decisions = [⟨7, 1⟩] ∧ Supported (run empty events) := by
  refine ⟨[.suggest ⟨7, 1⟩, .recordCommitment ⟨7, 1⟩, .adopt ⟨7, 1⟩], ?_, ?_⟩
  · decide
  · exact every_recorded_decision_has_commitment _

-- A new version does not revoke an old historical commitment in this model.
open Life.Commitments in
example : (run empty [.recordCommitment ⟨7, 1⟩,
    .recordCommitment ⟨7, 2⟩, .adopt ⟨7, 1⟩]).decisions = [⟨7, 1⟩] := by
  decide

-- Writing: a proper, nonidentity weakening has a consistent source witness.
abbrev W := Bool × Bool
def firstFact (w : W) : Prop := w.1 = true
def bothFacts (w : W) : Prop := w.1 = true ∧ w.2 = true

open Writing.Revision in
example : Faithful bothFacts firstFact bothFacts ∧
    Revision firstFact bothFacts firstFact ∧
    (∃ w, bothFacts w) ∧ ¬ Entails firstFact bothFacts := by
  refine ⟨⟨fun _ h => h, fun _ h => h.1⟩,
    ⟨fun _ h => h.1, fun _ h => h⟩,
    ⟨(true, true), rfl, rfl⟩, ?_⟩
  intro stronger
  have impossible := (stronger (true, false) rfl).2
  contradiction

-- Faithful alone does not establish a possible source or draft.
open Writing.Revision in
example : Faithful (fun _ : W => False) firstFact (fun _ => False) ∧
    ¬ ∃ w : W, (fun _ => False) w := by
  exact ⟨⟨fun _ h => h, fun _ h => False.elim h⟩,
    fun ⟨_, impossible⟩ => impossible⟩

-- The required-content contract itself must be substantive: True permits
-- deleting everything. This is a modeling responsibility, not an inference.
open Writing.Revision in
example : Faithful bothFacts (fun _ : W => True) (fun _ => True) := by
  exact ⟨fun _ _ => trivial, fun _ h => h⟩

end HumanDomainReview
```

## 附录：返回合同修复的独立复核

以下四项定向检查确认加强合同后仍有非空成功证书，且不要求报告诚实。保存到仓库外的 `ReturnContractSecondReview.lean`，以相同的 `lake env lean` 命令运行。它们同样不计入产品定理数量。

```lean
import AgentWorkflow.Progress

namespace ReturnContractSecondReview

open AgentWorkflow.Progress
open AgentWorkflow.Evidence

-- The strengthened contract is inhabited without forcing truthful reports.
def fixedWorldFalseReport : ObservationProtocol EffectWorld Unit EffectReport :=
  { deceptiveProtocol with
    execution := fun world _ output =>
      ∀ tick, output tick = some (world, .claimsApplied) }

example : TerminatingObservation fixedWorldFalseReport deceptiveBelief () := by
  intro world _ output allowed
  refine ⟨⟨0, (world, .claimsApplied), allowed 0⟩, ?_⟩
  intro tick after report returned
  have samePair : (world, EffectReport.claimsApplied) = (after, report) :=
    Option.some.inj ((allowed tick).symm.trans returned)
  exact ⟨congrArg Prod.fst samePair, trivial⟩

example : ∃ output,
    fixedWorldFalseReport.execution .absent () output ∧
    output 0 = some (.absent, .claimsApplied) := by
  exact ⟨fun _ => some (.absent, .claimsApplied), fun _ => rfl, rfl⟩

-- The repaired idealized success protocol has real executions, a full
-- certificate, and an initial belief which does not already meet acceptance.
example : ∃ output,
    replayProtocol.execution .absent () output ∧
    TerminatingObservation replayProtocol ambiguous () := by
  refine ⟨fun _ => some (.applied, ()), ?_, replay_has_finite_observation⟩
  refine ⟨rfl, ?_⟩
  intro tick world observation returned
  cases returned
  rfl

example : Nonempty (BeliefCertificate replayProtocol) ∧
    replayCertificate.region ambiguous ∧ ¬ BeliefTarget replayProtocol ambiguous := by
  refine ⟨⟨replayCertificate⟩, trivial, ?_⟩
  intro target
  have impossible := (target .absent trivial).1
  cases impossible

end ReturnContractSecondReview
```
