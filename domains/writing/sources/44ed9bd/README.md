# Writing Primitives / 写作原语

**版本：vNext 设计提案（2026-11-05）** · **状态：尚未通过比较实验验证** · **用途：中文非虚构、技术长文、经验分享、演讲与口播/对谈稿的写作和审稿**

> **先找真正影响作品目标的问题，再使用足够少的结构；以最小修改改善文本，同时保护事实、作者意图、独特表达和此前已成立的部分。**

Writing Primitives 不是写作的完整本体（ontology）、自动打分器，也不是必须填满字段的七张表。它是供作者和 AI 编辑按需使用的**轻量编辑中间表示（Writing IR）**和**可回归的修改协议**。其价值取决于最终是否减少误诊、误改、返工，能否保留作者自己的判断与声音；方法自身尚未被实验证明。

**新增的表达层补充**：事实、范围和论证正确，并不自动意味着写得自然、听得顺畅。自然语感不是与事实同级的新对象，而是 U 的媒介适配和 R 的真实回应问题；有依据的表达损害可以成为主问题，纯审美喜好仍保留为可选实验。详见 [Voice & Texture](references/VOICE_TEXTURE.md)，并可按需使用独立 [natural-chinese-voice Skill](skills/natural-chinese-voice/SKILL.md)。

## 1. 四个核心问题，四种核心对象

| 对象 | 问题 | 保护边界 |
|---|---|---|
| **D · Direction / Author Contract** | 作者要完成什么、给谁看、哪些不可改变？ | 只有作者确认的约定才是已确认约束；现稿不能偷偷反写作者目标 |
| **C · ContentItem** | 作品究竟说了什么，依据、归属、范围与确定性是什么？ | 意思不等于措辞；自述、来源事实、推论和假设分开 |
| **U · Unit** | 当前**哪个版本、哪段原文、哪位说话人**具体怎样表达？ | 修改要有可复查的锚点；优先保护同时承担多项功能的原句 |
| **R · Relation** | 两个内容/表达之间为什么相关、依据是否成立？ | 先后不自动是因果；同意不等于证明；不为完整图谱而建边 |

**旧七原语不是被遗忘，而是重新分层：**

- **E / Event** 是 `C.kind=event` 的按需细化，描述真实或虚构场景中的目标、行动、反馈、变化；不补造动机、冲突、情绪或结局。
- **B / Beat** 改为按需恢复的 **Move 讲述推进视图**，用于长文、叙事和演讲。它不再是必须持久化的顶层对象，不要求每段都有一次“认知升级”。
- **RS / ReaderStep** 转为独立的 **Reader Evidence 读者假设与观察协议**。作者预期、模型前缀预测、编辑判断与真人反馈不得混同。
- **Evidence Cluster、High-load Unit、Revision** 分别是派生分析、风险提示和修改工作协议，不新建顶层原语。

详见 [METHOD](references/METHOD.md) 与 [MIGRATION](references/MIGRATION.md)。

## 2. 写作先试写，审稿按问题展开

默认只读 [SKILL.md](SKILL.md)。方向未定时从简短 Brief 和现有材料试写，局部任务直接改指定文字；只有具体困难需要时才加载表示、视图或参考文件。下面是审稿路线，不是创作前必须走完的流程。

```text
作者约束 D + 当前真实版本 U
    → 只从正文恢复 observed 主线（不臆断作者意图）
    → 发现问题并按影响 × 证据排序
    → 默认选 1–3 个值得解决的问题（也允许 0 个）
    → 仅为这些问题提取所需 C / R / U 锚点
    → 产生最小 patch + preservation guards
    → 检查已成立约束、跨段影响与前轮回归
    → 作者决定采用；必要时真人阅读/试听
    → 若没有高影响问题则 STOP
```

**写作是递归过程**：可以先试写，再返回 D/C/R 调整，不能把上述流程理解成必须逐步编译、不可回退的流水线。

### 判断“真问题”的门槛

优先处理违反明确作者约束、事实与范围不符、论证桥不成立、读者理解有可观察障碍、重复造成明确功能损失、问答或说话人发生逻辑错位的问题。“更高级”“不够有情绪”“开头必须三句”等，无证据时只能列为**可选偏好实验**。没有值得改的地方，就写明保留理由，不制造意见。

### 最小修改的责任

一个建议至少要说明：**原句/版本与位置、问题依据、最小修补方案、必须保留的作用、可能损失、受影响范围、是否真实修改并复查**。提出建议 ≠ 作者同意 ≠ 正文已落实 ≠ 检查通过。见 [REVISION](references/REVISION.md)。

## 3. 不追求一个“质量总分”

事实忠实、论证、结构、声音、读者理解、对谈互动、时长和成本常常互相牵制。不要把模型对读者心理的猜测写成受众实测，也不要把一个分数当作作者价值取舍。对于播客，要检查实际可听性和轮次接力，而非只把转写稿“书面化”。

## 4. 入口与文件

- Agent 执行：[SKILL.md](SKILL.md)
- 按需中文语感/对谈：[references/VOICE_TEXTURE.md](references/VOICE_TEXTURE.md) · [可插拔伴侣 Skill](skills/natural-chinese-voice/SKILL.md)
- 对象和按需视图：[references/METHOD.md](references/METHOD.md)
- 局部 patch、回归和停止：[references/REVISION.md](references/REVISION.md)
- 七原语到 vNext：[references/MIGRATION.md](references/MIGRATION.md)
- 过往用法的匿名经验：[references/USAGE_AND_LESSONS.md](references/USAGE_AND_LESSONS.md)
- 经典与论文线索：[references/RESEARCH_SEEDS.md](references/RESEARCH_SEEDS.md)
- **纯虚构**演示：[examples/SYNTHETIC_REVIEW.md](examples/SYNTHETIC_REVIEW.md) · [Voice Pass 对照](examples/voice/SYNTHETIC_VOICE_COMPARISONS.md) · [小范围试写与非教学片段](examples/SMALL_PROBE_AND_NARRATIVE.md)
- 跨模型参考语料的**采集协议，暂无真实 Gemini 输出**：[examples/model-comparison/README.md](examples/model-comparison/README.md) · [三份统一任务](examples/model-comparison/BRIEFS.md)
- 未运行的评测与案例：[tests/EVALUATION.md](tests/EVALUATION.md)、[tests/CASES.md](tests/CASES.md)、[tests/VOICE_CASES.md](tests/VOICE_CASES.md)
- 研究任务：[RESEARCH_BRIEF.md](RESEARCH_BRIEF.md)
- 发布隐私检查：[PUBLICATION_CHECKLIST.md](PUBLICATION_CHECKLIST.md)
- 变更记录：[CHANGELOG.md](CHANGELOG.md)

## 5. 证据与版本边界

本版是**根据编辑实践、理论线索及研究报告重构的待验证方法提案**。关于某些写作失败机制的外部论文不等于本方法已被验证；文件里的“经验”不等于对照实验，“设计”不等于已运行系统。不得声称已有完整分析器、36 例测试通过或真人受众验证。旧版的七原语可继续作为历史分析术语，但默认 Agent 使用本版轻量规则。

**公开边界：**本目录只使用通用规范与合成案例，不包含私人稿件、真实个人经历、公司工程细节、内部仓库路径或未经授权的资料。发布前仍须完成 [公开检查](PUBLICATION_CHECKLIST.md) 并决定许可证。

## 听众价值与体验：按需视角（2026-11-06）

内容结构成立、表达自然、值得读/听是三个可分别检查的质量问题，不是三道固定流水线。复用 D 的听众与预期收获、C/R 的实质支撑、Move/U 的讲述和 Reader Evidence 的验证，不新增原语或强制 Skill。探索时可找更值得写的方向，定稿时保护作者已确认的约定；意图、文本依据、真人效果分别记录。

入口在 [SKILL](SKILL.md) 与 [METHOD](references/METHOD.md)；[同材料的两个候选](examples/AUDIENCE_VALUE_COMPARISON.md)不预设胜负，[测试设计](tests/AUDIENCE_CASES.md)尚未运行。[待解决问题](research-notes/AUDIENCE_OPEN_QUESTIONS.md)是讨论材料，不是 Agent 必须逐条执行的新规则。
