import PrimitiveCore.Abstraction

namespace Design.Disclosure

/-- A synthetic decision page, not a model of another domain's records. -/
structure PageState where
  authorized : Bool
  acceptancePassed : Bool
  supportingDetail : Nat
  expanded : Bool
  deriving DecidableEq, Repr

structure VisiblePage where
  authorized : Bool
  acceptancePassed : Bool
  detail : Option Nat
  deriving DecidableEq, Repr

inductive NextAction where
  | obtainPermission
  | repairOutput
  | proceed
  deriving DecidableEq, Repr

def render (state : PageState) : VisiblePage :=
  ⟨state.authorized, state.acceptancePassed,
    if state.expanded then some state.supportingDetail else none⟩

def nextAction (state : PageState) : NextAction :=
  if state.authorized then
    if state.acceptancePassed then .proceed else .repairOutput
  else .obtainPermission

def visibleAction (page : VisiblePage) : NextAction :=
  if page.authorized then
    if page.acceptancePassed then .proceed else .repairOutput
  else .obtainPermission

theorem rendering_recovers_next_action (state : PageState) :
    visibleAction (render state) = nextAction state := by
  rfl

theorem rendering_preserves_required_distinction :
    PrimitiveCore.Abstraction.FiberConstant render nextAction := by
  intro first second same
  exact congrArg visibleAction same

theorem collapsed_page_hides_only_detail (state : PageState) :
    render { state with expanded := false } =
      ⟨state.authorized, state.acceptancePassed, none⟩ := by
  rfl

theorem expanded_page_shows_detail (state : PageState) :
    render { state with expanded := true } =
      ⟨state.authorized, state.acceptancePassed, some state.supportingDetail⟩ := by
  rfl

theorem changing_hidden_detail_preserves_view (state : PageState) (detail : Nat) :
    render { state with expanded := false, supportingDetail := detail } =
      render { state with expanded := false } := by
  rfl

theorem toggling_detail_preserves_action (state : PageState) (expanded : Bool) :
    nextAction { state with expanded := expanded } = nextAction state := by
  rfl

/-- A deliberately incorrect single indicator conflates two different questions. -/
def mergedIndicator (state : PageState) : Bool :=
  state.authorized || state.acceptancePassed

def needsRepair : PageState := ⟨true, false, 7, false⟩
def needsPermission : PageState := ⟨false, true, 7, false⟩

theorem merged_indicator_has_conflicting_actions :
    mergedIndicator needsRepair = mergedIndicator needsPermission ∧
      nextAction needsRepair ≠ nextAction needsPermission := by
  decide

theorem merged_indicator_cannot_recover_action :
    ¬ PrimitiveCore.Abstraction.FactorsThrough mergedIndicator nextAction := by
  exact PrimitiveCore.Abstraction.collision_prevents_query_factorization
    mergedIndicator nextAction needsRepair needsPermission
    merged_indicator_has_conflicting_actions.1
    merged_indicator_has_conflicting_actions.2

theorem merged_indicator_cannot_support_correct_policy :
    ¬ ∃ policy : Bool → NextAction,
      PrimitiveCore.Abstraction.SoundPolicy mergedIndicator
        (fun state action => action = nextAction state) policy := by
  apply PrimitiveCore.Abstraction.disjoint_good_actions_prevent_policy
    mergedIndicator (fun state action => action = nextAction state)
    needsRepair needsPermission merged_indicator_has_conflicting_actions.1
  intro action both
  exact merged_indicator_has_conflicting_actions.2 (both.1.symm.trans both.2)

end Design.Disclosure
