# Writing Primitives vNext · 深度研究任务书

**研究问题：** 在同模型、同材料、同一作者约束、相近成本下，轻量 D/C/U/R 与回归协议是否能减少高影响问题漏检、无意义修改、事实/声音损失和多轮返工？若不能，允许减少或取消表示层。

## 研究任务

1. 以 [RESEARCH_SEEDS](references/RESEARCH_SEEDS.md) 为起点，系统对比 McKee、Hart、McPhee、Williams/Bizup、Booth、Minto、Toulmin、Flower–Hayes、RST、situation model 和 conversation analysis。区分创作工艺、理论解释和实验结果。
2. 检索 2024–2026 年 AI 写作反馈、编辑意图、长文结构、作者风格、中文口语、播客脚本、读者建模与多轮回归的原始论文。记录任务、语言、样本、方法、局限和外推条件。
3. 找到**最影响编辑决策**的机制：Author Contract、issue priority、U 的高承载保护、R 缺桥、span-level patch、regression guard、no-change、Move/Reader Evidence 的增量。
4. 专门比较 “普通编辑 prompt、Light IR、Full 7 IR”，不使用刻意削弱的基线，控制模型、材料、token/call 预算、交互轮次。
5. 通过真实作者的返工时间与真实读者/听众的理解、偏好验证可能的改善。没有真人测试时不把模型推断称为读者结果。

## 交付

来源矩阵、可吸收的原则和反例、按影响/证据/成本排序的最小改进、合成测试 gold issues、对照/消融实验、对应 README/SKILL/METHOD/REVISION 的小补丁。允许结论为“删掉某一原语或放弃整套形式化流程”。

**隐私：**只使用公开论文、公开方法与新编合成材料。不要恢复、猜测或引用私人稿件、真实个人经历、内部仓库及公司信息。未执行实验必须注明。
