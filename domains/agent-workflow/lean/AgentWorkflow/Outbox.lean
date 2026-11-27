import Std

/-!
# Durable outbox row transition slice

A per-row abstraction of the accepted three-channel outbox contract. It
captures channel enablement, exclusive claim ownership, settlement, retry /
UNKNOWN and kick-only dead-letter. SQL isolation, PostgreSQL lock scheduling,
HTTP and global per-instance forum ordering remain refinement obligations.
-/

namespace AgentWorkflow.Outbox

inductive Channel where
  | executionKick
  | forumEvent
  | ownerAssistanceWake
  deriving DecidableEq, Repr

inductive Status where
  | pending
  | claimed
  | delivered
  | deadLetter
  deriving DecidableEq, Repr

structure Row where
  eventKey : Nat
  channel : Channel
  status : Status
  claimant : Option Nat
  attempts : Nat
  deriving DecidableEq, Repr

def executionKickMaxAttempts : Nat := 12

inductive Command where
  | claim (worker : Nat)
  | settle (worker : Nat)
  | retry (worker : Nat)
  | unknown (worker : Nat)
  | deadLetter (worker : Nat)
  deriving DecidableEq, Repr

/-- Per-row transition relation parameterized by the channel gate. -/
inductive Step (enabled : Channel → Bool) : Row → Command → Row → Prop where
  | claim {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (pending : row.status = .pending)
      (unclaimed : row.claimant = none) :
      Step enabled row (.claim worker)
        { row with status := .claimed, claimant := some worker }
  | settle {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker) :
      Step enabled row (.settle worker)
        { row with status := .delivered, claimant := none }
  | retry {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker) :
      Step enabled row (.retry worker)
        { row with status := .pending, claimant := none, attempts := row.attempts + 1 }
  | unknownRetry {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker)
      (belowKickCap : row.channel = .executionKick → row.attempts + 1 < executionKickMaxAttempts) :
      Step enabled row (.unknown worker)
        { row with status := .pending, claimant := none, attempts := row.attempts + 1 }
  | unknownKickDeadLetter {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (channel : row.channel = .executionKick)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker)
      (atCap : executionKickMaxAttempts ≤ row.attempts + 1) :
      Step enabled row (.unknown worker)
        { row with status := .deadLetter, claimant := none, attempts := row.attempts + 1 }
  | deadLetter {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (channel : row.channel = .executionKick)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker) :
      Step enabled row (.deadLetter worker)
        { row with status := .deadLetter, claimant := none, attempts := row.attempts + 1 }

/-- Delivery identity is immutable across every row transition. -/
theorem step_preserves_event_key {enabled : Channel → Bool}
    {before after : Row} {command : Command}
    (step : Step enabled before command after) :
    before.eventKey = after.eventKey := by
  cases step <;> rfl

/-- A disabled channel has no transition at all. -/
theorem disabled_channel_has_no_transition {enabled : Channel → Bool}
    {row after : Row} {command : Command}
    (disabled : enabled row.channel = false) :
    ¬ Step enabled row command after := by
  intro step
  cases step <;> simp_all

/-- A row can enter dead-letter only when its kind is EXECUTION_KICK. -/
theorem dead_letter_is_kick_only {enabled : Channel → Bool}
    {before after : Row} {command : Command}
    (step : Step enabled before command after)
    (dead : after.status = .deadLetter) :
    before.channel = .executionKick := by
  cases step with
  | claim _ _ _ => cases dead
  | settle _ _ _ => cases dead
  | retry _ _ _ => cases dead
  | unknownRetry _ _ _ _ => cases dead
  | unknownKickDeadLetter _ channel _ _ _ => exact channel
  | deadLetter _ channel _ _ => exact channel

/-- UNKNOWN is never treated as a successful delivery. Below the kick cap
it returns to pending; at the kick cap it is durably dead-lettered. -/
theorem unknown_not_delivered {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.unknown worker) after) :
    after.status ≠ .delivered := by
  cases step <;> simp_all

/-- A Forum / Owner-Wake UNKNOWN, or a kick UNKNOWN below its cap, returns
to pending retry responsibility. -/
theorem unknown_below_cap_returns_to_pending {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.unknown worker) after)
    (belowKickCap : before.channel = .executionKick →
      before.attempts + 1 < executionKickMaxAttempts) :
    after.status = .pending ∧ after.claimant = none := by
  cases step with
  | unknownRetry _ _ _ _ => exact ⟨rfl, rfl⟩
  | unknownKickDeadLetter _ _ _ _ atCap =>
      exact False.elim (Nat.not_lt_of_ge atCap (belowKickCap rfl))
  | _ => contradiction

/-- At the retry cap, a kick UNKNOWN becomes dead-lettered rather than
remaining in the due queue. -/
theorem kick_unknown_at_cap_dead_letters {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.unknown worker) after)
    (isKick : before.channel = .executionKick)
    (atCap : executionKickMaxAttempts ≤ before.attempts + 1) :
    after.status = .deadLetter := by
  cases step with
  | unknownRetry _ _ _ below =>
      exact False.elim (Nat.not_lt_of_ge atCap (below isKick))
  | unknownKickDeadLetter _ _ _ _ _ => rfl
  | _ => contradiction

/-- A claimed row cannot be claimed by a second worker before release. -/
theorem claimed_row_cannot_be_claimed_again {enabled : Channel → Bool}
    {row after : Row} {worker : Nat}
    (claimed : row.status = .claimed) :
    ¬ Step enabled row (.claim worker) after := by
  intro step
  cases step <;> simp_all

end AgentWorkflow.Outbox
