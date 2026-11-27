// Offline probe against a clean checkout of either pinned Core revision.
// Usage: node domains/agent-workflow/evidence/core-attempt-vs-business-acceptance.mjs /path/to/core
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

// The joint fixture commit only adds a test driver. The four probed modules
// and their dependencies are byte-identical to the public baseline.
const pinnedCommits = [
  'ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e',
  'edd359fb4583d91c1832ae0d89244e53224e8fa7',
]
assert.equal(process.argv.length, 3, 'Pass the path of the Core checkout as the only argument')
const core = resolve(process.argv[2])
const git = (...args) => execFileSync('git', ['-C', core, ...args], { encoding: 'utf8' }).trim()
const revision = git('rev-parse', 'HEAD')
assert.ok(pinnedCommits.includes(revision), 'Core checkout must match a pinned revision')
git('diff', '--quiet', 'HEAD', '--')

const coreModule = (name) => import(pathToFileURL(resolve(core, 'packages/workflow-execution/src', name)))
const { judgeAttempt, judgeSettleFromDetail } = await coreModule('judgment.js')
const { projectExecutionTrace } = await coreModule('projection.js')
const { projectBusinessResult } = await coreModule('business-result.js')

const workflowInstanceId = '11111111-1111-4111-8111-111111111111'
const nodeVisitId = '22222222-2222-4222-8222-222222222222'
const nextVisitId = '33333333-3333-4333-8333-333333333333'
const attempt = {
  workflowInstanceId,
  nodeVisitId,
  attemptId: '44444444-4444-4444-8444-444444444444',
  generation: 1,
  phase: 'run_delivered',
}
const observedInstance = { workflow_instance_id: workflowInstanceId, workflow_state_version: 2 }

const cases = [
  {
    name: 'full_moved_visit_no_exact_timeline',
    detail: {
      visibility: 'full',
      detail: { instance: { ...observedInstance, is_terminal: true }, current_node_visit_id: nextVisitId },
    },
    expected: {
      settle: 'settled', judgment: 'business_commitment_observed', runState: 'SETTLED',
      closure: 'SETTLED', visitLeft: true, gap: 'CURRENT_EVENT_UNAVAILABLE',
    },
  },
  {
    name: 'historical_visibility_nonterminal',
    detail: { visibility: 'historical_participant', detail: { instance: { is_terminal: false } } },
    expected: {
      settle: 'settled', judgment: 'business_commitment_observed', runState: 'SETTLED',
      closure: 'SETTLED', visitLeft: null, gap: 'DETAIL_UNAVAILABLE',
    },
  },
  {
    name: 'full_same_visit_no_submission',
    detail: {
      visibility: 'full',
      detail: { instance: { ...observedInstance, is_terminal: false }, current_node_visit_id: nodeVisitId },
    },
    expected: {
      settle: 'still_current', judgment: 'run_ended_no_submission', runState: 'RUN_ENDED_NO_TRANSITION',
      closure: 'UNRESOLVED', visitLeft: false, gap: 'CURRENT_EVENT_UNAVAILABLE',
    },
  },
]

for (const { name, detail, expected } of cases) {
  const settle = judgeSettleFromDetail({ body: detail, nodeVisitId })
  const verdict = judgeAttempt(attempt, { turnState: 'settled', settle })
  const trace = projectExecutionTrace([{ ...attempt, ...verdict }], { workflowInstanceId })
  const { execution: [run], businessOutcome } = projectBusinessResult({
    workflowInstanceId, detail, execution: trace.nodeVisits, timeline: [], timelineComplete: false,
  })
  assert.equal(settle.kind, expected.settle, name)
  assert.equal(verdict.judgment, expected.judgment, name)
  assert.equal(run.executionState, expected.runState, name)
  assert.equal(run.attemptClosure, expected.closure, name)
  assert.equal(run.visitLeft, expected.visitLeft, name)
  assert.equal(businessOutcome.state, 'UNKNOWN', name)
  assert.deepEqual(businessOutcome.acceptance, { state: 'UNPROVEN', evidence: null }, name)
  assert.ok(businessOutcome.gaps.includes(expected.gap), name)
  console.log(JSON.stringify({
    case: name, settle: settle.kind, judgment: verdict.judgment, execution: run.executionState,
    closure: run.attemptClosure, visitLeft: run.visitLeft, business: businessOutcome.state,
    acceptance: businessOutcome.acceptance.state, gaps: businessOutcome.gaps,
  }))
}
console.log(`PASS ${cases.length}/${cases.length} on Core ${revision}`)
