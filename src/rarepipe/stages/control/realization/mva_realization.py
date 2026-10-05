"""The MVA case at the physical layer: what real pieces could implement the required functions.

Every primitive here is declared from a claim the repository already holds. Nothing in this module
introduces a biological fact: each capability cites an edge of the case's own causal chain, so the
support level, the scope and the caveats are the ones already recorded, and a capability cannot be
written for a claim nobody made.

That constraint is the point. The chain holds five citations. Four of them concern the route through
the altered protein's abundance, and the fifth is a null result on the shortest version of that
route. **Nothing in the inventory says anything about supplying checkpoint behaviour by a mechanism
that is not this protein** — so the bypass the synthesis layer found most interesting has, at the
physical layer, nothing to cite. That is a result, and the compiler is built to say it precisely
rather than to fill the gap.

Two problems are compiled, because the contrast is the finding:

* `problem()` targets `BB_CHECKPOINT_BYPASS_CIRCUIT`, the architecture the synthesis layer reports
  as reaching the state target under every evidence-compatible model;
* `abundance_problem()` targets `BB_ABUNDANCE_STABILIZATION`, the one route where the repository
  actually holds a physical chain, so the layer can be seen discriminating rather than refusing
  everything for one blanket reason.
"""
from __future__ import annotations

from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.realization.compiler import RealizationProblem
from rarepipe.stages.control.realization.evidence import EvidenceInventory, inventory_from_repo
from rarepipe.stages.control.realization.kinds import Effect, PrimitiveClass
from rarepipe.stages.control.realization.mechanisms import MechanisticRealization, Step
from rarepipe.stages.control.realization.primitives import (
    Capability, PhysicalPrimitive, PhysicalPrimitiveRegistry,
)
from rarepipe.stages.control.synthesis import mva_synthesis

REALIZATION_MODEL_VERSION = "mva-realization-v1"
REQUIRED_SYSTEM = "patient-derived cells"
PROPOSER = ("rarepipe realization compiler, MVA physical layer (prepared by AI; no human review)")

NICOTINIC_ACID = "nicotinic acid"
NMN = "nicotinamide mononucleotide"


def _p(kind: EpistemicType, source: str, *, refs: tuple[str, ...] = (), rationale: str = "") -> Provenance:
    return Provenance(epistemic_type=kind, source=source, proposed_by=PROPOSER, references=refs,
                      rationale=rationale)


def inventory() -> EvidenceInventory:
    return inventory_from_repo()


def registry() -> PhysicalPrimitiveRegistry:
    unknown_timing = ("unknown; the chain records no time constant for this step and none is "
                      "invented here")
    return PhysicalPrimitiveRegistry(primitives=(
        PhysicalPrimitive(
            primitive_id="PP_NICOTINIC_ACID", primitive_class=PrimitiveClass.PHARMACEUTICAL,
            identity="nicotinic acid, the precursor the case's hypothesis was built around",
            capabilities=(
                Capability(
                    capability_id="CAP_RAISE_CIRCULATING_NAD",
                    claim="raises circulating NAD precursor availability",
                    acts_on="", affects="nad_whole_blood", effect=Effect.INCREASE,
                    agent=NICOTINIC_ACID, compartment="whole blood",
                    evidence_edges=("nicotinic_acid_exposure->nad_whole_blood",)),
                Capability(
                    capability_id="CAP_RAISE_ABUNDANCE_DIRECTLY",
                    claim="raises the altered protein's level without the intervening steps",
                    acts_on="", affects="bubr1_abundance", effect=Effect.INCREASE,
                    agent=NICOTINIC_ACID,
                    evidence_edges=("nicotinic_acid_exposure->bubr1_abundance",)),
            ),
            required_context="oral exposure in a living subject",
            cell_type="not cell-specific; the cited measurement is a circulating one",
            biological_scale="organism", reversibility="reversible on withdrawal of exposure",
            temporal_properties=unknown_timing,
            delivery_requirements="oral; the cited study used healthy adults",
            known_dependencies=("conversion to the intracellular pool, which is unmeasured here",),
            known_safety_effects=("not represented in this state model",),
            evidence="one chain edge supporting the circulating effect, now retrieved and verified. "
                     "The edge that recorded a null on the direct effect lost its citation: the "
                     "document does not support it (REPAIR_R1)",
            validity_domain="whole-blood NAD in healthy adults",
            uncertainty="whether any of it reaches the relevant cells; a human trial measures the "
                        "tissue pool in skeletal muscle, which is a different system",
            feasibility_status="unassessed for this case",
            provenance=_p(EpistemicType.LITERATURE_EVIDENCE, "the case's causal chain",
                          refs=("PMID:42628241",))),

        PhysicalPrimitive(
            primitive_id="PP_NMN", primitive_class=PrimitiveClass.SMALL_MOLECULE,
            identity="nicotinamide mononucleotide, the precursor the cited animal work used",
            capabilities=(
                Capability(
                    capability_id="CAP_RAISE_INTRACELLULAR_NAD",
                    claim="raises the intracellular NAD pool the downstream enzyme depends on",
                    acts_on="", affects="nad_intracellular", effect=Effect.INCREASE, agent=NMN,
                    compartment="intracellular pool",
                    evidence_edges=()),
            ),
            required_context="exposure sufficient to raise the intracellular pool",
            cell_type="unspecified", biological_scale="cell",
            reversibility="reversible on withdrawal of exposure",
            temporal_properties=unknown_timing,
            delivery_requirements="unspecified for this case",
            evidence="no edge in this inventory claims that any agent raises the intracellular "
                     "pool; the chain's only claim about that step is the blood-to-cell transfer, "
                     "which it records as unmeasured",
            validity_domain="none established here",
            uncertainty="the step this primitive is meant to supply is the one the sensitivity "
                        "analysis already identified as unmeasured",
            feasibility_status="unassessed for this case",
            provenance=_p(EpistemicType.INFERRED_HYPOTHESIS, "the agent the cited animal work used",
                          rationale="declared so the gap it would fill is visible and named")),

        PhysicalPrimitive(
            primitive_id="PP_NAD_TRANSFER", primitive_class=PrimitiveClass.CELLULAR_PROCESS,
            identity="whatever carries the circulating precursor into the intracellular pool",
            capabilities=(
                Capability(
                    capability_id="CAP_TRANSFER_TO_CELL",
                    claim="the circulating precursor reaches the intracellular pool",
                    acts_on="nad_whole_blood", acts_by=Effect.INCREASE,
                    affects="nad_intracellular", effect=Effect.INCREASE,
                    compartment="intracellular pool",
                    evidence_edges=("nad_whole_blood->nad_intracellular",),
                    requires=("nad_whole_blood",)),
            ),
            required_context="the cell type the endpoints are measured in",
            cell_type="unmeasured for this case", biological_scale="cell",
            reversibility="follows the circulating level",
            temporal_properties=unknown_timing,
            delivery_requirements="none directly; it is the consequence of the circulating level",
            known_dependencies=("a circulating level raised in the first place",),
            evidence="one chain edge, which the chain records as a different compartment from the "
                     "one the mechanism needs; the cited readout was the circulating pool",
            validity_domain="none established for the intracellular pool",
            uncertainty="this is the step the sensitivity analysis already identified as "
                        "unmeasured, with an interval spanning no transfer to complete transfer",
            feasibility_status="unassessed for this case",
            provenance=_p(EpistemicType.LITERATURE_EVIDENCE, "the case's causal chain",
                          refs=("PMID:42628241",))),

        PhysicalPrimitive(
            primitive_id="PP_NAD", primitive_class=PrimitiveClass.METABOLITE,
            identity="intracellular NAD, the cofactor that gates the deacetylase",
            capabilities=(
                Capability(
                    capability_id="CAP_GATE_DEACETYLASE",
                    claim="NAD-dependence means the intracellular pool gates deacetylase activity",
                    acts_on="nad_intracellular", acts_by=Effect.INCREASE, affects="sirt2_activity",
                    effect=Effect.INCREASE, compartment="intracellular pool",
                    evidence_edges=("nad_intracellular->sirt2_activity",),
                    requires=("nad_intracellular",)),
            ),
            required_context="intracellular", cell_type="model systems in the cited work",
            biological_scale="cell", reversibility="reversible; it is a cofactor dependence",
            temporal_properties=unknown_timing,
            delivery_requirements="none; this is an internal dependence, not an intervention",
            evidence="one chain edge recorded as model-experimental with a verified citation",
            validity_domain="NAD-dependence of sirtuin activity in model systems",
            uncertainty="not measured for this variant background",
            feasibility_status="not an intervention; a dependence the chain records",
            provenance=_p(EpistemicType.LITERATURE_EVIDENCE, "the case's causal chain",
                          refs=("PMID:24825348",))),

        PhysicalPrimitive(
            primitive_id="PP_SIRT2", primitive_class=PrimitiveClass.ENZYME,
            identity="the deacetylase the cited work reports acting on the altered protein",
            capabilities=(
                Capability(
                    capability_id="CAP_REMOVE_ACETYL_MARK",
                    claim="deacetylates the altered protein at the residue the cited work reports",
                    acts_on="sirt2_activity", acts_by=Effect.INCREASE, affects="k668_acetylation",
                    effect=Effect.DECREASE, agent=NMN,
                    evidence_edges=("sirt2_activity->k668_acetylation",),
                    requires=("sirt2_activity",)),
            ),
            required_context="the system the cited work used", cell_type="aged mice in the cited work",
            biological_scale="cell", reversibility="the mark is re-established by acetylation",
            temporal_properties=unknown_timing,
            delivery_requirements="none directly; it is reached through the cofactor",
            evidence="one chain edge, recorded as a different agent than the case's hypothesis used",
            validity_domain="the cited animal system, with the precursor that work used",
            uncertainty="the agent that produced the effect is not the one the case proposed",
            feasibility_status="unassessed for this case",
            provenance=_p(EpistemicType.LITERATURE_EVIDENCE, "the case's causal chain",
                          refs=("PMID:24825348",))),

        PhysicalPrimitive(
            primitive_id="PP_ACETYL_MARK", primitive_class=PrimitiveClass.REGULATORY_ELEMENT,
            identity="the acetylation mark whose removal the cited work links to protein stability",
            capabilities=(
                Capability(
                    capability_id="CAP_STABILISE_PROTEIN",
                    claim="reducing the mark stabilises the altered protein, raising its level",
                    acts_on="k668_acetylation", acts_by=Effect.DECREASE, affects="bubr1_abundance",
                    effect=Effect.INCREASE,
                    evidence_edges=("k668_acetylation->bubr1_abundance",),
                    requires=("k668_acetylation",)),
            ),
            required_context="the system the cited work used", cell_type="aged mice in the cited work",
            biological_scale="cell", reversibility="follows the mark",
            temporal_properties=unknown_timing,
            delivery_requirements="none directly; it is reached through the deacetylase",
            evidence="one chain edge recorded as model-experimental in the same cited system",
            validity_domain="the stability effect reported in that system",
            uncertainty="not measured for this variant",
            feasibility_status="unassessed for this case",
            provenance=_p(EpistemicType.LITERATURE_EVIDENCE, "the case's causal chain",
                          refs=("PMID:24825348",))),
    ))


def _r(kind: EpistemicType, source: str, rationale: str,
       refs: tuple[str, ...] = ()) -> Provenance:
    return _p(kind, source, refs=refs, rationale=rationale)


def bypass_realizations() -> tuple[MechanisticRealization, ...]:
    """What was proposed for the three checkpoint functions, and what it reduces to.

    Only one of the three is given a candidate at all, and that one does not claim a chain: it
    declares the sub-transformation it would reduce to, which the compiler then tries to realize in
    turn. The other two are left without a proposal on purpose, so the report has to say that
    nothing was proposed rather than implying something was tried.
    """
    return (
        MechanisticRealization(
            realization_id="MR_ALIGNMENT_VIA_PHOSPHATASE",
            required_transformation="chromosome_alignment->normal",
            target_variable="chromosome_alignment", target_value="normal",
            required_effect=Effect.SET,
            mechanism=("supply chromosome alignment competence by restoring the phosphatase "
                       "recruitment the altered protein normally mediates, instead of by restoring "
                       "the protein"),
            steps=(),
            context_system=REQUIRED_SYSTEM,
            decomposes_into=("pp2a_b56_recruitment->normal",),
            unknown_steps=("what would recruit the phosphatase in the absence of the altered "
                           "protein is not represented by any primitive in this registry",),
            safety_dependencies=("the cited chain links segregation outcomes to cell death, so any "
                                 "readout here needs cell death measured beside it",),
            provenance=_r(EpistemicType.INFERRED_HYPOTHESIS,
                          "decomposition proposed at the physical layer",
                          "the model attributes alignment to the altered protein, so a bypass has "
                          "to name what else could recruit the phosphatase")),
    )


def abundance_realizations() -> tuple[MechanisticRealization, ...]:
    """Two chains to the same transformation, grounded on different halves of the same evidence."""
    common = dict(required_transformation="bubr1_abundance->restored",
                  target_variable="bubr1_abundance", target_value="restored",
                  required_effect=Effect.INCREASE, context_system=REQUIRED_SYSTEM,
                  safety_dependencies=("the chain links aneuploidy to cell death, so a readout "
                                       "needs cell death and viability measured beside it",),
                  confound_observables=("cell_death", "viability"))
    return (
        MechanisticRealization(
            realization_id="MR_ABUNDANCE_VIA_NICOTINIC_ACID", agent=NICOTINIC_ACID, **common,
            mechanism=("raise the circulating precursor, let it reach the intracellular pool, gate "
                       "the deacetylase, remove the mark, and so stabilise the altered protein"),
            steps=(
                Step(step_id="S1", uses_primitive="PP_NICOTINIC_ACID",
                     capability_id="CAP_RAISE_CIRCULATING_NAD",
                     rationale="the step the human measurement covers"),
                Step(step_id="S1b", uses_primitive="PP_NAD_TRANSFER",
                     capability_id="CAP_TRANSFER_TO_CELL",
                     rationale="declared rather than skipped: the chain needs the intracellular "
                               "pool and the cited readout was the circulating one"),
                Step(step_id="S2", uses_primitive="PP_NAD", capability_id="CAP_GATE_DEACETYLASE",
                     rationale="the cofactor dependence the chain records"),
                Step(step_id="S3", uses_primitive="PP_SIRT2",
                     capability_id="CAP_REMOVE_ACETYL_MARK",
                     rationale="the deacetylation the cited work reports"),
                Step(step_id="S4", uses_primitive="PP_ACETYL_MARK",
                     capability_id="CAP_STABILISE_PROTEIN",
                     rationale="the stability consequence reported in the same system"),
            ),
            provenance=_r(EpistemicType.BUILDING_BLOCK_CAPABILITY,
                          "the case's own hypothesis, compiled as a physical chain",
                          "the route the case was built around, assembled from the chain it came "
                          "from", refs=("PMID:42628241", "PMID:24825348"))),
        MechanisticRealization(
            realization_id="MR_ABUNDANCE_VIA_NMN", agent=NMN, **common,
            mechanism=("raise the intracellular pool directly with the precursor the cited animal "
                       "work used, then follow the same three downstream steps"),
            steps=(
                Step(step_id="S1", uses_primitive="PP_NMN",
                     capability_id="CAP_RAISE_INTRACELLULAR_NAD",
                     rationale="uses the agent the downstream measurement used, which removes the "
                               "agent substitution the other chain carries"),
                Step(step_id="S2", uses_primitive="PP_NAD", capability_id="CAP_GATE_DEACETYLASE",
                     rationale="the cofactor dependence the chain records"),
                Step(step_id="S3", uses_primitive="PP_SIRT2",
                     capability_id="CAP_REMOVE_ACETYL_MARK",
                     rationale="the deacetylation the cited work reports, with its own agent"),
                Step(step_id="S4", uses_primitive="PP_ACETYL_MARK",
                     capability_id="CAP_STABILISE_PROTEIN",
                     rationale="the stability consequence reported in the same system"),
            ),
            provenance=_r(EpistemicType.INFERRED_HYPOTHESIS,
                          "the agent-matched variant of the case's own route",
                          "tests whether matching the agent the measurement used changes what the "
                          "evidence entitles")),
        MechanisticRealization(
            realization_id="MR_ABUNDANCE_DIRECTLY", agent=NICOTINIC_ACID, **common,
            mechanism=("raise the altered protein's level directly with the precursor, skipping "
                       "the intervening steps. No retrieved source addresses this relation in "
                       "either direction"),
            steps=(
                Step(step_id="S1", uses_primitive="PP_NICOTINIC_ACID",
                     capability_id="CAP_RAISE_ABUNDANCE_DIRECTLY",
                     rationale="the shortest route, and the one an experiment already addressed"),
            ),
            provenance=_r(EpistemicType.BUILDING_BLOCK_CAPABILITY,
                          "the shortest version of the case's route",
                          "retained after REPAIR_R1 withdrew the refutation it used to carry: the "
                          "route is now unsupported rather than refuted, which is a weaker claim "
                          "and a different one")),
    )


def problem() -> RealizationProblem:
    """The PRD's first target: realize the bypass that does not depend on the altered protein."""
    return RealizationProblem(
        problem_id="MVA_REALIZATION_BYPASS", case_ref="MVA_001",
        synthesis=mva_synthesis.problem(),
        target_architecture="BB_CHECKPOINT_BYPASS_CIRCUIT",
        registry=registry(), inventory=inventory(), realizations=bypass_realizations(),
        required_system=REQUIRED_SYSTEM, realization_model_version=REALIZATION_MODEL_VERSION)


def abundance_problem() -> RealizationProblem:
    """The one route the repository holds a physical chain for, compiled for contrast."""
    return RealizationProblem(
        problem_id="MVA_REALIZATION_ABUNDANCE", case_ref="MVA_001",
        synthesis=mva_synthesis.problem(),
        target_architecture="BB_ABUNDANCE_STABILIZATION",
        registry=registry(), inventory=inventory(), realizations=abundance_realizations(),
        required_system=REQUIRED_SYSTEM, realization_model_version=REALIZATION_MODEL_VERSION)
