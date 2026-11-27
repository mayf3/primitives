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
  | unknown {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker) :
      Step enabled row (.unknown worker)
        { row with status := .pending, claimant := none, attempts := row.attempts + 1 }
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
  | unknown _ _ _ => cases dead
  | deadLetter _ channel _ _ => exact channel

/-- UNKNOWN returns to pending retry responsibility, never delivered. -/
theorem unknown_returns_to_pending {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.unknown worker) after) :
    after.status = .pending ∧ after.claimant = none := by
  cases step with
  | unknown _ _ _ => exact ⟨rfl, rfl⟩

/-- A claimed row cannot be claimed by a second worker before release. -/
theorem claimed_row_cannot_be_claimed_again {enabled : Channel → Bool}
    {row after : Row} {worker : Nat}
    (claimed : row.status = .claimed) :
    ¬ Step enabled row (.claim worker) after := by
  intro step
  cases step <;> simp_all

end AgentWorkflow.Outbox
