# 来源、版本与推导边界

**本层是 2026-11-13 新编的工作方法，版本 0.1.0。** 用户提出的任务是：为人生、写作、设计等领域的原语建立更底层的设计方法，追求极简、可组合和可推导，避免被语法或表现形式遮住内容关系。以下材料用于构造和检查，不等于支持本方法全部效果的独立证据。

<a id="repository"></a>
## 一、仓库内的固定基线

本次阅读基线为 [mayf3/primitives@2fdd514](https://github.com/mayf3/primitives/tree/2fdd51464efd47ea87fa2d2d857c1039fd97c51a)。完整 SHA：`2fdd51464efd47ea87fa2d2d857c1039fd97c51a`。人生、写作、视频模块为 `0.1.0`，设计模块为 `0.2.0`。下表为便于阅读提供工作文件链接；追溯本次依据时以固定提交的同路径为准。

| 来源 | 本次采用的内容 | 没有因此获得的结论 |
|---|---|---|
| [共享约定](../shared/CONTRACT.md)、[Agent 入口](../AGENTS.md) | 独立领域语义、显式交接、来源与新解释分开 | 四域必须共享一个本体或一套状态 |
| [人生概念](../domains/life/CONCEPTS.md)、[兼容说明](../domains/life/COMPATIBILITY.md) | 对象与关系分开；完成、承诺和证据作用不同 | 所有领域都应该转换为 Life 对象 |
| [Life State 来源定义](../domains/life/sources/life-state-v2/_definitions/concept-definitions.md) | State 的派生性质；Goal 作为操作性约定终点，不无限追问 | 派生对象都应删除；目标无需后续修订 |
| [人生合成例](../domains/life/examples/synthetic-review.md) | 用例内观察反驳必要条件，保留范围和本人承诺边界 | 任何真实人物已完成相同实验 |
| [写作动作](../domains/writing/ACTIONS.md)、[追溯与修订](../domains/writing/TRACE_AND_REVISION.md)、[写作合成例](../domains/writing/examples/action-and-trace.md) | 从材料、关系和声音分工；允许有身份的新解释 | 八动作已经独立、最简，或写作只能复述材料 |
| [设计候选](../domains/design/PRIMITIVES.md)、[0.2.0 评审](../domains/design/REVISIONS.md) | 直接决策的归属；下一步与入口预测可区分；允许回退和结束 | 十项必须保留，或所有点击都要带来新知识 |
| [视频候选](../domains/video/PRIMITIVES.md)、[配方](../domains/video/PATTERNS.md)、[验证](../domains/video/VALIDATION.md) | 语义与实现分层；身份与参照；比较可能是组合；理解与感受分别观察 | 十项不可约、画面正确就保证观众理解 |

元层不复制这些来源，也不改写原快照。四域的不可变导入文件仍由各自 `sources/manifest.json` 记录哈希；Git 固定提交用于追溯本次工作定义。

## 二、外部一手参考

以下仅作有限的方法参照。查阅日期 **2026-11-13**；正文为短摘要与本次应用说明，没有将整本书或论文导入仓库。

<a id="sicp"></a>
### SICP：基本表达、组合、抽象与表示分层

Harold Abelson、Gerald Jay Sussman、Julie Sussman，*Structure and Interpretation of Computer Programs*，第二版，1996。

- [1.1 The Elements of Programming，MIT Press 正文](https://mitp-content-server.mit.edu/books/content/sectbyfn/books_pres_0/6515/sicp.zip/full-text/book/book-Z-H-10.html)
- [2.1 Introduction to Data Abstraction，含 2.1.2 Abstraction Barriers，MIT Press 正文](https://mitp-content-server.mit.edu/books/content/sectbyfn/books_pres_0/6515/sicp.zip/full-text/book/book-Z-H-14.html)

**已查阅。** 1.1 将基本表达、组合与为复合结构命名的抽象分开；2.1 讨论使用方式与具体表示之间的接口。

**本次借鉴：** 原语基底与常用组合可以同时存在；方法使用者可以依赖清楚的行为约定，而不被迫绑定单一实现。把这一思想用于写作、交互和视频，是本稿的设计推论；该书没有证明本文的元问题数量或领域原语集合最少。

<a id="parnas"></a>
### Parnas：分解应围绕什么责任

D. L. Parnas，*On the Criteria To Be Used in Decomposing Systems into Modules*，*Communications of the ACM* 15(12)，1053–1058，1972。

- [正式出版与 DOI](https://doi.org/10.1145/361598.361623)
- [本次查阅的原论文扫描副本](https://ckrybus.com/static/papers/decomposing_systems_into_modules_1972.pdf)

**已查阅副本正文，重点为 What Is Modularization? 与 The Criteria。** 官方 PDF 抓取返回 403，不能记为已读官方全文。论文比较不同分解方式，讨论围绕设计决定分配责任和隐藏内部实现。

**本次借鉴：** 不只按表面顺序或表现形式分原语，要检查各项承担的决定与接口。这里的“隐藏实现”不等于隐藏判断归属：调用者可以不知道具体算法，但必须知道什么由该项负责、依据与限制是什么。论文对象是软件模块；把它用于领域方法构造，是本稿类比，不能替代实际使用检验。

## 三、本次新增的综合

下列内容由本次整理提出，不冒充上述材料中的原句或既有定理：

- 相对任务、默认能力与成本的领域原语定义。
- 一份领域约定与“辨认结构—定义责任和组合—用反例修订”的构造方法。
- 区分职责可分、相对集合不可删除、形式独立与全局最小。
- 把被转移到参数、上游准备和隐含常识中的判断计回简化成本。
- 四域推导的并列组织、交互四方案对照、视频比较的分解检查、轻量构造卡。

仓库既有合成例与本次新构造例均属于教学与审阅材料。Agent 的并行审阅用于发现定义冲突和遗漏，不属于相互独立的真人实验。当前没有冻结后的未见任务结果，也没有真实使用效果数据。

## 四、兼容与版本

元层 `0.1.0` 作为独立基础方法加入；仓库注册表升级为 `0.3.0`，只新增元层入口与检索范围，注册表 schema 仍为 `1.0`。四个领域的模块版本、ID、来源、状态规则和桥接版本不变。

新的 `meta.*` 是构造方法的定位地址，不是领域实例 ID。目录里有多少可检索小节，不等于声明有多少不可约元原语。后续若按本层建议修改某个领域，应单独评审、说明版本与兼容影响。
