# Assumption Freshness Checker · Batch 3

An execution receipt records a past observation. Evidence Graph recomputes whether the observation supports a current environment assumption, then applies the result to explicitly dependent runtime coverage. Proof validity and original business acceptance retain their own evidence.

## Model and probe scope

The [ExecutionRecovery model](../domains/agent-workflow/lean/AgentWorkflow/ExecutionRecovery.lean) relies on its durable delivery-start fence, execution scheduling and Router observation. These checks support a bounded isolated Core profile. Core owns the probe code, proposition, execution owner, TTL and failure semantics in `packages/workflow-execution/test-support/recovery-assumption-probes.json` at the probe commit pinned by the pilot runner.

| Assumption | Observation | Outside the observation |
| --- | --- | --- |
| `CORE.ASM.RESTART-WAL` | After a real SIGKILL, a fresh process reloads the same attempt and the same bytes containing `delivery_started`. | Power-loss durability, production storage and other crash windows. |
| `CORE.ASM.RECOVERY-RUNTIME` | A fresh child runs the expected Node version. A loader observation checks the exact loaded bytes and exports of three pinned modules. | Production install, all transitive imports, liveness and scheduler fairness. |
| `CORE.ASM.ROUTER-READBACK` | The loopback route returns the original persisted correlation receipt. The test makes the same listener return HTTP 503, restores it, and observes the original receipt digest again. | The production in-process channel, external effects and original business acceptance. |

The pilot freezes Batch 2's Core implementation and adds only the consumer probe entry and profile from the reviewed Core probe commit. Its lease is five minutes from the observation timestamp. A successful observation applies to the declared environment snapshot and exact artifact binding during that interval. Future samples are needed to observe changes within it.

## Receipt and current context

The `assumption-probe-context/v1` document supplies the current assumption ID, proposition, owner, probe ID, six revision bindings, environment-scope hash, TTL, failure semantics, blind spots and evidence coordinates. The receipt adds the actual invocation, exit code, result, executed and expiry times, input digests and sanitized environment snapshot. Probe stdout is parsed as a small structured observation. Free-form stdout and stderr are discarded. Use reviewed, isolated, no-secret commands and scope data. The runner records the argv verbatim, so paths and parameters must also be suitable for the evidence audience. The pilot uses no randomized test cases.

`PASS`, `FAIL` and `UNKNOWN` describe the observation. `STALE` is a later assessment of its applicability. A timeout follows the profile’s `failure_behavior`; the Core profile treats it as `UNKNOWN`. The receipt is kept byte-for-byte as recorded. An environment, policy or source change, a changed checker, or reaching expiry retracts current coverage. A missing observation contributes no coverage.

The graph requires an explicit `ASSUMPTION.current_probe_id` and a directed `PROBE → ASSUMPTION` `probes` link. Only the authorized current receipt can contribute coverage. A consumer publishes the current pointer from its authentic execution result, including failures, while retaining the earlier receipts for audit. An authorized writer with control of the graph context and pointer remains in the trust boundary. Evidence Graph cannot discover a receipt that the publishing authority omits.

A runtime `TEST`, `TRACE` or `REFINEMENT` can declare `required_assumption_ids` with matching `requires` links. The current coverage is withdrawn when any required assumption is unavailable or stale. The graph still exposes the historical execution evidence and existing Lean audit. The pilot verifies a narrowly scoped dependent claim, `CORE.TEST.RECOVERY.WITH-PROBES`. The existing Batch 2 observations and their five conformant/one unknown classification are preserved.

## Reproduce

Use Python 3.12 or newer and Node.js 26.7.0. `$repos` contains the sources in the Core Evidence Graph fixture. `$core` contains the exact Core implementation and probe Git objects. The pilot creates and removes an isolated scratch workspace, launches a local Router fixture, and writes raw probe receipts plus each graph and coverage snapshot to the output directory.

```sh
out=$(mktemp -d)
python3 tools/check_core_assumption_freshness.py \
  --repositories "$repos" --core-repo "$core" --output "$out/pilot"
```

To check a specific receipt, use `tools/assumption_freshness.py check --context current.json --receipt observed.json`. Omit `--receipt` for an unexecuted probe. `--at` sets a timezone-aware observation time for replay. Extract a probe's individual context from the pilot’s `contexts.json`. `PASS` exits 0, inapplicable or insufficient evidence exits 1, and unusable input exits 2.

To run a trusted probe directly, use `tools/assumption_freshness.py run --context current.json --scope environment.json --input probe=/absolute/probe.mjs --output new-receipt.json -- /absolute/node /absolute/probe.mjs runtime`. Use extra `--input name=/path` entries for additional checked artifacts. The checker adds its own hash. The output path is exclusive and each invocation gets a new receipt. Out-of-band scope discovery and source authorization are caller responsibilities.

The pilot includes a still-unexpired historical PASS at the moment a newer Router check fails. When the route is restored, coverage remains withdrawn until a fresh execution replaces the current failed receipt. Expiry uses a controlled evaluation clock. The scope and model-version drift checks change the independent current context and leave the recorded observation untouched.
