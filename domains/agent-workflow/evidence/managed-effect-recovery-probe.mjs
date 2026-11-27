// Offline characterization of the current gap. Uses real Core modules and
// temporary stores, with injected Svc responses and router exit facts.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { pathToFileURL } from 'node:url'

const revisions = [
  'ee4dbefb7f6a8d4726392ed5fa9590fb345b2c1e',
  'edd359fb4583d91c1832ae0d89244e53224e8fa7',
]
assert.equal(process.argv.length, 3, 'Pass the path to a fixed Core checkout')
const source = resolve(process.argv[2])
const git = (...args) => execFileSync('git', ['-C', source, ...args], { encoding: 'utf8' }).trim()
const revision = git('rev-parse', 'HEAD')
assert.ok(revisions.includes(revision), 'Core checkout must match a fixed revision')
git('diff', '--quiet', 'HEAD', '--')
const load = (file) => import(pathToFileURL(resolve(source, file)))
const { mountWorkflowExecutionRuntime } = await load('packages/production-runtime/src/workflow-execution-runtime.js')
const { TurnReconciliationStore } = await load('packages/agent-router/src/reconciliation/store.js')

const workflowInstanceId = '11111111-1111-4111-8111-111111111111'
const nodeVisitId = '22222222-2222-4222-8222-222222222222'
const dispatchIntentId = '33333333-3333-4333-8333-333333333333'
const ownerPrincipalId = '44444444-4444-4444-8444-444444444444'
const assignee = 'agt_repair'
const identity = { workflowInstanceId, nodeVisitId, dispatchIntentId, ownerPrincipalId }
const stamp = '2020-01-01T00:00:00Z'
const intents = [{ ...identity, readinessStatus: 'READY', nextEligibleAt: stamp, createdAt: stamp, updatedAt: stamp }]
const detail = { visibility: 'full', detail: {
  instance: { workflow_instance_id: workflowInstanceId, workflow_state_version: 3, is_terminal: false },
  current_node_visit_id: nodeVisitId, current_visit: { workflow_instance_id: workflowInstanceId,
    node_visit_id: nodeVisitId, assignee_principal_id: ownerPrincipalId },
} }
const log = { log() {}, warn() {}, error() {} }
const observed = new Map()

for (const [mode, effectState] of [
  ['restart_lost', 'UNKNOWN'], ['terminated_without_outcome', 'UNKNOWN'],
  ['restart_lost', 'SUCCEEDED'], ['terminated_without_outcome', 'SUCCEEDED'],
]) {
  const dir = await mkdtemp(join(tmpdir(), 'wfe-gov-test-'))
  try {
    let store = new TurnReconciliationStore({ runtimeEpoch: 'first', persistenceFile: join(dir, 'turns.json') })
    const handles = [], requests = [], calls = []
    const router = {
      async deliver(request) {
        requests.push(request.requestId)
        const handle = store.mintTurnExecution({ agentId: assignee, sessionId: 'main', processGeneration: handles.length + 1 })
        handles.push(handle)
        store.markAdmitted(handle, { eventWatermarkSeq: 1, promptRequestId: request.requestId })
        return { sessionId: 'main', reconciliationHandle: handle, messageId: `fixture-${handles.length}` }
      },
      getTurnReconciliation: (handle) => store.getTurnReconciliation(handle),
      resolveCallerCorrelation: (identity) => store.resolveCallerCorrelation(identity),
    }
    const gateway = { async execute({ capabilityId, operation }) {
      calls.push(`${capabilityId}.${operation}`)
      if (capabilityId === 'workflow_dispatch_intents' && operation === 'list_ready') return { ok: true, result: { items: intents } }
      if (capabilityId === 'workflow_instance_detail' && operation === 'read') return { ok: true, result: detail }
      if (capabilityId === 'workflow_owner_obligation' && operation === 'read') return {
        ok: true, result: { version: 1, workflowInstanceId, managedKind: 'INTAKE', state: 'ACTIVE',
          definitionVersionId: '55555555-5555-4555-8555-555555555555',
          caseId: '66666666-6666-4666-8666-666666666666', policyDigest: '0'.repeat(64),
          currentNode: { nodeVisitId, nodeDefinitionId: '77777777-7777-4777-8777-777777777777',
            workflowStateVersion: 3,
            operation: { slotKey: 'create-dependency',
              allowedOperations: [{ key: 'workflow.create_instance', version: 1, hash: '1'.repeat(64) }],
              targetDefinitionVersionId: '88888888-8888-4888-8888-888888888888', targetDefinitionDigest: '2'.repeat(64),
              effect: { state: effectState, effectId: '99999999-9999-4999-8999-999999999999',
                ...(effectState === 'SUCCEEDED' ? { commandId: '00000000-0000-4000-8000-000000000000',
                  requestDigest: '3'.repeat(64), result: { workflowInstanceId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' },
                  resultDigest: '4'.repeat(64) } : {}) } } } },
      }
      throw new Error(`unexpected gateway operation ${capabilityId}.${operation}`)
    } }
    const mount = () => mountWorkflowExecutionRuntime({
      ctx: { get: (name) => ({
        brokerGateway: gateway,
        agentPrincipalResolutionAccess: { handlers: { agent_resolve_principal: {
          resolve: async () => ({ ok: true, result: { principalId: ownerPrincipalId, agentId: assignee } }),
        } } },
        workflowAssistanceResumeEvidenceAccess: async () => {
          calls.push('owner_resume_evidence')
          return { ok: true, evidence: null }
        },
      })[name] },
      layout: { workflowExecutionDir: join(dir, 'workflow') }, router, log,
      config: { pollerAgentId: 'agt_poller', retryDelayMs: 200 },
    })
    const keepAlive = setTimeout(() => {}, 15000)
    try {
      const first = mount()
      assert.equal((await first.engine.pollOnce()).admissions[0].action, 'admitted')
      const prior = (await first.ledger.snapshotFresh())[0]
      const [handle] = handles
      if (mode === 'restart_lost') {
        // Inject the authority's old-epoch loss, not a claimed real child kill.
        store = new TurnReconciliationStore({ runtimeEpoch: 'restarted-without-old-router-store' })
      } else {
        store.markOutcomeUnknown(handle, { source: 'child_exit_without_parsed_outcome' })
        store.settleLate(handle, { lateOutcome: 'terminated_without_outcome', terminationEvidence: 'child_real_exit', exitObserved: true })
        store.markFenceCleared(handle)
        store = new TurnReconciliationStore({ runtimeEpoch: 'restarted-with-retained-router-store', persistenceFile: join(dir, 'turns.json') })
      }
      const initial = store.getTurnReconciliation(handle)
      const resumed = mount()
      calls.length = 0
      const classified = await resumed.engine.reconcileOnce()
      const classifiedAttempt = (await resumed.ledger.snapshotFresh())[0]
      const readbackAtClassification = classifiedAttempt.readback ?? null
      const callsAtClassification = calls.splice(0)
      await delay(220)
      const polls = [await resumed.engine.pollOnce(), await resumed.engine.pollOnce(), await resumed.engine.pollOnce()]
      const current = (await resumed.ledger.snapshotFresh())[0]
      const actions = polls.map(poll => poll.admissions.map(row => row.action)).flat()
      const result = { mode, effectState, routerState: initial.state, lateOutcome: initial.snapshot?.lateOutcome ?? null,
        sameVisit: current.nodeVisitId === prior.nodeVisitId, classifiedJudgment: classifiedAttempt.judgment,
        classifiedReconciliationReadbacks: classified.readbacks.length, readbackAtClassification,
        callsAtClassification, postClassificationGatewayCalls: calls, deliveries: requests.length,
        oldGeneration: prior.generation, latestGeneration: current.generation, actions }
      if (mode === 'restart_lost') {
        assert.equal(initial.state, 'restart_lost')
        assert.equal(classifiedAttempt.judgment, 'run_outcome_unknown')
        assert.equal(current.attemptId, prior.attemptId)
        assert.equal(requests.length, 1)
        assert.equal(readbackAtClassification, null)
        assert.ok(!callsAtClassification.includes('workflow_owner_obligation.read'))
        assert.ok(!calls.some(call => call.includes('effect') || call === 'owner_resume_evidence'))
        assert.ok(actions.every(action => action === 'already_attempted'))
      } else {
        assert.equal(initial.state, 'settled')
        assert.equal(initial.snapshot.lateOutcome, 'terminated_without_outcome')
        assert.equal(classifiedAttempt.judgment, 'run_ended_no_submission')
        assert.equal(current.generation, 2)
        assert.equal(requests.length, 2)
        assert.ok(actions.includes('admitted'))
      }
      assert.equal(result.sameVisit, true)
      assert.equal(classified.readbacks.length, 0)
      const { effectState: _effectState, ...projection } = result
      if (effectState === 'UNKNOWN') observed.set(mode, projection)
      else assert.deepEqual(projection, observed.get(mode), 'current behavior ignores exact effect state')
      console.log(JSON.stringify(result))
    } finally { clearTimeout(keepAlive) }
  } finally { await rm(dir, { force: true, recursive: true }) }
}
console.log("Characterization PASS 4/4 on Core", revision, "- no business writes invoked")
