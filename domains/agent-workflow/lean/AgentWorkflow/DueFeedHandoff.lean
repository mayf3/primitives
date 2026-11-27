import AgentWorkflow.Outbox

/-!
One original dispatch intent and its latency-only kick. Eligibility is a
projection of the authoritative activation, instance, assistance and time
facts. The caller must establish that the requested row is actually reached
on a successful page and that the recorded admission is durable. There is
no fairness theorem for an absent consumer, unreadable feed or stalled actor.
-/
namespace AgentWorkflow.DueFeedHandoff

/-- `UPDATE … RETURNING` supplies a provisional state. A lost confirmation
may be indistinguishable from rollback, so neither is logged as committed. -/
inductive SettlementReadback where
  | unconfirmed
  | rolledBack
  | committed (status : Outbox.Status)

inductive FailureReport where
  | retryScheduled
  | deadLettered
  deriving DecidableEq

def failureLog : SettlementReadback → Option FailureReport
  | .committed .pending => some .retryScheduled
  | .committed .deadLetter => some .deadLettered
  | _ => none

theorem dead_letter_log_requires_commit {seen : SettlementReadback}
    (logged : failureLog seen = some .deadLettered) :
    seen = .committed .deadLetter := by
  cases seen with
  | unconfirmed => contradiction
  | rolledBack => contradiction
  | committed status => cases status <;> simp_all [failureLog]

theorem committed_dead_letter_is_not_reported_as_retry :
    failureLog (.committed .deadLetter) ≠ some .retryScheduled := by decide

structure Identity where
  intent : Nat
  instanceId : Nat
  visit : Nat
  owner : Nat
  deriving DecidableEq, Repr

structure KickTarget where
  intent : Nat
  instanceId : Nat
  visit : Nat
  deriving DecidableEq, Repr

def kickTargetFor (id : Identity) : KickTarget := ⟨id.intent, id.instanceId, id.visit⟩

structure Acceptance where
  definition : Nat
  transition : Nat
  expectedVersion : Nat
  artifactDigest : Nat
  deriving DecidableEq, Repr

structure Receipt where
  identity : Identity
  definition : Nat
  transition : Nat
  newVersion : Nat
  artifactDigest : Nat
  committedEvent : Bool
  deriving DecidableEq, Repr

inductive Progress where
  | unclaimed
  | admitted (identity : Identity)
  | completed (receipt : Receipt)
  deriving DecidableEq, Repr

structure State where
  identity : Identity
  acceptance : Acceptance
  hasOpenDispatchActivation : Bool
  business : Bool
  cancelled : Bool
  archived : Bool
  assistanceOpen : Bool
  dueNow : Bool
  readinessPassed : Bool
  progress : Progress
  kickTarget : KickTarget
  kick : Outbox.Row
  deriving DecidableEq, Repr

def dueFeed (s : State) : Option Identity :=
  if s.hasOpenDispatchActivation && s.business && !s.cancelled && !s.archived &&
      !s.assistanceOpen && s.dueNow
  then some s.identity else none

/-- The runtime consumes the READY projection, not every row of the raw
due feed. The real readiness evaluator and authorized read are premises. -/
def readyFeed (s : State) : Option Identity :=
  if s.readinessPassed then dueFeed s else none

def matchesAcceptance (s : State) (r : Receipt) : Prop :=
  r.identity = s.identity ∧ r.definition = s.acceptance.definition ∧
    r.transition = s.acceptance.transition ∧ r.newVersion = s.acceptance.expectedVersion + 1 ∧
    r.artifactDigest = s.acceptance.artifactDigest ∧ r.committedEvent = true

instance (s : State) (r : Receipt) : Decidable (matchesAcceptance s r) := by
  unfold matchesAcceptance
  infer_instance

/-- A terminal transition closes the original activation; admission alone
does not. An admitted executable may finish even if future scans stop. The
`trusted` predicate is supplied by the actual business evidence authority. -/
inductive Step (consumer : Bool) (trusted : Receipt → Prop) : State → State → Prop where
  | idle (s : State) : Step consumer trusted s s
  | kick {s : State} {after : Outbox.Row} {command : Outbox.Command}
      (channel : s.kick.channel = .executionKick)
      (bound : s.kickTarget = kickTargetFor s.identity)
      (rowStep : Outbox.Step (fun _ => true) s.kick command after) :
      Step consumer trusted s { s with kick := after }
  | poll {s : State} {id : Identity}
      (running : consumer = true) (onPage : readyFeed s = some id)
      (first : s.progress = .unclaimed) :
      Step consumer trusted s { s with progress := .admitted id }
  | accept {s : State} {r : Receipt}
      (admitted : s.progress = .admitted s.identity)
      (authorized : trusted r) (ac : matchesAcceptance s r) :
      Step consumer trusted s { s with progress := .completed r, hasOpenDispatchActivation := false }

inductive Runs (consumer : Bool) (trusted : Receipt → Prop) : State → State → Prop where
  | refl (s : State) : Runs consumer trusted s s
  | next {s mid dest : State} : Step consumer trusted s mid →
      Runs consumer trusted mid dest → Runs consumer trusted s dest

theorem trace_preserves_original_binding {consumer : Bool} {trusted : Receipt → Prop}
    {s fin : State} (run : Runs consumer trusted s fin) :
    fin.identity = s.identity ∧ fin.acceptance = s.acceptance ∧ fin.kickTarget = s.kickTarget := by
  induction run with
  | refl => exact ⟨rfl, rfl, rfl⟩
  | next step _ ih => cases step <;> exact ih

theorem kick_dead_letter_preserves_due_and_identity {s : State} {after : Outbox.Row}
    {command : Outbox.Command}
    (bound : s.kickTarget = kickTargetFor s.identity)
    (dead : after.status = .deadLetter)
    (settled : Outbox.Step (fun _ => true) s.kick command after) :
    after.status = .deadLetter ∧ after.eventKey = s.kick.eventKey ∧
      dueFeed { s with kick := after } = dueFeed s ∧
      readyFeed { s with kick := after } = readyFeed s ∧
      ({ s with kick := after }).identity = s.identity ∧
      ({ s with kick := after }).progress = s.progress ∧
      ({ s with kick := after }).kickTarget = kickTargetFor s.identity := by
  exact ⟨dead, (Outbox.step_preserves_event_key settled).symm, rfl, rfl, rfl, rfl, bound⟩

theorem feed_identity {s : State} {id : Identity} (ready : readyFeed s = some id) :
    id = s.identity := by
  unfold readyFeed dueFeed at ready
  split at ready
  · split at ready
    · exact (Option.some.inj ready).symm
    · contradiction
  · contradiction

theorem disabled_unclaimed_stays_open {trusted : Receipt → Prop} {s fin : State}
    (run : Runs false trusted s fin) (first : s.progress = .unclaimed)
    (visible : readyFeed s = some s.identity) :
    fin.progress = .unclaimed ∧ readyFeed fin = some s.identity := by
  induction run with
  | refl => exact ⟨first, visible⟩
  | next step _ ih =>
      cases step with
      | idle => exact ih first visible
      | kick => exact ih first visible
      | poll running => cases running
      | accept admitted => simp_all

/-- Conditional two-step completion. A successful tick reaching the due row,
real admission and a trusted original AC witness must be realized by the
environment. The elapsed wall time or even availability is unbounded. -/
theorem periodic_path_can_complete_dead_lettered_intent {trusted : Receipt → Prop} {s : State}
    {r : Receipt} (ready : readyFeed s = some s.identity) (first : s.progress = .unclaimed)
    (dead : s.kick.status = .deadLetter) (bound : s.kickTarget = kickTargetFor s.identity)
    (authorized : trusted r) (ac : matchesAcceptance s r) :
    ∃ fin, Runs true trusted s fin ∧ fin.identity = s.identity ∧ fin.kick.status = .deadLetter ∧
      fin.kickTarget = kickTargetFor fin.identity ∧ fin.progress = .completed r ∧ dueFeed fin = none := by
  let admitted := { s with progress := .admitted s.identity }
  let fin := { admitted with progress := .completed r, hasOpenDispatchActivation := false }
  refine ⟨fin, ?_, rfl, dead, bound, rfl, ?_⟩
  · exact Runs.next (Step.poll rfl ready first)
      (Runs.next (Step.accept rfl authorized ac) (Runs.refl fin))
  · simp [fin, admitted, dueFeed]

theorem new_completion_requires_original_acceptance {consumer : Bool} {trusted : Receipt → Prop}
    {s fin : State} {r : Receipt} (transition : Step consumer trusted s fin)
    (notYet : s.progress ≠ .completed r) (observed : fin.progress = .completed r) :
    trusted r ∧ matchesAcceptance s r := by
  cases transition with
  | idle => exact False.elim (notYet observed)
  | kick => exact False.elim (notYet observed)
  | poll => contradiction
  | accept _ authority ac =>
      cases observed
      exact ⟨authority, ac⟩

private def original : Identity := ⟨41, 17, 2, 9⟩
private def state : State :=
  ⟨original, ⟨3, 8, 2, 55⟩, true, true, false, false, false, true, true,
    .unclaimed, kickTargetFor original, ⟨11, .executionKick, .claimed, some 5, 11⟩⟩

private def deadKick : Outbox.Row :=
  { state.kick with status := .deadLetter, claimant := none, attempts := 12 }

private def good : Receipt := ⟨original, 3, 8, 3, 55, true⟩

example : Outbox.Step (fun _ => true) state.kick (.unknown 5) deadKick :=
  Outbox.Step.unknownKickDeadLetter rfl rfl rfl rfl (by decide)

example : dueFeed { state with kick := deadKick } = some original := by decide
example : state.kickTarget ≠ kickTargetFor { original with intent := 22 } := by decide
example : readyFeed { state with kick := deadKick, readinessPassed := false } = none := by decide
example : dueFeed { state with kick := deadKick, assistanceOpen := true } = none := by decide
example : matchesAcceptance state good := by decide
example : ¬ matchesAcceptance state { good with identity.visit := 77 } := by decide
example : ¬ matchesAcceptance state { good with artifactDigest := 99 } := by decide

end AgentWorkflow.DueFeedHandoff
