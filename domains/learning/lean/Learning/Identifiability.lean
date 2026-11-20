import PrimitiveCore.Abstraction

namespace Learning.Identifiability

variable {Model Question Answer : Type}

/-- A finite test suite's ordered answers under a declared deterministic model. -/
def answerSignature (respond : Model → Question → Answer)
    (questions : List Question) (model : Model) : List Answer :=
  questions.map (respond model)

def Distinguishes (respond : Model → Question → Answer)
    (questions : List Question) : Prop :=
  ∀ first second,
    (∀ question, question ∈ questions → respond first question = respond second question) →
    first = second

theorem signature_eq_iff_same_answers
    (respond : Model → Question → Answer) (questions : List Question)
    (first second : Model) :
    answerSignature respond questions first = answerSignature respond questions second ↔
      ∀ question, question ∈ questions → respond first question = respond second question := by
  induction questions with
  | nil => simp [answerSignature]
  | cons head tail inductionHypothesis =>
    constructor
    · intro equalSignatures question included
      have split : respond first head = respond second head ∧
          answerSignature respond tail first = answerSignature respond tail second := by
        simpa only [answerSignature, List.map_cons, List.cons.injEq] using equalSignatures
      rcases List.mem_cons.mp included with atHead | inTail
      · subst question
        exact split.1
      · exact inductionHypothesis.mp split.2 question inTail
    · intro sameAnswers
      have atHead := sameAnswers head (by simp)
      have onTail : answerSignature respond tail first = answerSignature respond tail second :=
        inductionHypothesis.mpr (fun question included =>
          sameAnswers question (List.mem_cons_of_mem head included))
      simpa only [answerSignature, List.map_cons, List.cons.injEq] using And.intro atHead onTail

theorem distinguishes_iff_injective_signature
    (respond : Model → Question → Answer) (questions : List Question) :
    Distinguishes respond questions ↔
      ∀ first second,
        answerSignature respond questions first = answerSignature respond questions second →
        first = second := by
  constructor
  · intro distinguishes first second same
    exact distinguishes first second
      ((signature_eq_iff_same_answers respond questions first second).mp same)
  · intro injective first second same
    exact injective first second
      ((signature_eq_iff_same_answers respond questions first second).mpr same)

theorem same_answers_prevent_identification
    (respond : Model → Question → Answer) (questions : List Question)
    (first second : Model) (different : first ≠ second)
    (same : ∀ question, question ∈ questions → respond first question = respond second question) :
    ¬ Distinguishes respond questions := by
  intro distinguishes
  exact different (distinguishes first second same)

theorem adding_questions_preserves_distinguishability
    (respond : Model → Question → Answer) (questions extra : List Question)
    (distinguishes : Distinguishes respond questions) :
    Distinguishes respond (questions ++ extra) := by
  intro first second same
  exact distinguishes first second (fun question included =>
    same question (List.mem_append.mpr (Or.inl included)))

theorem query_recoverable_iff_constant_on_signature
    {QueryAnswer : Type} (respond : Model → Question → Answer)
    (questions : List Question) (query : Model → QueryAnswer) :
    PrimitiveCore.Abstraction.FactorsThrough (answerSignature respond questions) query ↔
      PrimitiveCore.Abstraction.FiberConstant (answerSignature respond questions) query := by
  exact (PrimitiveCore.Abstraction.fiberConstant_iff_factorsThrough
    (answerSignature respond questions) query).symm

/-- Three synthetic response rules, not diagnoses of real people. -/
inductive StrategyModel where
  | scaleWithSeconds
  | repeatSixty
  | memorizeTwoQuestions
  deriving DecidableEq, Repr

/-- Seconds-to-frames questions at a fixed 30 fps. -/
def frameResponse (model : StrategyModel) (seconds : Nat) : Nat :=
  match model with
  | .scaleWithSeconds => 30 * seconds
  | .repeatSixty => 60
  | .memorizeTwoQuestions => if seconds = 3 then 90 else 60

theorem practiced_question_does_not_distinguish :
    ¬ Distinguishes frameResponse [2] := by
  apply same_answers_prevent_identification frameResponse [2]
    .scaleWithSeconds .repeatSixty (by decide)
  intro question included
  have isTwo : question = 2 := by simpa using included
  subst question
  rfl

theorem one_variation_still_does_not_distinguish :
    ¬ Distinguishes frameResponse [2, 3] := by
  apply same_answers_prevent_identification frameResponse [2, 3]
    .scaleWithSeconds .memorizeTwoQuestions (by decide)
  intro question included
  have choices : question = 2 ∨ question = 3 := by simpa using included
  rcases choices with two | three
  · subst question
    rfl
  · subst question
    rfl

theorem three_questions_distinguish_declared_models :
    Distinguishes frameResponse [2, 3, 4] := by
  intro first second same
  have atThree := same 3 (by decide)
  have atFour := same 4 (by decide)
  cases first <;> cases second <;> simp_all [frameResponse]

end Learning.Identifiability
