// Runs from packages/workflow-execution/test/observation-cas in a scratch Core tree.
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { ExecutionLedger } from '../../src/ledger.js'
import { createWorkflowExecutionEngine } from '../../src/engine.js'
import { AGENT, detail, intent, VISIT } from './fixture.js'

const directory = mkdtempSync(join(tmpdir(), 'adapter-stop-revive-'))
let now = Date.UTC(2026, 8, 9, 2, 0, 0)
const clock = () => now
const observed = []
const deliveries = []
const record = (step, fields = {}) => observed.push({ step, ...fields })
const snapshot = async ledger => ({
  projection: await ledger.snapshotFresh(),
  native: readFileSync(ledger.eventsFile, 'utf8'),
})
let old, revived, releaseOld
try {
  const writer = new ExecutionLedger({ dir: directory, clock })
  const planned = await writer.beginAttemptIfAbsent(intent(), async () => ({
    kind: 'resolution_blocked', code: 'identity_resolution_unavailable',
  }))
  const original = planned.attempt
  assert.equal(original?.phase, 'resolution_blocked')
  now = Math.max(now, original.recoveryCheck?.nextCheckAtMs ?? 0) + 1
  record('seed', { state: await snapshot(writer) })
  let oldEntered
  const entered = new Promise(resolve => { oldEntered = resolve })
  const held = new Promise(resolve => { releaseOld = resolve })
  function engine(label, ledger, fetchDuePage, automaticRecoveryEnabled) {
    return createWorkflowExecutionEngine({ ledger, clock, fetchDuePage,
      config: { automaticRecoveryEnabled, recoveryRetryDelayMs: 80, recoveryMaxDelayMs: 160 },
      resolvePrincipalToAgent: async () => ({ ok: true, agentId: AGENT }),
      readInstanceDetail: async () => detail(7),
      resolveCallerCorrelation: () => ({ state: 'never_existed' }),
      getTurnReconciliation: async () => ({ state: 'pending' }),
      deliverRun: async request => {
        deliveries.push({ engine: label, requestId: request.requestId })
        return { ok: true, sessionId: 'main', reconciliationHandle: `turn:${request.requestId}` }
      },
      log: { log() {}, warn() {}, error(error) { record('engine-error', { label, error }) } },
    })
  }
  old = engine('old', writer, async () => {
    oldEntered()
    await held
    return { ok: true, items: [intent()] }
  }, false)
  old.kick()
  await entered
  record('old-poll-parked')
  let drained = false
  const stop = old.stop().then(() => { drained = true; record('old-drained') })
  const fresh = new ExecutionLedger({ dir: directory, clock })
  revived = engine('revived', fresh, async () => ({ ok: true, items: [] }), true)
  const recovery = await revived.reconcileOnce()
  record('revived-reconciled', { oldDrained: drained, recovery, state: await snapshot(fresh) })
  assert.equal(drained, false)
  releaseOld()
  await stop
  const afterDrain = await snapshot(fresh)
  assert.deepEqual(deliveries, [{ engine: 'revived', requestId: original.attemptId }])
  assert.equal(afterDrain.projection.length, 1)
  const [final] = afterDrain.projection
  assert.equal(final.attemptId, original.attemptId)
  assert.equal(final.generation, original.generation)
  assert.equal(final.phase, 'run_delivered')
  assert.equal(observed.filter(event => event.step === 'engine-error').length, 0)
  record('after-drain', { state: afterDrain })
  console.log(JSON.stringify({ status: 'PASS', observed, deliveries }))
} catch (error) {
  console.log(JSON.stringify({ status: 'FAIL', observed, deliveries, error: String(error) }))
  process.exitCode = 1
} finally {
  releaseOld?.()
  await Promise.all([old?.stop(), revived?.stop()])
  rmSync(directory, { recursive: true, force: true })
}
