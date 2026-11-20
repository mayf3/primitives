# 必要区别与组合契约的 Lean 核心

本目录把元层中两项责任变为可检查的数学命题：**表示是否保留指定查询所需的区别，以及动作组合是否保留指定约束。** 它没有统一各领域的业务对象，也没有证明现有原语集合最少。

对应方法入口：

- `meta.structure`：[必要区别](../FRAMEWORK.md#structure)。
- `meta.contract`：[局部责任与组合条件](../FRAMEWORK.md#contract)。
- `meta.minimality`：[相对最小性的边界](../FRAMEWORK.md#minimality)。本轮只证明一个必要区别下界，没有完成表达语言、成本模型或基底最小性的形式化。

## 查询与抽象

[Abstraction.lean](PrimitiveCore/Abstraction.lean) 的 `observe : State → Observation` 表示一个明确选择的信息投影，`query : State → Answer` 表示当前任务真正要回答的问题。

`FiberConstant observe query` 要求：两个状态若得到相同表示，就必须给出相同查询答案。`FactorsThrough observe query` 要求存在仅根据表示恢复答案的解码器。解码器定义在 **observe 的像集**，无需为从未出现的表示虚构默认答案。

| 定理 | 已证明的内容 |
|---|---|
| `fiberConstant_iff_factorsThrough` | 查询在每个观测纤维上恒定，当且仅当可从实际出现的观测精确恢复 |
| `collision_prevents_query_factorization` | 两状态表示相同但答案不同，足以否定精确恢复 |
| `disjoint_good_actions_prevent_policy` | 两状态表示相同且合格行动集合不相交，则不存在仅依该表示、对所有状态都满足任务的确定性策略 |
| `constant_observation_loses_boolean_query` | 具体反例：将两个布尔状态都投影为 `Unit`，无法恢复原布尔值 |

`good` 表示**满足已经声明的任务要求**。若“永远暂停”被定义为两状态都合格的行动，合格集合便不再不相交，不能使用第三条定理声称不存在安全策略。有限任务中的精确查询也不能替代完整动态系统的后继、权限和终态语义。

充要条件的存在性方向使用 Lean 标准的经典选择；它不是自动产生可运行 UI、摘要器或解码算法的程序。本轮给出了碰撞反例，没有把空类型或不可能成立的前提作为有效案例。

## 关系契约与有限执行

[Contracts.lean](PrimitiveCore/Contracts.lean) 用关系表示可能非确定的动作。`Hoare P step Q` 表示：从满足 `P` 的状态出发，凡发生 `step` 转换，其结果都满足 `Q`。

| 定理 | 已证明的内容 |
|---|---|
| `hoare_sequence` | 第一动作保证第二动作所需的中间条件时，顺序组合满足首尾契约 |
| `trace_preserves_invariant` | 初态满足不变量，且每个允许转换保持不变量，则任意有限执行轨迹的终态满足不变量 |

这是部分正确性。不存在后继的关系也可能满足 Hoare 契约，因此契约本身不证明动作可执行。有限轨迹保持不变量也不证明所有运行终止，不证明调度公平，更不证明现实任务成功。应用时需另行证明可达性、进展条件，或用真实执行与该关系建立对应。

## 验证与范围

在仓库根目录使用根配置的工具链执行：

```bash
lake build PrimitiveCore
python3 tools/verify_lean.py --domain meta
```

本轮有 **6 条显式定理**，没有未完成证明或自定义公理。两个证明文件分别使用唯一的 `PrimitiveCore.Abstraction` 和 `PrimitiveCore.Contracts` 命名空间。其他领域可导入这里的参数化数学定义；它们的状态、证据、权限和验收含义仍由各域独立定义。

模型与自然语言规则、模型与实际程序之间的对应尚需逐个应用确认。编译通过不证明信息选取得当、读者理解改善、使用成本降低或原语集合全局最小。
