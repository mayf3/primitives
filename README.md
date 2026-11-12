# 原语系统

**在同一个仓库里维护人生、写作、设计三套可复用方法。按当前问题进入一个领域，需要协作时再连接。**

这里的“整合”意味着：一起查找、保留来源、明确版本、能组合使用；每个领域继续拥有自己的对象、动作、状态和判断标准。仓库承载方法与合成案例，个人记录和各项目的运行数据留在原系统。

## 从你现在要做的事开始

| 当前问题 | 直接进入 | 能得到什么 |
|---|---|---|
| 我面对的是事实、判断、取舍，还是该执行的行动？ | [人生使用指南](domains/life/GUIDE.md) | 分清概念、找证据、形成待确认的取舍和下一步 |
| 材料很多写不出来，中段散，或一句话改得失去原味？ | [写作使用指南](domains/writing/GUIDE.md) | 选择具体创作动作，先产出可用的文字 |
| 读者不知道在哪里、点击后得到什么，或看完怎么继续？ | [设计使用指南](domains/design/GUIDE.md) | 找到可执行改变，并说明怎样观察其效果 |
| 一件事同时涉及判断、表达与页面交互？ | [跨领域组合示例](bridges/explain-and-guide.md) | 看三个领域怎样交接材料，而不互相替代判断 |

只改一句话时，直接进入写作。只改入口文案时，直接进入设计。无需先阅读三套系统，也无需为一次小任务填写完整记录。

## 三个独立领域

| 领域 | 本次默认内容 | 保持独立的部分 |
|---|---|---|
| [人生](domains/life/README.md) | Life State 的五类认知对象、Activity 行动侧对象及 Evidence 关系；早期 PCA V0 作为独立参考 | 事实与判断、本人确认的决策、人生记录格式与状态 |
| [写作](domains/writing/README.md) | 八个中文创作动作；后台按需保留“材料—新解释—成稿”的对应关系 | 作者声音、创作自由、事实边界、修改采用状态 |
| [设计与交互](domains/design/README.md) | 上传研究中的十个原语、组合模式、使用例子和验证办法 | 页面语义、交互、无障碍，以及来源/实施/用户验证三条状态轴 |

这不是把所有东西都改造成同一种对象。人生的 Activity 可以使用一个设计动作；设计原语本身仍是一种可复用方法。作者采用一句改写，也不会自动使某个人生判断得到证实。

## 仓库怎样组织

- `domains/life/`、`domains/writing/`、`domains/design/`：各自的入口、方法、索引、案例和只读来源快照。
- [shared/CONTRACT.md](shared/CONTRACT.md)：只约定 ID、路径、版本、来源与显式引用。
- `bridges/`：需要多领域配合时的交接说明与可检查例子。
- [registry.json](registry.json)：领域和组合的机器入口。
- [tools/primitives.py](tools/primitives.py)：离线检索和结构检查，使用 Python 标准库。
- [MIGRATION.md](MIGRATION.md)：从哪里来、整合了什么、什么仍有差异。

三个领域的 `depends_on` 都为空。一个领域的使用指南不会要求读完另一个领域。跨域依赖集中写在 `bridges/`，检验时显式检查。

## 人和 Agent 都能使用

人从上面的任务表进入。Agent 先读 [AGENTS.md](AGENTS.md)，再只加载相关领域的指南。

```bash
python3 tools/primitives.py list
python3 tools/primitives.py list --domain design
python3 tools/primitives.py find '下一步'
python3 tools/primitives.py show design.entry-outcome
python3 tools/primitives.py validate
python3 -m unittest discover -s tests -v
```

`show` 打印被选条目的正文；`find` 搜索工作索引和被索引内容，不把历史快照当成默认答案。检索不到时，可以回到该领域指南，不需要新造一个原语来填满分类。

## 本次来源与状态

整合日期：**2026-11-13（北京时间）**。模块版本各为 `0.1.0`；这是本仓库整合版本，不覆盖上游版本号。

- 人生：Life State 自带定义来自 `personal-cognition-data` 的固定提交；PCA V0 文档来自 `personal-cognition-audit` 的固定提交。两者差异在[人生兼容说明](domains/life/COMPATIBILITY.md)中保留。没有迁移真实人生记录。
- 写作：源于 `writing-primitives` 的 main 与仍未合并的 PR #1 候选。本次将中文创作动作建立为默认入口；这项整理是本次新增，效果仍待使用检验。
- 设计：上传研究的原文逐字保留。原研究的网页观察和会话引用保持其原有时间与证据边界；导入不代表重新核验网站或完成真人测试。

每个领域的 `sources/manifest.json` 记录导入文件的 SHA-256。来源快照保持不变，后续改进写在工作文档中。历史 `SKILL.md` 只作为来源保存，不会自动安装、触发或覆盖当前指南。

## 后续维护

本仓库是这三个领域**整合版方法**的后续维护入口。原仓库保留原历史和原运行职责；本次没有归档、重命名或改写它们，也没有建立双向自动同步。

修改一个领域时，只需更新该领域及受影响的跨域组合。增加视频等新领域时，按[共享约定](shared/CONTRACT.md)注册自己的模块；不预设它必须采用现有领域的对象或原语数量。

结构检查通过，只说明文件、来源和引用一致。写作是否更好、设计是否帮助真实读者、人生判断是否受到证据支持，仍分别由各自的方法检验。
