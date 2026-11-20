import AgentWorkflow.Evidence

/-!
# Conditional progress for an observation-based recovery policy

This file proves a bound in **completed macro steps**, not wall-clock time.
The protocol contract explicitly supplies termination of every admissible
macro execution.  Nonempty outcome sets alone would not supply termination.
The relation must include every allowed environment outcome; proving that an
installed program implements that relation remains a refinement obligation.
-/

namespace AgentWorkflow.Progress

/-- A region on which a particular strategy has a decreasing natural rank.
`next` is the complete relation for that fixed strategy, not a chosen good path.
The target is the original acceptance condition, not a WAIT or an escalation.
-/
structure RankedSystem (S : Type) where
  region : S → Prop
  target : S → Prop
  next : S → S → Prop
  rank : S → Nat
  regionClosed : ∀ {s t}, region s → next s t → region t
  progress : ∀ s, region s → ¬ target s → ∃ t, next s t
  zeroTarget : ∀ s, region s → rank s = 0 → target s
  decreases : ∀ {s t}, region s → ¬ target s → next s t → rank t < rank s
  targetClosed : ∀ {s t}, target s → next s t → target t

/-- Every finite execution prefix of sufficient length reaches its target
within an upper bound on its initial rank. This universally quantifies over
outcomes in `next`; it is not existential graph reachability. No infinite run
or post-target successor is needed for this theorem.
-/
theorem reaches_within (c : RankedSystem S) (budget : Nat) :
    ∀ run : Nat → S,
      c.region (run 0) →
      (∀ n, n < budget → ¬ c.target (run n) → c.next (run n) (run (n + 1))) →
      c.rank (run 0) ≤ budget →
      ∃ n, n ≤ budget ∧ c.target (run n) := by
  induction budget with
  | zero =>
      intro run hregion _ hbound
      exact ⟨0, Nat.le_refl 0,
        c.zeroTarget (run 0) hregion (Nat.eq_zero_of_le_zero hbound)⟩
  | succ k ih =>
      intro run hregion hsteps hbound
      by_cases htarget : c.target (run 0)
      · exact ⟨0, Nat.zero_le _, htarget⟩
      · have first := hsteps 0 (Nat.zero_lt_succ k) htarget
        have hnextRegion : c.region (run 1) := c.regionClosed hregion first
        have hdecrease : c.rank (run 1) < c.rank (run 0) :=
          c.decreases hregion htarget first
        have hnextBound : c.rank (run 1) ≤ k :=
          Nat.le_of_lt_succ (Nat.lt_of_lt_of_le hdecrease hbound)
        obtain ⟨n, hn, ht⟩ := ih (fun j => run (j + 1)) hnextRegion
          (fun j hj hnot => hsteps (j + 1) (Nat.succ_lt_succ hj) hnot) hnextBound
        exact ⟨n + 1, Nat.succ_le_succ hn, ht⟩

theorem reaches_in_initial_rank (c : RankedSystem S) (run : Nat → S)
    (hregion : c.region (run 0))
    (hsteps : ∀ n, c.next (run n) (run (n + 1))) :
    ∃ n, n ≤ c.rank (run 0) ∧ c.target (run n) :=
  reaches_within c (c.rank (run 0)) run hregion (fun n _ _ => hsteps n) (Nat.le_refl _)

theorem run_stays_in_region (c : RankedSystem S) (run : Nat → S)
    (hregion : c.region (run 0))
    (hsteps : ∀ n, c.next (run n) (run (n + 1))) : ∀ n, c.region (run n) := by
  intro n
  induction n with
  | zero => exact hregion
  | succ n ih => exact c.regionClosed ih (hsteps n)

/-- A finite maximal run cannot end at a non-target state in the certified
region.  Thus the infinite-run theorem does not license a deadlock by itself.
-/
theorem maximal_endpoint_is_target (c : RankedSystem S) (s : S)
    (hregion : c.region s) (hmaximal : ¬ ∃ t, c.next s t) : c.target s := by
  exact Classical.byContradiction (fun h => hmaximal (c.progress s hregion h))

/-- Acceptance is preserved by every later modeled transition.  If late
messages can revoke safety, they must appear in `next` and this premise fails.
-/
theorem target_persists (c : RankedSystem S) (run : Nat → S)
    (hsteps : ∀ n, c.next (run n) (run (n + 1))) (n : Nat)
    (htarget : c.target (run n)) : ∀ k, c.target (run (n + k)) := by
  intro k
  induction k with
  | zero => simpa using htarget
  | succ k ih =>
      exact c.targetClosed ih (by simpa [Nat.add_assoc] using hsteps (n + k))

/-- A belief contains at least one possible world.  The empty set cannot
vacuously satisfy acceptance or erase all outstanding work.
-/
structure Belief (World : Type) where
  possible : World → Prop
  nonempty : ∃ w, possible w

/-- A macro execution returns a final world and a received observation.
`emits` is relational: a world may produce several observations, including
false reports. No truthful or deterministic observation function is assumed.
The world component is a semantic trace annotation, not an assertion that the
acting agent sees the hidden world; its policy receives only the belief.
The adequacy of `execution`, `finish` and `emits` for a real program and its
environment must be justified separately.
-/
structure ObservationProtocol (World Action Observation : Type) where
  legal : World → Action → Prop
  safe : World → Prop
  acceptance : World → Prop
  emits : World → Observation → Prop
  finish : World → Action → World → Prop
  visits : World → Action → World → Prop
  execution : World → Action → (Nat → Option (World × Observation)) → Prop

def ObservedPost (m : ObservationProtocol World Action Observation)
    (b : Belief World) (a : Action) (o : Observation) (w' : World) : Prop :=
  m.emits w' o ∧ ∃ w, b.possible w ∧ m.finish w a w'

/-- Progress and evidence use exactly the same set-valued update, including
every deceptive observation admitted by the declared emission relation.
-/
theorem observed_post_iff_evidence_update
    (m : ObservationProtocol World Action Observation)
    (b : Belief World) (a : Action) (o : Observation) (w' : World) :
    ObservedPost m b a o w' ↔
      AgentWorkflow.Evidence.update m.finish m.emits b.possible a o w' := by
  constructor
  · rintro ⟨emitted, before, possible, finished⟩
    exact ⟨before, possible, finished, emitted⟩
  · rintro ⟨before, possible, finished, emitted⟩
    exact ⟨emitted, before, possible, finished⟩

/-- The *same* policy action is used for every world in the current belief.
The complete successor belief is selected by the received observation.
-/
def BeliefNext (m : ObservationProtocol World Action Observation)
    (policy : Belief World → Action) (b b' : Belief World) : Prop :=
  ∃ o, ∀ w', b'.possible w' ↔ ObservedPost m b (policy b) o w'

def BeliefTarget (m : ObservationProtocol World Action Observation)
    (b : Belief World) : Prop :=
  ∀ w, b.possible w → m.acceptance w ∧ m.safe w

/-- Every allowed execution must actually return a world-observation pair in
finite time, and that pair must satisfy `finish` and `emits`. Existence of a
possible report without an actual finite return would not meet this contract.
The world component describes the hidden outcome, not an extra visible report.
-/
def TerminatingObservation (m : ObservationProtocol World Action Observation)
    (b : Belief World) (a : Action) : Prop :=
  ∀ w, b.possible w → ∀ execution,
    m.execution w a execution →
    ∃ tick w' o, execution tick = some (w', o) ∧
      m.finish w a w' ∧ m.emits w' o

/-- Obligations a fixed observation-based policy must discharge on its winning
region. This package does NOT assert that an LLM, API or deployment satisfies
them. In particular `terminates`, `prefixesSafe` and truthful acceptance need
independent implementation evidence.
-/
structure BeliefCertificate (m : ObservationProtocol World Action Observation) where
  policy : Belief World → Action
  region : Belief World → Prop
  rank : Belief World → Nat
  legal : ∀ b, region b → ¬ BeliefTarget m b →
    ∀ w, b.possible w → m.legal w (policy b)
  executionsExist : ∀ b, region b → ¬ BeliefTarget m b →
    ∀ w, b.possible w → ∃ execution, m.execution w (policy b) execution
  terminates : ∀ b, region b → ¬ BeliefTarget m b →
    TerminatingObservation m b (policy b)
  prefixesSafe : ∀ b, region b →
    ∀ w, b.possible w → ∀ intermediate,
      m.visits w (policy b) intermediate → m.safe intermediate
  regionClosed : ∀ {b b'}, region b → BeliefNext m policy b b' → region b'
  zeroTarget : ∀ b, region b → rank b = 0 → BeliefTarget m b
  decreases : ∀ {b b'}, region b → ¬ BeliefTarget m b →
    BeliefNext m policy b b' → rank b' < rank b
  targetClosed : ∀ {b b'}, BeliefTarget m b →
    BeliefNext m policy b b' → BeliefTarget m b'

variable {World Action Observation : Type}
variable {m : ObservationProtocol World Action Observation}

/-- Universal finite return plus an inhabited execution model supplies a
nonempty observation successor. No completion probability is assumed here.
-/
theorem certified_successor (c : BeliefCertificate m) (b : Belief World)
    (hregion : c.region b) (hnot : ¬ BeliefTarget m b) :
    ∃ b', BeliefNext m c.policy b b' := by
  obtain ⟨w, hw⟩ := b.nonempty
  obtain ⟨execution, he⟩ := c.executionsExist b hregion hnot w hw
  obtain ⟨tick, w', o, _, hf, ho⟩ := c.terminates b hregion hnot w hw execution he
  let b' : Belief World :=
    { possible := ObservedPost m b (c.policy b) o
      nonempty := ⟨w', ho, w, hw, hf⟩ }
  exact ⟨b', o, fun _ => Iff.rfl⟩

def BeliefCertificate.toRanked (c : BeliefCertificate m) : RankedSystem (Belief World) where
  region := c.region
  target := BeliefTarget m
  next := BeliefNext m c.policy
  rank := c.rank
  regionClosed := c.regionClosed
  progress := certified_successor c
  zeroTarget := c.zeroTarget
  decreases := c.decreases
  targetClosed := c.targetClosed

/-- The main information-set result. It is conditional on actual adherence to
the fixed policy and on realization of its completed macro steps.
-/
theorem belief_prefix_reaches_original_acceptance (c : BeliefCertificate m)
    (budget : Nat) (run : Nat → Belief World) (hregion : c.region (run 0))
    (hsteps : ∀ n, n < budget → ¬ BeliefTarget m (run n) →
      BeliefNext m c.policy (run n) (run (n + 1)))
    (hbound : c.rank (run 0) ≤ budget) :
    ∃ n, n ≤ budget ∧
      ∀ w, (run n).possible w → m.acceptance w ∧ m.safe w :=
  reaches_within c.toRanked budget run hregion hsteps hbound

/-- Infinite completed runs are a convenient corollary, not a premise of the
finite-prefix theorem above. A terminating finite run can use that theorem.
-/
theorem belief_policy_reaches_original_acceptance (c : BeliefCertificate m)
    (run : Nat → Belief World) (hregion : c.region (run 0))
    (hsteps : ∀ n, BeliefNext m c.policy (run n) (run (n + 1))) :
    ∃ n, n ≤ c.rank (run 0) ∧
      ∀ w, (run n).possible w → m.acceptance w ∧ m.safe w :=
  reaches_in_initial_rank c.toRanked run hregion hsteps

/-- A refinement witness supplies ordered finite return times, execution of
the actual fixed policy, the received reports and their model coverage,
complete observation updates, and coverage of concrete intermediate states.
Only the initial world must be supplied as possible. The theorem
`MacroRealization.possibleAtBoundary` derives all later containment facts.
These local refinement obligations still need implementation evidence.
-/
structure MacroRealization (m : ObservationProtocol World Action Observation)
    (policy : Belief World → Action)
    (concrete : Nat → World) (abstractRun : Nat → Belief World) where
  boundary : Nat → Nat
  startsAtZero : boundary 0 = 0
  advances : ∀ n, boundary n < boundary (n + 1)
  initiallyPossible : (abstractRun 0).possible (concrete 0)
  observation : Nat → Observation
  output : Nat → Nat → Option (World × Observation)
  executesPolicy : ∀ n,
    m.execution (concrete (boundary n)) (policy (abstractRun n)) (output n)
  returnsAtBoundary : ∀ n,
    output n (boundary (n + 1) - boundary n) =
      some (concrete (boundary (n + 1)), observation n)
  realizesFinish : ∀ n,
    m.finish (concrete (boundary n)) (policy (abstractRun n))
      (concrete (boundary (n + 1)))
  realizesObservation : ∀ n,
    m.emits (concrete (boundary (n + 1))) (observation n)
  prefixCoverage : ∀ n tick, tick ≤ boundary (n + 1) - boundary n →
    m.visits (concrete (boundary n)) (policy (abstractRun n))
      (concrete (boundary n + tick))
  updatesFromObservation : ∀ n w',
    (abstractRun (n + 1)).possible w' ↔
      ObservedPost m (abstractRun n) (policy (abstractRun n))
        (observation n) w'

/-- All boundary truth-containment facts follow from the initial inclusion,
actual transition/report coverage and exact evidence update. They are no
longer assumed independently at every boundary. A false report is allowed;
only omission of that actual report from `emits` breaks the premise.
-/
theorem MacroRealization.possibleAtBoundary
    (r : MacroRealization m policy concrete abstractRun) :
    ∀ n, (abstractRun n).possible (concrete (r.boundary n)) := by
  intro n
  induction n with
  | zero => simpa only [r.startsAtZero] using r.initiallyPossible
  | succ n ih =>
      apply (r.updatesFromObservation n _).mpr
      apply (observed_post_iff_evidence_update m _ _ _ _).mpr
      exact AgentWorkflow.Evidence.update_contains_actual ih
        (r.realizesFinish n) (r.realizesObservation n)

theorem MacroRealization.follows_policy
    (r : MacroRealization m policy concrete abstractRun) :
    ∀ n, BeliefNext m policy (abstractRun n) (abstractRun (n + 1)) := by
  intro n
  exact ⟨r.observation n, r.updatesFromObservation n⟩

/-- Conditional bridge to a concrete trace. No upper bound on `boundary n`
(wall-clock time) is claimed, and the refinement witness is a premise.
-/
theorem realized_policy_reaches_original_acceptance (c : BeliefCertificate m)
    (concrete : Nat → World) (abstractRun : Nat → Belief World)
    (realization : MacroRealization m c.policy concrete abstractRun)
    (hregion : c.region (abstractRun 0)) :
    ∃ time, m.acceptance (concrete time) ∧ m.safe (concrete time) := by
  obtain ⟨n, _, ht⟩ := belief_policy_reaches_original_acceptance c abstractRun hregion
    realization.follows_policy
  exact ⟨realization.boundary n, ht _ (realization.possibleAtBoundary n)⟩

/-- If the implementation proves that `visits` covers each actual intermediate
state, the certificate's prefix-safety obligation transfers to that state.
Neither adequacy of `visits` nor safety of a real API is proved by this lemma.
-/
theorem realized_internal_prefix_safe (c : BeliefCertificate m)
    (concrete : Nat → World) (abstractRun : Nat → Belief World)
    (realization : MacroRealization m c.policy concrete abstractRun)
    (hregion : c.region (abstractRun 0)) (n tick : Nat)
    (htick : tick ≤ realization.boundary (n + 1) - realization.boundary n) :
    m.safe (concrete (realization.boundary n + tick)) := by
  have hb := run_stays_in_region c.toRanked abstractRun hregion
    realization.follows_policy n
  exact c.prefixesSafe (abstractRun n) hb _ (realization.possibleAtBoundary n) _
    (realization.prefixCoverage n tick htick)

/-! ## Small, deliberately idealized witness
Both hidden worlds have the same observation. A trusted original-key service
maps both to `applied`. This example assumes that service contract; it does
not implement an external idempotency service or authenticate its receipt.
-/

inductive ReplayWorld where
  | absent
  | applied
  deriving DecidableEq

def replayProtocol : ObservationProtocol ReplayWorld Unit Unit where
  legal := fun _ _ => True
  safe := fun _ => True
  acceptance := fun w => w = .applied
  emits := fun _ _ => True
  finish := fun _ _ w' => w' = .applied
  visits := fun _ _ _ => True
  execution := fun _ _ execution => execution 0 = some (.applied, ())

def ambiguous : Belief ReplayWorld :=
  { possible := fun _ => True, nonempty := ⟨.absent, trivial⟩ }

def recovered : Belief ReplayWorld :=
  { possible := fun w => w = .applied, nonempty := ⟨.applied, rfl⟩ }

theorem original_key_has_one_observed_successor :
    BeliefNext replayProtocol (fun _ => ()) ambiguous recovered := by
  refine ⟨(), ?_⟩
  intro w
  constructor
  · intro hw
    exact ⟨trivial, .absent, trivial, hw⟩
  · intro h
    obtain ⟨_, _, _, hw⟩ := h
    exact hw

theorem recovered_meets_original_acceptance : BeliefTarget replayProtocol recovered := by
  intro w hw
  exact ⟨hw, trivial⟩

theorem replay_has_finite_observation : TerminatingObservation replayProtocol ambiguous () := by
  intro w _ execution he
  exact ⟨0, .applied, (), he, rfl, trivial⟩

theorem replay_target_iff_no_absent (b : Belief ReplayWorld) :
    BeliefTarget replayProtocol b ↔ ¬ b.possible .absent := by
  constructor
  · intro ht ha
    have impossible := (ht .absent ha).1
    cases impossible
  · intro h w hw
    cases w with
    | absent => exact (h hw).elim
    | applied => exact ⟨rfl, trivial⟩

noncomputable def replayRank (b : Belief ReplayWorld) : Nat := by
  classical
  exact if b.possible .absent then 1 else 0

theorem replay_rank_zero_iff_target (b : Belief ReplayWorld) :
    replayRank b = 0 ↔ BeliefTarget replayProtocol b := by
  classical
  rw [replay_target_iff_no_absent]
  by_cases h : b.possible .absent <;> simp [replayRank, h]

theorem replay_successor_is_target {b b' : Belief ReplayWorld}
    (hn : BeliefNext replayProtocol (fun _ => ()) b b') :
    BeliefTarget replayProtocol b' := by
  intro w hw
  obtain ⟨o, ho⟩ := hn
  obtain ⟨_, _, _, hf⟩ := (ho w).mp hw
  exact ⟨hf, trivial⟩

/-- Every certificate field is instantiated for this idealized replay model.
Its trusted idempotent service and immediate return are modeling assumptions,
not conclusions about a deployed service.
-/
noncomputable def replayCertificate : BeliefCertificate replayProtocol where
  policy := fun _ => ()
  region := fun _ => True
  rank := replayRank
  legal := by intros; trivial
  executionsExist := by
    intro b _ _ w _
    exact ⟨fun _ => some (.applied, ()), rfl⟩
  terminates := by
    intro b _ _ w _ execution he
    exact ⟨0, .applied, (), he, rfl, trivial⟩
  prefixesSafe := by intros; trivial
  regionClosed := by intros; trivial
  zeroTarget := by
    intro b _ hz
    exact (replay_rank_zero_iff_target b).mp hz
  decreases := by
    intro b b' _ hnot hn
    have hb : b.possible .absent :=
      Classical.byContradiction (fun h => hnot ((replay_target_iff_no_absent b).mpr h))
    have hb' := (replay_target_iff_no_absent b').mp (replay_successor_is_target hn)
    simp [replayRank, hb, hb']
  targetClosed := by
    intro b b' _ hn
    exact replay_successor_is_target hn

/-- A non-vacuous instantiation of the full finite-prefix theorem: *every*
allowed one-step replay from the ambiguous belief reaches original acceptance.
-/
theorem replay_all_one_step_runs_finish (run : Nat → Belief ReplayWorld)
    (hstart : run 0 = ambiguous)
    (hsteps : ∀ n, n < 1 → BeliefNext replayProtocol (fun _ => ())
      (run n) (run (n + 1))) :
    ∃ n, n ≤ 1 ∧ BeliefTarget replayProtocol (run n) := by
  apply belief_prefix_reaches_original_acceptance replayCertificate 1 run trivial
    (fun n hn _ => hsteps n hn)
  change replayRank (run 0) ≤ 1
  rw [hstart]
  simp [replayRank, ambiguous]

/-! ## Non-vacuous bridge witness with persistently false reports

The actual effect remains absent while every received report claims success.
Both reports are allowed in either world, so this is not a deterministic or
truthful-observation example in disguise. Complete updates preserve both
worlds. It inhabits `MacroRealization` but cannot inhabit a progress certificate
whose region includes this unchanged ambiguous belief.
-/

def deceptiveProtocol : ObservationProtocol
    AgentWorkflow.Evidence.EffectWorld Unit AgentWorkflow.Evidence.EffectReport where
  legal := fun _ _ => True
  safe := fun _ => True
  acceptance := fun world => world = .applied
  emits := AgentWorkflow.Evidence.untrustedEmission
  finish := AgentWorkflow.Evidence.identityStep
  visits := fun _ _ _ => True
  execution := fun world _ execution => execution 0 = some (world, .claimsApplied)

def deceptiveBelief : Belief AgentWorkflow.Evidence.EffectWorld :=
  { possible := fun _ => True, nonempty := ⟨.absent, trivial⟩ }

/-- The new refinement interface is inhabited even when reports are always
false. Only initial containment is supplied; later containment is proved.
-/
def deceptiveRealization : MacroRealization deceptiveProtocol (fun _ => ())
    (fun _ => AgentWorkflow.Evidence.EffectWorld.absent) (fun _ => deceptiveBelief) where
  boundary := fun n => n
  startsAtZero := rfl
  advances := Nat.lt_succ_self
  initiallyPossible := trivial
  observation := fun _ => .claimsApplied
  output := fun _ _ => some (.absent, .claimsApplied)
  executesPolicy := by intro n; rfl
  returnsAtBoundary := by intro n; rfl
  realizesFinish := by intro n; rfl
  realizesObservation := by intro n; trivial
  prefixCoverage := by intros; trivial
  updatesFromObservation := by
    intro n world
    constructor
    · intro _
      exact ⟨trivial, world, trivial, rfl⟩
    · intro _
      trivial

theorem deceptive_reports_keep_absent_possible (n : Nat) :
    (deceptiveBelief).possible AgentWorkflow.Evidence.EffectWorld.absent :=
  deceptiveRealization.possibleAtBoundary n

theorem deceptive_reports_do_not_establish_acceptance :
    ¬ BeliefTarget deceptiveProtocol deceptiveBelief := by
  intro accepted
  have impossible := (accepted .absent trivial).1
  cases impossible

/-- Mere repetition of false success reports cannot satisfy the full progress
contract: the allowed unchanged false belief would have to decrease its own
natural-number rank. This rules out a vacuous claim of progress for this model.
-/
theorem deceptive_only_no_progress_certificate :
    ¬ ∃ c : BeliefCertificate deceptiveProtocol, c.region deceptiveBelief := by
  rintro ⟨c, inRegion⟩
  have unchanged : BeliefNext deceptiveProtocol c.policy deceptiveBelief
      deceptiveBelief := by
    refine ⟨.claimsApplied, ?_⟩
    intro world
    constructor
    · intro _
      exact ⟨trivial, world, trivial, rfl⟩
    · intro _
      trivial
  have impossible := c.decreases inRegion
    deceptive_reports_do_not_establish_acceptance unchanged
  exact Nat.lt_irrefl _ impossible


end AgentWorkflow.Progress
