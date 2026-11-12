# personal-cognition-audit

AI 辅助的**个人认知审计系统**（V0）。它不是人生管理平台，而是承接每天已有的随想与反思，把原始表达转化为**可追溯、可检验、可持续更新**的认知记录，用来回答一组具体问题：

- 我宣称的目标与我实际在优化的目标，偏离了多少？
- 当前支配我资源分配的主要矛盾是什么？
- 某个重复行为在给我什么隐藏收益？
- 哪些底层判断已经被我自己的行为证据反驳？
- 我的认知真的改变了吗——还是只是"被说服了"？

设计全貌见 [DESIGN.md](DESIGN.md)；四条冻结认知原则见 [PRINCIPLES.md](PRINCIPLES.md)。

## 核心机制（一段话版）

原始随想以 Markdown **逐字永久保留**（`data/entries/`，只增不改）；AI 按两个 Skill 契约把随想拆解为五种原语（`GOAL / STATE / OBSERVATION / CLAIM / DECISION`）及其关系，先落为**草稿**（`data/drafts/`），人工修订确认后写入图（`data/graph/*.jsonl`）。证据不是独立原语，而是 `OBSERVATION —SUPPORTS/CONTRADICTS→ CLAIM` 的边；主要矛盾、隐藏收益、代理目标替代等都是报告中引用证据 ID 的**派生发现**，不是新原语。每次审问必须产出至少一条 `STOP`（停止一件事）/ `CONSTRAIN`（加明确边界）/ `TEST`（产生新证据的最小验证）决策——只生成深刻文字不算有效输出。所有结论可通过 `pca trace` 回溯到原文。

## 快速开始

依赖：Python ≥ 3.9 + PyYAML（`pip3 install pyyaml`）。

```bash
./bin/pca init                                # 初始化数据目录
./bin/pca add today.md --date "2026-08-19 22:00" --source manual
# ↑ 或: cat 随想.txt | ./bin/pca add - --date "..."

# ① 让 AI 按 skills/thought-organizer/SKILL.md 整理该 entry，
#    生成 data/drafts/ENT-*.yaml；人工修订后：
./bin/pca confirm data/drafts/ENT-20260819-001.yaml

# ② 积累数篇后，让 AI 按 skills/cognition-interrogator/SKILL.md 审问，
#    生成 data/reports/*.md；人工修订后：
./bin/pca confirm data/reports/2026-08-19-RPT-0001-xxx.md

./bin/pca status          # 全局状态：待确认草稿、开放决策、被反驳的 CLAIM
./bin/pca trace DEC-0001  # 任何结论 → 证据 → 原文全文 的溯源链
./bin/pca validate        # 全图完整性校验
./bin/pca index           # 重建本地 SQLite 索引（index/，不入库）
```

完整示例（三篇随想从录入到 STOP/CONSTRAIN/TEST 决策的全链路）见 `examples/`。

## 目录

```
data/entries/  原始随想（append-only）   data/drafts/  待确认草稿
data/graph/    已确认节点与边(JSONL)     data/reports/ 审问报告与决策
skills/        两个 AI 执行契约           bin/pca       CLI
index/         可重建的本地索引(gitignore) examples/     验收示例
```

## 不可违反的规则

1. `data/entries/` 永不改写、永不删除；CLI 不提供该入口，AI 契约对它只读。
2. 不确定的内容必须标 `hypothesis`，不得伪装成事实。
3. 任何结构化结论必须携带原文 `quote` 与 `entry`，可被 `pca trace` 验证。
4. 付出（Activity）只能经由它产生的 OBSERVATION 进入系统，永远不能直接证明方向正确。
5. 审问报告没有 STOP/CONSTRAIN/TEST 决策即无效，`pca confirm` 会拒绝。
6. SQLite 只作索引（`index/`，可随时重建）；事实源永远是 Git 里的 Markdown + YAML/JSONL。

## 范围外（V0 明确不做）

网页前端、复杂 Agent 框架、向量数据库、自动任务调度、公开发布——完整清单见 [FUTURE.md](FUTURE.md)。
