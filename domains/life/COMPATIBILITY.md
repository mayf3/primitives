# 版本、来源与兼容边界

本模块把已有方法放在一个可检索入口中，保留各来源原本的语义与历史。这里没有执行记录格式转换，也没有替换任何现行校验器。

<a id="versions"></a>
## 两套已核对来源

| 项目 | 默认概念来源：Life State v2 / 定义 v1.1 | 历史实现来源：PCA V0 |
|---|---|---|
| 固定仓库版本 | `mayf3/personal-cognition-data` 的 `1ecfb09ec772e66ae5198581085fd12dc78c3485`，其中 `current/life/` 的方法文档 | `mayf3/personal-cognition-audit` 的 `c5e5cd953e5023fb49c09bc85823ae1427efca08` |
| 来源性质 | 已归档的数据快照中随数据保存的定义；不是本次对当前生产环境的检查 | 系统仓库当次核对的 `main` 基线；作为独立历史实现保留 |
| 认知对象 | Goal / State / Observation / Claim / Decision | GOAL / STATE / OBSERVATION / CLAIM / DECISION |
| Activity | 行动侧唯一原语，实际存在第六类记录目录 | 不入认知图，只通过产生 Observation 与图连接 |
| Evidence | 支持、反驳等引用关系 | OBSERVATION → CLAIM 的 SUPPORTS / CONTRADICTS 边 |
| Goal 范围 | 人生级长期方向；项目、工具与路径不得直接升级为 Goal | 希望抵达的状态，包含 claimed / revealed 类型 |
| Claim 状态 | `SUPPORTED / INCONCLUSIVE / CONTRADICTED / WEAKENED / RETIRED` | 按支持与反驳边派生的 `untested / supported / contradicted / mixed` |
| Decision | 本人明确拍板的行动承诺 | 输入与验收要求 STOP / CONSTRAIN / TEST 三类 |
| ID 与存储 | G1 / S1 / O1 / C1 / D1 / A1；一条记录一个 Markdown 文件，含 YAML 结构表 | GLM-0001 / STA-0001 / OBS-0001 / CLM-0001 / DEC-0001；原文 Markdown、草稿 YAML、图 JSONL |
| 本次导入 | README 与自带概念定义两份 | README / DESIGN / PRINCIPLES / FUTURE 四份 |

表中差异均可在 [Life State README](sources/life-state-v2/README.md)、[概念定义](sources/life-state-v2/_definitions/concept-definitions.md) 与 [PCA DESIGN](sources/pca-v0/DESIGN.md) 核对。Life State 来源文档标注 2026-08-24 / 2026-08-25；它们出现在 2026-10-04 的数据迁移快照中。本次导入日期为 2026-11-13，不能用导入日期覆盖原文版本日期。

## 合并目录不等于合并数据模型

默认使用 [GUIDE](GUIDE.md) 与 [CONCEPTS](CONCEPTS.md) 理解 Life State。阅读 `sources/pca-v0/` 时，切换到该历史实现自己的定义；不得把其四态 Claim、ID 规则或 Decision 子类型直接填进 Life State 记录。

本仓库的 `life.goal` 等 ID 只定位方法说明，不替代 `G1` 之类的具体记录 ID。跨文档引用用户记录时，还需指明来源系统及其版本，不能只凭 ID 字符串假定是同一条记录。

原始数据根仍拥有其记录与格式定义。本模块的更改不会自动回写原仓库、改写原记录或安装 Skill。后续若要迁移真实数据，需要另行准备明确的字段映射、状态处理、来源保留和验证方案；本轮不以目录整合代替这些工作。

<a id="open-differences"></a>
## 原文中保留的未解决差异

### 1. D8 出现在正文，但汇总表停在 D7

Life State 概念定义在 Claim 段落写出 D8“断言缺论证段”，末尾机器标记表却只有 D1–D7。本文记录这一不一致，原始快照保持不变；不能据此宣称原校验器已经执行 D8。[原文](sources/life-state-v2/_definitions/concept-definitions.md)。

### 2. Activity 的绑定与 expected 强制程度不完全一致

README 写行动与目标或断言至少绑定其一；概念定义则把 `related_goals / related_claims / expected` 列为至少一个绑定，并在后文写 `expected`“推荐必填”。这三处不能无说明地压成一个已实现的 schema。本指南要求调用者把预期产出和相关判断说清楚，但不冒充原运行层的验收规则。真实记录是否符合原系统，仍需查其正式格式规范与现行校验器。[README](sources/life-state-v2/README.md)、[概念定义](sources/life-state-v2/_definitions/concept-definitions.md)。

### 3. 方法快照没有携带运行环境

Life State 文档引用 `skills/life-state-format/references/format-spec.md`、语义门禁脚本和 `AGENTS.md`，这些文件不在本次方法快照中。PCA 文档引用 `bin/pca`、Skill 和示例数据，也未随行导入。源文里的命令、验收结果和“当前状态”属于来源版本，不能当成本轮已复现或今天仍然如此的结论。[来源范围与固定版本链接](sources/README.md)。

## 本次可验证到什么

文件哈希可以验证导入快照未被改写，内部链接和索引可以验证本模块入口连通。这些检查不能验证人生判断是否正确、现有运行程序是否健康，也不能确认某项建议已被本人采用。

本次用户授权的是方法仓库整合；它不会自动把任何方案写成用户的人生 Decision。已有明确承诺则按原证据记录，不凭空新增确认步骤。
