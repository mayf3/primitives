# Core Recovery fixture

This fixture indexes the affected same-attempt recovery slice of `mayf3/dsh-agent-core` main `ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e`. The owning authorities are PPR V2 and WEC V5. They are accepted implementation Specs with `production_apply_authority: none`. The accepted local governance lock still records the vendored `2.0.0-rc.3` distribution at `c1fad8976e50e96adb27a4c7e2dd4f97bf2e899e`. This fixture makes no adoption. The local source checkout was on `docs/agent-delivery-resilience-v1` with existing untracked artifacts. The test run used a clean detached checkout of the independently fetched public main.

The existing [Core recovery pilot](https://github.com/mayf3/dsh-agent-core/blob/ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e/docs/reports/MODEL_CENTERED_PILOT_WORKFLOW_RECOVERY_V1.md) supplies the manual mapping. Its older notation references the pre-report code snapshot and the merged PR #12 model. This fixture keeps the mapping separate and binds fresh evidence to the actual tested versions. In this snapshot the requested recovery projection lives at `packages/workflow-execution/src/projection.js`, not under `src/recovery/`. The five linked Contract IDs and original Acceptance anchors represent this selected slice. They do not cover all of PPR V2 or WEC V5.

| Evidence | Exact binding and scope |
| --- | --- |
| Lean kernel and audit | Public primitives main `1456f5b39fe6f39d106d90504a75adab5422b45e`, exact [CI run 46080833058](https://github.com/mayf3/primitives/actions/runs/46080833058). `lean-ci-all.json` is its downloaded native artifact. The audit contains the model source SHA and audited theorem declarations, with only permitted standard Lean axioms. The local 4.19.0 toolchain download timed out, so the fixture uses the exact-head CI artifact for kernel evidence. |
| Focused execution | `core-test-execution.json` binds 57/57 passing tests to the exact Core files and the comparison model. It records the command, environment scope, toolchain and hashes of the raw TAP and extracted native diagnostics. The Node tests did not execute the Lean model or compare each state. |
| Real-process observations | `core-restart-observations.jsonl` extracts the original B2 diagnostic documents from the TAP, decoding TAP escaping of `#` and backslashes. It retains process exits, durable attempts, write-ahead markers, delivery counts and Router state. There is no normalized or independently validated abstract trace, so the graph marks trace conformance UNKNOWN. |
| Remaining evidence | Initial correspondence and step simulation between the ledger and Lean model are unproved. The test scope includes process SIGKILL against a real ledger and loopback fixture. It leaves device power-loss durability, live Svc authority, production scheduler fairness and original Acceptance UNKNOWN. |

The execution command can be rerun in a clean, detached Core checkout of the exact revision above with Node 26.7.0. The tests use temporary storage, actual child processes and a loopback fixture. No live environment credentials are required.

```sh
scratch="$(mktemp -d)"
env -i PATH="$PATH" HOME="$scratch" TMPDIR="$scratch" \
  EKR_SOURCE_SHA=ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e \
  node --test --test-reporter=tap \
  packages/workflow-execution/test/recovery.test.js \
  packages/workflow-execution/test/observation-cas/blocked-recovery.test.js \
  packages/workflow-execution/test/observation-cas/blocked-recovery-restart.test.js \
  packages/workflow-execution/test/observation-cas/ledger-identity.test.js
```
