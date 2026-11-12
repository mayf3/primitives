# 人生模块来源快照

此目录保留本次选定的六份方法文档，按原始字节复制。来源文件与本次编写的 README、指南、概念摘要和示例分开维护；源文中的版本日期、历史状态和表述不作悄悄纠正。

## Life State：默认概念来源

- 仓库：`mayf3/personal-cognition-data`。
- 固定提交：`1ecfb09ec772e66ae5198581085fd12dc78c3485`。
- 本地保留：[README](life-state-v2/README.md)、[概念定义](life-state-v2/_definitions/concept-definitions.md)。
- 原路径：`current/life/README.md`、`current/life/_definitions/concept-definitions.md`。
- [固定版本上游目录](https://github.com/mayf3/personal-cognition-data/tree/1ecfb09ec772e66ae5198581085fd12dc78c3485/current/life)。

这是数据归档中随数据保存的方法定义。README 标注存储格式 v2；概念文件标注定义 v1.1。文件中的“当前状态”指来源文档所述时点，不是 2026-11-13 的运行观测。来源仓库包含的个人条目、原始随想与历史数据库不在本次导入范围内。

README 提到的 `format-spec.md`、三个 Skill、脚本及权限文件没有随这两份方法文档导入。本目录是**部分方法快照**，不是可启动的 Life State 环境；不能用当前仓库的结构检查替代原运行层验证。

## PCA V0：独立历史实现参考

- 仓库：`mayf3/personal-cognition-audit`。
- 固定提交：`c5e5cd953e5023fb49c09bc85823ae1427efca08`。
- 本地保留：[README](pca-v0/README.md)、[DESIGN](pca-v0/DESIGN.md)、[PRINCIPLES](pca-v0/PRINCIPLES.md)、[FUTURE](pca-v0/FUTURE.md)。
- [固定版本上游目录](https://github.com/mayf3/personal-cognition-audit/tree/c5e5cd953e5023fb49c09bc85823ae1427efca08)。

本次没有导入该实现的 `bin/pca`、Skill、运行数据或示例工作区。源文中这些路径与命令仍原样保留，以便回到固定上游版本查看；它们不是本仓库已提供的运行入口。PCA 的五节点图、四态 Claim 和 STOP / CONSTRAIN / TEST 决策契约保持原义，不覆盖默认 Life State 定义。

## 哈希与已知差异

[manifest.json](manifest.json) 逐文件记录上游路径和 SHA-256。任何后续解释或修正应写进工作文档或新增来源版本，不覆盖这些固定快照。

Life State 原文中 D8 只出现在正文、末表停在 D7，以及 Activity 绑定与 `expected` 强制程度不完全一致，均已在 [兼容说明](../COMPATIBILITY.md#open-differences) 记录。本轮没有修订原定义，也没有把这些差异推断为校验器的实际行为。
