import Std

/-!
Semantic revision contracts. A meaning is a predicate on possible worlds.
Natural-language parsing, source reliability, voice and audience response
are deliberately outside this formal model.
-/

namespace Writing.Revision

abbrev Meaning (World : Type) := World → Prop

def Entails (before after : Meaning World) : Prop :=
  ∀ world, before world → after world

/-- Both sides matter: do not add unsupported facts, and preserve what the
caller actually encodes in `required`. The caller must state the task's required
information accurately. If `required` is constantly `True`, a constantly `True`
draft passes even with satisfiable evidence; this contract cannot prevent such
information deletion or discover the required information itself. -/
def Faithful (evidence required draft : Meaning World) : Prop :=
  Entails evidence draft ∧ Entails draft required

/-- A caller-supplied contract for a particular conservative edit. Both
implications must be established for that edit. Preservation theorems compose
these certificates; they do not automatically certify arbitrary edits. -/
def Revision (required before after : Meaning World) : Prop :=
  Entails before after ∧ Entails after required

inductive RevisionTrace (required : Meaning World) :
    Meaning World → Meaning World → Prop where
  | refl (draft) : RevisionTrace required draft draft
  | step {before middle after} :
      Revision required before middle → RevisionTrace required middle after →
      RevisionTrace required before after

theorem entails_transitive (a b c : Meaning World)
    (ab : Entails a b) (bc : Entails b c) : Entails a c := by
  intro world ha
  exact bc world (ab world ha)

theorem revision_preserves_faithfulness
    (evidence required before after : Meaning World)
    (old : Faithful evidence required before)
    (revision : Revision required before after) :
    Faithful evidence required after :=
  ⟨entails_transitive evidence before after old.1 revision.1, revision.2⟩

theorem repeated_revisions_preserve_faithfulness
    {evidence required before after : Meaning World}
    (trace : RevisionTrace required before after)
    (old : Faithful evidence required before) :
    Faithful evidence required after := by
  induction trace with
  | refl => exact old
  | step revision rest ih =>
      exact ih (revision_preserves_faithfulness _ _ _ _ old revision)

/-- A real witness for the source model also witnesses the final draft.
Satisfiability must be supplied, not inferred from contradictory evidence. -/
theorem supported_draft_has_a_world {evidence required draft : Meaning World}
    (faithful : Faithful evidence required draft)
    (inhabited : ∃ world, evidence world) : ∃ world, draft world := by
  obtain ⟨world, hw⟩ := inhabited
  exact ⟨world, faithful.1 world hw⟩

abbrev AudienceWorld := Bool → Bool

def someInterested (world : AudienceWorld) : Prop :=
  ∃ person, world person = true

def everyoneInterested (world : AudienceWorld) : Prop :=
  ∀ person, world person = true

theorem one_person_cannot_be_upgraded_to_everyone :
    ¬ Entails someInterested everyoneInterested := by
  intro upgrade
  have all := upgrade (fun person => person) ⟨true, rfl⟩
  have impossible := all false
  contradiction

theorem deleting_required_information_is_not_faithful :
    ¬ Faithful someInterested someInterested (fun _ : AudienceWorld => True) := by
  rintro ⟨_, keeps⟩
  obtain ⟨person, impossible⟩ := keeps (fun _ => false) trivial
  contradiction

theorem unchanged_supported_meaning_is_faithful (meaning : Meaning World) :
    Faithful meaning meaning meaning :=
  ⟨fun _ h => h, fun _ h => h⟩

/-- Reordering a conjunction changes presentation order, not these explicitly
declared facts. This says nothing about discourse or actual event order. -/
theorem reordered_facts_preserve_meaning (a b : Meaning World) :
    Faithful (fun w => a w ∧ b w) (fun w => a w ∧ b w)
      (fun w => b w ∧ a w) := by
  exact ⟨fun _ h => ⟨h.2, h.1⟩, fun _ h => ⟨h.2, h.1⟩⟩

end Writing.Revision
