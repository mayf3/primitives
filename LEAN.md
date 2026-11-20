# 原语的数学模型与 Lean 验证

**仓库 0.6.1 · 2026-11-20 · 条件模型证明**

每个已注册领域保留原语描述，并在自己的 `lean/` 内维护数学定义、证明、正反例及范围说明。工具链与构建配置在仓库根统一管理；各领域的业务对象、状态和效果标准仍然独立。

2026-11-20 对已合并版本做了独立语义与验收入口复核，发现并修复声明漏审与返回合同过弱，另澄清写作的必要信息前提。完整发现与复核方法见 [LEAN_REVIEW.md](LEAN_REVIEW.md)。编译通过不替代规格审查。

## 目录约定

| 位置 | 职责 |
|---|---|
| `domains/<domain>/README.md`、`GUIDE.md`、原语定义文档 | 人和 Agent 日常使用的方法描述、边界与入口 |
| `domains/<domain>/lean/README.md` | 原语 ID 与定理的对应、模型假设、反例、未验证范围和复现命令 |
| `domains/<domain>/lean/<Library>.lean` | 本域证明库的导入入口 |
| `domains/<domain>/lean/<Library>/*.lean` | 本域数学定义与显式定理 |
| `meta/lean/` | 参数化的抽象保真和契约组合；不定义共享业务状态 |
| `lean-toolchain`、`lakefile.toml`、`lake-manifest.json` | 唯一工具链与 Lake 配置，当前无外部依赖 |
| [lean-projects.json](lean-projects.json) | 源码、库、领域归属及实例适配器的完整清单 |
| [tools/verify_lean.py](tools/verify_lean.py) | 全仓／单域验证入口及传递公理审计 |
| [lean-verification.json](lean-verification.json) | 最近一次全仓验证的源哈希、命令、定理依赖与边界 |
| `.lake/` | 构建与临时验证文件，不提交 |

旧 `domains/agent-workflow/formal/` 已迁移为 `domains/agent-workflow/lean/`，旧目录中的重复 Lake 配置、固定审计名单与独立脚本由根统一入口取代。原语卡片名称和稳定 ID 保持原状；没有强制把 `CONCEPTS.md`、`ACTIONS.md` 等语义不同的说明改成同一模板。

## 已实现切片

| 范围 | 说明 | 证明入口 |
|---|---|---|
| 元层 | 查询保真、不可辨识、契约串联与有限轨迹不变量 | [元层](meta/lean/README.md) |
| Agent Workflow | 关系观察与证据更新接缝、初态到逐边界真值包含、条件进展、验收门及反模型 | [工作流](domains/agent-workflow/lean/README.md) |
| 设计 | 展开/隐藏保留正确后继；错误压缩混同授权与验收 | [设计](domains/design/lean/README.md) |
| 学习 | 指定理解模型的回答签名、可辨识性及变式正反例 | [学习](domains/learning/lean/README.md) |
| 视频 | 共同正整数仿射时间映射、重叠/时长/计数、积压守恒与已有 JSON 样例 | [视频](domains/video/lean/README.md) |
| 人生 | 版本绑定的历史承诺登记与根来源集合 | [人生](domains/life/lean/README.md) |
| 写作 | 有前提的保守修订、有限组合与范围升级反例 | [写作](domains/writing/lean/README.md) |

这些是有选择的数学切片。游戏仍是提案；本轮没有注册新领域。证明数量包含辅助引理、正控及反例，不代表同等数量的现实保障。

## 复现

准备 Python 3.11+ 和 `leanprover/lean4:v4.19.0`，在仓库根运行：

```bash
python3 tools/primitives.py validate
python3 -m unittest discover -s tests -v
python3 tools/verify_lean.py
```

若工具链没有在 PATH 中：

```bash
python3 tools/verify_lean.py --bin-dir /absolute/path/to/lean-4.19.0/bin
```

只验证一个领域及公共数学核心：

```bash
python3 tools/verify_lean.py --domain video
```

单域结果写入 `.lake/verification/video.json`，不能覆盖全仓回执。`--check-layout` 只检查目录、导入和声明清单，不运行内核；输出明确为 `PASS_LAYOUT_ONLY`。增量 `lake build Video` 可用于开发，不替代验收。

统一验证会先冻结输入哈希，再执行 `lake clean`、选定库的 `lake build`、自动生成的全部显式定理 `#print axioms`、编译环境声明审计和选定实例适配器，最后再次核对输入。标准公理白名单为 `propext`、`Classical.choice`、`Quot.sound`；`sorryAx`、自定义逻辑公理及编译器原生求值公理会被拒绝。声明风格受限，新增源码必须登记清单。

编译环境审计使用固定工具链自带的 `Lean` 库，按实际所属模块枚举声明；全部安全逻辑声明（含私有声明、自动生成定理）都检查传递依赖，并核对显式定理清单。Lean 标记为 unsafe/partial 的编译辅助单列，不作为已审计逻辑定理；模型源码仍禁止引入 `unsafe`、`partial` 或自定义元编程。源文本扫描只检查受限写法与目录约定，不再单独承担公理覆盖保证。回执区分显式原语定理数与编译环境声明数。

视频适配器从既有 JSON 生成临时 Lean 断言，把实际事件区间、计数口径和余额与定理实例绑定。原样例通过，故意改变关键事件、余额或媒体核验身份会失败。源数据与适配器同样计入哈希。

失败运行不会刷新成功回执；旧回执只能说明其记录哈希所对应的旧版本。判断当前是否通过，应以本次退出码及输入哈希为准。验证脚本是受审代码，不是面对恶意插件或被篡改工具链的安全沙箱；未另行运行独立内核实现。

## 扩展与审阅规则

1. 先选一个真实错误或边界，确定本次模型要排除什么。
2. 在本域 `lean/README.md` 说明对象、假设、命题、正例、反例，以及实际实现尚需满足什么。
3. 仅导入本域模块、`PrimitiveCore` 或随附 `Init/Std`。领域之间不得直接导入业务模型；通用证明的参数由各域自行解释。
4. 在 `lean-projects.json` 登记新模块与实例输入；证明文件采用一个库内命名空间、顶格显式 `theorem`，不使用未经审查的元编程或自定义公理。
5. 运行验证并按源哈希保存回执；更新相应版本、入口与范围说明。源快照不改，真实用户／观众数据留在原系统。

数学存在性不自动产生可执行策略；部分正确性不自动产生终止；可辨识不等于真实掌握；结构保真不等于好读、好看或省注意力。实际程序精化与经验效果分别提供证据。
