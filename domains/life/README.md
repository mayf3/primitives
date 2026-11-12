# 人生原语

用可追溯的事实检查判断，区分长期方向、当前状况、本人承诺和下一步行动。日常从 [使用指南](GUIDE.md) 开始；只在分类拿不准时查 [概念与边界](CONCEPTS.md)。

本模块的默认概念入口来自 **Life State 存储格式 v2 与概念定义 v1.1**：五类认知对象 `Goal / State / Observation / Claim / Decision`，加上行动侧的 `Activity`；`Evidence` 表达支持或反驳关系。因此有六类记录目录，但没有新增第六类认知节点或独立 Evidence 内容节点。[来源：Life State README](sources/life-state-v2/README.md)、[自带概念定义](sources/life-state-v2/_definitions/concept-definitions.md)。

## 从问题进入

| 你现在遇到的问题 | 从哪里开始 |
|---|---|
| 一段随想混着事实、解释和打算 | [拆开事实与判断](GUIDE.md#separate) |
| 想知道某个判断是否仍站得住 | [检查判断与证据](GUIDE.md#check-claim) |
| 已经讨论很多，但不知道下一步做什么 | [把缺口变成有产出的行动](GUIDE.md#next-action) |
| 不确定一句话算目标、状态还是行动 | [六类概念与 Evidence](CONCEPTS.md) |
| 要对接旧记录、PCA 或校验器 | [版本与兼容边界](COMPATIBILITY.md) |
| 想看一次完整使用 | [合成复盘示例](examples/synthetic-review.md) |

## 本次整合的范围

这是 `life` 模块的 **0.1.0 整合版方法入口**，版本号只表示本模块的文档与检索接口。它不替换原 Life State 数据格式版本，也不表示人生记录、运行程序或个人决策已经迁移。

本次只导入六份方法文档的固定版本快照。用户的日记、173 条记录、数据库以及现行校验器均未导入。原记录继续由原来源管理；当前仓库只维护这套整合版方法、来源说明与示例。旧 PCA 作为独立历史实现参考保留，与默认 Life State 定义的差异见 [兼容表](COMPATIBILITY.md#versions)。

这里的 `life.goal`、`life.claim` 等是**方法条目的检索 ID**，不是用户记录里的 `G1`、`C1`。一个 Claim 的定义与某次使用产生的一条 Claim 记录是两种不同东西。

## 使用时保留的边界

- 原始材料提供事实出处；整理后的摘要不能替代原材料。
- 一次行动的工时和完成状态不能自动证明相关判断正确。
- Agent 可以整理证据、提出解释和候选行动；只有本人已明确作出的承诺才写成 Decision。
- 本模块中的合成例子和结构检查，不构成对用户生活的观察，也不构成方法效果验证。

来源的完整 SHA、文件哈希与导入范围见 [来源说明](sources/README.md) 和 [来源清单](sources/manifest.json)。
