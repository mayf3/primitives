# Project Adapter Contract · Workflow P0 Batch 4

The [pilot plan](PROJECT_ADAPTER_BATCH4_PLAN.md) fixes the implementation and evidence sources. This contract compares a finite native execution with an independent model. Its inputs are reviewed adapters, versioned mappings, a sealed trace where required, and current scoped probe evidence.

## Process protocol

The Python standard-library runner `tools/project_adapter.py` sends UTF-8 JSONL RPC to independently started SUT and Oracle processes. Each request has `id`, `method` and `params`. Each response echoes the request ID and contains `result` or an `error`. [The v1 schema](../schemas/project-adapter-v1.schema.json) defines the suite and interchange shapes.

| Method | What the reply supplies |
| --- | --- |
| `reset(seed, environment_profile)` | Start from a fresh instance in the declared isolated profile. |
| `snapshot()` | SUT returns concrete state. Oracle returns its abstract state. |
| `execute(command, test_context)` | Both execute the same command. A complete result carries ordered events, and any effect or refusal observation remains explicit. |
| `abstract_state(snapshot, mapping_id)` | Project concrete state using the named reviewed mapping. |
| `normalize(event, mapping_id)` | Produce a model event, a declared stutter, or an unsupported result. |
| `observe(result, observation_id)` | Interpret only facts available in the SUT result. |

The two workers have separate process state and working directories. The SUT receives commands and test context. The Oracle receives the same inputs and evaluates its own state. The runner compares the projected states and ordered event labels after each command. Accepted stutter IDs require explicit justifications. When a command has no model transition, its projected state must stay unchanged. The protocol tests and replay digest cover unframed output, early closure, missing sequence position and mismatched observations. A reviewed adapter and an independent execution authority remain part of the trust boundary.

A receipt records the seed, complete input plan, initial state, every executed step, the last failure point, the raw worker exchanges and the environment evidence. Adapter, mapping, Oracle and SUT revisions are immutable bindings. A source mutation has its own patch and file digest. `TRACE_DRIFTED` records a concrete disagreement. `TRACE_INCOMPLETE` removes support when collection is incomplete. `STALE` removes support when a required input revision or probe has expired. `UNKNOWN` preserves unsupported model or effect claims.

## Core Recovery mapping

Core Recovery processes run in a detached worktree of `ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e`. The SUT executes real ledger and recovery operations with a loopback Router and an isolated store. `attempts.jsonl` and a fresh native replay supply concrete state. The mapping uses the tuple `(NodeVisit, Attempt, Generation)`, phase and the persisted `delivery_started` fence, with Router response and reconciliation facts observed separately. Test support adds subprocess fault injection and observation. `reconcileSettled` uses isolated fixture evidence for the ledger command. Core product source changes appear only in the disposable mutation worktree.

The new Lean theorem `step_result_exact` proves the executable decision agrees with the original `ExecutionRecovery.Step`. Lean generates the finite table used by the independent Python Oracle. A fixed rule composes two legal steps for blocked recovery. Native metadata and a first original-key Router observation are stutters only within the documented projection. Cross-generation CAS and concurrent stop/revive are checked with native witnesses; the Lean relation covers a single attempt. The latter witness records the old poll and stop, new-engine recovery over the same persisted attempt, and the final delivery count.

If an ACK is lost after Router acceptance, the effect verdict remains `UNKNOWN`. The per-step result can still show that all observed ledger transitions match the model. Evidence Graph only uses that narrow observed-transition claim when the complete segment compared successfully. It keeps the raw `UNKNOWN` effect verdict and does not infer original business acceptance. Missing or stale evidence cannot contribute that coverage.

Batch 1 supplies the compiled graph and exact model/code coordinates. Batch 2 supplies native traces and verifies the removed-event negative control. Batch 3 supplies an independently scoped probe receipt and its actual expiry. The Batch 3 fixture's socket is separate from the per-command SUT fixture. The SUT records its own Router observations throughout the comparison.

## Run and replay

Use Python 3.12+, Node 26.7.0, and the repository's pinned Lean toolchain. CI collects `evidence-graph-results`, `core-recovery-capture`, and `core-assumption-freshness` using the previously merged Batch 1–3 entry points. Then run the pilot with those fresh inputs. `$repos` points to the fixed Git repositories and `$out` is new.

```sh
python3 tools/check_core_project_adapter.py \
  --repositories "$repos" --core-repo "$repos/dsh-agent-core" \
  --graph "$inputs/evidence-graph-results/core/evidence-graph.json" \
  --capture "$inputs/core-recovery-capture/core-recovery-capture.json" \
  --probes "$inputs/core-assumption-freshness" --output "$out"
```

The same command accepts `--replay "$original/mutant-post-wal-router.json"`. It checks the saved command digest and independent tool coordinates, reconstructs the exact Core tree, reapplies the recorded patch and verifies the preimage and resulting source hashes. The other source mutations can be replayed the same way. For a saved expiry or missing-trace control, replay independently computes the expiry or removes the trace row again. For other consumers, use `tools/project_adapter.py run suite.json --output receipt.json`. The generic `replay` accepts the prior receipt with independent current version and evidence bindings.

The pilot preserves original and restored receipts, all three mutation patches, the exact array of seeded commands, native transcript and oracle table, and every derived coverage snapshot. Each mutation must first produce a semantic disagreement during real execution. A source-hash mismatch alone cannot pass the challenge. Reverting it must restore the original source bytes and observable coverage under the same plan.

## Governance

PR #20 remains the Evidence Graph implementation. PR #21 is closed with the original review threads intact. Its applicable additions are tracked separately in PR #24 on top of #20. Scope here is finite isolated verification. Full implementation refinement, original business AC, production environment and independently enforced CI and review remain open.
