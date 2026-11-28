// Isolated JSONL bridge to native Core entry points and persisted observations.
import { fork } from 'node:child_process'
import { once } from 'node:events'
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'node:fs'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createInterface } from 'node:readline'
import { ExecutionLedger } from '../../src/ledger.js'
import { createWorkflowExecutionEngine } from '../../src/engine.js'
import { TurnReconciliationStore } from '../../../agent-router/src/reconciliation/store.js'
import { AGENT, VISIT, T0, intent, identity, detail, delivered, advance } from './fixture.js'

const bytes = file => existsSync(file) ? readFileSync(file, 'utf8') : ''
const rows = raw => raw.split('\n').filter(Boolean).map(line => JSON.parse(line))
let fixture

async function makeFixture() {
  const dir = mkdtempSync(join(tmpdir(), 'batch4-core-sut-'))
  const ledgerFile = join(dir, 'attempts.jsonl')
  const persistenceFile = join(dir, 'router-reconciliation.json')
  const router = new TurnReconciliationStore({ runtimeEpoch: 'batch4-loopback-writer', persistenceFile })
  const transport = []
  let oldAttempt, resolved = true, loseAck = false, sawAcceptance
  const server = createServer(async (request, response) => {
    const json = (status, payload) => {
      response.writeHead(status, { 'content-type': 'application/json' })
      response.end(JSON.stringify(payload))
    }
    try {
      if (request.method === 'GET' && request.url === '/resolve') {
        return json(resolved ? 200 : 503, resolved ? { ok: true, agentId: AGENT } : { error: 'injected_resolution_503' })
      }
      if (request.method === 'GET' && request.url === '/detail') return json(200, detail(7).body)
      if (request.method !== 'POST' || request.url !== '/deliver') return json(404, { ok: false })
      let body = ''
      for await (const chunk of request) body += chunk
      const received = JSON.parse(body)
      let fence = false
      for (const event of rows(bytes(ledgerFile))) {
        if (event.kind === 'attempt_planned') fence = false
        if (event.kind === 'delivery_started') fence = true
      }
      const observation = { kind: 'router_post', requestId: received.requestId, fence, accepted: false,
        index: transport.filter(i => i.requestId === received.requestId).length + 1 }
      transport.push(observation)
      const handle = router.mintTurnExecution({ agentId: received.agentId, processGeneration: 1,
        sessionId: 'main', callerCorrelation: { requestId: received.requestId } })
      router.markAdmitted(handle, { eventWatermarkSeq: 0, promptRequestId: 'batch4-native-prompt',
        deadlineAtWallMs: Date.now() + 60000 })
      router.markPromptWriteAttempted(handle)
      router.markPromptReceipt(handle, { messageId: 'batch4-native-receipt' })
      observation.accepted = true
      sawAcceptance?.(router.resolveCallerCorrelation({ requestId: received.requestId }))
      if (!loseAck) json(200, { ok: true, sessionId: 'main', reconciliationHandle: handle, messageId: 'batch4-native-receipt' })
    } catch (error) {
      if (!response.headersSent) json(409, { ok: false, code: 'router_rejected', error: String(error.message) })
      else response.end()
    }
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const endpoint = `http://127.0.0.1:${server.address().port}`
  let now = Date.now
  const newLedger = () => new ExecutionLedger({ dir, maxAttemptsPerVisit: 3, clock: () => now() })
  let ledger = newLedger()
  function correlation(requestId) {
    // Reload exactly the persistent Router facts rather than the writer's memory.
    return new TurnReconciliationStore({ runtimeEpoch: 'batch4-loopback-reader', persistenceFile })
      .resolveCallerCorrelation({ requestId })
  }
  const post = async request => (await fetch(`${endpoint}/deliver`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request),
    signal: AbortSignal.timeout(5000),
  })).json()
  const engine = () => createWorkflowExecutionEngine({
    ledger, config: { automaticRecoveryEnabled: true, recoveryRetryDelayMs: 80, recoveryMaxDelayMs: 160 },
    fetchDuePage: async () => ({ ok: true, items: [] }),
    resolvePrincipalToAgent: async () => resolved ? { ok: true, agentId: AGENT } : { ok: false, code: 'http_503' },
    readInstanceDetail: async () => detail(7), deliverRun: post,
    resolveCallerCorrelation: query => correlation(query.requestId),
    getTurnReconciliation: () => ({ state: 'pending' }),
    log: {},
  })

  async function snapshot() {
    const attempts = await newLedger().snapshotFresh()
    const current = attempts.find(attempt => attempt.nodeVisitId === VISIT)
    return { attempts, ledgerBytes: bytes(ledgerFile), routerBytes: bytes(persistenceFile),
      routerRequests: structuredClone(transport), correlation: current ? correlation(current.attemptId) : null }
  }

  async function fault(mode) {
    // Same setup and actual crashing child as the Batch 2 restart witness.
    resolved = false
    await engine().reconcileOnce()
    // The preceding durable failed check schedules a bounded 80ms retry.
    resolved = true
    loseAck = mode === 'auto'
    const child = fork(new URL('./blocked-recovery-process.js', import.meta.url), [dir, endpoint, mode], {
      stdio: ['ignore', 'ignore', 'pipe', 'ipc'], env: { ...process.env, EKR_BLOCKED_RECOVERY_CHILD: '1' },
    })
    const exit = once(child, 'exit')
    let stderr = '', timer
    const stages = []
    child.stderr.on('data', chunk => { stderr += chunk })
    try {
      const boundary = await Promise.race([
        new Promise((resolve, reject) => {
          sawAcceptance = receipt => { if (loseAck) resolve({ receipt }) }
          child.on('message', message => {
            stages.push(message)
            if (message.stage === 'error') reject(new Error(JSON.stringify(message)))
            if (!loseAck && message.stage === 'crash-ready') resolve(message)
          })
        }),
        exit.then(result => { throw new Error(`crash child left boundary early: ${JSON.stringify(result)} ${stderr}`) }),
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('crash boundary was not reached')), 7000) }),
      ])
      child.kill('SIGKILL')
      const [code, signal] = await exit
      if (code !== null || signal !== 'SIGKILL') throw new Error('isolated child did not exit by SIGKILL')
      return { boundary, code, signal, stages }
    } finally {
      clearTimeout(timer)
      sawAcceptance = undefined
      loseAck = false
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL')
      await exit
    }
  }

  async function execute(command) {
    const before = await snapshot()
    const current = before.attempts[0]
    const input = { nodeVisitId: VISIT, ...identity(current) }
    let outcome, rejected, faultWitness
    try {
      switch (command.kind) {
        case 'blockResolution': outcome = await ledger.recordResolutionBlocked({ nodeVisitId: VISIT, code: 'http_503' }); break
        case 'beginDelivery': outcome = await ledger.recordDeliveryStarted({ nodeVisitId: VISIT }); break
        case 'confirmDelivery': {
          const requestId = current.attemptId
          const routerAck = await post({ requestId, agentId: AGENT })
          if (!routerAck.ok) throw new Error('loopback Router did not acknowledge the delivery')
          outcome = await ledger.recordRunDelivered({ nodeVisitId: VISIT, agentId: AGENT,
            requestId, sessionId: routerAck.sessionId, reconciliationHandle: routerAck.reconciliationHandle,
            messageId: routerAck.messageId, workflowStateVersionAtDispatch: 7 })
          break
        }
        case 'reconcileSettled':
        case 'reconcileNeedsReview':
        case 'staleGeneration': {
          const settlement = command.kind !== 'reconcileNeedsReview'
          outcome = await ledger.recordReconciled({ ...input,
            ...(command.kind === 'staleGeneration' ? identity(oldAttempt) : {}), expectedPhase: 'run_delivered',
            verdict: settlement ? 'SETTLED' : 'NEEDS_REVIEW',
            judgment: settlement ? 'business_commitment_observed' : 'run_ended_no_submission', reason: 'batch4 isolated fixture' })
          break
        }
        case 'restart': ledger = newLedger(); outcome = await ledger.snapshotFresh(); break
        case 'recoverBlocked':
        case 'recoverAfterStart': outcome = await engine().recoverAttempt({ nodeVisitId: VISIT, authorityRef: 'batch4-isolated:test' }); break
        case 'sigkillBeforeWal': faultWitness = await fault('crash-before-wal'); break
        case 'sigkillAfterWal': faultWitness = await fault('crash-after-wal'); break
        case 'sigkillAckLost': faultWitness = await fault('auto'); break
        case 'reconcileAfterStart': outcome = await engine().reconcileOnce(); break
        case 'queryOriginal': outcome = correlation(current.attemptId); break
        default: throw new Error('unsupported isolated command')
      }
    } catch (error) {
      rejected = String(error.message)
    }
    const after = await snapshot()
    const appendOnly = after.ledgerBytes.startsWith(before.ledgerBytes)
    const events = appendOnly ? rows(after.ledgerBytes.slice(before.ledgerBytes.length)) : []
    events.push(...after.routerRequests.slice(before.routerRequests.length))
    return { before, after, appendOnly, events, outcome, rejected, faultWitness }
  }

  return { execute, snapshot, async seed(profile) {
    if (profile === 'core-generation-two') {
      now = () => T0 // Same delivered timestamp in both generations, so it cannot substitute for identity.
      oldAttempt = await delivered(ledger)
      await advance(ledger, oldAttempt)
    } else await ledger.beginAttemptIfAbsent(intent())
    return snapshot()
  }, async close() {
    server.closeAllConnections()
    await new Promise(resolve => server.close(resolve))
    rmSync(dir, { recursive: true, force: true })
  } }
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity })
try {
  for await (const line of input) {
    const request = JSON.parse(line)
    try {
      let result
      switch (request.method) {
        case 'reset':
          if (fixture) await fixture.close()
          fixture = await makeFixture()
          result = await fixture.seed(request.params.profile)
          break
        case 'snapshot': result = await fixture.snapshot(); break
        case 'execute': result = await fixture.execute(request.params.command); break
        default: throw new Error('unknown Core fixture RPC method')
      }
      process.stdout.write(JSON.stringify({ id: request.id, result }) + '\n')
    } catch (error) {
      process.stdout.write(JSON.stringify({ id: request.id, error: String(error.message) }) + '\n')
    }
  }
} finally {
  if (fixture) await fixture.close()
}
