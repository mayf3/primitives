import Std

/-!
# Time relationships in an explanatory video

Integer ticks have an explicitly tagged clock. Source-media time, edited
presentation time, and a synthetic diagram's time are different types of
interval. A positive affine map supplies a common change of clock. The file
proves properties of that map; it does not assert that an edit implements it.

An interval is half open, `[start, finish)`. Invalid or empty intervals remain
representable so that validity is an explicit predicate, not an assumption
silently supplied by a constructor. Positive overlap uses `max start < min
finish`, and therefore rejects invalid and zero-length intersections.
-/

namespace Video.Temporal

inductive Clock where
  | source
  | presentation
  | schematic
  deriving DecidableEq, Repr

structure Interval (clock : Clock) where
  start : Int
  finish : Int
  deriving DecidableEq, Repr

def valid (i : Interval c) : Prop := i.start < i.finish

def contains (i : Interval c) (t : Int) : Prop := i.start ≤ t ∧ t < i.finish

def overlaps (i j : Interval c) : Prop :=
  max i.start j.start < min i.finish j.finish

instance (i j : Interval c) : Decidable (overlaps i j) :=
  inferInstanceAs (Decidable (max i.start j.start < min i.finish j.finish))

def duration (i : Interval c) : Int := i.finish - i.start

/-- A single shared map is required when comparing several source events.
The scale is a positive integer. Refining both clocks to the same finer tick
unit does not turn a fractional slope into an integer. Fractional speeds need
a rational-map model, or separately specified source/target tick units with a
justified physical-time conversion; neither extension is supplied here.
Rounded timestamps are not covered.
-/
structure Affine (inputClock outputClock : Clock) where
  scale : Int
  offset : Int
  positive : 0 < scale

def Affine.at (m : Affine c d) (t : Int) : Int := m.scale * t + m.offset

def Affine.mapInterval (m : Affine c d) (i : Interval c) : Interval d :=
  ⟨m.at i.start, m.at i.finish⟩

theorem affine_lt_iff (m : Affine c d) (x y : Int) :
    m.at x < m.at y ↔ x < y := by
  constructor
  · intro h
    have hmul : m.scale * x < m.scale * y := by
      unfold Affine.at at h
      omega
    exact Int.lt_of_mul_lt_mul_left hmul (Int.le_of_lt m.positive)
  · intro h
    exact Int.add_lt_add_right (Int.mul_lt_mul_of_pos_left h m.positive) m.offset

theorem affine_le_iff (m : Affine c d) (x y : Int) :
    m.at x ≤ m.at y ↔ x ≤ y := by
  have h := affine_lt_iff m y x
  omega

theorem affine_valid_iff (m : Affine c d) (i : Interval c) :
    valid (m.mapInterval i) ↔ valid i :=
  affine_lt_iff m i.start i.finish

theorem affine_contains_iff (m : Affine c d) (i : Interval c) (t : Int) :
    contains (m.mapInterval i) (m.at t) ↔ contains i t := by
  exact and_congr (affine_le_iff m i.start t) (affine_lt_iff m t i.finish)

/-- Four endpoint inequalities characterize a positive-length intersection,
including validity of the two input intervals. Merely checking two crossed
inequalities would incorrectly accept some reversed input intervals.
-/
theorem overlap_iff_endpoints (i j : Interval c) :
    overlaps i j ↔
      i.start < i.finish ∧ i.start < j.finish ∧
      j.start < i.finish ∧ j.start < j.finish := by
  unfold overlaps
  omega

theorem affine_overlap_iff (m : Affine c d) (i j : Interval c) :
    overlaps (m.mapInterval i) (m.mapInterval j) ↔ overlaps i j := by
  rw [overlap_iff_endpoints, overlap_iff_endpoints]
  exact and_congr (affine_lt_iff m i.start i.finish)
    (and_congr (affine_lt_iff m i.start j.finish)
      (and_congr (affine_lt_iff m j.start i.finish)
        (affine_lt_iff m j.start j.finish)))

theorem affine_duration (m : Affine c d) (i : Interval c) :
    duration (m.mapInterval i) = m.scale * duration i := by
  change (m.scale * i.finish + m.offset) - (m.scale * i.start + m.offset) =
    m.scale * (i.finish - i.start)
  rw [Int.mul_sub]
  omega

/-- Equality by cross multiplication expresses preservation of duration
ratios without integer division. For an ordinary ratio interpretation, the
denominator duration must additionally be nonzero (valid intervals suffice).
-/
theorem affine_duration_ratio (m : Affine c d) (i j : Interval c) :
    duration (m.mapInterval i) * duration j =
      duration i * duration (m.mapInterval j) := by
  rw [affine_duration, affine_duration]
  simp only [Int.mul_assoc, Int.mul_comm, Int.mul_left_comm]

theorem affine_duration_order_iff (m : Affine c d) (i j : Interval c) :
    duration (m.mapInterval i) < duration (m.mapInterval j) ↔
      duration i < duration j := by
  rw [affine_duration, affine_duration]
  have h := affine_lt_iff m (duration i) (duration j)
  unfold Affine.at at h
  omega

/-- Count actual completion endpoints in `(lo, hi]`; each list entry is one
event even when two distinct events have identical intervals. Source event
identity and completeness of this list remain input obligations.
-/
def completedCount (lo hi : Int) : List (Interval c) → Nat
  | [] => 0
  | i :: rest =>
      (if lo < i.finish ∧ i.finish ≤ hi then 1 else 0) + completedCount lo hi rest

theorem affine_completed_count (m : Affine c d) (lo hi : Int)
    (events : List (Interval c)) :
    completedCount (m.at lo) (m.at hi) (events.map m.mapInterval) =
      completedCount lo hi events := by
  induction events with
  | nil => rfl
  | cons i rest ih =>
      simp only [List.map_cons, completedCount, Affine.mapInterval,
        affine_lt_iff, affine_le_iff, ih]

def remaining (initial arrived completed : Nat) : Nat := initial + arrived - completed

/-- The budget premise rules out consumption of nonexistent work; otherwise
natural-number subtraction would silently saturate at zero.
-/
theorem queue_balance (initial arrived completed : Nat)
    (hbudget : completed ≤ initial + arrived) :
    remaining initial arrived completed + completed = initial + arrived := by
  unfold remaining
  omega

/-! ## Counterexamples to unjustified editing inferences -/

def earlySource : Interval .source := ⟨0, 2⟩

def lateSource : Interval .source := ⟨3, 5⟩

def keepStart : Affine .source .presentation := ⟨1, 0, by decide⟩

def alignLate : Affine .source .presentation := ⟨1, -3, by decide⟩

/-- Two individually valid positive affine edits can fabricate overlap when
they do not share the same source-to-presentation map.
-/
theorem independent_alignment_forges_overlap :
    ¬ overlaps earlySource lateSource ∧
      overlaps (keepStart.mapInterval earlySource) (alignLate.mapInterval lateSource) := by
  decide

def squareTime (t : Int) : Int := t * t

def squareInterval (i : Interval .source) : Interval .presentation :=
  ⟨squareTime i.start, squareTime i.finish⟩

theorem square_time_increases_on_nonnegative (x y : Int) (hx : 0 ≤ x) (hxy : x < y) :
    squareTime x < squareTime y := by
  exact Int.mul_lt_mul' (Int.le_of_lt hxy) hxy hx (by omega)

/-- A common nonlinear time map can preserve endpoint order and nevertheless
reverse the ordering of durations: 1 < 2 becomes 7 > 4 after squaring.
-/
theorem nonlinear_map_reverses_duration_order :
    duration (⟨3, 4⟩ : Interval .source) < duration (⟨0, 2⟩ : Interval .source) ∧
      duration (squareInterval ⟨0, 2⟩) < duration (squareInterval ⟨3, 4⟩) := by
  decide

/-! ## Existing synthetic four-window example

These are the explicitly synthetic intervals in `concurrent-replies.json`,
not measurements of an installed Agent or a person's reading speed. The
separate JSON adapter checks that the current repository example still maps
to these constants and sends its actual numeric fields to Lean.
-/

def fourWriters : List (Interval .schematic) :=
  [⟨2, 5⟩, ⟨3, 6⟩, ⟨4, 7⟩, ⟨4, 7⟩]

def firstReader : List (Interval .schematic) := [⟨2, 8⟩]

theorem four_writers_common_interval (t : Int) :
    (∀ i ∈ fourWriters, contains i t) ↔ (4 ≤ t ∧ t < 5) := by
  simp [fourWriters, contains] <;> omega

theorem four_writers_completion_count : completedCount 2 8 fourWriters = 4 := by
  decide

theorem first_reader_completion_count : completedCount 2 8 firstReader = 1 := by
  decide

theorem four_window_remaining :
    remaining 1 (completedCount 2 8 fourWriters) (completedCount 2 8 firstReader) = 4 := by
  decide

end Video.Temporal
