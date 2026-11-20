# 题目回答签名与模型可辨识性

本目录把“哪些题能区分目前考虑的理解方式”变成精确问题。对应 `learning.elicit-starting-model`、`learning.elicit-performance`、`learning.vary-conditions`，见[原语卡](../PRIMITIVES.md)、[使用指南](../GUIDE.md)。

模型与证明在 [Identifiability.lean](Learning/Identifiability.lean)。这里的 `Model` 是事先明确列出的回应规则，不是未经评估就赋予真实学习者的标签。

## 一般定义

固定题目、回答及模型的类型，并给定确定性回应函数 `respond model question`。有限题目列表的 `answerSignature` 是按题目顺序记录的回答列表。

`Distinguishes respond questions` 表示：在题目列表中给出全部相同回答的两个模型必须相同。这是**相对于给定候选模型空间**的精确辨识，前提还包括回答规则在测验期间不变、回答被准确观察、题目及允许帮助的含义保持一致。

| 定理 | 已证明的内容 |
|---|---|
| `signature_eq_iff_same_answers` | 回答签名相同，当且仅当列表中每道题的回答相同 |
| `distinguishes_iff_injective_signature` | 题目能区分全部候选模型，当且仅当签名映射是单射 |
| `same_answers_prevent_identification` | 两个不同候选模型对全部题回答相同，就不能从该测验识别模型 |
| `adding_questions_preserves_distinguishability` | 固定回应规则下，向题目列表追加题目不会破坏已有的可辨识性 |
| `query_recoverable_iff_constant_on_signature` | 只需判断某项指定性质时，它能从签名精确恢复，当且仅当它在相同签名的模型之间恒定 |

最后一条允许辨认任务真正需要的性质，不强求识别整个内部模型。它复用参数化数学命题，不引入其他领域的学习状态或证据语义。

## 可计算的正反例

合成任务是固定 **30 fps** 下把秒数换算为帧号。明确列出三个回应模型：

| 模型 | 回应规则 | 2 秒 | 3 秒 | 4 秒 |
|---|---|---:|---:|---:|
| `scaleWithSeconds` | 回答 `30 × 秒数` | 60 | 90 | 120 |
| `repeatSixty` | 始终回答 60 | 60 | 60 | 60 |
| `memorizeTwoQuestions` | 3 秒时答 90，其余答 60 | 60 | 90 | 60 |

| 定理 | 结果 |
|---|---|
| `practiced_question_does_not_distinguish` | 只测原题 2 秒，三个模型的相同答案不能识别理解方式 |
| `one_variation_still_does_not_distinguish` | 加入 3 秒变式仍不能区分按关系计算与记住两题 |
| `three_questions_distinguish_declared_models` | `[2, 3, 4]` 三道题能区分表中全部三个模型 |

这是有明确失败案例与通过案例的小模型。第三条**只对表中三个模型成立**。如果再加入记住三题答案的第四个模型，同一题组便可能再次无法区分；证明没有把有限回答升级成跨场景掌握。

## 验证与现实边界

在仓库根目录执行：

```bash
lake build Learning
python3 tools/verify_lean.py --domain learning
```

本轮有 **8 条显式定理**，没有未完成证明或自定义公理。所有学习对象与回应语义均在本目录定义。

本模型没有包括猜测、失误、疲劳、提示变化、作答过程中学习、遗忘或候选模型之外的策略。追加题目不破坏可辨识性的定理依赖固定回应函数；现实中前题改变了后题的知识或动机时，需要扩展成有状态或概率模型。

没有取得真人学习数据，也没有证明这套题具有现实测量效度、教学收益或保持效果。把真实任务译为这里的题目及回应规则、判断候选模型是否充分、核对允许工具和帮助条件，仍是需要证据的工作。
