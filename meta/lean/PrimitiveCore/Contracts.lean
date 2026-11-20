import Std

namespace PrimitiveCore.Contracts

variable {State : Type}

/-- Relational partial correctness; existence and termination are not asserted. -/
def Hoare (precondition : State → Prop) (step : State → State → Prop)
    (postcondition : State → Prop) : Prop :=
  ∀ before after, precondition before → step before after → postcondition after

def Sequence (first second : State → State → Prop) : State → State → Prop :=
  fun before after => ∃ intermediate, first before intermediate ∧ second intermediate after

theorem hoare_sequence
    (precondition intermediate postcondition : State → Prop)
    (first second : State → State → Prop)
    (firstCorrect : Hoare precondition first intermediate)
    (secondCorrect : Hoare intermediate second postcondition) :
    Hoare precondition (Sequence first second) postcondition := by
  intro before after preconditionHolds composite
  rcases composite with ⟨middle, firstStep, secondStep⟩
  exact secondCorrect middle after
    (firstCorrect before middle preconditionHolds firstStep) secondStep

/-- An arbitrary finite sequence of allowed transitions, including zero steps. -/
inductive Trace (step : State → State → Prop) : State → State → Prop where
  | nil (state : State) : Trace step state state
  | cons {first middle last : State} :
      step first middle → Trace step middle last → Trace step first last

theorem trace_preserves_invariant
    (step : State → State → Prop) (invariant : State → Prop)
    (preserves : Hoare invariant step invariant)
    {first last : State} (trace : Trace step first last) :
    invariant first → invariant last := by
  induction trace with
  | nil => exact fun established => established
  | cons transition _ inductionHypothesis =>
    intro established
    exact inductionHypothesis (preserves _ _ established transition)

end PrimitiveCore.Contracts
