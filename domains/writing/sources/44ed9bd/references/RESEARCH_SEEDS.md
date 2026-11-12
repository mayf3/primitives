# 研究入口与证据边界（2026-11-05）

这是公开文献**研究起点**，不是完整系统综述。区分 [实证] [理论] [创作实践] [设计假设]。论文支持其自身任务范围内的结论，**不证明 Writing IR 已有效**。

## 经典作品与理论

| 来源与公开入口 | 研究对象 | 可启发的部分 | 迁移边界 |
|---|---|---|---|
| Robert McKee, [Story](https://mckeestory.com/books/story/) [创作实践] | 场景变化与戏剧结构 | 事件目标/行动/变化 | 不强制真实非虚构有反转；麦基 Beat 不等于 Move |
| Jack Hart, [Storycraft](https://press.uchicago.edu/ucp/books/book/chicago/S/bo71028154.html) [创作实践] | 非虚构、人物、声音、podcast | 故事与口播审阅 | 工艺经验非通用因果实证 |
| John McPhee, [Draft No.4](https://us.macmillan.com/books/9780374537975/draftno4/) [创作实践] | 素材排列、语调、修订 | IR 是幕后支架 | 个人实践不能直接当算法 |
| Williams / Bizup, [Style](https://www.pearson.com/en-us/subject-catalog/p/style%3A-lessons-in-clarity-and-grace/P200000002140/9780137536603) [创作实践] | 连贯、重点、清晰 | U 局部润色 | 英语句法不直接适配中文 |
| Booth et al., [The Craft of Research](https://press.uchicago.edu/ucp/books/book/chicago/C/bo215874008) [方法] | 主张、理由、证据、异议 | C 的范围及 R 支持链 | 非所有文章都要写成研究论文 |
| Barbara Minto, [Pyramid Principle](https://www.barbaraminto.com/textbook) [创作实践] | 商务沟通层级与受众 | 体裁性的结论先行 | 不是叙事普适规则 |
| Toulmin, *The Uses of Argument* [理论] | 前提、限定、反驳 | R supports + C.scope | 不必复制全部 taxonomy |
| Flower–Hayes 写作过程研究 [理论] | 计划、表达、审阅的递归 | 工作流可反复回退 | 不证明严格按流程运行更好 |
| RST 篇章关系研究 [理论] | 文本片段功能连贯 | R 解释何以关联 | 不需完整关系树 |
| Situation Model / Conversation Analysis [理论/实证传统] | 阅读理解、对话相互回应 | Reader Evidence 与 U/R 对谈检查 | 不等于精确预测某人情绪 |

## 近期论文（已核公开论文页面与摘要，未做全篇复现实验）

| 论文及入口 | 论文任务与主要观察 | 对本方法的**待验证启发** |
|---|---|---|
| [FOXGLOVE · EMNLP 2026](https://aclanthology.org/2026.emnlp-main.781/) | 69 篇议论文、2,340 条专家/模型反馈；反馈锚点有差异，较长反馈影响质量评价 | 锚定、优先级，不把长意见当质量 |
| [Beyond Single-shot Writing / Mr Dre · ACL 2026](https://aclanthology.org/2026.acl-long.609/) | 五种报告 Agent 多轮修订，论文报告先前已覆盖内容与引用出现 16–27% 回归 | 保护前轮成果、检查非目标变化 |
| [Help Me Write a Story · ACL 2025](https://aclanthology.org/2025.acl-long.1254/) | 1,300 篇受控扰动故事，模型常没找准最大问题、不会可靠决定何时批评 | issue ranking、no-change |
| [Can You Make It Sound Like You? · ACL 2026](https://aclanthology.org/2026.acl-long.2030/) | 81 人风格后编辑实验，仍留模型风格与较低多样性 | 高承载 U 与作者判断，而非单一风格分 |
| [PodBench · ACL 2026](https://aclanthology.org/2026.acl-long.2019/) | 800 个播客脚本生成样本，指令遵循不保证内容实质 | 内容、轮次、角色声音分别评估 |
| [UniT · Findings ACL 2025](https://aclanthology.org/2025.findings-acl.1180/) | 编辑意图 taxonomy（细节待深入复核） | 避免增殖重复编辑标签 |
| [Author-in-the-Loop Response Generation and Evaluation · ACL 2026](https://aclanthology.org/2026.acl-long.565/) | 作者相关的回复生成评价（需核具体任务） | D 的作者约束，不直接外推所有写作 |

## 必须寻找反证

AI 介入有时能提高单篇写作品质，也可能导致不同作品同质化；长文先规划可能改善任务完成，也可能引入重复；中文口语不能直接用英文书面测评替代。请研究**什么时候某个原语没有增量，何时简单编辑提示词更好**。

研究记录至少保留：论文发表状态、原始 URL、体裁/语言、数据和对照、主要发现、局限、源材料阅读程度（论文全文/摘要/待核）、与本系统关系（解释/启发/直接验证）。此目录目前**不存在本系统的直接效果验证**。
