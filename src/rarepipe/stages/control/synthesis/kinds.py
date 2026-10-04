"""The closed vocabularies of the synthesis layer.

Kept in one module with no internal imports, so every other module can name a scale, an origin or
a result class without an import cycle. Each enum is closed on purpose: a free-text label would let
a proposer invent a category and smuggle a claim in with it.
"""
from __future__ import annotations

from enum import StrEnum


class TransformationScale(StrEnum):
    """Where a transformation acts. The target may be defined at a different scale than the lesion.

    A population-scale change is not a cellular rescue, and the report must never let one be read
    as the other.
    """

    INTRACELLULAR = "intracellular"
    POPULATION = "population"
    TISSUE_FUNCTION = "tissue_function"


class Direction(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    SET = "set"
    SUPPRESS = "suppress"
    MAINTAIN = "maintain"


class Reversibility(StrEnum):
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


class BlockClass(StrEnum):
    """What kind of thing a building block is. Representable does not mean available."""

    GENE = "gene"
    PROTEIN = "protein"
    ENZYME = "enzyme"
    METABOLITE = "metabolite"
    SMALL_MOLECULE = "small_molecule"
    PHARMACEUTICAL = "pharmaceutical"
    RNA_CONTROL = "rna_control"
    PROTEIN_DEGRADATION = "protein_degradation"
    PROTEIN_STABILIZATION = "protein_stabilization"
    GENE_REGULATION = "gene_regulation"
    CELLULAR_PROCESS = "cellular_process"
    CELL_POPULATION = "cell_population"
    SYNTHETIC_CIRCUIT = "synthetic_circuit"
    EXTERNAL_CONTROL = "external_control"


class CompositionMode(StrEnum):
    """How an architecture's components are composed in time.

    SEQUENTIAL is not a synonym for SIMULTANEOUS: a composition whose order is load-bearing is
    reported as such, and the engine distinguishes the two because pinning one variable changes
    which states the system settles into before the next component acts.
    """

    SEQUENTIAL = "sequential"
    SIMULTANEOUS = "simultaneous"
    CONDITIONAL = "conditional"
    PULSED = "pulsed"
    MAINTENANCE = "maintenance"


class ArchitectureOrigin(StrEnum):
    """How the architecture relates to normal physiology.

    SYNTHETIC_COMPOSITION means the function emerges from combining operations that do not form a
    normal physiological pathway. It carries no epistemic discount and no epistemic credit: the
    verdict comes from reachability, safety and feasibility like every other origin.
    """

    NATURAL_PATHWAY = "natural_pathway"
    NATURAL_BYPASS = "natural_bypass"
    COMPENSATORY = "compensatory"
    SYNTHETIC_COMPOSITION = "synthetic_composition"
    POPULATION_CONTROL = "population_control"
    FEEDBACK_CONTROL = "feedback_control"


class LogicalStatus(StrEnum):
    """Whether a composition reaches the target in the mathematics. Says nothing about feasibility."""

    TARGET_REACHABLE = "TARGET_REACHABLE"
    TARGET_UNREACHABLE = "TARGET_UNREACHABLE"
    REACHABLE_UNDER_SOME_MODELS = "REACHABLE_UNDER_SOME_MODELS"
    UNSAFE = "UNSAFE"
    NOT_REPRESENTABLE = "NOT_REPRESENTABLE"


class PhysicalStatus(StrEnum):
    """Whether the declared transformations can be implemented. Never inferred from the logic."""

    PHYSICALLY_FEASIBLE = "PHYSICALLY_FEASIBLE"
    SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN = "SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN"
    PHYSICALLY_INFEASIBLE = "PHYSICALLY_INFEASIBLE"


class RobustnessClass(StrEnum):
    MODEL_SPECIFIC_CONTROL = "MODEL_SPECIFIC_CONTROL"
    MULTI_MODEL_CONTROL = "MULTI_MODEL_CONTROL"
    ROBUST_CONTROL_CANDIDATE = "ROBUST_CONTROL_CANDIDATE"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    NO_MODEL_SUPPORT = "NO_MODEL_SUPPORT"


class StabilityClass(StrEnum):
    """Reaching the target and holding it are different claims.

    UNKNOWN_STABILITY is the default whenever withdrawal is not modelled. Stability is never
    inferred from the absence of evidence that the state decays.
    """

    TRANSIENT_TARGET = "TRANSIENT_TARGET"
    MAINTAINED_TARGET = "MAINTAINED_TARGET"
    SELF_STABILIZING_TARGET = "SELF_STABILIZING_TARGET"
    UNKNOWN_STABILITY = "UNKNOWN_STABILITY"


class FamilyVerdict(StrEnum):
    """What the compiler can say about a whole family of architectures it was asked to consider."""

    SUPPORTED = "SUPPORTED"
    CONDITIONALLY_SUPPORTED = "CONDITIONALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_REPRESENTABLE = "NOT_REPRESENTABLE"


class SynthesisResultClass(StrEnum):
    ARCHITECTURE_SYNTHESIZED = "ARCHITECTURE_SYNTHESIZED"
    SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN = "SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN"
    ARCHITECTURE_INDETERMINATE = "ARCHITECTURE_INDETERMINATE"
    ARCHITECTURE_MODEL_DISAGREEMENT = "ARCHITECTURE_MODEL_DISAGREEMENT"
    ARCHITECTURE_OBSERVABILITY_INSUFFICIENT = "ARCHITECTURE_OBSERVABILITY_INSUFFICIENT"
    NO_ARCHITECTURE_SYNTHESIZED = "NO_ARCHITECTURE_SYNTHESIZED"
    SPECIFICATION_INCOMPLETE = "SPECIFICATION_INCOMPLETE"


SYNTHESIS_MEANING: dict[SynthesisResultClass, str] = {
    SynthesisResultClass.ARCHITECTURE_SYNTHESIZED:
        "a composition reaches the target under every evidence-compatible model, stays out of the "
        "unsafe region, and every component's implementation is established",
    SynthesisResultClass.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN:
        "a composition reaches the target in the mathematics, but at least one declared "
        "transformation has no demonstrated way to implement it — a successful output, not a "
        "failure",
    SynthesisResultClass.ARCHITECTURE_INDETERMINATE:
        "whether any composition reaches the target depends on biology that is not yet known; the "
        "blockers are named",
    SynthesisResultClass.ARCHITECTURE_MODEL_DISAGREEMENT:
        "evidence-compatible models imply different architectures",
    SynthesisResultClass.ARCHITECTURE_OBSERVABILITY_INSUFFICIENT:
        "a composition may reach the target, but the available measurements cannot distinguish it "
        "from a process that merely looks the same",
    SynthesisResultClass.NO_ARCHITECTURE_SYNTHESIZED:
        "no composition of the registered building blocks reaches the target safely — not a claim "
        "that none exists",
    SynthesisResultClass.SPECIFICATION_INCOMPLETE:
        "what counts as success is not sufficiently defined, so no architecture can be synthesized "
        "for it",
}
