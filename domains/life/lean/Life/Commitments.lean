import Std

/-!
Version-bound historical commitments and source identity.

`recordCommitment` is the trusted input boundary: its caller must have a real
record of the person's commitment. This model does not authenticate speech,
grant current execution permission, or merge Life State with PCA V0.
-/

namespace Life.Commitments

structure Key where
  subject : Nat
  version : Nat
  deriving DecidableEq, Repr

structure State where
  commitments : List Key
  suggestions : List Key
  decisions : List Key
  deriving DecidableEq, Repr

inductive Event where
  | recordCommitment (key : Key)
  | suggest (key : Key)
  | adopt (key : Key)
  deriving DecidableEq, Repr

def empty : State := ⟨[], [], []⟩

def step (s : State) : Event → State
  | .recordCommitment key => { s with commitments := key :: s.commitments }
  | .suggest key => { s with suggestions := key :: s.suggestions }
  | .adopt key =>
      if key ∈ s.commitments then { s with decisions := key :: s.decisions }
      else s

def Supported (s : State) : Prop :=
  ∀ key, key ∈ s.decisions → key ∈ s.commitments

def run : State → List Event → State
  | s, [] => s
  | s, event :: events => run (step s event) events

theorem empty_supported : Supported empty := by
  intro key member
  simp [empty] at member

theorem step_preserves_support (s : State) (event : Event)
    (supported : Supported s) : Supported (step s event) := by
  cases event with
  | recordCommitment key =>
      intro other member
      exact List.mem_cons_of_mem key (supported other member)
  | suggest key => exact supported
  | adopt key =>
      by_cases known : key ∈ s.commitments
      · intro other member
        simp only [step, if_pos known, List.mem_cons] at member ⊢
        rcases member with rfl | old
        · exact known
        · exact supported other old
      · simpa only [step, if_neg known] using supported

theorem run_preserves_support (events : List Event) (s : State)
    (supported : Supported s) : Supported (run s events) := by
  induction events generalizing s with
  | nil => exact supported
  | cons event events ih =>
      exact ih (step s event) (step_preserves_support s event supported)

theorem every_recorded_decision_has_commitment (events : List Event) :
    Supported (run empty events) :=
  run_preserves_support events empty empty_supported

theorem unsupported_adoption_is_unchanged (s : State) (key : Key)
    (missing : key ∉ s.commitments) : step s (.adopt key) = s := by
  simp [step, missing]

/-- Existing commitment evidence may be reused; a new confirmation event is
not required each time the same historical decision is recorded. -/
theorem known_commitment_can_be_adopted (s : State) (key : Key)
    (known : key ∈ s.commitments) : key ∈ (step s (.adopt key)).decisions := by
  simp [step, known]

theorem suggestion_alone_cannot_create_decision (key : Key) :
    (run empty [.suggest key, .adopt key]).decisions = [] := by
  simp [run, step, empty]

theorem commitment_does_not_support_another_version :
    (run empty [.recordCommitment ⟨7, 1⟩, .adopt ⟨7, 2⟩]).decisions = [] := by
  decide

/-- A deliberately broken transition demonstrates why the adoption guard
is necessary. This countermodel is not an allowed transition above. -/
theorem unguarded_adoption_breaks_support :
    ¬ Supported { empty with decisions := [⟨7, 2⟩] } := by
  intro h
  have impossible := h ⟨7, 2⟩ (by simp)
  simp [empty] at impossible

structure Reference where
  root : Nat
  excerpt : Nat
  deriving DecidableEq, Repr

def HasRoot (references : List Reference) (root : Nat) : Prop :=
  ∃ reference, reference ∈ references ∧ reference.root = root

/-- A new excerpt or summary from an already represented root changes the
reference list, but not its set of root sources. Distinct root IDs are NOT
asserted to be statistically independent. -/
theorem repost_preserves_root_sources (references : List Reference)
    (reference : Reference) (present : HasRoot references reference.root) (root : Nat) :
    HasRoot (reference :: references) root ↔ HasRoot references root := by
  constructor
  · rintro ⟨candidate, member, sameRoot⟩
    rcases List.mem_cons.mp member with same | old
    · obtain ⟨original, old, originalRoot⟩ := present
      exact ⟨original, old, originalRoot.trans (same ▸ sameRoot)⟩
    · exact ⟨candidate, old, sameRoot⟩
  · rintro ⟨candidate, member, sameRoot⟩
    exact ⟨candidate, List.mem_cons_of_mem reference member, sameRoot⟩

end Life.Commitments
