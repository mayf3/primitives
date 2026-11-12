# 概念与边界

本页是 Life State 自带定义的检索与阅读摘要。来源为 [概念定义 v1.1](sources/life-state-v2/_definitions/concept-definitions.md) 和 [存储格式 v2 README](sources/life-state-v2/README.md)。下列七个索引条目包括**五类认知对象、一类行动对象、一类关系说明**；索引条目数量不等于顶层原语节点数量。

原始定义随本模块保存，本文的例句与使用检查由本次整合编写。记录 ID、字段细节和历史实现差异见 [兼容说明](COMPATIBILITY.md)。

<a id="goal"></a>
## 目标 Goal

**回答的问题**：长期希望抵达怎样的生活状态？

既有定义把 Goal 限定为人生级、长期稳定的方向。换一种工具、工作路径或具体项目，目标仍应成立。“搭一个平台”“制作一期节目”是路径或行动，不能仅因重要就升级为人生 Goal。必要前提可以与终态一同说明，但前提是否成立仍要由 Claim 接受证据检验。

Goal 声明进展看什么，通过 `verified_by` 引用 State 或 Observation；数值由观察记录、由状态承载，Goal 本身不存当前值。

**使用检查**：把眼前做法拿走，这个方向是否仍然成立？它是否声明了观察进展的依据？[来源：Goal 定义](sources/life-state-v2/_definitions/concept-definitions.md)。

<a id="state"></a>
## 状态 State

**回答的问题**：在这个时间点，我处在什么可核查的状况？

State 是当前事实性现状的快照，可引用观察、判断和决策的已有记录，但不把解释写成事实。“现有草稿共三页”可以是当前状态；“草稿太差”“还差读者证据”“应该先重写”属于判断或检验点。过去发生过什么，应保留在 Observation。

State 可承载指标的当前值，并引用相应原始观察。更新状态不等于覆盖过去的观察；“当前”应有时间边界。

**使用检查**：读者能否区分现状、推断、建议和未来计划？每个关键数值是否有出处？[来源：State 定义](sources/life-state-v2/_definitions/concept-definitions.md)。

<a id="observation"></a>
## 观测 Observation

**回答的问题**：发生了什么、谁说了什么、记录到了什么？

Observation 保存可由感官、记录或引文核对的事件、数据和原话，不把因果判断混入事实。记录“某人说自己焦虑”不等于证明某个行为由焦虑引起；记录一段原话也不代表认可原话中的判断。

出处应指向结构化条目或原始素材，保留足以定位的坐标。会重编或清理的摘要不承担原始证据的角色。找不到来源时明确标注待溯源，不补造出处。

**使用检查**：别人能否从保留的材料确认这件事？句子中是否暗含了尚未证实的解释？[来源：引用纪律与 Observation 定义](sources/life-state-v2/_definitions/concept-definitions.md)。

<a id="claim"></a>
## 断言 Claim

**回答的问题**：我作出了什么判断，它如何接受观察检验？

Claim 可采用反驳性检验，也可采用累积性检验。因果或预测判断可以被反例推翻；立场、偏好与价值判断通常依赖一系列行为和观察来支持或削弱，不能机械套成一次实验定真假的命题。

每条判断需要保留陈述、论证、适用范围或反方边界、证据及检验点。原陈述不能被悄悄改成另一句话；新增解释、补全论证或立场变化应留下版本和关系。

| Life State 状态 | 在本模块中的含义 |
|---|---|
| `INCONCLUSIVE` | 证据不足；新建判断的默认状态 |
| `SUPPORTED` | 来源要求反驳型达到“证据确凿”、累积型达到“可信度充分”；不能仅凭出现一条弱支持就升级，仍需保留适用范围与反对证据 |
| `CONTRADICTED` | 被相关观察反驳，主要用于可证伪判断 |
| `WEAKENED` | 反例或行为背离累积，使原判断减弱 |
| `RETIRED` | 判断已过时或立场发生变化；旧记录保留 |

立场型 Claim 通常在 `INCONCLUSIVE` 与 `SUPPORTED` 之间随证据积累变化；行为背离可导致 `WEAKENED`，立场改变则保留旧条目为 `RETIRED` 并建立新条目。来源保留了直接相反观察下使用 `CONTRADICTED` 的例外，不能简化为绝对禁用。[来源：Claim 定义](sources/life-state-v2/_definitions/concept-definitions.md)。

**使用检查**：能否说清哪种观察与判断相关？支持了多大的范围？有没有把“我已决定这样做”误当成判断已得到支持？

<a id="decision"></a>
## 决策 Decision

**回答的问题**：本人已经明确承诺了什么？

Life State 把 Decision 限定为本人已经拍板、通常涉及资源或路线取舍的行动承诺。Agent 的建议、本人暂时的倾向、对一种方案的讨论，都不能自动变成 Decision。本人先前已经明确作出的承诺，可以依据原始记录整理，无需为每次整理重复确认。

保留谁作出决定、何时作出、依据哪些判断或观察；后续改变应保留取代关系与旧记录。具体决策类型不要借用旧 PCA 的强制三分法替代 Life State 的定义。

**使用检查**：能否指出本人明确承诺的原话或可靠记录？是已经决定，还是仍在考虑？[来源：Decision 定义](sources/life-state-v2/_definitions/concept-definitions.md)、[版本差异](COMPATIBILITY.md#versions)。

<a id="activity"></a>
## 活动 Activity

**回答的问题**：具体做什么，完成后会得到什么？

Activity 是行动侧唯一原语；它与五类认知对象分层。它需要可执行动作、明确目的和相应绑定。意图使用 `Observe / Hypothesize / Test / Optimize`，状态使用 `active / next / done / superseded`。来源对日常维护活动的收录另有限定，应按该系统的范围理解，而不是对生活价值作判断。

预期产出与实际产出要分开。Activity 可以计划产生新观察，却不能在执行前就把结果写成已有证据；执行完成也不意味着相关 Claim 成立。`Test` 和 `Hypothesize` 需要关联判断。字段强制程度的来源差异见 [遗留差异](COMPATIBILITY.md#open-differences)。

**使用检查**：能否说明行动产出将怎样检验判断或改变状态？若失败或没有获得结果，是否仍能如实记录？[来源：Activity 定义与状态枚举](sources/life-state-v2/_definitions/concept-definitions.md)、[Life State README](sources/life-state-v2/README.md)。

<a id="evidence"></a>
## 证据 Evidence：关系说明

**回答的问题**：哪条观察，在什么范围内支持或反驳哪个判断？

Evidence 在这里表达 Observation 与 Claim 的支持或反驳关系，不创建独立的第七类内容记录。引用必须能回到真实材料，关系的解释也要接受审查；把两个 ID 连起来并不自动证明推断成立。

例如，一次工具运行成功只直接说明那次运行结果；要支持“这种做法能帮助读者理解”，仍需要与理解有关的观察。多次转述同一份材料，不会自动增加独立证据数量。

**使用检查**：证据是否与判断针对同一问题和条件？是否把努力、接受建议或完成部署当成效果证明？[来源：Life State 关系摘要](sources/life-state-v2/README.md)、[PCA V0 证据定义与 P2](sources/pca-v0/README.md)、[PCA 认知原则](sources/pca-v0/PRINCIPLES.md)。后两个来源只支持证据与付出的边界，不把 PCA 数据模型引入 Life State。
