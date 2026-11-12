# personal-cognition-audit · V0 设计文档

本文档是 V0 的完整设计：定位、仓库结构、数据模型、两个 Skill 的输入输出契约、一次完整示例、最小实施步骤与验收对照。V0 冻结范围见 §9；任何超出 §8 验收的功能一律记入 `FUTURE.md`，本轮不得实现。

---

## 0. 定位与边界

**是什么**：承接每天已有的随想与反思，把原始表达转化为可追溯、可检验、可持续更新的认知记录；帮助识别——真实目标与实际优化目标的偏离、主要矛盾、隐藏心理收益、错误底层观念、认知是否真正改变。

**不是什么**：不是人生管理平台，不是任务系统，不是日记美化工具。

**硬边界（V0 明确不做）**：网页前端、复杂 Agent 框架、向量数据库、自动任务调度、公开发布、任何形式的自动写入原始记录。

---

## 1. 仓库结构

```
personal-cognition-audit/
├── README.md                 # 总览与快速开始
├── DESIGN.md                 # 本文档
├── PRINCIPLES.md             # 四条冻结认知原则（审问判据）
├── FUTURE.md                 # 未来候选功能（本轮一律不做）
├── .gitignore                # 忽略 index/（可重建的本地索引）等
├── bin/
│   └── pca                   # 唯一 CLI（Python3 标准库 + PyYAML）
├── skills/
│   ├── thought-organizer/SKILL.md        # 随想整理器（AI 执行契约）
│   └── cognition-interrogator/SKILL.md   # 认知审问者（AI 执行契约）
├── data/                     # ★ 长期事实源（真实使用区，初始为空骨架）
│   ├── entries/              #   原始随想 Markdown（append-only，永不改写）
│   ├── drafts/               #   整理器产出的待确认草稿 YAML（人工修订点）
│   ├── graph/                #   已确认结构化记录 JSONL（nodes + edges）
│   └── reports/              #   审问报告 Markdown（含派生发现与决策）
├── index/                    # 本地 SQLite 索引（gitignore，随时可重建）
└── examples/
    ├── README.md             # 验收对照与复现步骤
    └── workspace/            # 一个完整走通的示例数据区（--root 指向此处）
        └── data/{entries,drafts,graph,reports}
```

数据分层规则：

- **事实源** = Git 中的 Markdown（原文）+ YAML（草稿）+ JSONL（图）。一切可 diff、可审查。
- **索引** = `index/` 下 SQLite，仅由 `pca index` 重建生成，不提交，删除无损。
- **禁止**：以任何数据库为唯一真相；提交二进制数据库文件。

---

## 2. 数据模型

### 2.1 五种基础原语（冻结）

原语 = 图中的节点。V0 冻结为五种，不得新增第六种。

| 原语 | 含义 | 关键字段 |
|---|---|---|
| `GOAL` | 希望抵达的状态。`kind: claimed` 来自口头宣称；`kind: revealed` 由重复行为推导（默认 hypothesis） | `kind` |
| `STATE` | 当时真实的时间、精力、情绪、项目与现实约束（快照） | — |
| `OBSERVATION` | 实际发生的行为、结果、冲动、外部反馈。**不夹带解释** | — |
| `CLAIM` | 对因果、价值、身份、规则、未来的判断 | 状态为派生值（见 §2.7） |
| `DECISION` | 基于当前证据的取舍/限制/承诺。JSONL 节点记录中 `type` 为 `DECISION`，子类型存于 `decision_type ∈ {STOP, CONSTRAIN, TEST}`（报告/草稿输入段中简写为 `type`） | `decision_type, trigger, success_criteria, evidence[], review_after` |

所有节点公共必填字段：`id, type, text, entry, quote, epistemic_status, created_at`。
`entry` = 来源随想 ID；`quote` = 原文**逐字连续片段**（溯源锚点）。

不设独立原语的三个显式决定：

- **Evidence 不是原语**：证据 = `OBSERVATION —SUPPORTS/CONTRADICTS→ CLAIM` 边。
- **Activity 不是原语**：活动只是产生新 OBSERVATION 的行为本身；付出多少不能自动证明方向正确（原则 P2），因此活动与图的关系只能通过它产生的 OBSERVATION 表达。
- **"主要矛盾 / 次要矛盾 / 隐藏收益 / 重复认知模式 / 代理替代"不是原语**：它们是报告中的派生发现（findings，见 §2.4），必须引用证据节点 ID。

### 2.2 关系枚举（冻结初始集）与方向约束

| 关系 | 方向 | 语义 |
|---|---|---|
| `SUPPORTS` | OBSERVATION → CLAIM | 该观察支持该判断 |
| `CONTRADICTS` | OBSERVATION → CLAIM | 该观察反驳该判断 |
| `SERVES` | OBSERVATION → GOAL | 该行为实际服务某目标（含隐藏目标，需标 hypothesis） |
| `AVOIDS` | OBSERVATION → GOAL | 该行为在回避某对象/状态 |
| `COSTS` | OBSERVATION → GOAL | 该行为的机会成本所牺牲的目标 |
| `REVEALS` | OBSERVATION → GOAL | 行为模式揭示出 revealed 目标 |
| `PROXY_FOR` | GOAL → GOAL | 代理目标替代（实际优化 X 冒充优化 Y） |
| `CONFLICTS_WITH` | GOAL ↔ GOAL | 两个目标争夺同一资源 |
| `GENERATES` | DECISION → OBSERVATION | TEST 决策落地后产生的新证据（事后回填） |

扩展规则：新增关系必须先修订本表并注明版本，不得在记录中临时发明。`pca confirm` 按此表做方向校验。

### 2.3 ID 规则

- 随想：`ENT-YYYYMMDD-NNN`（按日递增），文件名 `data/entries/YYYY-MM-DD-<slug>.md`。
- 节点：`GLM-/STA-/OBS-/CLM-/DEC-` + 4 位全局流水号（`OBS-0001`）。ID 在 **confirm 时统一分配**，草稿中只用 `local_id`（如 `l1`），避免多份草稿争抢流水号。
- 报告：`RPT-NNN`。

### 2.4 派生发现（findings，仅存在于报告，不入图）

固定枚举：`goal_divergence`（宣称/行为目标偏离）、`proxy_substitution`（代理目标替代）、`main_contradiction`（主要矛盾）、`secondary_contradiction`（次要矛盾）、`hidden_benefit`（隐藏收益）、`repeated_pattern`（重复认知模式）、`refuted_claim`（被证据反驳的判断）。

每条 finding 必填：`kind, text, epistemic_status, evidence[]`（evidence 只能引用已确认节点 ID）。

### 2.5 认识论标记 `epistemic_status`（冻结枚举）

| 值 | 含义 |
|---|---|
| `fact` | 外部可核验或当事人直接报告的低层事实（行为、时长、外部反馈） |
| `asserted` | 当事人作出但未经证据检验的断言（多数 CLAIM 的初始态） |
| `hypothesis` | 推断、回忆、不确定内容。**无法确定的内容必须落在这里，不得伪装成事实** |

### 2.6 不可变性与溯源规则

1. `data/entries/` 为 **append-only**：CLI 不提供任何修改/删除入口；AI 契约中整理器对 entries 只读。修正认知 = 追加新记录，不是改写历史；Git 历史即审计轨迹。
2. 每个节点必须携带 `entry + quote`；`pca confirm` 会校验 quote 确实是原文的连续子串（去空白匹配），校验不过拒绝入图。
3. 每条 DECISION 必须携带 `evidence[]`；`pca trace` 可从决策一路回溯到原文全文。
4. 草稿（drafts）与报告（reports）在 confirm 前可任意人工修订；confirm 后的修订直接编辑 JSONL（Git diff 可见），但不得触碰 entries。

### 2.7 CLAIM 状态为派生值

不手工维护：读取时统计该 CLAIM 的 SUPPORTS / CONTRADICTS 边——
`untested(0/0) · supported(S>C=0 有支持无反驳) · contradicted(C>S=0) · mixed(兼有)`。`refuted_claim` 类 finding 依据 `contradicted` 产生。

### 2.8 文件格式

**entry（`data/entries/2026-08-12-evening.md`）**
```markdown
---
id: ENT-20260812-001
date: '2026-08-12 22:40'      # 随想写下时刻
source: manual                 # manual / import:xxx
status: raw                    # 永远是 raw
created_at: '2026-08-19 ...'   # 系统录入时刻
---

（原始随想全文，逐字保留，永不改写）
```

**draft（`data/drafts/ENT-20260812-001.yaml`）——整理器输出，人工修订点**
```yaml
entry: ENT-20260812-001
generated_by: skill/thought-organizer
status: draft                  # confirm 后变为 confirmed 并附 id_map
nodes:
  - {local_id: l1, type: OBSERVATION, text: ..., quote: ..., epistemic_status: fact}
  - {local_id: l5, type: GOAL, kind: claimed, text: ..., quote: ..., epistemic_status: fact}
edges:
  - {from: l2, rel: SERVES, to: l5, epistemic_status: hypothesis, note: 表层叙事}
questions_for_human: [...]
```

**graph（`data/graph/*.jsonl`）**——`goals/states/observations/claims/decisions.jsonl` + `edges.jsonl`，每行一个对象；节点字段 = 草稿字段去掉 local_id、加上 `id/created_at/origin`。边对象：`{from, rel, to, epistemic_status, origin, note, created_at}`。

**report（`data/reports/2026-08-19-RPT-0001-<slug>.md`）**
```markdown
---
id: RPT-0001
date: '2026-08-19'
generated_by: skill/cognition-interrogator
scope: [ENT-..., ENT-...]
status: draft
nodes: [...]          # 审问中推导的新节点（如 revealed GOAL，须带 entry+quote）
edges: [...]          # 审问提出的新关系（PROXY_FOR / CONFLICTS_WITH / CONTRADICTS...）
findings: [...]       # §2.4 派生发现，各带 evidence[]
decisions: [...]      # STOP / CONSTRAIN / TEST，各带 evidence[]
---

（正文：六问审问叙事，引用节点 ID）
```

---

## 3. CLI 契约（`bin/pca`，全局选项 `--root <dir>` 默认仓库根）

| 命令 | 输入 | 行为 | 输出 |
|---|---|---|---|
| `init` | — | 创建 data/ 四个子目录骨架 | 目录路径 |
| `add <file\|->` | 原文文件或 stdin；`--date --source --slug` | 逐字落盘为新 entry，**只新建不覆盖** | entry ID 与路径 |
| `confirm <file>` | draft YAML 或 report MD | 校验（枚举、必填、quote 逐字命中原文、边方向、evidence 存在性）→ 统一分配正式 ID → 追加 JSONL → 回写 status/id_map | 分配的 ID 清单 |
| `trace <ID>` | 任意 ID（ENT/OBS/CLM/GLM/STA/DEC/RPT） | 打印节点 → 来源原文（全文）→ 关联边 → 引用它的报告/决策；DEC 展开证据链 | 溯源文本 |
| `status` | — | 各类计数、待确认草稿、开放决策（含逾期）、被反驳的 CLAIM | 摘要 |
| `validate` | — | 全图完整性：ID 唯一、边端点存在且方向合法、quote 命中原文、evidence 存在 | 通过/错误清单（退出码） |
| `index` | — | 重建 `index/pca.sqlite3`（可删可重建，不入库） | 计数 |

CLI **不提供** entry 的编辑/删除命令（§2.6）。

---

## 4. Skill 契约 A：随想整理器 `skills/thought-organizer`

**职责**：把一篇自然语言随想拆分为候选原语与关系，区分观察与解释，保留不确定性，产出**待确认**结构化记录。它不做跨篇分析、不下结论、不产出决策。

- **输入**：entry ID（原文必须已经 `pca add` 落盘）。
- **输出**：`data/drafts/<entry-id>.yaml`，格式见 §2.8。
- **硬规则**：
  1. 对 `data/entries/` 只读；禁止改写、删减、润色原文。
  2. 每个候选节点必须带原文逐字 `quote`；`text` 是提炼，`quote` 是证据，两者缺一不可。
  3. 只允许五种原语与 §2.2 关系枚举；禁止发明类型。
  4. 观察/解释判定表（强制执行）：
     | 原文形态 | 归属 |
     |---|---|
     | "刷了两小时手机" | OBSERVATION |
     | "因为焦虑所以刷手机"（因果） | CLAIM（hypothesis） |
     | "做完挺爽的"（行为后的内部反馈/结果） | OBSERVATION |
     | "今天很累/很焦虑"（当时状态） | STATE |
     | "我总是这样"（频率/概括） | CLAIM；其中可数的具体实例另记 OBSERVATION |
     | "还是得先学 X 才能做 Y"（规则） | CLAIM |
     | "我想/我要 X" | GOAL（claimed） |
     | 对过去事件的回忆 | OBSERVATION（hypothesis，注明是回忆） |
  5. 无法确定 → `epistemic_status: hypothesis`，并在 `questions_for_human` 中列出需人回答的问题；禁止把推断伪装成 fact。
  6. SERVES/COSTS/AVOIDS 等解释性关系只能以 hypothesis 提出。
  7. 不产出 DECISION（STOP/CONSTRAIN/TEST 是审问者的职责）。

## 5. Skill 契约 B：认知审问者 `skills/cognition-interrogator`

**职责**：结合历史图与原文，对宣称目标与实际行为做对照审问，产出报告与至少一条可执行决策。

- **输入**：审问范围（日期区间 / 最近 N 篇 / 指定 GOAL 或 CLAIM ID）+ 可选焦点。
- **必答六问**（每问的回答必须引用节点 ID 作为证据）：
  1. 我当前实际在优化什么？（按资源流向推断，不采信自我描述）
  2. 宣称目标与行为揭示的目标是否偏离？偏离多久了？
  3. 哪个矛盾正在支配资源分配？矛盾的主要方面是什么？
  4. 某个重复行为提供了什么隐藏收益？
  5. 现有证据支持/反驳哪些 CLAIM？
  6. 相同诱因再次出现时，什么不同选择能证明认知发生了变化？（P4）
- **输出**：`data/reports/...md`（§2.8），正文含六问叙事 + 四原则中至少一条的应用。
- **有效输出判定（硬性）**：
  - 必须产出 **≥1 条 STOP / CONSTRAIN / TEST** 决策：停止一件具体的事（含时长）／给行为加明确边界（含触发条件与期限）／执行产生新证据的最小验证（含"不同选择"与将产生的 新 OBSERVATION）。
  - **无效输出**：仅生成深刻文字、更多分类、更多系统建设。报告若无决策，confirm 拒绝。
  - findings 默认 hypothesis；除非有 ≥2 篇不同 entry 的 observations 支持且无反证，才可标 fact。
  - 新推导的 revealed GOAL 必须以 hypothesis 节点入图（带 entry+quote），不得直接当事实陈述。
  - 每条 finding/decision 的 evidence 非空且全部可溯源。

---

## 6. 完整示例（详见 `examples/workspace/`，可完整复现）

场景：三篇随想（08-12 / 08-16 / 08-19），宣称"完成 side project 并上线"，行为却持续指向"学习/折腾工具"。

**走查链路**：

1. `pca add` 三篇原文 → `ENT-20260812-001`、`ENT-20260816-001`、`ENT-20260819-001`（原文逐字保留）。
2. 整理器产出三份 draft（共 9 个 OBSERVATION、4 个 CLAIM、1 个 claimed GOAL、3 个 STATE），人工修订后 `pca confirm` 入图。
3. 审问者产出 `RPT-0001`：
   - 推导 revealed goals：`GLM-0002`（维持"准备中"状态，hypothesis）、`GLM-0003`（回避发布与被评价，hypothesis）；
   - 关键边：`GLM-0002 —PROXY_FOR→ GLM-0001`、`GLM-0002 —CONFLICTS_WITH→ GLM-0001`、`OBS-0007/OBS-0003 —CONTRADICTS→ CLM-0003`；
   - findings：代理目标替代、主要矛盾、隐藏收益（掌控感 + 免于被评价）、重复周末循环、`CLM-0003`（"下班两三小时没法做正经开发"）被反驳；
   - 决策：`DEC-0001 CONSTRAIN`（工作日 21:30 后不刷技术资讯）、`DEC-0002 TEST`（周日前部署最简 landing page 发给 3 人，产生新 OBSERVATION）、`DEC-0003 STOP`（30 天不注册新课程/不重构工具）。
4. `pca trace DEC-0002` → 展开证据链一路回到三篇原文全文；`pca validate` 全绿。

验收要点对照见 `examples/README.md`。

---

## 7. 最小实施步骤

1. 建骨架与文档（DESIGN/PRINCIPLES/FUTURE/.gitignore）。
2. 实现 `bin/pca`（七个子命令，标准库 + PyYAML）。
3. 撰写两个 SKILL.md 契约。
4. `pca init` + `pca add` 录入示例随想。
5. 以整理器契约产出 drafts → 人工修订（示例中即修订稿）→ `pca confirm`。
6. 以审问者契约产出 RPT-0001 → 人工修订 → `pca confirm`。
7. `pca trace / status / validate / index` 验证验收。
8. git 提交，创建私有 GitHub 仓库并推送。

## 8. V0 验收对照

| 验收项 | 对应物 |
|---|---|
| 录入一篇真实随想，原文完整保留，生成可人工修订的结构化记录 | `pca add` → entry MD；draft YAML；`pca confirm` |
| 跨多篇识别 ≥1 次代理目标替代 | `GLM-0002 PROXY_FOR GLM-0001` + finding `proxy_substitution` |
| 识别 ≥1 次主要矛盾 | `GLM-0002 CONFLICTS_WITH GLM-0001` + finding `main_contradiction` |
| 识别 ≥1 条被证据反驳的 Claim | `CLM-0003` contradicted（OBS-0003/0007 CONTRADICTS）+ finding `refuted_claim` |
| 生成 ≥1 条具体 STOP/CONSTRAIN/TEST | DEC-0001/0002/0003 |
| 所有结论可追溯到原始 Observation | `evidence[]` + `quote` + `pca trace` 全链路回溯原文 |

## 9. 冻结与变更

- 冻结：五原语、§2.2 关系枚举、findings 枚举、epistemic_status 枚举、四条认知原则（PRINCIPLES.md）。
- V0 内上述任何一项不得增改；扩展 = 修订本设计文档并升版本号，先记录于 `FUTURE.md`。
