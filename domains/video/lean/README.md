# 视频时间关系的 Lean 样板

本目录把[呈现时间关系](../PRIMITIVES.md#temporal-relations)中的一小部分约束写成数学模型，并检查[四窗回复合成例](../examples/concurrent-replies.json)与模型一致。它也对应[锁定参照](../PRIMITIVES.md#reference-lock)的共同尺度要求。证明使用 Lean 4.19.0 与标准库，不依赖 mathlib。

## 模型与已检查的命题

`Video/Temporal.lean` 使用整数 tick 与半开区间 `[start, finish)`。区间带 `source`、`presentation` 或 `schematic` 时钟标签；源媒体、成片与合成图内时间不能直接混作同一种区间。有效性要求 `start < finish`。两个区间的正长度重叠定义为：

```text
max(start₁, start₂) < min(finish₁, finish₂)
```

命题由 Lean 内核检查，而不是仅计算下列数值例子：

| 命题 | 证明的保证 | 关键条件 |
|---|---|---|
| `affine_lt_iff`、`affine_le_iff` | 共同映射 `f(t)=a*t+b` 保留严格／非严格先后 | 整数 `a>0`；所有所比较事件使用同一映射 |
| `affine_valid_iff`、`affine_contains_iff` | 区间有效性及对应时刻的归属保真 | 同一个源／目标时钟转换 |
| `overlap_iff_endpoints`、`affine_overlap_iff` | 正长度重叠等价于四个端点不等式，并在共同正仿射变换后保真 | 不把空区间、反向区间或仅端点接触当成正长度重叠 |
| `affine_duration`、`affine_duration_ratio`、`affine_duration_order_iff` | 时长按同一系数变化、时长比的交叉乘积相等、长短排序不变 | 比值解释还需要分母时长非零；有效区间足够 |
| `affine_completed_count` | 在共同转换后的观察窗 `(lo,hi]` 内，完成事件计数不变 | 相同事件列表；每条记录代表一个独立事件，重复时间端点不去重 |
| `queue_balance` | 期末剩余与实际完成之和等于期初加实际到达 | `completed ≤ initial + arrived`；否则自然数相减会截断，不能据此声称守恒 |

正仿射模型的系数只允许正整数。把两种时钟同时换成更细的共同 tick 单位，不能使有理斜率变成整数。若需覆盖有理倍速，须另建有理系数映射，或分别规定源／目标 tick 单位并证明它们与实际时间的换算；本轮没有提供这两类扩展。舍入、丢帧造成的时间误差未建模。任意剪辑、跳剪、分段倍率与视频渲染器不自动满足这一模型。

## 两个已检查的反例

- `independent_alignment_forges_overlap`：源区间 `[0,2)` 与 `[3,5)` 不重叠。第一段不移动，第二段单独减去 3，成片都变为 `[0,2)`。每段各自都是合法正仿射变换，但它们没有共同映射，成片重叠不能证明源过程重叠。
- `square_time_increases_on_nonnegative` 与 `nonlinear_map_reverses_duration_order`：平方映射在非负整数上严格递增，却能把 `[3,4)` 与 `[0,2)` 的时长顺序从 `1<2` 变为 `7>4`。保留先后不足以保留时长或速率比较。

## 与现有 JSON 例子的绑定

`four_writers_common_interval` 对任意整数时刻证明，四个生成区间 `[2,5)`、`[3,6)`、`[4,7)`、`[4,7)` 的共同活动范围恰好为 `[4,5)`。两个同起同止的事件仍是两条记录。`completedCount` 在观察窗 `(2,8]` 内得到生成 4 段、阅读 1 段；期初 1 段，期末为 4 段。

`check_example.py` 读取当前 JSON 的五个具名事件、起止、观察窗与账面数值，检查对象绑定和合成材料身份，然后将整数数据写入 `.lake/verification` 下的临时 Lean 模块。该模块检查与基准区间一致、共同交集、完成计数、可消费上界、队列余额，以及事件是否落在计划片长内。临时文件不加入本域证明源码。

原 JSON 的关键事件数值或计数语义变化时，检查会失败；维护者须显式重审并更新模型。适配器没有把“JSON 解析正确”“所选字段就是现实事件”“列表没有漏记录”升级为 Lean 定理。它也不把合成例改成源媒体测量。

从仓库根目录运行统一验收：

```bash
python3 tools/verify_lean.py --domain video
```

单独构建与核对数据：

```bash
lake build Video
python3 domains/video/lean/check_example.py --lake /absolute/path/to/lean-4.19.0/bin/lake
```

## 证明之外的条件

实际使用仍须核对：事件身份与时间采集、每条记录的计量单位、源媒体到成片的真实映射、取消或丢弃工作的计数规则、渲染画面是否准确体现模型。区间重叠也不等于共享硬件上真正并行执行。

本目录未验证渲染效果、设备可读性、观众理解、观看感受或实际阅读速度；没有证明所有视频原语最简、完备或普遍有效。原有卡片、来源快照和这些验证状态保持各自含义。
