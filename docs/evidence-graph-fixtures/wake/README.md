# SVC Wake 证据图夹具

本夹具声明证据关系和 Git 来源坐标。源 Spec、模型、实现与执行回执从 `mayf3/svc-workflow` 的固定提交读取。材料由夹具工具复制到隔离目录，证据图可随时重建。

| 范围 | 固定坐标 | 可读事实 |
| --- | --- | --- |
| 已接受权威、旧实现 | `c50ab2ac98decceaa26138a282c34dd92ede0ddc` | Visit Activation V3 的 `CTR-VAI-008/014`、`ACC-VAI-005/009`；Execution Control V3 与 PostgreSQL Storage Contract V0.3 为相关权威 |
| 草稿 [SVC PR #142](https://github.com/mayf3/svc-workflow/pull/142) | `a22a0180ebf0775d42f9e54f09eed33a2de9ed25` | `formal/wake/`、Rust 修复、PG 回归、主变更记录与审计回执 |
| 消费仓治理 | `c50ab2ac` 内的 `.agents/governance.lock.json` | 已接受 1.1.0，vendored source `0595e7e8a5f5bcd45660ca19fdabe932637af2ec` |

同一权威文件以 MAIN 和 PR142 的别名求覆盖，防止把候选证明计作 main 已交付。候选模型分开表示 typed replay、确定性拒绝和提交观察，映射到 `decode_replay`、`deterministic_failure` 与 `wake_dispatch_intent_atomically`。模型审计覆盖 44 条显式定理。审计回执记载了当时的基础 HEAD 和 dirty overlay。所有记录的模型哈希与候选 Git 字节一致，图的定理证据使用本轮 [独立复编译回执](wake-lean-verification.json)，执行在 Lean 4.19.0、候选 Git SHA 精确匹配且干净的 checkout，只有 `Quot.sound`、`propext` 标准公理。

独立复编译原始回执 SHA-256 为 `ccdd52def9b5a097e515155f2147d58fc2d1d4fbea341fa0bef0267d0764acd6`。公开副本只将三条 `commands[].command[0]` 中的本机用户目录下的 Lean 可执行文件路径替换为 `<LEAN_4_19_0_DIR>/bin/lean`。其余字节保持原样，包括版本、源码哈希、命令参数、退出码、定理和公理审计。公开副本 SHA-256 为 `a3b3d4658132737da1ffd994e0a2454687c4f33c01ff8798e068092204dc8c78`，图坐标使用该值。

隔离 PostgreSQL 回执记录 2 项 codec 与 17 项 Visit/Activation 通过，所有 470 个执行输入的 manifest 哈希与 #142 的固定字节一致。旧 Wake Rust 配同一组回归的负对照为 10 通过、7 失败，历史 receipt、manifest 和原始日志仍是不同材料。测试证据支持对应执行输入和断言。失去提交 ACK 的网络故障、完整 Rust/SQL 精化、运行期前提的 probe 及原始需求的最终验收留在 UNKNOWN。独立子流程回执里的已知 PostgreSQL 回滚与不可观测的提交结果分开处理。

复现图时需要本地 Svc 仓拥有上述 Git 对象。夹具工具直接读取指定提交。应用仓无需切换当前工作树。

```sh
project=$(mktemp -d)
python3 tools/evidence_graph_fixture.py \
  --fixture docs/evidence-graph-fixtures/wake/fixture.json \
  --repositories /path/to/repositories --destination "$project"
python3 tools/evidence_graph.py build --project "$project"
python3 tools/evidence_graph.py coverage --project "$project"
```
