# Life State — 人生战略的结构化表达（存储格式 v2，2026-08-24 定稿）

> 老板 2026-08-18 拍板启动：以 Research Grammar 为范式，把过去随想与讨论推导为结构化目录，替代"随手写一个文档丢进 docs/"。
> 目标：**更少在错误方向上极度努力，并始终能从当前认知状态推导出最值得做的下一步 Activity。**
> **存储格式规范（目录结构 + 命名 + YAML 结构表）的单一事实源**：`skills/life-state-format/references/format-spec.md`。
> 三 skill 分工：`life-state-format`（格式硬 Gate）→ `life-state-conflict`（语义门禁：存量 audit + 增量 gate）→ `life-state-action`（行动推导，提案须老板确认）。权限红线见 AGENTS.md「Life State 权限红线」。

## 目录结构（最终格式）

```
life/
├── README.md         ← 本文件
├── journal.md        ← append-only 时间序索引（只追加不修改）
├── goal/             ← G* 条目：G1-人生自由
├── state/            ← S* 条目：S1-职业 / S2-技术 / S3-商业 / S4-创作 / S5-执行
├── observation/      ← O* 条目：O1~O15
├── claim/            ← C* 条目：C1~C12
├── decision/         ← D* 条目：D1-不裸辞 / D2-不再证明能力 / D3-优先市场证据 / D4-最小建设 / D5-启动V0
├── activity/         ← A* 条目：A1(已完成) / A2(next,唯一) / A3(active)
├── _definitions/     ← 数据自带定义（概念定义与判别标准，单一事实源；_ 前缀豁免校验）
└── _legacy-v0/       ← V0 旧格式归档（不参与校验，仅存档保底）
```

## 核心规则（摘要，详细见 format-spec.md）

1. **一个元语一个目录，一条记录一个文件**：`<字母><编号>-<简短描述>.md`，编号从 1 连续、无前导零（`G1` 不是 `G01`）。
2. **文件头 YAML 结构表**（必填：`id / type / title / created / provenance`）+ 索引关系（如 Observation→`supports/contradicts`→Claim；Decision→`related_claims/evidence/supersedes`；Goal→`verified_by` 声明"进展看什么指标"）。
3. **封闭枚举**：claim.status ∈ SUPPORTED/INCONCLUSIVE/CONTRADICTED/WEAKENED/RETIRED；activity.intent ∈ Observe/Hypothesize/Test/Optimize；activity.status ∈ active/next/done/superseded；**activity.expected** = 预期得到的观测/证据（行动可证伪，与目标/断言至少绑其一）。
4. **索引关系只引用已存在且类型匹配的 ID**——由校验器强制。
5. **数据自带定义**：什么是目标/状态/观测/断言/决策/行动（五问判别口诀 + D1~D7 机器标记）→ `life/_definitions/concept-definitions.md`（单一事实源；校验器只检验，不拥有定义）。
6. **十条不冲突原则**：唯一 ID、单一事实源、Claim 陈述不可篡改、证据优先、决策 SUPERSEDES、State 派生快照、冲突不删除、主题唯一归属、provenance 必带、状态词汇封闭。

## 三 skill 门禁流程（所有新增/修改后必跑）

```bash
python3 skills/life-state-format/scripts/validate.py              # ① 格式硬 Gate
python3 skills/life-state-conflict/scripts/check.py --mode audit   # ②a 存量审计（只报告）
python3 skills/life-state-conflict/scripts/check.py --mode gate --file <条目>  # ②b 增量门禁
python3 skills/life-state-action/scripts/derive.py                 # ③ 差距事实表（推导输入）
```

## 状态流转（一条材料如何进入 Life State）

```
新材料（随想/对话/经历）
  → 拆出 Observation（可观测的事实/原文）
  → Observation SUPPORTS/CONTRADICTS 某个 Claim（有则更新其状态与证据；无则新建 Claim）
  → 判断是否触发 Decision（老板拍板才算）
  → 更新 state/（当前快照，派生+复核）
  → 更新 activity/（进行中 + 唯一的 Next Activity）
  → 全部写入 journal.md（append-only 索引）
  → 跑 validate.py 校验（全绿才算落盘完成）
```

## 当前状态（2026-08-25）

- 存储格式 v2 + 三 skill 家族建成（format/conflict/action）；定义迁入数据根 `life/_definitions/`（数据自带定义）
- 条目：G1 / S1-S5 / O1-O15 / C1-C12 / D1-D5 / A1-A3（旧档在 `_legacy-v0/`）
- 定义合规层 D1~D7：目标必备 verified_by、正文引用必须存在（G0 旧称已清理）
- Next Activity：A2（对老板做一次 Life State 战略 Reading）
- 后续：平台化（老板计划做平台，当前按文件保存）