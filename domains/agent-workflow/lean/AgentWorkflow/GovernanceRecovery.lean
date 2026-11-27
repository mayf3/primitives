import AgentWorkflow.OriginalObligation

/-!
One authorized, durable technical recovery episode. The binding indexes every
transition; claiming physical work and returning to the original execution
are separate from recording duties, resolving a Case or accepting the business.
-/
namespace AgentWorkflow.GovernanceRecovery

open OriginalObligation (Original Visit)

inductive Blocker
  | technical
  | humanDecision
  deriving DecidableEq, Repr

structure Binding where
  original : Original
  visit : Visit
  caseId : Nat
  generation : Nat
  effectKey : Nat
  blocker : Blocker
  deriving DecidableEq, Repr

structure Repair where
  diagnosis : Nat
  author : Nat
  artifact : Nat
  deriving DecidableEq, Repr

structure Review where
  repair : Repair
  reviewer : Nat
  evidence : Nat
  deriving DecidableEq, Repr

inductive Recovery where
  | retryOriginalKey (operationKey : Nat) (target : Visit) (attempt : Nat)
  | readCommitted (operationKey : Nat) (commandReceipt : Nat)
  deriving DecidableEq, Repr

/-- Durable authorized registrations and observed admissions come from their
own repositories. Retry authority includes the live fence, current CAS and
a sound no-effect or original-key replay proof. A readback includes the
authoritative original command, payload and scope. -/
structure Authority where
  debugRegistered : Binding → Nat → Prop
  debugAdmitted : Binding → Nat → Prop
  diagnosisVerified : Binding → Nat → Nat → Prop
  repairRegistered : Binding → Nat → Prop
  repairAdmitted : Binding → Nat → Nat → Prop
  repairProduced : Binding → Repair → Prop
  repairVerified : Binding → Review → Prop
  adopted : Binding → Review → Prop
  resolvedWithDurableHandoff : Binding → Review → Prop
  safeOriginalRetry : Binding → Visit → Nat → Prop
  authorityReadback : Binding → Nat → Prop
  consumedHandoff : Binding → Review → Recovery → Prop

def sameCurrentDuty (b : Binding) (v : Visit) : Prop :=
  v.instanceId = b.original.instanceId ∧ v.intentId = b.visit.intentId ∧
    v.visitId = b.visit.visitId ∧ v.principal = b.visit.principal ∧ b.visit.version ≤ v.version

def recoverySupported (auth : Authority) (b : Binding) : Recovery → Prop
  | .retryOriginalKey key target attempt =>
      key = b.effectKey ∧ sameCurrentDuty b target ∧ auth.safeOriginalRetry b target attempt ∧
        (∀ receipt, ¬ auth.authorityReadback b receipt)
  | .readCommitted key receipt => key = b.effectKey ∧ auth.authorityReadback b receipt

inductive Phase
  | beforeRequest
  | debugQueued
  | debugging (consumer : Nat)
  | repairQueued (diagnosis : Nat)
  | repairing (diagnosis : Nat) (author : Nat)
  | awaitingReview (repair : Repair)
  | verified (review : Review)
  | awaitingRecovery (review : Review)
  | returned (review : Review) (route : Recovery)
  deriving DecidableEq, Repr

/-- A registered episode's durable identity is the index. Recognition of a
duplicate is the same idempotent episode, represented by a stuttering step. -/
inductive Step (auth : Authority) (b : Binding) : Phase → Phase → Prop where
  | wait (s : Phase) : Step auth b s s
  | register (actor : Nat) (technical : b.blocker = .technical)
      (bound : b.visit.instanceId = b.original.instanceId)
      (durable : auth.debugRegistered b actor) :
      Step auth b .beforeRequest .debugQueued
  | admitDebug (actor : Nat) (admitted : auth.debugAdmitted b actor) :
      Step auth b .debugQueued (.debugging actor)
  | diagnose {actor : Nat} (finding : Nat)
      (verified : auth.diagnosisVerified b actor finding)
      (nextDurable : auth.repairRegistered b finding) :
      Step auth b (.debugging actor) (.repairQueued finding)
  | admitRepair {finding : Nat} (actor : Nat) (admitted : auth.repairAdmitted b finding actor) :
      Step auth b (.repairQueued finding) (.repairing finding actor)
  | deliverRepair (r : Repair) (produced : auth.repairProduced b r) :
      Step auth b (.repairing r.diagnosis r.author) (.awaitingReview r)
  | verifyRepair (r : Review) (independent : r.repair.author ≠ r.reviewer)
      (verified : auth.repairVerified b r) :
      Step auth b (.awaitingReview r.repair) (.verified r)
  | resolve {r : Review} (adopted : auth.adopted b r)
      (handoff : auth.resolvedWithDurableHandoff b r) :
      Step auth b (.verified r) (.awaitingRecovery r)
  | returnToOriginal {r : Review} (route : Recovery)
      (safe : recoverySupported auth b route) (consumed : auth.consumedHandoff b r route) :
      Step auth b (.awaitingRecovery r) (.returned r route)

inductive Runs (auth : Authority) (b : Binding) : Phase → Phase → Prop where
  | refl (s : Phase) : Runs auth b s s
  | next {s m t : Phase} : Step auth b s m → Runs auth b m t → Runs auth b s t

/-- A successful repair never grants original business acceptance. The
caller must still use OriginalObligation and its authority for exit/AC. -/
def parentWhileHeld (b : Binding) : OriginalObligation.State :=
  ⟨b.original, .working b.visit .held⟩

theorem parent_held_is_open (b : Binding) :
    OriginalObligation.isOpen (parentWhileHeld b) ∧
      OriginalObligation.readyFeed (parentWhileHeld b) = none :=
  OriginalObligation.held_is_open_without_ready b.original b.visit

def evidence (auth : Authority) (b : Binding) : Phase → Prop
  | .beforeRequest => True
  | p =>
      (∃ actor, auth.debugRegistered b actor) ∧ b.blocker = .technical ∧
        b.visit.instanceId = b.original.instanceId ∧
        match p with
        | .verified r => r.repair.author ≠ r.reviewer ∧ auth.repairVerified b r
        | .awaitingRecovery r =>
            (r.repair.author ≠ r.reviewer ∧ auth.repairVerified b r) ∧
              auth.adopted b r ∧ auth.resolvedWithDurableHandoff b r
        | .returned r route =>
            (r.repair.author ≠ r.reviewer ∧ auth.repairVerified b r) ∧
              (auth.adopted b r ∧ auth.resolvedWithDurableHandoff b r) ∧
              recoverySupported auth b route ∧ auth.consumedHandoff b r route
        | _ => True

theorem step_preserves_evidence {auth : Authority} {b : Binding} {s t : Phase}
    (step : Step auth b s t) (prior : evidence auth b s) : evidence auth b t := by
  cases step with
  | wait => exact prior
  | register actor technical bound durable => exact ⟨⟨actor, durable⟩, technical, bound, True.intro⟩
  | admitDebug => exact prior
  | diagnose => exact prior
  | admitRepair => exact prior
  | deliverRepair => exact prior
  | verifyRepair _ independent verified => exact ⟨prior.1, prior.2.1, prior.2.2.1, independent, verified⟩
  | resolve adopted handoff =>
      exact ⟨prior.1, prior.2.1, prior.2.2.1, prior.2.2.2, adopted, handoff⟩
  | returnToOriginal _ safe consumed =>
      exact ⟨prior.1, prior.2.1, prior.2.2.1, prior.2.2.2.1, prior.2.2.2.2, safe, consumed⟩

theorem trace_preserves_evidence {auth : Authority} {b : Binding} {s t : Phase}
    (run : Runs auth b s t) (prior : evidence auth b s) :
    evidence auth b t := by
  induction run with
  | refl => exact prior
  | next step _ ih => exact ih (step_preserves_evidence step prior)

theorem queued_debug_has_durable_registration {auth : Authority} {b : Binding}
    (run : Runs auth b .beforeRequest .debugQueued) :
    ∃ actor, auth.debugRegistered b actor :=
  (trace_preserves_evidence run True.intro).1

theorem returning_requires_independent_review_and_authoritative_recovery
    {auth : Authority} {b : Binding} {r : Review} {route : Recovery}
    (run : Runs auth b .beforeRequest (.returned r route)) :
    r.repair.author ≠ r.reviewer ∧ auth.repairVerified b r ∧
      (auth.adopted b r ∧ auth.resolvedWithDurableHandoff b r) ∧
      recoverySupported auth b route ∧ auth.consumedHandoff b r route := by
  have seen := trace_preserves_evidence run True.intro
  exact ⟨seen.2.2.2.1.1, seen.2.2.2.1.2, seen.2.2.2.2⟩

theorem true_human_decision_cannot_enter_technical_queue {auth : Authority}
    {b : Binding} (human : b.blocker = .humanDecision) :
    ¬ Runs auth b .beforeRequest .debugQueued := by
  intro run
  have seen := trace_preserves_evidence run True.intro
  have technical : b.blocker = .technical := seen.2.1
  rw [human] at technical
  cases technical

theorem original_key_and_duty_preserved_on_retry {auth : Authority} {b : Binding}
    {r : Review} {key attempt : Nat} {target : Visit}
    (run : Runs auth b .beforeRequest (.returned r (.retryOriginalKey key target attempt))) :
    key = b.effectKey ∧ sameCurrentDuty b target ∧ auth.safeOriginalRetry b target attempt ∧
        (∀ receipt, ¬ auth.authorityReadback b receipt) :=
  (returning_requires_independent_review_and_authoritative_recovery run).2.2.2.1

theorem committed_receipt_blocks_new_attempt {auth : Authority} {b : Binding}
    {r : Review} {key attempt receipt : Nat} {target : Visit}
    (known : auth.authorityReadback b receipt) :
    ¬ Runs auth b .beforeRequest (.returned r (.retryOriginalKey key target attempt)) := by
  intro run
  exact (original_key_and_duty_preserved_on_retry run).2.2.2 receipt known

theorem unresolved_effect_cannot_return {auth : Authority} {b : Binding}
    {r : Review} {route : Recovery}
    (noRetry : ∀ target attempt, ¬ auth.safeOriginalRetry b target attempt)
    (noCommitted : ∀ receipt, ¬ auth.authorityReadback b receipt) :
    ¬ Runs auth b .beforeRequest (.returned r route) := by
  intro run
  have safe := (returning_requires_independent_review_and_authoritative_recovery run).2.2.2.1
  cases route with
  | retryOriginalKey _ target attempt => exact noRetry target attempt safe.2.2.1
  | readCommitted _ receipt => exact noCommitted receipt safe.2

private def binding : Binding :=
  ⟨⟨1, 23, 9, 12⟩, ⟨100, 23, 101, 3, 8⟩, 10, 1, 77, .technical⟩

private def review : Review := ⟨⟨21, 5, 45⟩, 7, 54⟩
private def target : Visit := { binding.visit with version := 11 }

private def fixture : Authority where
  debugRegistered := fun b actor => b = binding ∧ actor = 3
  debugAdmitted := fun b actor => b = binding ∧ actor = 4
  diagnosisVerified := fun b actor finding => b = binding ∧ actor = 4 ∧ finding = 21
  repairRegistered := fun b finding => b = binding ∧ finding = 21
  repairAdmitted := fun b finding actor => b = binding ∧ finding = 21 ∧ actor = 5
  repairProduced := fun b r => b = binding ∧ r = review.repair
  repairVerified := fun b r => b = binding ∧ r = review
  adopted := fun b r => b = binding ∧ r = review
  resolvedWithDurableHandoff := fun b r => b = binding ∧ r = review
  safeOriginalRetry := fun b v attempt => b = binding ∧ v = target ∧ attempt = 4
  authorityReadback := fun b receipt => b = binding ∧ receipt = 63
  consumedHandoff := fun b r _ => b = binding ∧ r = review

private def readyInFixture {readback : Binding → Nat → Prop} :
    Runs { fixture with authorityReadback := readback } binding
      .beforeRequest (.awaitingRecovery review) := by
  refine .next (.register 3 rfl rfl ⟨rfl, rfl⟩) ?_
  refine .next (.admitDebug 4 ⟨rfl, rfl⟩) ?_
  refine .next (.diagnose 21 ⟨rfl, rfl, rfl⟩ ⟨rfl, rfl⟩) ?_
  refine .next (.admitRepair 5 ⟨rfl, rfl, rfl⟩) ?_
  refine .next (.deliverRepair review.repair ⟨rfl, rfl⟩) ?_
  refine .next (.verifyRepair review (by decide) ⟨rfl, rfl⟩) ?_
  exact .next (.resolve ⟨rfl, rfl⟩ ⟨rfl, rfl⟩) (.refl _)

theorem append_step {auth : Authority} {b : Binding} {s t u : Phase}
    (run : Runs auth b s t) (step : Step auth b t u) : Runs auth b s u := by
  induction run with
  | refl => exact .next step (.refl _)
  | next first _ ih => exact .next first (ih step)

private def retryFixture : Authority :=
  { fixture with authorityReadback := fun _ _ => False }

example : Runs retryFixture binding .beforeRequest (.returned review (.retryOriginalKey 77 target 4)) :=
  append_step (readyInFixture (readback := fun _ _ => False))
    (.returnToOriginal _ ⟨rfl, ⟨rfl, rfl, rfl, rfl, by decide⟩,
      ⟨rfl, rfl, rfl⟩, fun _ absent => absent⟩ ⟨rfl, rfl⟩)

example : Runs fixture binding .beforeRequest (.returned review (.readCommitted 77 63)) :=
  append_step (readyInFixture (readback := fixture.authorityReadback))
    (.returnToOriginal _ ⟨rfl, ⟨rfl, rfl⟩⟩ ⟨rfl, rfl⟩)

example : ¬ Runs fixture binding .beforeRequest (.returned review (.retryOriginalKey 77 target 4)) :=
  committed_receipt_blocks_new_attempt (receipt := 63) ⟨rfl, rfl⟩

example : ¬ Runs retryFixture binding .beforeRequest (.returned review (.retryOriginalKey 88 target 4)) := by
  intro run
  exact (by decide : (88 : Nat) ≠ 77) (original_key_and_duty_preserved_on_retry run).1

example : ¬ Runs { fixture with repairVerified := fun _ _ => True } binding .beforeRequest
    (.returned { review with reviewer := review.repair.author } (.readCommitted 77 63)) := by
  intro run
  exact (returning_requires_independent_review_and_authoritative_recovery run).1 rfl

private def noEffectEvidence : Authority :=
  { fixture with
    safeOriginalRetry := fun _ _ _ => False
    authorityReadback := fun _ _ => False }

example : ¬ Runs noEffectEvidence binding .beforeRequest
    (.returned review (.retryOriginalKey 77 target 4)) :=
  unresolved_effect_cannot_return (fun _ _ absent => absent) (fun _ absent => absent)

example : ¬ Runs { fixture with consumedHandoff := fun _ _ _ => False } binding
    .beforeRequest (.returned review (.readCommitted 77 63)) := by
  intro run
  exact (returning_requires_independent_review_and_authoritative_recovery run).2.2.2.2

end AgentWorkflow.GovernanceRecovery
