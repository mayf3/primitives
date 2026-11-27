# Workflow Evidence Graph · Batch 1

The [model-centered development method](../MODEL_CENTERED_DEVELOPMENT.md), [refinement and assumption protocol](../MODEL_IMPLEMENTATION_CONFORMANCE.md), and consumer Specs retain authority. This compiler indexes declared relationships and checks exact bound evidence. It can validate a coordinate or withdraw stale evidence. The result is separate from a Lean execution, a refinement judgment, a current environment probe, or original product acceptance.

## Local and upstream inventory

Snapshot 2026-11-28 Asia/Shanghai. The primary worktrees were inspected before using isolated checkouts and pinned Git objects.

| Repository | Primary local ref and state | Fresh public main |
| --- | --- | --- |
| primitives | local main at 5be98da, clean. Compiler reused draft PR #20 at c67500b in an isolated branch. | `1456f5b39fe6f39d106d90504a75adab5422b45e` |
| agent-development-governance | governance/agent-multi-repo-six-pack-host-v1 at 8186595, 4 untracked entries and no tracked changes | `895d191f7e0c624abdd13e82c5428c45543fd88d` |
| svc-workflow | feat/zero-ops-2b-overnight at 330be4e, 6 untracked entries and no tracked changes | `c50ab2ac98decceaa26138a282c34dd92ede0ddc` |
| dsh-agent-core | docs/agent-delivery-resilience-v1 at 2d6c64455, 136 untracked entries and no tracked changes | `ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e` |

Reviewed latest Governance `.agents/protocol/MODEL_CODE_CONFORMANCE_V1.md`, current Development Grammar and Protocol V1, Conformance Record and Change Brief templates, and `tools/build_manifest.py`. Svc and Core still select locally adopted governance via their `.agents/governance.lock.json` and local handoffs. Svc uses 1.1.0 at `0595e7e8`, Core 2.0.0-rc.3 at `c1fad897`. Upstream PR #27 is merged. Neither fixture treats that merge as consumer adoption. Consumers retain their accepted Product, Architecture, Spec and scope restrictions.

| Capability | Existing authority or implementation | Gap and Batch 1 action |
| --- | --- | --- |
| Requirement ID / authority | Svc `SVC_WORKFLOW_EXECUTION_CONTROL_V3` and Visit Activation / PostgreSQL storage Specs. Core accepted PPR V2 / WEC V5. Exact file coordinates in each fixture. | Trace selected affected scope via existing IDs and original acceptance. Expose missing mappings. |
| Model ID / state / transition | Svc #142 `formal/wake/WakeReceipt.lean`, `WakeDurability.lean`. Shared `AgentWorkflow.Outbox` and `ExecutionRecovery`. | Retain original model ownership. Distinguish current main from proposed Wake and Outbox repairs. |
| Lean theorem / audit | Primitives exact-main CI 46080833058, #13 draft audit, and clean Wake #142 candidate audit. | Independently verify name, exact input hash, revision, successful commands and allowed axioms; declarations and successful audits have distinct statuses. |
| Code mapping | Svc Rust/SQL `src/store/postgres/outbox.rs`, `src/forum_sync.rs`, Wake repository modules. Core `packages/workflow-execution/src/{ledger,ledger-events,engine,projection}.js` and `recovery/automatic.js`. | Check actual file, declaration and bytes. Mapping verification does not establish behavior. |
| Refinement relation | `meta/lean/PrimitiveCore/Refinement.lean` supplies finite simulation and snapshot-probe lemmas. Core merged model-centered pilot conformance mapping locates WAL ordering and recovery. | Svc and Core implementation refinement unproved. Record the gap. |
| Structured trace / PBT | Core has native restart JSONL and raw TAP. Svc has PG isolation regressions, concurrency/order cases and historical failure logs. | Normalized closed-segment trace and model-versus-SUT property testing absent in scope. Native tests retain their bounded scope. |
| Assumption probe | Existing tests exercise isolated storage/process behavior. Governance records expected probe/validity semantics. | No fixture supplies current deployment probe evidence. Compiler checks existing typed time, TTL and environment scope bindings. |
| Evidence graph / CI | Primitives draft #20 CLI, registry validator and Lean audit; governance build manifest validates its own distribution. | Extend draft compiler and add independent CI fixture materialization, four report types and real mutation controls. |

Draft candidates retain their own exact scope. Svc #142 `a22a0180ebf0775d42f9e54f09eed33a2de9ed25` is unmerged. Svc #141 `6c19d318b7aa6f03ed7bbe8cfcc2b768f8c67da6` is unmerged. Primitives #13 `6a0386588c767aaa998ff7552ee7364451c73da0` is an unmerged draft. See [Wake](evidence-graph-fixtures/wake/README.md), [Outbox](evidence-graph-fixtures/outbox/README.md), and [Core](evidence-graph-fixtures/core/README.md) for exact input paths, source observations and affected coverage.

## Input and validation protocol

Use a line containing `@evidence-node {JSON}` or `@evidence-link {JSON}` in the relevant Markdown or source comment, or use adjacent `evidence-receipt/v1` JSON with `nodes` and `links` arrays. Existing documentation prose and test filenames do not create a pass. IDs are stable in the affected scope. Use the project's existing authority IDs and record their provenance. Namespacing the same ID in a second candidate track preserves both versions.

- A node records `id`, `kind`, optional `critical`, and a `coordinate` containing a project-relative `path`, optional declared `symbol` or `line`, and a version/hash pin. The compiler hashes observed bytes. Cross-repository fixtures materialize raw files into scratch from pinned Git objects and supply the derived `evidence-sources/v1` path/commit/hash map.
- A link records `from`, `to`, and `relation`. Required connections are inferred from node kinds. A Requirement links to its Model and original Acceptance. Properties link to named theorems, States/Transitions to implementation maps, and Assumptions to Probes. Acceptance binds explicit original `requirement_ids` and their precise source files.
- Evidence declares `evidence_state` as `PASS`, `FAIL`, or `UNKNOWN`, and `bindings` keyed by related authority ID with its exact `revision` and `sha256`. This metadata alone cannot verify a claim. Lean requires an actual named audit matching the cited declaration and source bytes. Generic execution records must attest successful execution and carry their own observed `evidence_bindings`. Test receipts require positive executed counts. Explicit `receipt_checks` are supplemental checks over JSON fields via dot paths or JSON Pointer. An unexecuted or unsupported raw evidence format remains UNKNOWN.
- A Probe must record `executed_at`, a valid `ttl_seconds` or `expires_at`, and the observed and expected environment scope. The runner's receipt must attest the same observation. An expired/mismatched probe withdraws its dependent coverage. This checks the scope provided by the project and does not measure the environment.
- The four derived JSON reports keep source hashes, target and evidence revisions, declaration/verification distinctions and reasons. An invalid coordinate, mismatched version, or failed original binding cannot silently be inherited. A missing materialization map or pinned input invalidates its dependent evidence.

## Run

```sh
python3 tools/evidence_graph.py build --project /path/to/project
python3 tools/evidence_graph.py validate --project /path/to/project
python3 tools/evidence_graph.py coverage --project /path/to/project
python3 tools/evidence_graph.py stale --project /path/to/project
python3 tools/evidence_graph_fixture_check.py --repositories /path/to/checkouts --output /path/to/new-report-directory
```

`build` and `coverage` produce inspectable data even for an incomplete project. `validate` exits 1 on structural errors, stale evidence or uncovered critical items. `stale` exits 1 when evidence invalidations exist. The fixture runner expects an incomplete validation for these real projects, while checking that current source tuples have no dangling/stale inputs and that qualifying proofs and the scoped Core execution still verify.

Fixtures are recipes for selected existing authorities, not replacements. The materializer reads exact Git blobs from the named local repositories and copies separately listed execution artifacts. It runs no consumer code and performs no network fetch. CI obtains the public pins, then calls the same runner. Output files and command receipts are uploaded under `evidence-graph-fixtures`.

The independent negative corpus changes one projected input at a time, leaving the compiler and original consumer repositories intact. It renames a real symbol, edits the accepted Spec text, weakens a same-name Lean theorem, deletes a real test, removes a regression receipt and changes the original Requirement link. The compiler must recognize each deliberate drift. Remaining acceptance and refinement gaps stay visible.

The compiler is an integrity check over supplied evidence within its trust boundary. It cannot prevent a writer able to replace the checker, input coordinates and independent receipts together. The existing independent exact-head review and CI authority still govern verifier and corpus changes. No adoption, deployment, or new release permission derives from graph coverage. Batch 2 remains separate.
