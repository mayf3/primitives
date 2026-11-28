import AgentWorkflow.ExecutionRecovery

/-!
Executable decision for the existing single-attempt transition relation.
The table export is an IO boundary. It does not decide whether native traces
are complete or whether a concrete effect took place.
-/

namespace AgentWorkflow.ExecutionRecovery.Decision

def stepResult (a : Attempt) : Event → Option Attempt
  | .blockResolution =>
      if a.phase = .planned then some { a with phase := .resolutionBlocked } else none
  | .beginDelivery =>
      if (a.phase = .planned ∨ a.phase = .resolutionBlocked) ∧ a.deliveryStarted = false then
        some { a with phase := .deliveryStarted, deliveryStarted := true }
      else none
  | .confirmDelivery =>
      if a.phase = .deliveryStarted ∧ a.deliveryStarted = true then
        some { a with phase := .runDelivered }
      else none
  | .observeUnknown =>
      if a.phase = .deliveryStarted ∧ a.deliveryStarted = true then
        some { a with phase := .outcomeUnknown }
      else none
  | .rejectAfterStart =>
      if a.phase = .deliveryStarted ∧ a.deliveryStarted = true then
        some { a with phase := .needsReview }
      else none
  | .reconcileSettled =>
      if a.phase = .runDelivered then some { a with phase := .settled } else none
  | .reconcileNeedsReview =>
      if a.phase = .runDelivered then some { a with phase := .needsReview } else none
  | .readOnlyRecheck =>
      if a.phase = .outcomeUnknown then some a else none
  | .recordHandoffMetadata =>
      if a.phase = .needsReview then some a else none

/-- The executable decision accepts precisely the constructors of the original Step relation. -/
theorem step_result_exact {a b : Attempt} {event : Event} :
    stepResult a event = some b ↔ Step a event b := by
  constructor
  · intro result
    cases a with
    | mk identity phase fence =>
      cases phase <;> cases fence <;> cases event <;>
        simp [stepResult] at result <;> subst b <;>
        first
        | exact Step.blockResolution rfl
        | exact Step.plannedBeginDelivery rfl rfl
        | exact Step.blockedRecoveryBeginDelivery rfl rfl
        | exact Step.confirmDelivery rfl rfl
        | exact Step.observeUnknown rfl rfl
        | exact Step.rejectAfterStart rfl rfl
        | exact Step.reconcileSettled rfl
        | exact Step.reconcileNeedsReview rfl
        | exact Step.readOnlyRecheck rfl
        | exact Step.recordHandoffMetadata rfl
  · intro step
    cases step <;> simp [stepResult, *]

def phases : List (String × Phase) :=
  [("planned", .planned), ("resolutionBlocked", .resolutionBlocked),
   ("deliveryStarted", .deliveryStarted), ("outcomeUnknown", .outcomeUnknown),
   ("runDelivered", .runDelivered), ("settled", .settled), ("needsReview", .needsReview)]

def events : List (String × Event) :=
  [("blockResolution", .blockResolution), ("beginDelivery", .beginDelivery),
   ("confirmDelivery", .confirmDelivery), ("observeUnknown", .observeUnknown),
   ("rejectAfterStart", .rejectAfterStart), ("reconcileSettled", .reconcileSettled),
   ("reconcileNeedsReview", .reconcileNeedsReview), ("readOnlyRecheck", .readOnlyRecheck),
   ("recordHandoffMetadata", .recordHandoffMetadata)]

def exportTable : IO Unit := do
  let stdout ← IO.getStdout
  for (phaseName, phase) in phases do
    for fence in [false, true] do
      for (eventName, event) in events do
        let attempt : Attempt := ⟨⟨0, 0, 1⟩, phase, fence⟩
        let source := s!"{phaseName}\t{fence}\t{eventName}"
        match stepResult attempt event with
        | none => stdout.putStrLn s!"{source}\t-\t-"
        | some next =>
          let target := (phases.find? (fun (_, candidate) => decide (candidate = next.phase))).map Prod.fst
          match target with
          | none => throw (IO.userError "unregistered target phase")
          | some name => stdout.putStrLn s!"{source}\t{name}\t{next.deliveryStarted}"

end AgentWorkflow.ExecutionRecovery.Decision

def main : IO Unit := AgentWorkflow.ExecutionRecovery.Decision.exportTable
