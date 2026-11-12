# Changelog

## Lighter default and bounded probes — 2026-11-06 (PR proposal)

- 压缩主 SKILL，日常先交付文字或判断，表示与参考按需展开；不添加新核心原语或 Skill。
- 将“守与探”保留为可选试写，不限定开头、字数、唯一触发证据或永久停止。
- 对新增推论提供反例检查，同时保留数量、归属、删减限定检查；不宣称完整证明。
- 固定材料虚构与自由虚构分开，新增非教学试写例；技术 A/B 保留原文，另给局部口播候选。
- 增补未运行的回归场景；未新增模型/受众效果结论，外部参考本轮未复核。
- 跟进评审：压缩入口重复段，明确高承载功能承接；固定材料允许自然成句，示例增加前史选材与语流备选，不新增规则体系。


## Audience value & journey clarification — 2026-11-06

- 复用 D/C/U/R、Move 与 Reader Evidence，加入按需听众审阅，不增加原语或独立 Skill。
- 区分探索与定稿、理解与关注、意图与文本依据与真人效果；非功利性作品按自身目标评价。
- 将最小修改澄清为风险与有效性取舍，不以字数或最浅层级排序，不自动降低作者承诺。
- 新增同材料 A/B 候选及语义越界反例；不将某个偏爱的版本预设为零问题金标准。
- 新增听众测试设计与独立开放问题说明；未运行行为实验、模型对照或真人试听。
- 未复制私人稿件或外部评审原文；本轮没有重新核验既有文献索引。

## Optional Voice & Texture supplement — 2026-11-05

- 依据跨模型审阅建议，新增 U 的隐式边界承载和 R 的有内容接力检查，**不新增核心原语**。
- 新增按需 [Voice & Texture](references/VOICE_TEXTURE.md) 和独立 [natural-chinese-voice Skill](skills/natural-chinese-voice/SKILL.md)。
- 在 SKILL/METHOD/REVISION 增加媒介适配、语义回查、表达回归与停止规则，禁止为“自然”编造故障、经历或硬造分歧。
- 加入三类原创合成对照稿、十二个未执行 Voice 测试场景和三份跨模型固定任务；**暂无真实 Gemini 生成稿**。
- Gemini 优势、Voice Pass 改善与读者效果均属待验证问题，不作为已证明的事实。

## vNext design proposal — 2026-11-05

**Not a stable release; no parser, automated evaluator, or real-reader study is claimed.**

- 建议将 Writing IR 从七个同级原语，收缩为 **D/C/U/R 四核心对象**。
- 将 E 调整为 `C.kind=event`，B 改为按需派生的 Move，RS 移出作品 IR，成为 Reader Evidence。
- 将“审稿数量”转成“问题证据与优先级”，默认 0–3 个关键问题，允许明确不改。
- 建立 issue → anchored patch → preservation guards → regression → status → stop 的独立修订协议。
- 强化作者约束、范围/情态、来源、表达归属、高承载语句与对话关系。
- 纳入对照实验和消融实验设计；不宣称已有实验结果。
- 公开目录使用合成案例与通用说明；旧版历史保持独立。

Related: [Migration](references/MIGRATION.md) · [Evaluation plan](tests/EVALUATION.md).
