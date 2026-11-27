# 治理执行者中断后的接管可行性

本轮检验 [Agent 主动治理规格](AGENT_INITIATED_GOVERNANCE.md) 的故障窗口。隔离样本以正式 Case、原业务节点、已建立的治理义务和原外部操作指向同一个绑定。中断发生在治理责任已持久接纳、修复结果尚无权威结算之后。

## 先对齐要验证的需求

| 条件 | 可失败的验收 |
| --- | --- |
| 故障前责任可接回 | 库中有已持久接纳的治理身份、执行者及当前租约。仅开 Case、只持久等待或仅投递消息无法证明此项。 |
| 接得回同一治理责任 | 观察到执行者死亡或权威围栏后，由不依赖故障执行者的消费者见到同一记录，通过当前租约 CAS 登记实际接纳。新 epoch 拒绝旧执行者再写。原任务仍开放。 |
| 日志缺口按 UNKNOWN 处理 | UNKNOWN 时允许独立消费者接管读取和对账。无可信未生效证据、可证明的原键重放能力或权威提交回执时，禁止发起新外部写。 |
| 最后按原标准恢复 | 对账、修复、核验、合法采用、原工作流恢复及原 AC 提交各有证据。关闭独立消费者时，原义务仍开放。 |
| 故障局部隔离 | 一条治理失败持续存在时，健康任务仍能获取服务。已知的嵌套 STOP 可以验证安全停止；模拟进程退出及实际接管是独立用例。 |

本轮的数学切片聚焦租约与对账。接受、结果结算、原任务完成沿用此前模型。隔离验证规定不借助人工重派，不更换原业务键，也不先认可业务完成。关闭消费者指没有可运行的独立接管者，已在飞的操作仍须对账。

## 数学判据

令治理绑定 g 固定。持久状态为 (g, phase, worker, epoch, effect)，其中 effect 至少取 UNKNOWN、权威未生效、原命令已提交。故障或围栏使状态进入持久 hold。合法的重新接管在同一 g 上按旧 epoch 做 CAS，原子推进 epoch，登记新的独立消费者并保留 effect 原值。接管赋予对账能力，其本身没有外部写授权。只有单独通过原键和效果证据门，才可重新执行。

由此检验以下条件定理：接管保持 g 与 effect；旧 token 无法修改已转移的持久事实；UNKNOWN 可以被接管而不能单独开启重做；任意有限次无效扫描保持 hold，在首次具备权限、可达、满足 CAS 的真实扫描时接回。持续没有合格扫描的轨迹是合法反例。物理租约、调度公平、证据权威和真实 AC 由实际实现与隔离回执验证。

## 隔离实跑

固定 Svc 提交 `787278729486381afb8e5976db912fbc190b875c`，Core 提交 `edd359fb4583d91c1832ae0d89244e53224e8fa7`。测试使用自建回环 PostgreSQL、临时执行账和隔离测试身份。Svc 进程试验中的目录服务是受控夹具；Core 探针注入受管 Svc 响应以及 Router 退出事实。

| 假设或故障点 | 观测与裁定 |
| --- | --- |
| 原请求已立项，Svc 生产器退出 | **通过。** 在真实 Svc 周期生产器等待目录 admission 响应时 SIGKILL。原 INTAKE 保持 PENDING，子任务与提交回执均为零。同一二进制的继任进程自动认回同一 intent、source、visit、Case，得到一个子任务、一个绑定、一条完成回执。多运行一轮无重复。 |
| 现有 Svc 能自行恢复嵌套 STOP | **未通过。** 真实 Svc 带合法 Policy Actor 启动并运行 6.3 秒，原 `NESTED_ASSISTANCE_UNSUPPORTED` STOP 与所有计数保持不变。此负控验证当前生产器的覆盖范围。嵌套求助或耗尽上限触发的 STOP 和单次进程退出是两种事实。 |
| Core 复用持久执行账 | **隔离通过。** 76 项恢复用例及 6 项治理通知用例通过。写前 SIGKILL 的原 attempt 自动接续，Router 已接纳但 ACK 丢失时保留 UNKNOWN 和活跃 fence，均无第二次投递。Owner 恢复正控使用 Svc/Router 夹具，受管节点的三次上限负控拒绝用旧式解案证据继续。 |
| Core 自动建立受管效果对账 | **未发现接续。** 真实模块探针中，Router 的 `restart_lost` 被分类为 `run_outcome_unknown`，后三次扫描均为 `already_attempted`，没有登记效果回读。Router 的 `settled / terminated_without_outcome` 则进入同 visit 第 2 代执行。夹具中的效果从 UNKNOWN 改为 SUCCEEDED，含原提交回执，四个场景按两类 Router 输入分别得到相同 Core 决策。探针没有调用业务写入。现有 Svc/Broker 对受管操作仍有独立效果门。 |
| 受管修复者退出 → 实际接管 → 原业务 AC | **仍待联合验证。** 上述 Svc 继任接回的是待建立的子任务。Core 的真实 SIGKILL 试验只覆盖既有 B2 恢复。四场景探针覆盖了受管执行的缺口，但没有连接正式 Svc 子任务及父业务。健康业务与故障治理同场无饥饿也未实跑。 |

[Svc 原始计数与测试回执](evidence/svc-governance-recovery-receipt.txt) · [Core 真实模块探针](evidence/managed-effect-recovery-probe.mjs) · [四场景原始输出](evidence/core-managed-effect-recovery.txt)

Svc 既有套件的复跑命令如下。测试夹具本身对宿主和端口有隔离约束，须按固定版本的测试守卫启动私有回环 PostgreSQL。上表两个 Svc 进程场景均使用真实固定二进制，通过本地目录阻断和对账观察独立接管。

```sh
cargo test --locked --offline --test 46_owner_obligations -- --test-threads=1 --nocapture
```

Core 定向回归在固定 Core 仓库根目录运行。

```sh
node --test \
  packages/workflow-execution/test/owner-assistance-resume-engine.test.js \
  packages/workflow-execution/test/owner-assistance-resume.test.js \
  packages/workflow-execution/test/managed-obligation.test.js \
  packages/workflow-execution/test/observation-cas/blocked-recovery.test.js \
  packages/workflow-execution/test/observation-cas/blocked-recovery-restart.test.js \
  packages/workflow-execution/test/shutdown-contract.test.js \
  packages/production-runtime/test/owner-assistance-resume-evidence.test.js
node --test packages/production-runtime/test/workflow-owner-assistance-wake.test.js
```

模型仓复跑证据门和失配探针。Core 探针也可使用字节一致的公开基线 `ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e`。

```sh
python3 tools/verify_lean.py
node domains/agent-workflow/evidence/managed-effect-recovery-probe.mjs /absolute/path/to/fixed-core
```

## 机检与实现前提

[GovernanceTakeover.lean](lean/AgentWorkflow/GovernanceTakeover.lean) 新增 12 条 Lean 定理并检验首次合格扫描恢复同一责任、CAS 换代、较旧 epoch 拒写和 UNKNOWN 保持。没有合格扫描或权限时，状态保持 hold。正式真人决策不能走该技术接管与写路径。接管者再中断时，可在可信围栏后再次换代，前两位执行者都不能再写。业务写门同时核验当前租约、原效果键及可信效果证明。已提交回执只能读回，UNKNOWN 无安全重放凭证时无法写。Lean 对授权、进程独立、围栏与原键和回执作为待落实的证据入口；物理 CAS、跨系统副作用和调度公平没有被证明。

第一条值得实施的生产精化是「已经持久接纳的受管执行丢失 → 同一治理身份的持久只读对账 → 独立获准消费者自动取回精确效果证据」。复用现有效果记录、原 visit 和稳定操作键。Core 当前对账读取的常规触发条件并不覆盖同 visit 的 `run_outcome_unknown`，受管效果读取又只允许当前受派者或当前有效 Domain Owner。必须明确实际进程如何获准读取以及它不依赖被治理执行者。保持现有 STOP 约束；需要恢复已停止治理时，以独立有权承接合同接回，禁止把 STOP 伪作 READY。原业务端到端的正控是核对真实 Case、原治理绑定、接管 CAS 与独立核验之后，再取得原节点正式提交及原 AC。同场留一条健康义务作公平性对照。

固定公开代码锚点：[Core 读取 Router 摘要](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/engine.js#L161) · [Core 常规对账触发条件](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/packages/workflow-execution/src/recovery/readback-ledger.js#L8) · [Svc 效果读取权限](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/prerequisite/reads.rs#L2) · [Svc 生产器只读 PENDING](https://github.com/mayf3/svc-workflow/blob/c50ab2ac98decceaa26138a282c34dd92ede0ddc/src/store/postgres/workflow_instance_repository/owner_obligation/reconcile.rs#L74)
