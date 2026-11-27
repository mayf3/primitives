import AgentWorkflow.DueFeedHandoff

/-!
One original obligation in a single workflow instance. Visit handoff and
original acceptance have different durable witnesses. The evidence authority
is a parameter: code must refine it using authoritative readbacks.
-/
namespace AgentWorkflow.OriginalObligation

structure Original where
  obligationId : Nat
  instanceId : Nat
  definitionVersion : Nat
  acceptanceId : Nat
  deriving DecidableEq, Repr

structure Visit where
  intentId : Nat
  instanceId : Nat
  visitId : Nat
  principal : Nat
  version : Nat
  deriving DecidableEq, Repr

inductive Visibility
  | ready
  | held
  | unavailable
  deriving DecidableEq, Repr

structure ExitReceipt where
  original : Original
  source : Visit
  event : Nat
  successor : Option Visit
  deriving DecidableEq, Repr

structure AcceptanceReceipt where
  original : Original
  terminalEvent : Nat
  evidence : Nat
  deriving DecidableEq, Repr

inductive Phase
  | working (visit : Visit) (visibility : Visibility)
  | awaitingAc (terminalEvent : Nat)
  | accepted (receipt : AcceptanceReceipt)
  deriving DecidableEq, Repr

structure State where
  original : Original
  phase : Phase
  deriving DecidableEq, Repr

structure Authority where
  committed : ExitReceipt → Prop
  successorDurable : Original → Visit → Prop
  acceptedAc : AcceptanceReceipt → Prop

def isOpen (s : State) : Prop :=
  match s.phase with
  | .working .. | .awaitingAc _ => True
  | .accepted _ => False

def readyFeed (s : State) : Option Visit :=
  match s.phase with
  | .working visit .ready => some visit
  | _ => none

/-- Identity and version checks retained even for an authoritative receipt. -/
def lawfulSuccessor (r : ExitReceipt) (next : Visit) : Prop :=
  r.successor = some next ∧ r.source.instanceId = r.original.instanceId ∧
    next.instanceId = r.original.instanceId ∧
    next.visitId ≠ r.source.visitId ∧ r.source.version < next.version

inductive Step (auth : Authority) : State → State → Prop where
  | idle (s : State) : Step auth s s
  | observe (q : Original) (v : Visit) (before after : Visibility) :
      Step auth ⟨q, .working v before⟩ ⟨q, .working v after⟩
  | follow {r : ExitReceipt} {next : Visit} (visibility : Visibility)
      (committed : auth.committed r)
      (lawful : lawfulSuccessor r next) (durable : auth.successorDurable r.original next) :
      Step auth ⟨r.original, .working r.source visibility⟩ ⟨r.original, .working next .unavailable⟩
  | stageFinal {r : ExitReceipt} (visibility : Visibility)
      (committed : auth.committed r) (sourceBound : r.source.instanceId = r.original.instanceId)
      (terminal : r.successor = none) :
      Step auth ⟨r.original, .working r.source visibility⟩ ⟨r.original, .awaitingAc r.event⟩
  | finish {r : AcceptanceReceipt} (accepted : auth.acceptedAc r) :
      Step auth ⟨r.original, .awaitingAc r.terminalEvent⟩ ⟨r.original, .accepted r⟩

inductive Runs (auth : Authority) : State → State → Prop where
  | refl (s : State) : Runs auth s s
  | next {s mid dest : State} : Step auth s mid →
      Runs auth mid dest → Runs auth s dest

theorem step_preserves_original {auth : Authority} {s t : State}
    (step : Step auth s t) : t.original = s.original := by
  cases step <;> rfl

theorem trace_preserves_original {auth : Authority} {s t : State}
    (run : Runs auth s t) : t.original = s.original := by
  induction run with
  | refl => rfl
  | next step _ ih => exact ih.trans (step_preserves_original step)

/-- A visibility update on the current visit cannot close the obligation. -/
theorem working_visibility_preserves_open (q : Original) (v : Visit)
    (before after : Visibility) :
    isOpen ⟨q, .working v before⟩ ↔ isOpen ⟨q, .working v after⟩ := by
  rfl

theorem held_is_open_without_ready (q : Original) (v : Visit) :
    isOpen ⟨q, .working v .held⟩ ∧ readyFeed ⟨q, .working v .held⟩ = none :=
  ⟨True.intro, rfl⟩

/-- Changing visits needs a receipt and a durable, exact successor. -/
theorem changed_visit_has_durable_successor {auth : Authority} {q q' : Original}
    {source next : Visit} {before after : Visibility}
    (step : Step auth ⟨q, .working source before⟩ ⟨q', .working next after⟩)
    (changed : next.visitId ≠ source.visitId) :
    q' = q ∧ after = .unavailable ∧
      ∃ r : ExitReceipt, r.original = q ∧ r.source = source ∧ auth.committed r ∧
        lawfulSuccessor r next ∧ auth.successorDurable q next := by
  cases step with
  | idle => exact False.elim (changed rfl)
  | observe => exact False.elim (changed rfl)
  | follow _ committed lawful durable => exact ⟨rfl, rfl, _, rfl, rfl, committed, lawful, durable⟩

theorem stage_final_keeps_open_with_receipt {auth : Authority} {q q' : Original}
    {source : Visit} {visibility : Visibility} {event : Nat}
    (step : Step auth ⟨q, .working source visibility⟩ ⟨q', .awaitingAc event⟩) :
    q' = q ∧ isOpen ⟨q', .awaitingAc event⟩ ∧
      ∃ r : ExitReceipt, r.original = q ∧ r.source = source ∧
        r.event = event ∧ r.source.instanceId = q.instanceId ∧
        r.successor = none ∧ auth.committed r := by
  cases step with
  | stageFinal _ committed sourceBound terminal =>
      exact ⟨rfl, True.intro, _, rfl, rfl, rfl, sourceBound, terminal, committed⟩

theorem new_acceptance_requires_matching_pending_event {auth : Authority} {s : State}
    {q : Original} {r : AcceptanceReceipt}
    (step : Step auth s ⟨q, .accepted r⟩) (openBefore : isOpen s) :
    s.phase = .awaitingAc r.terminalEvent ∧ s.original = r.original ∧
      q = r.original ∧ auth.acceptedAc r := by
  cases step with
  | idle => exact False.elim openBefore
  | finish accepted => exact ⟨rfl, rfl, rfl, accepted⟩

/-- Invariant for finite traces originating at a working visit. Once a
terminal event is staged, retain its precise authority through acceptance. -/
def hasFinalEvidence (auth : Authority) (s : State) : Prop :=
  match s.phase with
  | .working .. => True
  | .awaitingAc event =>
      ∃ r : ExitReceipt, r.original = s.original ∧ r.event = event ∧
        r.source.instanceId = s.original.instanceId ∧ r.successor = none ∧ auth.committed r
  | .accepted ac =>
      ac.original = s.original ∧ auth.acceptedAc ac ∧
        ∃ r : ExitReceipt, r.original = s.original ∧ r.event = ac.terminalEvent ∧
          r.source.instanceId = s.original.instanceId ∧ r.successor = none ∧ auth.committed r

theorem final_evidence_preserved {auth : Authority} {s t : State}
    (run : Runs auth s t) (evidence : hasFinalEvidence auth s) :
    hasFinalEvidence auth t := by
  induction run with
  | refl => exact evidence
  | next step _ ih =>
      apply ih
      cases step with
      | idle => exact evidence
      | observe => exact True.intro
      | follow => exact True.intro
      | stageFinal _ committed sourceBound terminal =>
          exact ⟨_, rfl, rfl, sourceBound, terminal, committed⟩
      | finish accepted => exact ⟨rfl, accepted, evidence⟩

theorem acceptance_from_working_has_original_ac_and_commit {auth : Authority}
    {q q' : Original} {first : Visit} {visibility : Visibility} {ac : AcceptanceReceipt}
    (run : Runs auth ⟨q, .working first visibility⟩ ⟨q', .accepted ac⟩) :
    q' = q ∧ ac.original = q ∧ auth.acceptedAc ac ∧
      ∃ r : ExitReceipt, r.original = q ∧ r.event = ac.terminalEvent ∧
        r.source.instanceId = q.instanceId ∧ r.successor = none ∧ auth.committed r := by
  have origin : q' = q := trace_preserves_original run
  have evidence := final_evidence_preserved run True.intro
  cases origin
  exact ⟨rfl, evidence⟩

theorem accepted_is_stable {auth : Authority} {s t : State} {ac : AcceptanceReceipt}
    (run : Runs auth s t) (accepted : s.phase = .accepted ac) :
    t = s := by
  induction run with
  | refl => rfl
  | next step _ ih =>
      cases step with
      | idle => exact ih accepted
      | observe => contradiction
      | follow => contradiction
      | stageFinal => contradiction
      | finish => contradiction

/-- The earlier model permits infinite idling even after actual admission.
An enabled consumer and a perpetually visible dead-lettered intent do not
give an execution/acceptance fairness premise. -/
theorem ready_dead_lettered_admission_can_idle_forever
    {s : DueFeedHandoff.State} (ready : DueFeedHandoff.readyFeed s = some s.identity)
    (dead : s.kick.status = .deadLetter) (admitted : s.progress = .admitted s.identity) :
    ∃ rho : Nat → DueFeedHandoff.State, rho 0 = s ∧
      ∀ n, DueFeedHandoff.Step true (fun _ => True) (rho n) (rho (n + 1)) ∧
        DueFeedHandoff.readyFeed (rho n) = some s.identity ∧
        (rho n).kick.status = .deadLetter ∧ (rho n).progress = .admitted s.identity := by
  exact ⟨fun _ => s, rfl, fun _ => ⟨DueFeedHandoff.Step.idle s, ready, dead, admitted⟩⟩

private def original : Original := ⟨41, 17, 3, 44⟩
private def first : Visit := ⟨10, 17, 11, 5, 2⟩
private def second : Visit := ⟨20, 17, 21, 6, 5⟩
private def exitFirst : ExitReceipt := ⟨original, first, 29, some second⟩
private def exitSecond : ExitReceipt := ⟨original, second, 33, none⟩
private def actualAc : AcceptanceReceipt := ⟨original, 33, 55⟩

private def fixture : Authority :=
  ⟨fun r => r = exitFirst ∨ r = exitSecond,
    fun q v => q = original ∧ v = second, fun ac => ac = actualAc⟩

example : Runs fixture ⟨original, .working first .ready⟩ ⟨original, .accepted actualAc⟩ := by
  refine .next (Step.follow (r := exitFirst) (next := second) .ready
    (Or.inl rfl) ⟨rfl, rfl, rfl, by decide, by decide⟩ ⟨rfl, rfl⟩) ?_
  exact .next (Step.stageFinal (r := exitSecond) .unavailable (Or.inr rfl) rfl rfl)
    (.next (Step.finish (r := actualAc) rfl) (.refl _))

example :
    ¬ Step { fixture with committed := fun _ => True, successorDurable := fun _ _ => True }
      ⟨original, .working first .ready⟩
      ⟨original, .working { second with instanceId := 99 } .unavailable⟩ := by
  intro step
  obtain ⟨_, _, r, origin, _, _, ⟨_, _, instanceId, _, _⟩, _⟩ :=
    changed_visit_has_durable_successor step (by decide)
  rw [origin] at instanceId
  exact (by decide : (99 : Nat) ≠ 17) instanceId

example :
    ¬ Step { fixture with committed := fun _ => True }
      ⟨original, .working { first with instanceId := 99 } .ready⟩
      ⟨original, .awaitingAc 33⟩ := by
  intro step
  obtain ⟨_, _, r, _, source, _, sourceBound, _, _⟩ := stage_final_keeps_open_with_receipt step
  rw [source] at sourceBound
  exact (by decide : (99 : Nat) ≠ 17) sourceBound

example :
    ¬ Step { fixture with successorDurable := fun _ _ => False }
      ⟨original, .working first .ready⟩ ⟨original, .working second .unavailable⟩ := by
  intro step
  obtain ⟨_, _, _, _, _, _, _, durable⟩ := changed_visit_has_durable_successor step (by decide)
  exact durable

example :
    ¬ Step { fixture with acceptedAc := fun _ => True }
      ⟨original, .awaitingAc 33⟩ ⟨original, .accepted { actualAc with terminalEvent := 29 }⟩ := by
  intro step
  have bound := new_acceptance_requires_matching_pending_event step True.intro
  exact (by decide : Phase.awaitingAc 33 ≠ .awaitingAc 29) bound.1

example :
    ¬ Step { fixture with acceptedAc := fun _ => True }
      ⟨original, .awaitingAc 33⟩
      ⟨original, .accepted { actualAc with original.acceptanceId := 99 }⟩ := by
  intro step
  have bound := new_acceptance_requires_matching_pending_event step True.intro
  exact (by decide : original ≠ { actualAc.original with acceptanceId := 99 }) bound.2.1

example :
    ¬ Step fixture ⟨original, .working first .ready⟩ ⟨original, .accepted actualAc⟩ := by
  intro step
  have bound := new_acceptance_requires_matching_pending_event step True.intro
  cases bound.1

example :
    ¬ Runs fixture ⟨original, .working first .ready⟩
      ⟨original, .accepted { actualAc with evidence := 99 }⟩ := by
  intro run
  have bound := acceptance_from_working_has_original_ac_and_commit run
  exact (by decide : { actualAc with evidence := 99 } ≠ actualAc) bound.2.2.1

example : readyFeed ⟨original, .working first .held⟩ =
    readyFeed ⟨original, .accepted actualAc⟩ ∧
    isOpen ⟨original, .working first .held⟩ ∧ ¬ isOpen ⟨original, .accepted actualAc⟩ :=
  ⟨rfl, True.intro, fun closed => closed⟩

end AgentWorkflow.OriginalObligation
