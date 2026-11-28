# Evidence Graph Compiler v1 — Batch 1 implementation plan

Status: initial plan for PR #20. See [the implemented Batch 1 protocol and Workflow fixtures](EVIDENCE_GRAPH_COMPILER_V1.md) for the current surfaces and evidence.

## 1. Goal and boundary

Build a small offline Python-standard-library CLI that derives an evidence graph from annotations and receipts already owned by a consumer project. The graph is a generated index, never an editable authority or a second source of truth.

The compiler checks structural traceability and evidence freshness. It does not decide whether a natural-language requirement is correct, whether a model faithfully captures it, whether a Lean theorem is meaningful, or whether a product is accepted.

## 2. Existing capabilities to reuse

| Existing capability | Existing location | Compiler relationship |
|---|---|---|
| Primitive catalog IDs, local references and path/anchor validation | `tools/primitives.py` | Reuse its path-containment and structural-validation lessons; do not alter catalog semantics |
| Lean source inventory, theorem declaration inventory and axiom audit | `tools/verify_lean.py` | Consume its outputs/Lean annotations; do not duplicate Lean parsing or axiom auditing |
| Generic finite-trace refinement and snapshot-probe soundness | `meta/lean/PrimitiveCore/Refinement.lean` | Link theorem/model evidence to this existing generic core; do not add another refinement theory |
| Spec frontmatter, governance route and conformance record schemas | consumer copy of `agent-development-governance/.agents/schemas` and `.agents/protocol/MODEL_CODE_CONFORMANCE_V1.md` | Recognize IDs and receipt coordinates without copying governance rules into primitives |
| Project business states and transitions | consumer project | Keep all domain state machines in the consumer project |

## 3. Source convention (first version)

The compiler will discover declarations embedded in authoritative files and structured receipts. It will not require a central graph manifest.

Supported declarations:

- Markdown/HTML comments and source comments:
  - `@evidence-node ID kind=REQ|DEC|MODEL|STATE|TRANSITION|PROP|THM|LEAN|MAP|CODE|TEST|TRACE|ASSUMPTION|PROBE|ACCEPTANCE`
  - `@evidence-link FROM relation=... to=TARGET`
- JSON receipt files using `schema_version: evidence-receipt/v1`, with explicit `nodes` and `links` arrays.
- Node metadata may declare criticality, model/code/mapping/verifier revisions, timestamps, TTL, source coordinates and deferred reasons.

Every extracted node records its source file and content SHA-256. Every receipt records its own source hash. The compiler derives graph JSON and reports; it never rewrites the input files.

## 4. CLI and outputs

Commands:

```sh
python3 tools/evidence_graph.py build --project .
python3 tools/evidence_graph.py validate --project .
python3 tools/evidence_graph.py coverage --project .
python3 tools/evidence_graph.py stale --project .
```

Generated under `.evidence-graph/` by default:

- `evidence-graph.json`
- `coverage-report.json`
- `dangling-links.json`
- `stale-evidence.json`

All outputs include schema version, project root identity, git revision (when available), generation time, and source file hashes. Output is deterministic apart from explicitly recorded generation metadata.

## 5. Required validation

- duplicate IDs across source annotations and receipts;
- dangling references;
- critical REQ without MODEL and original ACCEPTANCE link;
- critical PROP without THM or explicit deferred reason;
- critical STATE/TRANSITION without MAP;
- MAP with missing file or missing declared symbol;
- theorem/receipt model revision mismatch;
- test/trace receipt code or model revision mismatch;
- expired probe TTL or changed environment scope hash;
- acceptance whose requirement reference is absent or whose Spec revision/hash no longer matches.

A missing revision is UNKNOWN/incomplete evidence, not a fresh PASS. Staleness is reported separately from structural invalidity.

## 6. Safety and implementation constraints

- Python standard library only; no graph database, web server or UI.
- Ignore VCS internals, virtual environments, dependency trees, generated graph output and binary files.
- Resolve all code coordinates under the project root; reject path traversal and symlink escapes.
- Never execute project code or shell commands as part of graph compilation. Git revision lookup is optional metadata only.
- Parse only declared annotation syntax and JSON receipts; do not guess IDs from arbitrary prose.
- Preserve all duplicate/conflicting declarations in diagnostics; never silently pick one.
- Write outputs atomically and do not overwrite source files.
- Nonzero exit for invalid graph; distinguish UNKNOWN/incomplete from PASS in reports.

## 7. Unit-test matrix

Use temporary project fixtures and unittest:

1. valid minimal graph builds and validates;
2. duplicate node ID is rejected;
3. dangling link is reported;
4. critical requirement without model/acceptance is uncovered;
5. critical property with deferred rationale is reported as deferred, not falsely proved;
6. missing code file or symbol invalidates MAP;
7. model revision mismatch marks theorem stale;
8. code/model revision mismatch marks test receipt stale;
9. expired probe and environment-scope mismatch mark assumption evidence stale;
10. acceptance with changed Spec hash/revision is stale;
11. path traversal/symlink escape is rejected;
12. malformed receipt and unsupported schema are rejected;
13. build output is derived and never ingested as an authoritative source on a second build.

## 8. Acceptance gate for Batch 1

Batch 1 is complete only when the CLI runs against at least one real consumer project without changing its source authorities, all unit tests and negative controls pass, the four output files are inspectable, and an independent reviewer can reproduce the result.

The Workflow acceptance uses Svc Wake, Svc Outbox and Core Recovery. The earlier personal-agent idea remains outside this change. A fixture run must clearly distinguish what is actually machine-checked from evidence merely declared by the project.

No Batch 2 work starts until this gate is met.
