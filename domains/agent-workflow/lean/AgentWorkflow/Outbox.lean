import Std

/-!
# Durable outbox row transition slice

A per-row abstraction of the accepted three-channel outbox contract. It
captures channel enablement, exclusive claim ownership, settlement, retry /
UNKNOWN and kick-only dead-letter. SQL isolation, PostgreSQL lock scheduling,
HTTP and global per-instance forum ordering remain refinement obligations.
Ordinary retry and UNKNOWN both enforce the kick cap. Traces below contain
only automatic row transitions: authorized operator requeue and transaction
rollback are separate implementation boundaries, not silent automatic resets.
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
      (owner : row.claimant = some worker)
      (belowKickCap : row.channel = .executionKick → row.attempts + 1 < executionKickMaxAttempts) :
      Step enabled row (.retry worker)
        { row with status := .pending, claimant := none, attempts := row.attempts + 1 }
  | retryKickDeadLetter {row : Row} {worker : Nat}
      (channelEnabled : enabled row.channel = true)
      (channel : row.channel = .executionKick)
      (claimed : row.status = .claimed)
      (owner : row.claimant = some worker)
      (atCap : executionKickMaxAttempts ≤ row.attempts + 1) :
      Step enabled row (.retry worker)
        { row with status := .deadLetter, claimant := none, attempts := row.attempts + 1 }
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
  | retry _ _ _ _ => cases dead
  | retryKickDeadLetter _ channel _ _ _ => exact channel
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
  | unknownKickDeadLetter _ isKick _ _ atCap =>
      exact False.elim (Nat.not_lt_of_ge atCap (belowKickCap isKick))
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

/-- Ordinary retry has the same kick budget as UNKNOWN. Durable channels
retain pending responsibility regardless of their failure count. -/
theorem retry_below_cap_returns_to_pending {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.retry worker) after)
    (belowKickCap : before.channel = .executionKick →
      before.attempts + 1 < executionKickMaxAttempts) :
    after.status = .pending ∧ after.claimant = none := by
  cases step with
  | retry _ _ _ _ => exact ⟨rfl, rfl⟩
  | retryKickDeadLetter _ isKick _ _ atCap =>
      exact False.elim (Nat.not_lt_of_ge atCap (belowKickCap isKick))
  | _ => contradiction

/-- The twelfth or later retryable kick failure cannot return to pending. -/
theorem kick_retry_at_cap_dead_letters {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.retry worker) after)
    (isKick : before.channel = .executionKick)
    (atCap : executionKickMaxAttempts ≤ before.attempts + 1) :
    after.status = .deadLetter ∧ after.claimant = none := by
  cases step with
  | retry _ _ _ below =>
      exact False.elim (Nat.not_lt_of_ge atCap (below isKick))
  | retryKickDeadLetter _ _ _ _ _ => exact ⟨rfl, rfl⟩
  | _ => contradiction

/-- Neither ordinary retry branch records a successful delivery. -/
theorem retry_not_delivered {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.retry worker) after) :
    after.status ≠ .delivered := by
  cases step <;> simp_all

/-- Every ordinary retry consumes exactly one recorded failure. -/
theorem retry_increments_attempts_once {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.retry worker) after) :
    after.attempts = before.attempts + 1 := by
  cases step <;> rfl

/-- No transition changes the row's channel. -/
theorem step_preserves_channel {enabled : Channel → Bool}
    {before after : Row} {command : Command}
    (step : Step enabled before command after) :
    before.channel = after.channel := by
  cases step <;> rfl

/-- Every permitted dead-letter is kick-only; there is no cap-based or
permanent-rejection dead-letter path for the two durable channels. -/
theorem durable_channel_never_dead_letters {enabled : Channel → Bool}
    {before after : Row} {command : Command}
    (step : Step enabled before command after)
    (durable : before.channel ≠ .executionKick) :
    after.status ≠ .deadLetter := by
  intro dead
  exact durable (dead_letter_is_kick_only step dead)

/-- The automatic reconciler cannot restart a terminal row. Authorized
operator requeue, which resets attempts, is deliberately outside Step. -/
theorem terminal_has_no_automatic_transition {enabled : Channel → Bool}
    {before after : Row} {command : Command}
    (terminal : before.status = .delivered ∨ before.status = .deadLetter) :
    ¬ Step enabled before command after := by
  intro step
  cases step <;> rcases terminal with terminal | terminal <;> simp_all

/-- The cap is not achieved by disabling all retries: an enabled owner of
a claimed row always has an ordinary retry successor, including at the cap. -/
theorem retry_has_successor {enabled : Channel → Bool}
    {row : Row} {worker : Nat}
    (channelEnabled : enabled row.channel = true)
    (claimed : row.status = .claimed)
    (owner : row.claimant = some worker) :
    ∃ after, Step enabled row (.retry worker) after := by
  by_cases isKick : row.channel = .executionKick
  · by_cases atCap : executionKickMaxAttempts ≤ row.attempts + 1
    · exact ⟨_, Step.retryKickDeadLetter channelEnabled isKick claimed owner atCap⟩
    · exact ⟨_, Step.retry channelEnabled claimed owner
        (fun _ => Nat.lt_of_not_ge atCap)⟩
  · exact ⟨_, Step.retry channelEnabled claimed owner
      (fun h => False.elim (isKick h))⟩

/-- Failure count is bounded for kicks, and a live kick is strictly below
the cap. This invariant is conditional on a well-formed initial row. -/
def KickBounded (row : Row) : Prop :=
  row.channel = .executionKick →
    row.attempts ≤ executionKickMaxAttempts ∧
      ((row.status = .pending ∨ row.status = .claimed) →
        row.attempts < executionKickMaxAttempts)

/-- The normal initial row has not consumed any failure budget. -/
def initialRow (eventKey : Nat) (channel : Channel) : Row :=
  ⟨eventKey, channel, .pending, none, 0⟩

/-- Every channel's fresh row satisfies the kick-only invariant. -/
theorem initial_row_kick_bounded (eventKey : Nat) (channel : Channel) :
    KickBounded (initialRow eventKey channel) := by
  intro _
  constructor
  · exact Nat.zero_le _
  · intro _
    change 0 < 12
    decide

/-- Claim preserves the remaining budget, either failure path consumes one,
and terminal outcomes cannot reopen the remaining budget. -/
theorem step_preserves_kick_bound {enabled : Channel → Bool}
    {before after : Row} {command : Command}
    (step : Step enabled before command after)
    (bounded : KickBounded before) :
    KickBounded after := by
  cases step with
  | claim _ pending _ =>
      intro isKick
      obtain ⟨count, live⟩ := bounded isKick
      exact ⟨count, fun _ => live (Or.inl pending)⟩
  | settle _ _ _ =>
      intro isKick
      exact ⟨(bounded isKick).1, by simp⟩
  | retry _ _ _ below =>
      intro isKick
      exact ⟨Nat.le_of_lt (below isKick), fun _ => below isKick⟩
  | retryKickDeadLetter _ _ claimed _ _ =>
      intro isKick
      exact ⟨Nat.succ_le_of_lt ((bounded isKick).2 (Or.inr claimed)), by simp⟩
  | unknownRetry _ _ _ below =>
      intro isKick
      exact ⟨Nat.le_of_lt (below isKick), fun _ => below isKick⟩
  | unknownKickDeadLetter _ _ claimed _ _ =>
      intro isKick
      exact ⟨Nat.succ_le_of_lt ((bounded isKick).2 (Or.inr claimed)), by simp⟩
  | deadLetter _ _ claimed _ =>
      intro isKick
      exact ⟨Nat.succ_le_of_lt ((bounded isKick).2 (Or.inr claimed)), by simp⟩

/-- Any finite sequence of automatic transitions; length is unbounded. -/
inductive Trace (enabled : Channel → Bool) : Row → List Command → Row → Prop where
  | nil {row : Row} : Trace enabled row [] row
  | cons {before middle after : Row} {command : Command} {rest : List Command}
      (step : Step enabled before command middle)
      (tail : Trace enabled middle rest after) :
      Trace enabled before (command :: rest) after

/-- Inductive, arbitrary-length preservation, not bounded enumeration. -/
theorem trace_preserves_kick_bound {enabled : Channel → Bool}
    {before after : Row} {commands : List Command}
    (trace : Trace enabled before commands after)
    (bounded : KickBounded before) :
    KickBounded after := by
  induction trace with
  | nil => exact bounded
  | cons step _ ih => exact ih (step_preserves_kick_bound step bounded)

/-- Channel identity is invariant over the same finite trace. -/
theorem trace_preserves_channel {enabled : Channel → Bool}
    {before after : Row} {commands : List Command}
    (trace : Trace enabled before commands after) :
    before.channel = after.channel := by
  induction trace with
  | nil => rfl
  | cons step _ ih => exact (step_preserves_channel step).trans ih

/-- A fresh kick's failure counter never exceeds twelve on an automatic
trace; an active pending/claimed row is always strictly below twelve. -/
theorem reachable_kick_respects_cap {enabled : Channel → Bool}
    {eventKey : Nat} {after : Row} {commands : List Command}
    (trace : Trace enabled (initialRow eventKey .executionKick) commands after) :
    after.attempts ≤ executionKickMaxAttempts ∧
      ((after.status = .pending ∨ after.status = .claimed) →
        after.attempts < executionKickMaxAttempts) := by
  have bounded := trace_preserves_kick_bound trace (initial_row_kick_bounded _ _)
  exact bounded (trace_preserves_channel trace).symm

/-- Delivery identity remains stable across any finite automatic trace. -/
theorem trace_preserves_event_key {enabled : Channel → Bool}
    {before after : Row} {commands : List Command}
    (trace : Trace enabled before commands after) :
    before.eventKey = after.eventKey := by
  induction trace with
  | nil => rfl
  | cons step _ ih => exact (step_preserves_event_key step).trans ih

/-- Nonempty normal delivery remains possible. -/
theorem fresh_kick_can_deliver :
    Trace (fun _ => true) (initialRow 7 .executionKick) [.claim 3, .settle 3]
      ⟨7, .executionKick, .delivered, none, 0⟩ := by
  exact Trace.cons (Step.claim rfl rfl rfl)
    (Trace.cons (Step.settle rfl rfl rfl) Trace.nil)

/-- The original 11→12 pending counterexample is now a dead-letter path. -/
theorem twelfth_retry_dead_letter_positive_control :
    Step (fun _ => true) ⟨7, .executionKick, .claimed, some 3, 11⟩ (.retry 3)
      ⟨7, .executionKick, .deadLetter, none, 12⟩ := by
  exact Step.retryKickDeadLetter rfl rfl rfl rfl (by decide)

/-- The last below-cap ordinary retry is still a real permitted step. -/
theorem eleventh_retry_pending_positive_control :
    Step (fun _ => true) ⟨7, .executionKick, .claimed, some 3, 10⟩ (.retry 3)
      ⟨7, .executionKick, .pending, none, 11⟩ := by
  exact Step.retry rfl rfl rfl (by decide)

/-- High failure counts do not silently discard durable Forum work. -/
theorem forum_retry_above_kick_cap_positive_control :
    Step (fun _ => true) ⟨7, .forumEvent, .claimed, some 3, 99⟩ (.retry 3)
      ⟨7, .forumEvent, .pending, none, 100⟩ := by
  exact Step.retry rfl rfl rfl (by intro h; cases h)

/-- The old pending-at-twelve branch is impossible for any kick row. -/
theorem kick_retry_at_cap_cannot_remain_pending {enabled : Channel → Bool}
    {before after : Row} {worker : Nat}
    (step : Step enabled before (.retry worker) after)
    (isKick : before.channel = .executionKick)
    (atCap : executionKickMaxAttempts ≤ before.attempts + 1) :
    after.status ≠ .pending := by
  have dead := (kick_retry_at_cap_dead_letters step isKick atCap).1
  rw [dead]
  decide

end AgentWorkflow.Outbox
