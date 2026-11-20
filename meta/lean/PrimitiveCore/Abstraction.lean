import Std

namespace PrimitiveCore.Abstraction

variable {State Observation Answer Action : Type}

/-- Only observations actually produced by a state require a decoder value. -/
def ObservedRange (observe : State → Observation) :=
  { observation : Observation // ∃ state, observe state = observation }

def observed (observe : State → Observation) (state : State) : ObservedRange observe :=
  ⟨observe state, state, rfl⟩

/-- The query does not distinguish states that the observation merges. -/
def FiberConstant (observe : State → Observation) (query : State → Answer) : Prop :=
  ∀ first second, observe first = observe second → query first = query second

/-- The exact query can be recovered from an observed representation alone. -/
def FactorsThrough (observe : State → Observation) (query : State → Answer) : Prop :=
  ∃ decode : ObservedRange observe → Answer,
    ∀ state, decode (observed observe state) = query state

theorem fiberConstant_iff_factorsThrough
    (observe : State → Observation) (query : State → Answer) :
    FiberConstant observe query ↔ FactorsThrough observe query := by
  classical
  constructor
  · intro constant
    refine ⟨fun observation => query (Classical.choose observation.property), ?_⟩
    intro state
    exact constant _ state (Classical.choose_spec (observed observe state).property)
  · rintro ⟨decode, correct⟩ first second same
    calc
      query first = decode (observed observe first) := (correct first).symm
      _ = decode (observed observe second) := congrArg decode (Subtype.ext same)
      _ = query second := correct second

theorem collision_prevents_query_factorization
    (observe : State → Observation) (query : State → Answer)
    (first second : State)
    (same : observe first = observe second)
    (different : query first ≠ query second) :
    ¬ FactorsThrough observe query := by
  intro factorization
  exact different ((fiberConstant_iff_factorsThrough observe query).mpr
    factorization first second same)

/-- Correctness means satisfying the declared task, not merely avoiding harm. -/
def SoundPolicy (observe : State → Observation) (good : State → Action → Prop)
    (policy : Observation → Action) : Prop :=
  ∀ state, good state (policy (observe state))

theorem disjoint_good_actions_prevent_policy
    (observe : State → Observation) (good : State → Action → Prop)
    (first second : State)
    (same : observe first = observe second)
    (disjoint : ∀ action, ¬ (good first action ∧ good second action)) :
    ¬ ∃ policy, SoundPolicy observe good policy := by
  rintro ⟨policy, correct⟩
  apply disjoint (policy (observe first))
  constructor
  · exact correct first
  · simpa only [same] using correct second

theorem constant_observation_loses_boolean_query :
    ¬ FactorsThrough (fun _ : Bool => ()) (fun state : Bool => state) := by
  exact collision_prevents_query_factorization
    (fun _ : Bool => ()) (fun state : Bool => state) true false rfl (by decide)

end PrimitiveCore.Abstraction
