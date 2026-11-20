# 人生原语的形式化切片

**Lean 4.19.0 · life 0.1.1 · 2026-11-20**

对应[决策](../CONCEPTS.md#decision)和[证据关系](../CONCEPTS.md#evidence)。本目录的合成模型验证历史承诺记录、版本绑定和来源集合，不导入真实个人数据，也不重新定义 Life State 或 PCA V0。

## 模型与定理

源码：[Life/Commitments.lean](Life/Commitments.lean)。

| 模型 | 已形式化的性质 | 前提与限制 |
|---|---|---|
| `Key` 与 `State` | `step_preserves_support`、`run_preserves_support`：从合格初态执行任意有限事件序列，所有已登记 Decision 都能在承诺记录中找到相同 subject/version | `recordCommitment` 是可信输入边界；外部调用者必须提供真实本人承诺，模型不鉴别语音、身份或来源真实性 |
| 受控 `adopt` | 无承诺的采用保持原状态；已有同版本承诺可以复用，无需再次确认 | 只证明历史决定的依据，不授予当前执行权限；撤权及承诺变更需另建模型 |
| 正反例 | 单独建议不能产生 Decision；版本 1 不能支持版本 2；去掉采用守卫会破坏不变量 | 反例属于明确的小模型，不是现实行为统计 |
| `Reference` / `HasRoot` | 同一根来源的新摘要或摘录不会扩大根来源集合 | 不同 root ID 不自动意味着统计独立或内容可信 |

这些定义是面向原语约束的一份可执行数学样板，不要求人生记录系统改用本目录的数据结构。当前没有证明任何生产录入系统符合 `step`。

## 验证

在仓库根目录执行：

```bash
python3 tools/verify_lean.py --domain life
```

统一工具负责固定工具链、干净构建、所有显式定理的传递公理审计及输入 SHA-256。单域回执位于 `.lake/verification/life.json`；根 `lean-verification.json` 只由全仓验证产生。`lake build Life` 可用于开发时的增量编译，但不能替代完整审计。

完成活动、登记承诺或增加引用，都不会由本模型推导出某个人生判断真实、生活更好或干预有效。
