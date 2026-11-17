# 视频领域来源与边界

本领域最初整合了用户上传的《视频呈现原语：从理解、审美到可验证制作系统的研究报告》。整合日期为 **2026-11-13（北京时间）**，原报告写作日期未知。**2026-11-15** 另存了[视频化播客评审的一手资料](#podcast-review)。

## 原文与工作文档分开

- [research-original.txt](research-original.txt) 是逐字保存的报告快照；文件名与 SHA-256 记录在 [manifest.json](manifest.json)。只在工作文档解释差异，不覆盖原文。
- [references.json](references.json) 登记本轮实际打开的少量官方来源、核对范围及限制。它不是原报告全部参考文献的复原表。
- 原文的 `turn…search…`、`turn…file…` 等旧会话引用没有可独立定位的 URL、书目信息或文件锚点，本轮保持 **unresolved**。原文说“已核验”的部分仍只是原报告的自述，不能自动成为本仓库本轮已核验事实。
- 原文 A/B/C/D 是报告作者的分级。它把元分析和正式标准同列 A，本领域不沿用为一个统一证据强度分数：实验回答效果，标准约束可访问性，行业指南表达制作经验，本项目假设仍需实际检验。
- 十项原语是从报告整理的候选方法，不是已被实验验证的最小完备集合。来源已读、方法整理、代码实施、观众效果是不同状态。

## 导入时必须保留的差异

| 原报告中的情况 | 工作文档采用的处理 | 原因 |
|---|---|---|
| 报告没有取得 `EP03-Seaside-1080p-v1(1).mp4`；本轮附件也是文字报告 | 应用记录中 `source.media_accessed: false`；示例标为合成分镜 | 不能把报告里的诊断假设写成实际观看记录 |
| 六个候选源时间码没有经过视频或逐字稿核对 | 实际源范围为空，或另存为待核线索；不给出“已核”时间锚点 | 节目主题相符不等于具体时间、画面相符 |
| 源范围 `16:45–17:30` 为 45 秒，改版 B 为 78 秒，焦点排程还有 `t:66` | 分开记录 `source.source_range_seconds` 与 `presentation.planned_duration_seconds`；排程使用成片片段的局部时间 | 源素材窗口不能直接充当改版时间线 |
| `transcript:ep03:L412-L438` 没有提供可核对的逐字稿 | 正式记录锚点为 `null`，待真实材料补齐 | 例子中的格式演示不是来源证据 |
| “对应”卡直接给出三层 Prompt 名称，后文又说明三层尚未确认 | 卡片改用通用配对示例；三层 Prompt 保留为待核结构模板 | 不把未经定义的包含、并列或作用范围画成事实 |
| Current 产生 archive 快照，Plan 根据选择形成 | 明确区分同一对象状态变化与新对象派生 | 视觉连续不代表两个对象事实上的同一性 |
| 箭头走到 Execute，或安装示意结束 | 保持“流程示意”；没有真实输出时不得声称执行成功 | 动画完成不证明现实任务完成 |

本轮没有重新审看 EP03、核对软件录制版本、实施改版视频或进行真实观众测试。将来做真实应用时，源片段、逐字稿、素材版本及观察记录仍留在对应视频项目，本仓库保存方法和必要引用。

## 本轮有限核对的来源

以下均为 **2026-11-13（北京时间）实际打开的网页**。W3C 的 Understanding 页面是解释材料；正式规范见 [WCAG 2.2](https://www.w3.org/TR/WCAG22/)。本轮只核对相关条目的适用范围，不构成对成片、播放器或网站的完整 WCAG 合规评估。

| 来源 | 本轮核对什么 | 能支持什么；不能支持什么 |
|---|---|---|
| [W3C：预录字幕，SC 1.2.2](https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html) | 预录同步媒体的字幕要求、文本替代媒体例外、必要说话者和非语音信息 | 支持字幕验收条件；不证明某种字幕动画提高学习效果 |
| [W3C：颜色使用，SC 1.4.1](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) | 不能只依靠颜色传达必要信息 | 支持增加文字、形状等线索；灰度自查不是完整合规证明 |
| [W3C：暂停、停止、隐藏，SC 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html) | 自动开始、超过五秒、与其他内容并行的移动信息及必要活动例外 | 约束适用的网页和播放器情境；不能简化为“所有视频动作超过五秒都须独立暂停” |
| [W3C：闪烁阈值，SC 2.3.1](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html) | 一秒内闪烁次数或一般/红色闪烁阈值 | 支持成片闪烁检查；有暂停按钮不能替代阈值检查 |
| [IBM Animation：Overview](https://www.ibm.com/design/language/animation/overview/) | 运动服务意义，以及 productive / expressive 两类表达取向 | 支持行业制作取舍；不作为理解增益的实验结论 |
| [IBM Animation：Tips and techniques](https://www.ibm.com/design/language/animation/tips-and-techniques/) | 焦点交接、构图与动作复杂度、节奏与停留 | 支持工作假设和制作参考；不把其品牌偏好变成所有视频的定律 |
| [Remotion：Sequence](https://www.remotion.dev/docs/sequence) | 时间偏移、持续时间及相对时间线 | 支持渲染时间的分层；不决定语义关系或原语数量 |
| [Remotion：Caption](https://www.remotion.dev/docs/captions/caption) | 字幕文本与毫秒时间字段 | 支持实现记录；数据结构存在不等于字幕正确、同步或完整 |

Remotion 本次页面已说明不再推荐直接使用 `<Sequence>`，其时序属性可由相关组件使用或继承。这里保留对时序概念的引用，不锁定唯一组件写法；实际制作按项目所固定版本复核 API。当前网页不用于反推 EP03 录制时的实现。

<a id="podcast-review"></a>

## 视频化播客评审的一手资料 · 2026-11-15

下表便于按制作问题查原文。每份来源的章节、英文短摘、可支持的判断、本仓库的转用与限制均收入[固定摘录快照](podcast-review-20261115.json)，其 SHA-256 登记在[导入清单](manifest.json)。

| 生产中要判别什么 | 查哪份来源 | 能用到什么范围 |
|---|---|---|
| 提示该落在何处、何时出现 | [Boucheix 与 Lowe 的眼动实验](https://doi.org/10.1016/j.learninstruc.2009.02.015) | 钢琴机构动画里，提示与相关部件及事件同步，帮助定位与理解 |
| 变化前后能否追踪到同一对象 | [Heer 与 Robertson 的图表研究](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/InfoVis2007-DynaVis.pdf) | 统计图形转场设计与识别实验，尤其适合检查复杂转场的中间状态 |
| 运动有无用途 | [3Blue1Brown 作者答疑](https://www.3blue1brown.com/about/) | 数学动画作者的创作经验 |
| 什么材料能让观众看到依据 | [Vox 制片人 Sam Ellis 的采访](https://www.storybench.org/how-vox-explained-chinas-belt-and-road-initiative/) | 一条地图解释视频中寻找资料与视觉证据的经过 |
| 如何识别重演的边界 | [BBC 旧版编辑指南 §3.4.18](https://downloads.bbc.co.uk/guidelines/editorialguidelines/pdfs/Section_03_Accuracy.pdf) | 纪实重演的证据要求与标识方式 |
| 留存曲线究竟测到了什么 | [YouTube Help 的峰谷说明](https://support.google.com/youtube/answer/9314415?hl=en) | 重看、分享、跳过与退出等行为；原因需结合片段另查 |
| 如何清洗字幕并保住原意 | [W3C WAI 转录指南](https://www.w3.org/WAI/media/av/transcribing/) | 听辨原话、选择有意义的声音、在短语边界切分 |
| 如何比较简中字幕的密度 | [Netflix 简中定时字幕指南](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215986007-Chinese-Simplified-Timed-Text-Style-Guide) | Netflix 普通字幕与听障字幕各有交付条件 |
| 分支从哪条消息产生 | [OpenAI 网页端分支发布说明](https://help.openai.com/en/articles/6825453-chatgpt-release-notes) | 2025-09-04 发布时的网页版入口和动作；节目所录版本仍待核实 |

本次两段用户反馈另供案例线索，包括节目时码、候选字幕修字、三层节奏与动画试值。九份外部资料的计数限于上表。实际镜头、原声、字幕和观众反应需回到相应制作项目核对。

<a id="architecture-review"></a>
## 0.3.0 结构评审与核查

[外部 Agent 评审原文](architecture-review-20261115-original.txt)以 0.2.0 为对象。附件末尾的四处手术与正文的七项架构是两种提案；其中的源片效果、实测性能和一致率都没有附独立观察记录。附件中带前缀的锚点来自合并评审稿，域内工作文件使用自己的短锚点。

本次另存[六份资料的核对范围](architecture-references-20261115.json)，记录采样算法、图表转场、文字和非文字对比、可访问字幕、冗余文字研究。既有九份资料保持原日期。具体采纳、收窄和仍待观察的问题见[六项评审处置](../REVISIONS.md)。

<a id="boundary-review"></a>
## 0.3.1 制作边界复审

[第二轮评审原件](boundary-review-20261115-original.txt)记录四个反例和一份多卡训练分镜。收到的附件逐字保存，四项改动、原提案中需要纠正的技术条件与编辑后的关键帧见[处置记录](../REVISIONS.md#boundary-review)。

[六份训练资料的固定摘录](bucket-review-references-20261115.json)登记了 PyTorch 调优指南、2.9 API、带历史版本限制的设计说明、v2.9.0 归约器的固定源码、DDP 原论文和 Profiler 说明。它们用于确认可以在何种配置下累积、何时可以按桶重叠。算例的十格与八格来自作者给定的理想排程，尚无对应训练测量。

<a id="narration-and-readout-reviews"></a>
## 0.4.0 两份独立评审与复核材料

[评审一原件](readout-review-20261115-original.txt)讨论重叠排程的布局豁免、连续阈值和分块归一化。[评审二原件](narration-review-20261115-original.txt)讨论原声与屏幕文字的绑定、提前揭示和示例误用。两份附件均评审 0.3.1，当前修订接在 0.3.2 之后。附件中对于具体成片错误、研究公理与硬件收益的说法，需依各自来源判定。

[算法与实现资料](online-normalizer-references-20261115.json)按原文核对数学量及实现范围。[两篇认知研究](narration-references-20261115.json)各附作者全文定位、研究任务与应用限制。组织讲解用的“预告／回顾”和“总数／分期”来自这次编辑决策。此前已归档的短关键词冗余实验仍按原核对范围使用。[具体处理](../REVISIONS.md#audiovisual-and-readout)

## 0.4.1 冻结版复核

[独立评审意见原件](independent-review-v0.4.0-20261115.md)记录 v0.4.0 的复跑条件、W3C 键盘操作短片的版本与抽帧位置，以及时间轴、回顾引语和两个数学算例的反例。报告中的节目范例、机器结果和观众验证各有范围。具体修订见[0.4.1 处置](../REVISIONS.md#independent-review)。

<a id="viewer-friction"></a>
## 0.4.2 正常观看摩擦的反馈

[用户消息摘录](viewer-friction-feedback-20261115.json)按问题保存这轮审片分析的内容、待核时码和建议，明确其为分项摘录。消息提及的盲测版本、观众条件与原始回答尚未提供，70%／30% 为消息作者的估计。输入总表末行截断，第四项建议按其后完整段落整理。本文及工作文档中的入场预算、机位方案与检验反例属于本次编辑选择，具体取舍见[0.4.2 修订](../REVISIONS.md#viewer-friction)。此前固定来源保持各自的原文、哈希和状态。

<a id="narrative-review"></a>
## 0.4.3 声画叙事建议与有限核查

2026-11-18 收到的[升级报告](narrative-review-20261118-original.txt)逐字保存，附件名称与哈希记入清单。报告包含节目版本历程、审美评价、工作室归因、认知科学论断及制作提案。本轮未取得所述八轮制作产物、观众原始回答或留存数据，相关时码与评分保持转述状态。原报告提出的自动化管线归为提案。[采用与收窄](../REVISIONS.md#narrative-review)

本轮直接复核四份一手材料，短摘、定位和应用边界保存于[核查快照](narrative-references-20261118.json)。既有研究快照继续保留原日期和范围。

| 核查问题 | 来源与适用范围 |
|---|---|
| 提前阅读能否推出通用 −300ms | Malone 与 Hui 的阅读伴随听音研究观察二语读者的目标词注视。它可帮助提出时序问题，未提供任意图形提前 200～400 毫秒效率最优的实验结论。[研究原文](https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/audiovisual-asynchrony/E9478ADE37908019FAF84A262200E2C4) |
| 少量重复文字与完整字幕是否同一任务 | Mayer 与 Johnson 研究在图中对应位置放少量关键词，回忆与迁移结果不同。该任务范围不足以推出中文播客应隐藏完整字幕。[论文](https://doi.org/10.1037/0022-0663.100.2.380) |
| 字幕要保留什么 | W3C WAI 说明字幕承载理解所需的语音及非语音声音，并与音频同步。局部概括词能否承担这些内容仍需逐项核对。[字幕指南](https://www.w3.org/WAI/media/av/captions/) |
| 先例后定义、有目的运动是否有作者依据 | Grant Sanderson 的 FAQ 确有这两项建议，并说明不同讲解体裁的节奏与风格有别。它们作为作者经验使用，未推出全片禁止切镜或统一形变。[作者原文](https://www.3blue1brown.com/about/) |

已有[机械动画提示研究](podcast-review-20261115.json)用于复核提示与对象及事件的对应，未用于建立“两个运动元素负荷翻倍”的计分公式。原报告中的 85 分拦截、字幕消耗 50% 视觉算力、音效改变一半吸引力及沉浸提升一个数量级，本轮均未获得对应的可核实依据。Dan Koe／Keyframe、各频道统一节奏时钟等归因未全面核查，工作文档仅吸收可说明条件的制作选择。

<a id="mental-model-review"></a>
## 0.5.0 组块、联动与观看方式的评审

2026-11-18 收到的[评审附件](mental-model-review-20261118-original.txt)逐字保存。新增 `video.chunk` 候选组合及五张卡的条件修订来自本次编辑判断。附件所述神经科学机制、频道惯例与自动认知收益分别按证据范围处理。[删替与处置](../REVISIONS.md#mental-model-review)

本轮直接复核三份一手来源，短摘与定位保存为[固定核查记录](mental-model-references-20261118.json)。Cowan 讨论特定条件下的组块容量，不能直接限制屏幕元素数量。Victor 展示具体状态与抽象总体的双向探索，未测出代入某个固定数字最快。Heer 与 Robertson 要求转场中间态尽量语义有效，也讨论错误因果印象和时间成本。它们用于提出有条件的制作与验证方法。[Cowan 原文](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/44023F1147D4A1D44BDC0AD226838496/S0140525X01003922a.pdf/the-magical-number-4-in-short-term-memory-a-reconsideration-of-mental-storage-capacity.pdf) · [Victor 作者文章](https://worrydream.com/LadderOfAbstraction/) · [图表转场论文](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/InfoVis2007-DynaVis.pdf)

声画微时差沿用[此前同步研究](narration-references-20261115.json)与[阅读先后核查](narrative-references-20261118.json)，本轮未重新打开这两份原文。它们未确立本附件的两个毫秒区间或必漏前三词的结论。条件化的预备与命名时序继续作为试播方案，连续层与暂停层的分工属于本次编辑约定，实际可用性仍需指定版本的观看记录。

## 下次怎样补证据

若要把某条效果主张从“报告转述”提升为独立核对，新增可解析的原始论文或正式材料记录，写清被支持的具体主张、研究对象、任务条件和反例；不要仅凭找到同名论文就标为全部核实。若要提高某张原语卡的实际可信度，记录指定视频版本、实施差异、理解任务及感受问题，并保留不支持预期的结果。

来源补充可以改变方法取舍，但不能反向修改已有原文。所有效果判断都要指明范围，不能从一次网页核对或结构检查产生通用的 `verified: true`。

<a id="sensory-review"></a>
## 0.6.0 感知通道与作品级审阅 · 2026-11-18

[本轮附件](sensory-review-20261118-original.txt)逐字保存，原文件名与 SHA-256 登入清单。它对 v0.5.0 提出边界反例与作品级评价建议；其中频道评价、采用比例、阅读成本倍数和传播推断均非本仓库已核实的观看或统计结果。工作文档保留有条件的制作方法，具体取舍见[修订记录](../REVISIONS.md#sensory-review)。

另存[四项一手资料核查](sensory-references-20261118.json)，记录本轮实际读取的位置与可用范围：

| 来源 | 采用范围与限制 |
|---|---|
| [W3C：预录纯音频与纯视频，SC 1.2.1](https://www.w3.org/WAI/WCAG22/Understanding/audio-only-and-video-only-prerecorded.html) | 区分媒体类型与替代访问。声音重要不使同步视频变成纯音频；等效必要信息不等于复制所有听觉体验。 |
| [W3C：预录字幕，SC 1.2.2](https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html) | 字幕承担对白、说话者及理解所需的声音信息，不能由概括卡替代。本轮重新核查；这是官方解释页，不是完整交付验收。 |
| [Netflix：字幕通则](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements) | 核第 4 节断行、第 5 节位置。中文转用语义切分思路，不沿用全部英文词类规则、平台时值或行数作为普遍标准。 |
| [Walker 与 Nees：Theory of Sonification](https://sites.lafayette.edu/neesm/files/2011/10/WalkerNeesTheSonificationHandbook-chapter2.pdf) | 核 §2.5.3、§2.6 的映射、方向、尺度、并发表现、上下文和评价。属于作者综述，未逐一复核所引实验，不支持听觉普遍更快。 |

BBC 官方字幕资料读取受限，未以镜像冒充已核官网。问题锚点、双向封装、离片复述及三面作品审阅属于本轮编辑构造，仍待实际样片与明确受众检验。旧来源快照及其日期、哈希、核查范围保持不变。

<a id="sequence-review"></a>
## 0.6.1 通道补充、更正与连续观看 · 2026-11-18

[附件原文](sequence-review-20261118-original.txt)逐字保留，其完备性判断、固定节律、认知压缩比、刺激频段与生理效果均不是本仓库已核事实。更新细化制作与审片任务，不把十二个入口认证为零失误语法。[采用与边界](../REVISIONS.md#sequence-review)

[本轮三份原件的核查记录](sequence-references-20261118.json)保存实际读取位置、版本与应用范围：

| 原件 | 所核内容与限制 |
|---|---|
| [The Debunking Handbook 2020](https://skepticalscience.com/docs/DebunkingHandbook2020.pdf) | 核持续影响、反噬及更正建议章节；作者共识手册，未逐篇复核转引实验。支持明确配对旧说法、更正与依据，不支持画叉就消除误记或更正普遍反噬。 |
| [EBU Tech 3342 v4，2023-11](https://tech.ebu.ch/docs/tech/tech3342.pdf) | 核 LRA 定义、算法范围与短片局限；描述宏观响度变化，不衡量生理舒适、压缩失真或疲劳。 |
| [EBU R 128 v5，2023-11](https://tech.ebu.ch/docs/r/r128.pdf) | 核节目响度、LRA、真峰值及不足一分钟节目测 LRA 的限制；广播建议不直接成为所有网络视频的电平目标，未给齿音或审美的万能阈值。 |

手册在 GMU 的 PDF 读取返回 526，实际采用共同作者 John Cook 在[发布页](https://skepticalscience.com/debunking-handbook-2020-downloads-translations.html)链接的下载原件。未将未成功读取的位置写作核查证据。布局与帧时间检查属于本轮制作提案，没有新核帧率 API 或执行媒体分析；实际结果仍由目标成片提供。
