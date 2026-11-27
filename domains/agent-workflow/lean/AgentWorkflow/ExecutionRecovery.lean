import Std

/-!
# Workflow execution recovery transition slice

A bounded abstract model of same-attempt recovery. The durable delivery-start
fence is a monotone latch. Node.js scheduling, filesystem durability, Router
behavior and service business transitions remain refinement obligations.
-/

namespace AgentWorkflow.ExecutionRecovery

inductive Phase where
  | planned
  | resolutionBlocked
  | deliveryStarted
  | outcomeUnknown
  | runDelivered
  | settled
  | needsReview
  deriving DecidableEq, Repr

structure Identity where
  nodeVisitId : Nat
  attemptId : Nat
  generation : Nat
  deriving DecidableEq, Repr

structure Attempt where
  identity : Identity
  phase : Phase
  deliveryStarted : Bool
  deriving DecidableEq, Repr

inductive Event where
  | blockResolution
  | beginDelivery
  | confirmDelivery
  | observeUnknown
  | rejectAfterStart
  | reconcileSettled
  | reconcileNeedsReview
  deriving DecidableEq, Repr

/-- All allowed transitions for one attempt. Recovery preserves identity and
can cross the delivery fence only from a blocked, not-yet-started state.
There is intentionally no transition out of UNKNOWN or terminal states. -/
inductive Step : Attempt → Event → Attempt → Prop where
  | blockResolution {a : Attempt}
      (phase : a.phase = .planned) :
      Step a .blockResolution { a with phase := .resolutionBlocked }
  | plannedBeginDelivery {a : Attempt}
      (phase : a.phase = .planned)
      (notStarted : a.deliveryStarted = false) :
      Step a .beginDelivery
        { a with phase := .deliveryStarted, deliveryStarted := true }
  | blockedRecoveryBeginDelivery {a : Attempt}
      (phase : a.phase = .resolutionBlocked)
      (notStarted : a.deliveryStarted = false) :
      Step a .beginDelivery
        { a with phase := .deliveryStarted, deliveryStarted := true }
  | confirmDelivery {a : Attempt}
      (phase : a.phase = .deliveryStarted)
      (started : a.deliveryStarted = true) :
      Step a .confirmDelivery { a with phase := .runDelivered }
  | observeUnknown {a : Attempt}
      (phase : a.phase = .deliveryStarted)
      (started : a.deliveryStarted = true) :
      Step a .observeUnknown { a with phase := .outcomeUnknown }
  | rejectAfterStart {a : Attempt}
      (phase : a.phase = .deliveryStarted)
      (started : a.deliveryStarted = true) :
      Step a .rejectAfterStart { a with phase := .needsReview }
  | reconcileSettled {a : Attempt}
      (phase : a.phase = .runDelivered) :
      Step a .reconcileSettled { a with phase := .settled }
  | reconcileNeedsReview {a : Attempt}
      (phase : a.phase = .runDelivered) :
      Step a .reconcileNeedsReview { a with phase := .needsReview }

/-- A modeled transition never changes NodeVisit/attempt/generation identity. -/
theorem step_preserves_identity {before after : Attempt} {event : Event}
    (step : Step before event after) :
    before.identity = after.identity := by
  cases step <;> rfl

/-- Every modeled delivery-start transition requires the fence to be clear. -/
theorem begin_delivery_requires_clear_fence {before after : Attempt}
    (step : Step before .beginDelivery after) :
    before.deliveryStarted = false := by
  cases step <;> simp_all

/-- UNKNOWN is not an automatic-recovery source: no transition leaves it. -/
theorem unknown_has_no_automatic_successor {before after : Attempt} {event : Event}
    (unknown : before.phase = .outcomeUnknown)
    (step : Step before event after) : False := by
  cases step <;> simp_all

/-- Settled and reviewed attempts are terminal in this model. -/
theorem terminal_has_no_successor {before after : Attempt} {event : Event}
    (terminal : before.phase = .settled ∨ before.phase = .needsReview)
    (step : Step before event after) : False := by
  cases step <;> simp_all

/-- Blocked recovery is same-attempt and crosses the fence exactly once. -/
theorem blocked_recovery_is_same_attempt {before after : Attempt}
    (step : Step before .beginDelivery after)
    (blocked : before.phase = .resolutionBlocked) :
    before.identity = after.identity ∧
      before.deliveryStarted = false ∧
      after.phase = .deliveryStarted := by
  cases step <;> simp_all

end AgentWorkflow.ExecutionRecovery
