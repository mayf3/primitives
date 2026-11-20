import Std

/-!
# Evidence, partial observation, and the limits of compressed state

This file uses only Lean's bundled libraries. It proves conditional statements
about a declared relational model, not properties of a deployed LLM or service.

`Emits` describes every observation that the declared environment can produce;
it need not be deterministic or truthful. Omitting a possible deceptive report
invalidates the trace-refinement premise, not the theorem below.
-/

namespace AgentWorkflow.Evidence

universe u v w

abbrev Belief (S : Type u) := S → Prop

/-- Relational, set-valued observation update. No posterior probabilities or
independence assumptions are introduced. -/
def update {S : Type u} {A : Type v} {O : Type w}
    (Step : S → A → S → Prop) (Emits : S → O → Prop)
    (belief : Belief S) (action : A) (observation : O) : Belief S :=
  fun after => ∃ before,
    belief before ∧ Step before action after ∧ Emits after observation

/-- A real successor remains possible if the initial information set contains
the real predecessor and the model includes the real transition/observation. -/
theorem update_contains_actual {S : Type u} {A : Type v} {O : Type w}
    {Step : S → A → S → Prop} {Emits : S → O → Prop}
    {belief : Belief S} {before after : S} {action : A} {observation : O}
    (contains : belief before) (actualStep : Step before action after)
    (actualObservation : Emits after observation) :
    update Step Emits belief action observation after :=
  ⟨before, contains, actualStep, actualObservation⟩

inductive ActualTrace {S : Type u} {A : Type v} {O : Type w}
    (Step : S → A → S → Prop) (Emits : S → O → Prop) :
    S → List (A × O) → S → Prop where
  | nil (state : S) : ActualTrace Step Emits state [] state
  | cons {before middle after : S} {action : A} {observation : O}
      {rest : List (A × O)} :
      Step before action middle → Emits middle observation →
      ActualTrace Step Emits middle rest after →
      ActualTrace Step Emits before ((action, observation) :: rest) after

def filterTrace {S : Type u} {A : Type v} {O : Type w}
    (Step : S → A → S → Prop) (Emits : S → O → Prop)
    (belief : Belief S) : List (A × O) → Belief S
  | [] => belief
  | (action, observation) :: rest =>
      filterTrace Step Emits (update Step Emits belief action observation) rest

/-- Truth containment holds for arbitrary finite observation traces, including
correlated or deceptive observations admitted by `Emits`. -/
theorem trace_contains_actual {S : Type u} {A : Type v} {O : Type w}
    {Step : S → A → S → Prop} {Emits : S → O → Prop}
    {before after : S} {observations : List (A × O)}
    (trace : ActualTrace Step Emits before observations after) :
    ∀ belief : Belief S, belief before →
      filterTrace Step Emits belief observations after := by
  induction trace with
  | nil state =>
      intro belief contains
      exact contains
  | cons actualStep actualObservation rest ih =>
      intro belief contains
      exact ih _ (update_contains_actual contains actualStep actualObservation)

inductive EffectWorld where
  | absent
  | applied
  deriving DecidableEq, Repr

inductive EffectReport where
  | claimsApplied
  | unknown
  deriving DecidableEq, Repr

def identityStep (before : EffectWorld) (_ : Unit) (after : EffectWorld) : Prop :=
  before = after

/-- An untrusted reporter may produce either report in either world. -/
def untrustedEmission (_ : EffectWorld) (_ : EffectReport) : Prop := True

theorem claimed_applied_keeps_absent_possible :
    update identityStep untrustedEmission (fun _ => True)
      () EffectReport.claimsApplied EffectWorld.absent := by
  exact ⟨EffectWorld.absent, trivial, rfl, trivial⟩

theorem claimed_applied_keeps_applied_possible :
    update identityStep untrustedEmission (fun _ => True)
      () EffectReport.claimsApplied EffectWorld.applied := by
  exact ⟨EffectWorld.applied, trivial, rfl, trivial⟩

/-! ## Exact relational state abstraction

The following conditions concern lossless abstraction of a declared history
model. They are not a proof that a real LLM is Markov, IID, or stationary.
Actions, possible abstract successors, and original acceptance must all survive
the compression. A probabilistic Markov quotient would additionally require
matching conditional probability kernels; no such kernels are postulated here.
-/

def EnabledCompatible {H : Type u} {S : Type v} {A : Type w}
    (compress : H → S) (Enabled : H → A → Prop) : Prop :=
  ∀ h₁ h₂, compress h₁ = compress h₂ →
    ∀ action, Enabled h₁ action ↔ Enabled h₂ action

def PostCompatible {H : Type u} {S : Type v} {A : Type w}
    (compress : H → S) (Step : H → A → H → Prop) : Prop :=
  ∀ h₁ h₂, compress h₁ = compress h₂ → ∀ action abstractAfter,
    (∃ after, Step h₁ action after ∧ compress after = abstractAfter) ↔
    (∃ after, Step h₂ action after ∧ compress after = abstractAfter)

def AcceptanceCompatible {H : Type u} {S : Type v}
    (compress : H → S) (Acc : H → Prop) : Prop :=
  ∀ h₁ h₂, compress h₁ = compress h₂ → (Acc h₁ ↔ Acc h₂)

structure RelationallySufficient {H : Type u} {S : Type v} {A : Type w}
    (compress : H → S) (Enabled : H → A → Prop)
    (Step : H → A → H → Prop) (Acc : H → Prop) : Prop where
  enabled : EnabledCompatible compress Enabled
  successors : PostCompatible compress Step
  acceptance : AcceptanceCompatible compress Acc

/-- Enabled-action compatibility is exactly the condition for a lossless
state-only representation of the enabled-action relation. This theorem makes
the implementation's proof obligation explicit; it does not assume it holds. -/
theorem enabled_factorization_iff {H : Type u} {S : Type v} {A : Type w}
    (compress : H → S) (Enabled : H → A → Prop) :
    EnabledCompatible compress Enabled ↔
      ∃ AbstractEnabled : S → A → Prop,
        ∀ history action,
          Enabled history action ↔ AbstractEnabled (compress history) action := by
  constructor
  · intro compatible
    refine ⟨fun state action =>
      ∃ history, compress history = state ∧ Enabled history action, ?_⟩
    intro history action
    constructor
    · intro enabled
      exact ⟨history, rfl, enabled⟩
    · rintro ⟨other, same, enabled⟩
      exact (compatible other history same action).mp enabled
  · rintro ⟨abstractEnabled, factors⟩
    intro h₁ h₂ same action
    rw [factors h₁ action, factors h₂ action, same]

theorem post_factorization_iff {H : Type u} {S : Type v} {A : Type w}
    (compress : H → S) (Step : H → A → H → Prop) :
    PostCompatible compress Step ↔
      ∃ AbstractStep : S → A → S → Prop,
        ∀ history action abstractAfter,
          (∃ after, Step history action after ∧ compress after = abstractAfter) ↔
            AbstractStep (compress history) action abstractAfter := by
  constructor
  · intro compatible
    refine ⟨fun state action abstractAfter =>
      ∃ history, compress history = state ∧
        ∃ after, Step history action after ∧ compress after = abstractAfter, ?_⟩
    intro history action abstractAfter
    constructor
    · intro successor
      exact ⟨history, rfl, successor⟩
    · rintro ⟨other, same, successor⟩
      exact (compatible other history same action abstractAfter).mp successor
  · rintro ⟨abstractStep, factors⟩
    intro h₁ h₂ same action abstractAfter
    rw [factors h₁ action abstractAfter, factors h₂ action abstractAfter, same]

theorem acceptance_factorization_iff {H : Type u} {S : Type v}
    (compress : H → S) (Acc : H → Prop) :
    AcceptanceCompatible compress Acc ↔
      ∃ AbstractAcc : S → Prop,
        ∀ history, Acc history ↔ AbstractAcc (compress history) := by
  constructor
  · intro compatible
    refine ⟨fun state => ∃ history, compress history = state ∧ Acc history, ?_⟩
    intro history
    constructor
    · intro accepted
      exact ⟨history, rfl, accepted⟩
    · rintro ⟨other, same, accepted⟩
      exact (compatible other history same).mp accepted
  · rintro ⟨abstractAcc, factors⟩
    intro h₁ h₂ same
    rw [factors h₁, factors h₂, same]

/-- The three explicit compatibility conditions are necessary and sufficient
for exact state-level relations for enabled actions, possible abstract
successors, and acceptance. This does not preserve probabilities, fairness,
time bounds, or observations unless those are separately included in the model.
It does not establish the conditions for any production state serialization. -/
theorem sufficient_iff_exact_relational_quotient
    {H : Type u} {S : Type v} {A : Type w}
    (compress : H → S) (Enabled : H → A → Prop)
    (Step : H → A → H → Prop) (Acc : H → Prop) :
    RelationallySufficient compress Enabled Step Acc ↔
      ∃ (AbstractEnabled : S → A → Prop) (AbstractStep : S → A → S → Prop)
        (AbstractAcc : S → Prop),
        (∀ history action,
          Enabled history action ↔ AbstractEnabled (compress history) action) ∧
        (∀ history action abstractAfter,
          (∃ after, Step history action after ∧ compress after = abstractAfter) ↔
            AbstractStep (compress history) action abstractAfter) ∧
        (∀ history, Acc history ↔ AbstractAcc (compress history)) := by
  constructor
  · intro sufficient
    obtain ⟨abstractEnabled, enabledFactor⟩ :=
      (enabled_factorization_iff compress Enabled).mp sufficient.enabled
    obtain ⟨abstractStep, stepFactor⟩ :=
      (post_factorization_iff compress Step).mp sufficient.successors
    obtain ⟨abstractAcc, accFactor⟩ :=
      (acceptance_factorization_iff compress Acc).mp sufficient.acceptance
    exact ⟨abstractEnabled, abstractStep, abstractAcc,
      enabledFactor, stepFactor, accFactor⟩
  · rintro ⟨abstractEnabled, abstractStep, abstractAcc,
      enabledFactor, stepFactor, accFactor⟩
    exact ⟨(enabled_factorization_iff compress Enabled).mpr
        ⟨abstractEnabled, enabledFactor⟩,
      (post_factorization_iff compress Step).mpr ⟨abstractStep, stepFactor⟩,
      (acceptance_factorization_iff compress Acc).mpr ⟨abstractAcc, accFactor⟩⟩

inductive RetryHistory where
  | notSent
  | inFlight
  deriving DecidableEq, Repr

inductive RetryAction where
  | newWrite
  | readback
  deriving DecidableEq, Repr

def nodeOnly (_ : RetryHistory) : Unit := ()

def retryEnabled : RetryHistory → RetryAction → Prop
  | .notSent, _ => True
  | .inFlight, .newWrite => False
  | .inFlight, .readback => True

theorem node_only_loses_enabled_actions :
    ¬ EnabledCompatible nodeOnly retryEnabled := by
  intro compatible
  have impossible :=
    (compatible .notSent .inFlight rfl .newWrite).mp True.intro
  exact impossible

theorem no_exact_node_only_enabled_relation :
    ¬ ∃ AbstractEnabled : Unit → RetryAction → Prop,
      ∀ history action,
        retryEnabled history action ↔ AbstractEnabled (nodeOnly history) action := by
  intro factorization
  exact node_only_loses_enabled_actions
    ((enabled_factorization_iff nodeOnly retryEnabled).mpr factorization)

inductive PendingHistory where
  | unsent
  | inFlight
  | applied
  deriving DecidableEq, Repr

inductive VisibleState where
  | waiting
  | finished
  deriving DecidableEq, Repr

def collapsePending : PendingHistory → VisibleState
  | .applied => .finished
  | _ => .waiting

def environmentTick : PendingHistory → Unit → PendingHistory → Prop
  | .unsent, _, after => after = .unsent
  | .inFlight, _, after => after = .applied
  | .applied, _, after => after = .applied

/-- Even when the current node is identical, an old in-flight request changes
the possible future. This is a successor-support counterexample, not merely an
action-label counterexample. -/
theorem node_only_loses_future_behavior :
    ¬ PostCompatible collapsePending environmentTick := by
  intro compatible
  have pendingCanFinish :
      ∃ after, environmentTick .inFlight () after ∧
        collapsePending after = VisibleState.finished :=
    ⟨.applied, rfl, rfl⟩
  have unsentCanFinish :=
    (compatible .unsent .inFlight rfl () .finished).mpr pendingCanFinish
  rcases unsentCanFinish with ⟨after, tick, visible⟩
  change after = PendingHistory.unsent at tick
  subst after
  cases visible

/-! ## Untrusted proposals and an authority-gated acceptance transition

`Report` is arbitrary: no honesty, independence, error rate, or lack of
sycophancy is assumed. `BoundEvidence` and `verify` belong to the declared
trusted boundary. The model does not prove that a deployed verifier is sound.
World changes are outside this local acceptance slice; preservation after later
external effects is a separate invariant/refinement obligation.
-/

structure ReviewState (World : Type u) (Report : Type v) where
  world : World
  latest : Report
  closed : Bool

inductive GateStep {World : Type u} {Report : Type v} {Artifact : Type w}
    (Authorized : World → Prop) (BoundEvidence : World → Artifact → Prop)
    (verify : Artifact → Bool) :
    ReviewState World Report → ReviewState World Report → Prop where
  | propose (state : ReviewState World Report) (report : Report) :
      GateStep Authorized BoundEvidence verify state {state with latest := report}
  | commit (state : ReviewState World Report) (artifact : Artifact)
      (authority : Authorized state.world)
      (binding : BoundEvidence state.world artifact)
      (checked : verify artifact = true) :
      GateStep Authorized BoundEvidence verify state {state with closed := true}

def EvidenceSound {World : Type u} {Artifact : Type w}
    (Acc : World → Prop) (BoundEvidence : World → Artifact → Prop)
    (verify : Artifact → Bool) : Prop :=
  ∀ world artifact,
    BoundEvidence world artifact → verify artifact = true → Acc world

def GateInvariant {World : Type u} {Report : Type v}
    (Acc Authorized : World → Prop) (state : ReviewState World Report) : Prop :=
  state.closed = true → Acc state.world ∧ Authorized state.world

theorem gate_step_preserves_truth {World : Type u} {Report : Type v}
    {Artifact : Type w} {Acc Authorized : World → Prop}
    {BoundEvidence : World → Artifact → Prop} {verify : Artifact → Bool}
    (sound : EvidenceSound Acc BoundEvidence verify)
    {before after : ReviewState World Report}
    (step : GateStep Authorized BoundEvidence verify before after)
    (prior : GateInvariant Acc Authorized before) :
    GateInvariant Acc Authorized after := by
  cases step with
  | propose report => exact prior
  | commit artifact authority binding checked =>
      intro _
      exact ⟨sound before.world artifact binding checked, authority⟩

inductive Steps {S : Type u} (Step : S → S → Prop) : S → S → Prop where
  | refl (state : S) : Steps Step state state
  | tail {first middle last : S} :
      Steps Step first middle → Step middle last → Steps Step first last

/-- Arbitrarily many, arbitrarily correlated report updates cannot create a
false close through this gate, conditional on the evidence boundary's soundness
and completeness of the modeled write paths. -/
theorem reports_cannot_bypass_sound_gate {World : Type u} {Report : Type v}
    {Artifact : Type w} {Acc Authorized : World → Prop}
    {BoundEvidence : World → Artifact → Prop} {verify : Artifact → Bool}
    (sound : EvidenceSound Acc BoundEvidence verify)
    {initial final : ReviewState World Report} (initiallyOpen : initial.closed = false)
    (execution : Steps (GateStep Authorized BoundEvidence verify) initial final) :
    final.closed = true → Acc final.world ∧ Authorized final.world := by
  have initialInvariant : GateInvariant Acc Authorized initial := by
    intro closed
    rw [initiallyOpen] at closed
    cases closed
  have preserves : ∀ {first last : ReviewState World Report},
      Steps (GateStep Authorized BoundEvidence verify) first last →
      GateInvariant Acc Authorized first → GateInvariant Acc Authorized last := by
    intro first last trace
    induction trace with
    | refl => exact fun invariant => invariant
    | tail previous step ih =>
        intro invariant
        exact gate_step_preserves_truth sound step (ih invariant)
  exact preserves execution initialInvariant

structure Assessment where
  actual : Bool
  worker : Bool
  reviewerOne : Bool
  reviewerTwo : Bool
  deriving DecidableEq, Repr

def Consensus (assessment : Assessment) : Prop :=
  assessment.worker = true ∧ assessment.reviewerOne = true ∧
    assessment.reviewerTwo = true

def sharedWrong : Assessment := ⟨false, true, true, true⟩

theorem shared_wrong_has_consensus : Consensus sharedWrong := by
  simp [Consensus, sharedWrong]

theorem shared_wrong_is_not_complete : sharedWrong.actual ≠ true := by decide

/-- Two agreeing reviewers do not entail truth without an additional connection
to the original acceptance predicate. No statistical claim is made here. -/
theorem consensus_does_not_imply_truth :
    ¬ (∀ assessment, Consensus assessment → assessment.actual = true) := by
  intro allegedSoundness
  exact shared_wrong_is_not_complete
    (allegedSoundness sharedWrong shared_wrong_has_consensus)

/-- Removing the sound-evidence premise admits a concrete false completion,
even though the syntactic gate and an authorization check are present. -/
theorem unsound_gate_can_close_false_goal :
    ∃ before after : ReviewState Bool Bool,
      before.world = false ∧ before.closed = false ∧
      GateStep (fun _ => True) (fun _ (_ : Unit) => True) (fun _ => true)
        before after ∧ after.closed = true ∧ after.world = false := by
  let before : ReviewState Bool Bool := ⟨false, true, false⟩
  let after : ReviewState Bool Bool := ⟨false, true, true⟩
  refine ⟨before, after, rfl, rfl, ?_, rfl, rfl⟩
  exact GateStep.commit before () trivial trivial rfl

/-- A concrete synthetic evidence contract is sound: the accepted artifact is
equal to the world fact. Establishing such a binding in a service remains an
implementation obligation; the worker does not get to assert it as authority. -/
theorem equality_evidence_is_sound :
    EvidenceSound (fun world : Bool => world = true)
      (fun world artifact => artifact = world) (fun artifact => artifact) := by
  intro world artifact binding checked
  exact binding ▸ checked

/-- A non-vacuous positive control: the sound gate can accept real success. -/
theorem sound_gate_can_close_true_goal :
    ∃ before after : ReviewState Bool Bool,
      before.closed = false ∧
      GateStep (fun _ => True) (fun world artifact => artifact = world)
        (fun artifact => artifact) before after ∧
      after.closed = true ∧ after.world = true := by
  let before : ReviewState Bool Bool := ⟨true, false, false⟩
  let after : ReviewState Bool Bool := ⟨true, false, true⟩
  refine ⟨before, after, rfl, ?_, rfl, rfl⟩
  exact GateStep.commit before true trivial rfl rfl


end AgentWorkflow.Evidence
