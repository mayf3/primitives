# 写作原语的形式化切片

**Lean 4.19.0 · writing 0.1.2 · 2026-11-20**

对应[定向修补](../ACTIONS.md#targeted-revision)、[揭示顺序](../ACTIONS.md#sequence-reveal)与[事实修订约束](../TRACE_AND_REVISION.md)。源码：[Writing/Revision.lean](Writing/Revision.lean)。

## 精确范围

`Meaning World := World → Prop` 把已明确解释的事实表达成可能世界上的谓词。`Faithful evidence required draft` 同时要求：证据蕴含草稿、草稿蕴含任务要求保留的内容。第二项只保护 `required` 实际表达出的必要信息；调用者必须准确写出这些要求。若 `required` 是恒真命题（`fun _ => True`），即使证据可满足，删空成恒真草稿也会通过。本模型不会自动判断任务必须保留什么。

本轮 `Revision required before after` 限于**保守弱化或等义改写**：旧稿蕴含新稿，新稿保留任务必要信息。它不覆盖所有创作修改；从原材料补充旧稿没有写出的事实、纠正原稿错误、改变解释或自由虚构，都需另定义操作及授权条件。

`Revision` 的两项条件是调用者需针对具体修改提交的契约证明。下面的保持定理说明合格修改可以组合；它不自动判定一段自然语言编辑是否合格，也不替调用者证明新稿保留了哪些必要信息。

| 定理 | 保证 |
|---|---|
| `revision_preserves_faithfulness` | 满足上述契约的一次保守改写，保留两侧约束 |
| `repeated_revisions_preserve_faithfulness` | 任意有限合格修订轨迹仍保留这两侧约束 |
| `supported_draft_has_a_world` | 若证据至少有一个相容世界，合格草稿也有相容世界 |
| `one_person_cannot_be_upgraded_to_everyone` | 一位参与者感兴趣，不能普遍推出所有人感兴趣 |
| `deleting_required_information_is_not_faithful` | 把指定事实删成无信息的真命题，会丢失任务要求 |
| `reordered_facts_preserve_meaning` | 已明确建模的两个合取事实可以交换呈现顺序，保留该命题意义 |

若证据矛盾，蕴含可能真空成立；`Faithful` 单独不保证证据可满足，更不证明来源真实。非空世界定理将这项前提单列。重排定理也不允许改写真实事件时间或因果关系。

自然语言到谓词的解释、事实来源可靠性、作者声音、可读性与听众体验没有被形式化验证。这里不把条件逻辑正确写成现实无幻觉。

## 验证

在仓库根目录执行：

```bash
python3 tools/verify_lean.py --domain writing
```

根入口统一固定 Lean 4.19.0、干净构建和传递公理审计。单域回执是 `.lake/verification/writing.json`；全仓结果另写根 `lean-verification.json`。开发时可 `lake build Writing`，完整验收使用上面的命令。
