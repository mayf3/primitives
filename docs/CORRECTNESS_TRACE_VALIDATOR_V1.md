# Correctness Trace Validator v1

Batch 2 checks finite observations against a versioned projection of a mathematical model. The input is a compiled Batch 1 Evidence Graph, a reviewed transition contract, native JSONL, a normalized JSONL projection and a closed segment manifest. A conformant trace is evidence for the recorded execution and scope. Lean proofs and original business acceptance have their own evidence.

## Core Recovery pilot

| Requirement | Model and Lean | Implementation observation |
| --- | --- | --- |
| A successor recovers the same durable responsibility before the delivery fence | `ExecutionRecovery.Step.blockedRecoveryBeginDelivery`, `blocked_recovery_is_same_attempt` | One original attempt and request ID from a real Core subprocess after HTTP 503 or a pre-WAL SIGKILL |
| Once delivery may have started, an unverified effect requires reconciliation | `Step.rejectAfterStart`, `begin_delivery_requires_clear_fence`, `terminal_cannot_begin_delivery` | `delivery_started` and no positive Core acknowledgment, with the native terminal projection and Router correlation recorded separately |
| Old observations cannot advance the successor's newly planned attempt | Same-attempt identity preservation in `step_preserves_identity` | Real Core CAS negative control at the old-read / new-generation race, plus refusal of stale identity in an individual trace. General cross-generation lifecycle rules require their own model. |

The held-out Router ACK and the post-WAL crash before dispatch can yield the same Core event kinds. The isolated Router's bound receipt distinguishes them. A Router acceptance receipt establishes prompt admission in the loopback test. The enclosing business obligation and eventual business outcome remain unknown to the test.

The capture helper reads a pinned Git tree, copies it to a scratch directory and adds one field to the existing test reporter. It captures `attempts.jsonl` after the fixture's children exit. The Core modules, test assertions and fault injection remain those at the recorded revision. The manifest covers only this closed, local **persisted ledger**. Observation sequences and causal links within this ledger come from the ordered file and its row digests. Core has no native per-process sequence or global cross-system closure witness for these historical files. The old Batch 1 summary is retained as a partial input.

## Reproduction

Use Python 3.12 or newer and Node.js 26.7.0, as pinned in CI. Set `$repos` to the directory with the three Git repositories and the revisions in the fixture descriptors.

```bash
out=$(mktemp -d)
python3 tools/evidence_graph_fixture_check.py \
  --repositories "$repos" --output "$out/graph"
python3 tools/capture_core_recovery_trace.py \
  --core-repo "$repos/dsh-agent-core" --output "$out/core"
python3 tools/trace_validate_core_check.py \
  --graph "$out/graph/core/evidence-graph.json" \
  --capture "$out/core/core-recovery-capture.json" \
  --output "$out/core-validation.json"
```

`model-trace/v1` rows use the [JSON Schema](../schemas/model-trace-v1.schema.json). The validator reports `TRACE_CONFORMANT`, `TRACE_DRIFTED`, `TRACE_INCOMPLETE`, `STALE` or `UNKNOWN`. Examples include an illegal modeled step, a missing ledger row or causal parent, stale coordinates, and an observed event outside the current model. Those outcomes preserve the distinctions between a witnessed violation, missing observations and an unmapped path.

The Core check saves each segment's native bytes, normalized rows, manifest and contract alongside its report. Replaying a saved segment checks the supplied projection. Run the Core check above to regenerate that projection from native bytes and the subprocess receipts.

```bash
python3 tools/trace_validate.py \
  --graph "$out/graph/core/evidence-graph.json" \
  --contract "$segment/contract.json" --manifest "$segment/manifest.json" \
  --normalized "$segment/normalized.jsonl" --raw "$segment/native.jsonl"
```

The Evidence Graph and transition contract originate from the reviewed source revision. The capture receipt ties raw and normalized records to the observed run. These checks detect inconsistency among the supplied artifacts. Trust in their provenance still depends on the independently controlled runner, source and artifact chain. The transition contract is a reviewed projection of the Lean relation. This pilot does not establish an executable Lean refinement of the entire JavaScript implementation.
