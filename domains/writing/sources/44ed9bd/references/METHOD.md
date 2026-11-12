# Writing IR vNext · 最小对象与按需视图

本规范只保留**四种核心对象 D / C / U / R**。它们服务具体编辑决策，不要求每篇生成完整语义图、统一 JSON 文档或唯一合理的篇章分析。凡是对问题判断没有帮助的字段或边，均可省略。

## 一、四个对象

### D · Direction / Author Contract

表示作者真正委托的写作问题与限制，优先记录：

```yaml
id: D-01
status: author_confirmed  # 或 proposed / unknown
question: "为哪类读者解释一个现象？"
audience: "具备一般背景的中文读者"
medium: article            # article / speech / monologue / dialogue / other
intended_takeaway: "理解收益和边界，而非相信绝对结论"
hard_constraints:
  - "不扩大材料适用范围"
non_goals:
  - "不写成产品宣传"
voice_preferences:  # optional, only if author supplied/confirmed
  register: "自然、准确，不强制幽默"
  reference_refs: []  # must be authorized and appropriate for publication
version: "contract-1"
```

事实或写作偏好都可以写入 D，但应标出确认状态。**Observed D** 只是编辑根据现稿恢复出的“稿子实际做了什么”，不替代已确认的 D。标题、风格模板或模型判断不能自动变成作者目标。

**用好已有的听众字段，不新建听众本体。** `audience` 可说明已有知识、当前处境和关注点，未测的起点写成假设；`question` 说明此稿具体处理什么；`intended_takeaway` 写预期留下的理解、判断、体验或处境辨认，`non_goals` 限定不承诺什么。不能贬低受众起点制造“认知升级”，也不要求所有作品交付行动清单。

例如（作者尚未采用的候选）：面向准备把事务交给工具的非工程读者，解释一个状态提示究竟支持哪些判断，希望他们能在新情境中问清还缺什么证据；不承诺排查具体故障。比“普通读者、了解概念”具体，但是否值得这个受众投入时间仍待判断。

**探索与定稿不是新增状态机。** 构思/试写时可比较不同方向及材料能支撑的价值；定稿审阅保护已确认 D，不每轮重开方向。D 已兑现不自动证明选题对受众有价值；要改变已确认方向，应单独提出理由与代价并由作者采用，不能因易于过审偷偷降低承诺。

### C · ContentItem（“作品在说什么”）

```yaml
id: C-01
kind: claim            # claim / evidence / question / concept / recommendation / event
meaning: "在一次小规模试验中参与者完成任务更快"
scope: "仅该试验中的参与者与任务"
modality: reported     # reported / possible / likely / established / hypothetical
attribution: "原始材料作者"
provenance:
  source_kind: provided_material  # verified_public_source / author_statement / inference / hypothetical / unknown
  source_ref: "source-note-1"
verification: not_independently_verified
expression_refs: [U-02]
```

**概念归一化不意味着事实升级。**“有一次被观察到”不得改成“普遍证明”；外部数据与作者推导不能合并归属；说话人的玩笑和比喻不能自动转成事实。证据强度、范围、情态和说话人归属分别记录。

#### `C.kind=event` 的可选槽位（旧 E 迁移）

```yaml
id: C-05
kind: event
meaning: "一次读书会临时调整环节"
event:
  reality_mode: fictional_demo   # lived / external_case / hypothetical / fictional_demo
  actor: "组织者"
  context: "首次活动"
  goal: "让新参与者更容易讨论"
  obstacle: "部分问题无人回应"
  action: "缩短介绍、延长讨论"
  expected: unknown
  feedback: "有参与者主动补充"
  change: "参与方式变化（未证实长期效果）"
  time: unknown
provenance: {source_kind: hypothetical, source_ref: "fictional-case"}
```

只在需要叙事时填字段；`unknown` 是合法答案。非虚构中的人物内心、利害和结局不能自动补造。**固定材料限制事实与关系，不限制原句字面**：允许同义改写、自然衔接、拆合句与有目的的选材，但衔接词也不能暗增排他性、时序、因果或感受。即便材料虚构也如此；获准的自由虚构可补写设定，不能再声称只改变了表达。假设场景不冒充真人经历。区分现实顺序、讲述顺序与成稿揭示顺序；麦基的戏剧 Beat 不等于本系统 Move。

### U · Unit（“这版原文具体如何说”）

```yaml
id: U-02
document_version: "draft-v3"
anchor:
  location: "第 3 段第 2 句"
  exact_text: "至少在这次尝试里，我们没再冷场。"
  context_before: "主持人原先担心讨论时间太短。"
  context_after: "她还不确定下次是否适用。"
speaker: "组织者"
expression_roles: [self_report, limitation, voice]
content_refs: [C-01]
high_load: true    # 编辑风险提示，不是独立本体对象
```

锚点必须来自**实际当前版本**；多人对谈保留轮次、说话者与回应对象。High-load U 是一个句子承担事实、归属、语气、论证或人物定位等多项作用时的保护提示：可改，但要有替代承接。

**U 的隐式边界承载（可选表达策略）**：`C.scope` 与 `C.modality` 是必须保留的**意义约束**，并非规定 U 必须出现“不能据此断言”“这并不意味着”之类固定句式。若符合 D.medium，允许将限定融入具体观察、简短条件、前后两句或人物已提供的口语方式；**不得借“更自然”新增动作、故障位置、内心或更强的确定性**。必须明确的警告、法律/学术限制可保留原句。该策略不是第 5 原语，细则见 [VOICE_TEXTURE](VOICE_TEXTURE.md)。

### R · Relation（“为什么相关”）

```yaml
id: R-01
source: C-02
target: C-01
type: qualifies
basis: "只在一次试验中观察到，不能外推到所有场景"
status: supported       # supported / partial / disputed / missing
```

**初始最小词表：**`supports`、`qualifies`、`contrasts`、`depends_on`、`exemplifies`、`replies_to`、`temporally_precedes`、`serves`。如缺少某类关系，可在具体任务中用自然语言说明，不应自动扩建大型 taxonomy。只保存会影响编辑决定的关系。

- `temporally_precedes` 是先后，不是因果。
- 人物声称“因为 A 所以做 B”是带归属的动机陈述，不等于客观因果或普遍结论。
- `supports` 要注明范围、来源与隐含前提；写“因此”不能替代论证。
- 对谈以 `replies_to` 和 U 的 speech action 标明提问、回答、追问、澄清、纠正；不靠添加语气词制造互动。
- **有内容的接力，不强制对抗**：有效回应可包括补充、复述确认、提供证据、边界追问、修复误解或在有真实根据时提出反例。角色无须每轮抬杠；“很有意思，下一个特点呢”若只是换题并无新作用，则需要检查 U/R。

## 二、按需视图，不增加核心本体

### Move（旧 B/Beat 的兼容视图）

```yaml
move:
  current_question: "一次活动改善，不代表规律已经成立"
  content_refs: [C-01, C-02]
  key_units: [U-02]
  intended_progress: "读者理解为什么保留限定"
  handoff: "下一步如何检验？"
  source: editor_hypothesis
```

在结构较复杂、确有重复或顺序问题时使用。**不是每段都需一 Move，也不规定每 Move 必有一个心理变化。**它是编辑对讲述作用的可反驳假设，而不是作品中的持久对象或读者实测。

**意图、文本依据与受众效果分开。** `intended_progress` 只记录作者/编辑预期，不能改称“本段实际交付”；当前版本究竟写出了什么要引用 `key_units` 和相关 C/R，受众是否真的获得则属于 Reader Evidence。不要让意图字段同时充当检验结果。

在关键位置按需看：正文呈现了什么，为什么值得理解、关注或停留？可以来自解释、人物选择、处境辨认、声音或余韵，这些是例子，不是必须归类的穷尽清单。无知识疑问时可省略 `current_question`，不为填字段制造问题；`handoff` 可是过渡、停顿或结束。具体细节与留白不因没有方法论总结就被判错，也不因此免于检查与 D 的关系。**理解顺畅不等于愿意继续**，两者另看。见 [非教学试写例](../examples/SMALL_PROBE_AND_NARRATIVE.md)。

### Reader Evidence（旧 RS/ReaderStep 的独立协议）

```yaml
reader_evidence:
  mode: model_prefix_prediction   # author_hypothesis / model_prefix_prediction / editor_inference / reader_observation
  audience_definition: "符合目标起点、未接触后文与预期答案的读者"
  stop_at_version: "draft-v3"
  stop_at_anchor: "第 4 段末"
  exposed_text_scope: "第 1–4 段"
  prompt_or_question: "到这里主要理解了什么？仍有哪些疑问？"
  response_summary: "预测可能仍想知道下一场是否有效"
  alternative_readings: ["部分读者会把一次改进看成长期保证"]
  observed_sample_size: null       # 仅真人观察时填写
```

模型前缀测试只准读取对应前缀；作者的预期或模型预测不称“听众已经感到”。实测应记录受众招募、题目、材料、时间和观测样本。可比较理解、疑问、关注、负荷和偏好，但不得凭理论直接赋予一个“感染力分数”。

**证据限制**：真正的 `model_prefix_prediction` 必须由未见后文、总结或预设答案的新调用完成；读过全文再模拟属于 `editor_inference`。少数真人反馈可以记录为 `reader_observation`，但不据此证明普遍效果。没有标记、下一问题与作者不同、能复述或愿意继续，均不是单独的成功/失败判据。详见 [听众测试设计](../tests/AUDIENCE_CASES.md)。

### 其他派生视图

- **Evidence Cluster**：多项材料若只支持同一结论，按组处理，不默认每项都成为新推进段落。
- **High-load U**：标出容易在润色中失去多重功能的原句。
- **Planned / Observed Diff**：把作者确认的计划与当前正文独立比较，不拿一方覆盖另一方。

## 三、递归的写作与审稿

写新稿可从材料和 C 开始，也可先试写 U 再恢复 R/D。审稿应先确认 U 的当前版本，再识别 observed，然后与已确认 D 比较。**两者都不是不可返回的线性编译管线。**不为“这篇文字为什么好”而形式化一切；只为当前问题调用足够的表示。

## 四、体裁策略，而非普适定律

| 体裁 | 主要风险 | 适用取舍 |
|---|---|---|
| 技术长文 | 删掉条件、混淆外部事实与作者推导 | 保留推导与必要细节，先修 R，再调整 U |
| 商务说明/决策稿 | 结论和依据不便定位 | 可以结论先行，但不是其他体裁的强规则 |
| 非虚构故事 | 为戏剧性虚构预期、动机或结局 | 重点核 C[event] 的来源与同维度变化 |
| 演讲/教学 | 结构清楚却难听懂 | 以真人听众的停点理解而非纯书面判断验证 |
| 单人口播 | 书面句法、术语连续密集，或把 C 的范围限定机械写成免责套话 | 试读 U、按需削减形式动词和抽象词簇，让限定融入具体可说的表达；事实密度与范围不能降低 |
| 双人/多人对谈 | 问题藏答案、轮流读提纲、捧哏式接力、角色同质化 | 检查 R.replies_to 是否真的承接对方：补充、确认、澄清、类比或有根据的反驳；**不强制冲突**，优先真人试听 |

规则应允许合理多解：两个不同顺序都满足 D 时，给出得失而不强判其中一个“结构错误”。

## 五、解释与研究边界

D/C/U/R 是待验证的设计，不是已证明的最小表示。文本核对、模型/编辑推断、作者选择和真人观察分别记录；有受众观察也不自动证明普遍效果。外部文献不是本方法的直接验证。

日常创作可依据现有材料、作者判断与有限反馈选稿，不必先运行实验；需要检验效果时查 Reader Evidence 与 [测试](../tests/AUDIENCE_CASES.md)，未执行的测试不写通过。
