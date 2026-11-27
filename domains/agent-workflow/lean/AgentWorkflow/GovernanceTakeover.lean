import AgentWorkflow.GovernanceRecovery

/-!
An executable slice for one persisted recovery lease. A poll may claim the
reconciliation duty even with UNKNOWN effects. Lease acquisition does not
authorize another business write. The poll, lock and effect evidence inputs
must be refined by a real consumer and authoritative storage.
-/
namespace AgentWorkflow.GovernanceTakeover

open GovernanceRecovery (Binding)

inductive Phase
  | active
  | held
  | reconciling
  deriving DecidableEq, Repr

inductive Effect
  | unknown
  | verifiedAbsent
  | committed (receipt : Nat)
  deriving DecidableEq, Repr

structure Lease where
  worker : Nat
  epoch : Nat
  deriving DecidableEq, Repr

structure State where
  binding : Binding
  phase : Phase
  lease : Lease
  effect : Effect
  deriving DecidableEq, Repr

structure Claim where
  binding : Binding
  expectedEpoch : Nat
  worker : Nat
  online : Bool
  authorized : Bool
  independent : Bool
  deriving DecidableEq, Repr

/-- Record a hold only on authoritative failure/fence evidence. In-flight
effects are unchanged even when ownership is fenced. -/
def hold (s : State) (failedOrFenced : Bool) : State :=
  if failedOrFenced && s.phase != .held then { s with phase := .held } else s

def eligible (s : State) (c : Claim) : Bool :=
  s.binding.blocker == .technical && s.phase == .held && c.binding == s.binding && c.expectedEpoch == s.lease.epoch &&
    c.worker != s.lease.worker && c.online && c.authorized && c.independent

def claim (s : State) (c : Claim) : State :=
  if eligible s c then { s with phase := .reconciling, lease := ⟨c.worker, s.lease.epoch + 1⟩ }
  else s

def scan (s : State) (claims : List Claim) : State :=
  claims.foldl claim s

/-- Eligibility for mutating the local held work, separate from a provider
write. Real writes still need the database CAS on the full binding and lease. -/
def acceptsLease (s : State) (binding : Binding) (lease : Lease) : Bool :=
  s.phase != .held && binding == s.binding && lease == s.lease

def writeGate (s : State) (binding : Binding) (lease : Lease)
    (key : Nat) (originalKeyReplayProven : Bool) : Bool :=
  s.binding.blocker == .technical && acceptsLease s binding lease && s.phase == .reconciling && key == s.binding.effectKey &&
    match s.effect with
    | .unknown => originalKeyReplayProven
    | .verifiedAbsent => true
    | .committed _ => false

theorem hold_preserves_binding_and_effect (s : State) (evidence : Bool) :
    (hold s evidence).binding = s.binding ∧ (hold s evidence).effect = s.effect := by
  unfold hold
  split <;> exact ⟨rfl, rfl⟩

theorem takeover_preserves_binding_and_effect (s : State) (c : Claim) :
    (claim s c).binding = s.binding ∧ (claim s c).effect = s.effect := by
  unfold claim
  split <;> exact ⟨rfl, rfl⟩

theorem eligible_takeover_rotates_lease {s : State} {c : Claim}
    (allowed : eligible s c = true) :
    (claim s c).phase = .reconciling ∧ (claim s c).lease = ⟨c.worker, s.lease.epoch + 1⟩ := by
  simp [claim, allowed]

theorem stale_lease_cannot_write_after_takeover {s : State} {c : Claim}
    (allowed : eligible s c = true) :
    acceptsLease (claim s c) s.binding s.lease = false := by
  have different : s.lease ≠ ⟨c.worker, s.lease.epoch + 1⟩ := by
    intro eq
    have epoch := congrArg Lease.epoch eq
    exact (Nat.ne_of_lt (Nat.lt_succ_self s.lease.epoch)) epoch
  simp [acceptsLease, claim, allowed, different]

theorem older_epoch_cannot_mutate {s : State} (binding : Binding) {lease : Lease}
    (older : lease.epoch < s.lease.epoch) :
    acceptsLease s binding lease = false := by
  have different : lease ≠ s.lease := fun eq => (Nat.ne_of_lt older) (congrArg Lease.epoch eq)
  simp [acceptsLease, different]

theorem human_decision_is_not_a_technical_claim {s : State} {c : Claim}
    (human : s.binding.blocker = .humanDecision) : claim s c = s := by
  simp [claim, eligible, human]

theorem ineligible_scans_preserve (s : State) (claims : List Claim)
    (ineligible : ∀ c ∈ claims, eligible s c = false) :
    scan s claims = s := by
  induction claims with
  | nil => rfl
  | cons first rest ih =>
      have skipped := ineligible first (by simp)
      have restSkipped : ∀ c ∈ rest, eligible s c = false := fun c mem =>
        ineligible c (List.mem_cons_of_mem first mem)
      simpa [scan, claim, skipped] using ih restSkipped

theorem first_eligible_scan_recovers_original (s : State) (earlier : List Claim) (c : Claim)
    (skipped : ∀ r ∈ earlier, eligible s r = false) (allowed : eligible s c = true) :
    let after := scan s (earlier ++ [c])
    after.phase = .reconciling ∧ after.lease = ⟨c.worker, s.lease.epoch + 1⟩ ∧
      after.binding = s.binding ∧ after.effect = s.effect := by
  have atLast : scan s (earlier ++ [c]) = claim s c := by
    simp only [scan, List.foldl_append, List.foldl_cons, List.foldl_nil]
    rw [show earlier.foldl claim s = s from ineligible_scans_preserve s earlier skipped]
  rw [atLast]
  exact ⟨(eligible_takeover_rotates_lease allowed).1, (eligible_takeover_rotates_lease allowed).2,
    takeover_preserves_binding_and_effect s c⟩

theorem unknown_without_proof_cannot_write {s : State} (binding : Binding) (lease : Lease)
    (key : Nat) (unknown : s.effect = .unknown) :
    writeGate s binding lease key false = false := by
  simp [writeGate, unknown]

theorem known_commit_never_writes_again {s : State} (binding : Binding) (lease : Lease)
    (key : Nat) (proof : Bool) {receipt : Nat} (known : s.effect = .committed receipt) :
    writeGate s binding lease key proof = false := by
  simp [writeGate, known]

theorem write_requires_original_key {s : State} {binding : Binding} {lease : Lease}
    {key : Nat} {proof : Bool} (allowed : writeGate s binding lease key proof = true) : key = s.binding.effectKey := by
  simp only [writeGate, Bool.and_eq_true, beq_iff_eq] at allowed
  exact allowed.1.2

theorem stale_lease_cannot_authorize_new_write {s : State} {c : Claim}
    (allowed : eligible s c = true) (key : Nat) (proof : Bool) :
    writeGate (claim s c) s.binding s.lease key proof = false := by
  simp [writeGate, stale_lease_cannot_write_after_takeover allowed]

private def binding : Binding :=
  ⟨⟨1, 23, 9, 12⟩, ⟨100, 23, 101, 3, 8⟩, 10, 1, 77, .technical⟩

private def failed : State := ⟨binding, .active, ⟨4, 9⟩, .unknown⟩
private def nextClaim : Claim := ⟨binding, 9, 6, true, true, true⟩
private def isolated : State := hold failed true
private def recovered : State := claim isolated nextClaim

example : recovered = ⟨binding, .reconciling, ⟨6, 10⟩, .unknown⟩ := by decide
example : claim isolated { nextClaim with online := false } = isolated := by decide
example : claim isolated { nextClaim with expectedEpoch := 8 } = isolated := by decide
example : claim isolated { nextClaim with worker := 4 } = isolated := by decide
example : claim isolated { nextClaim with binding.caseId := 12 } = isolated := by decide
example : claim recovered { nextClaim with worker := 8 } = recovered := by decide

private def secondClaim : Claim := { nextClaim with expectedEpoch := 10, worker := 7 }
private def recoveredAgain : State := claim (hold recovered true) secondClaim

example : recoveredAgain = ⟨binding, .reconciling, ⟨7, 11⟩, .unknown⟩ := by decide
example : acceptsLease recoveredAgain binding failed.lease = false := by decide
example : acceptsLease recoveredAgain binding recovered.lease = false := by decide

private def humanBinding : Binding := { binding with blocker := .humanDecision }
private def humanHeld : State := { isolated with binding := humanBinding, effect := .verifiedAbsent }

example : claim humanHeld { nextClaim with binding := humanBinding } = humanHeld := by decide
example : writeGate { humanHeld with phase := .reconciling } humanBinding humanHeld.lease 77 true =
    false := by decide

example : acceptsLease recovered binding failed.lease = false := by decide
example : writeGate recovered binding recovered.lease 77 false = false := by decide
example : writeGate recovered binding recovered.lease 77 true = true := by decide
example : writeGate recovered binding recovered.lease 88 true = false := by decide
example : writeGate { recovered with effect := .verifiedAbsent } binding recovered.lease 77 false = true := by decide
example : writeGate { recovered with effect := .committed 62 } binding recovered.lease 77 true = false := by decide

end AgentWorkflow.GovernanceTakeover
