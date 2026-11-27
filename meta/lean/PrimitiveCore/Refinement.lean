import Std
import PrimitiveCore.Contracts

namespace PrimitiveCore.Refinement

variable {Concrete Abstract : Type}

/-- A concrete-to-abstract relation: each concrete state has an abstract meaning. -/
def Refines (relates : Concrete → Abstract → Prop)
    (concreteInitial : Concrete) (abstractInitial : Abstract) : Prop :=
  relates concreteInitial abstractInitial

/-- Finite abstract executions, including the zero-step execution. -/
inductive Trace (step : Abstract → Abstract → Prop) :
    Abstract → Abstract → Prop where
  | nil (state : Abstract) : Trace step state state
  | cons {first middle last : Abstract} :
      step first middle → Trace step middle last → Trace step first last

/-- Concatenate two adjacent finite traces. -/
def Trace.append {step : Abstract → Abstract → Prop}
    {first middle last : Abstract}
    (prefix : Trace step first middle)
    (suffix : Trace step middle last) : Trace step first last := by
  induction prefix with
  | nil => exact suffix
  | cons transition _ inductionHypothesis =>
      exact Trace.cons transition (inductionHypothesis suffix)

/-- A concrete step is simulated by zero or more abstract steps while preserving R. -/
def StepSimulation
    (relates : Concrete → Abstract → Prop)
    (concreteStep : Concrete → Concrete → Prop)
    (abstractStep : Abstract → Abstract → Prop) : Prop :=
  ∀ {before after abstractBefore},
    relates before abstractBefore →
    concreteStep before after →
    ∃ abstractAfter,
      Trace abstractStep abstractBefore abstractAfter ∧
      relates after abstractAfter

/-- Initial-state correspondence plus step simulation lifts to every finite concrete trace. -/
theorem finite_trace_refinement
    (relates : Concrete → Abstract → Prop)
    (concreteStep : Concrete → Concrete → Prop)
    (abstractStep : Abstract → Abstract → Prop)
    (simulation : StepSimulation relates concreteStep abstractStep)
    {concreteStart concreteEnd : Concrete}
    (concreteTrace : PrimitiveCore.Contracts.Trace concreteStep concreteStart concreteEnd)
    {abstractStart : Abstract}
    (initialCorrespondence : relates concreteStart abstractStart) :
    ∃ abstractEnd,
      Trace abstractStep abstractStart abstractEnd ∧
      relates concreteEnd abstractEnd := by
  induction concreteTrace with
  | nil state =>
      exact ⟨abstractStart, Trace.nil abstractStart, initialCorrespondence⟩
  | cons concreteTransition _ inductionHypothesis =>
      obtain ⟨abstractMiddle, abstractPrefix, middleCorrespondence⟩ :=
        simulation initialCorrespondence concreteTransition
      obtain ⟨abstractEnd, abstractSuffix, finalCorrespondence⟩ :=
        inductionHypothesis middleCorrespondence
      exact ⟨abstractEnd, Trace.append abstractPrefix abstractSuffix, finalCorrespondence⟩

/-- A probe is sound when a positive observation implies its declared assumption. -/
def ProbeSound {Environment : Type}
    (assumption : Environment → Prop)
    (probe : Environment → Bool) : Prop :=
  ∀ environment, probe environment = true → assumption environment

/-- A positive probe establishes the assumption for that observed environment only. -/
theorem probe_establishes_assumption {Environment : Type}
    (assumption : Environment → Prop)
    (probe : Environment → Bool)
    (sound : ProbeSound assumption probe)
    {environment : Environment}
    (observedPositive : probe environment = true) :
    assumption environment :=
  sound environment observedPositive

/-- A failed or unavailable probe provides no proof of the assumption. -/
def ProbeResult (Environment : Type) :=
  Environment → Option Bool

/-- A probe result is tied to an environment snapshot; it says nothing about later snapshots. -/
def SnapshotEvidence {Environment : Type}
    (assumption : Environment → Prop)
    (probe : ProbeResult Environment)
    (environment : Environment) : Prop :=
  probe environment = some true → assumption environment

end PrimitiveCore.Refinement
