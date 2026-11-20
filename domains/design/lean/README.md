# 按需展开的查询保真模型

本目录检查一个具体问题：**折叠辅助详情以后，用户是否仍能从可见字段决定规定的下一步？** 对应 `design.progressive-disclosure`、`design.prerequisites`、`design.visible-change` 和 `design.next-step`，见[原语卡](../PRIMITIVES.md)、[使用指南](../GUIDE.md)。

模型和定理在 [Disclosure.lean](Design/Disclosure.lean)。它是合成决策页面，不是现有网站、用户数据或其他领域状态机的复制。

## 实际建模的字段与行为

`PageState` 保留四个字段：

| 字段 | 本模型中的含义 |
|---|---|
| `authorized` | 当前动作具备所要求的授权 |
| `acceptancePassed` | 当前产物已通过本任务要求的验收 |
| `supportingDetail` | 本任务声明不影响下一步的辅助详情，用自然数代表内容 |
| `expanded` | 详情是否展开 |

`render` 始终呈现授权与验收两个字段，只根据展开状态把详情变为 `some detail` 或 `none`。`nextAction` 是显式任务规则：没有授权时取得授权；已有授权但未验收时修复产物；两者均成立时继续。

这些是模型的输入约定。真实页面如果把价格、风险或必要设备藏进 `supportingDetail`，就改变了必要信息的定义，不能直接引用本证明。

## 已证明的正例与反例

| 定理 | 内容 |
|---|---|
| `rendering_recovers_next_action` | 根据实际可见字段计算出的下一步与完整状态要求的一致 |
| `rendering_preserves_required_distinction` | 相同视图不会对应两个不同的规定下一步 |
| `collapsed_page_hides_only_detail` | 折叠结果保留授权、验收，只将详情置为 `none` |
| `expanded_page_shows_detail` | 展开结果保留授权、验收，并实际显示详情 |
| `changing_hidden_detail_preserves_view` | 在折叠状态修改辅助详情，不改变当前可见视图 |
| `toggling_detail_preserves_action` | 单独改变展开状态，不改变本模型的规定下一步 |
| `merged_indicator_has_conflicting_actions` | 将授权与验收合并为一个“至少一项通过”指示会产生具体碰撞 |
| `merged_indicator_cannot_recover_action` | 该错误指示无法单独恢复规定下一步 |
| `merged_indicator_cannot_support_correct_policy` | 不存在仅依该错误指示、对所有模型状态都正确的确定性行动策略 |

反例有两个具体状态：

- 已获授权、未通过验收：下一步应修复产物。
- 未获授权、已通过验收：下一步应取得授权。

二者的 `authorized || acceptancePassed` 都为真，但下一步不同。这说明被隐藏的**区别**与任务相关；它不要求页面增加更多按钮，也没有规定所有产品必须使用这套审批流程。

## 验证与现实边界

在仓库根目录执行：

```bash
lake build Design
python3 tools/verify_lean.py --domain design
```

本轮有 **9 条显式定理**，没有未完成证明或自定义公理。数学复用仅是导入参数化的查询/策略定义；页面、权限、验收与下一步的业务含义全部在 `Design.Disclosure` 命名空间内定义。

没有对浏览器 DOM、键盘操作、屏幕阅读器或线上接口做形式化连接，也没有真人阅读测试。因此不能从本证明推出“折叠一定更易懂”“用户一定看见关键信息”“操作已获真实授权”或“实际验收正确”。在具体产品使用时，仍需核对字段来源、渲染与交互实现、信息是否真的可感知，并观察真实任务表现。
