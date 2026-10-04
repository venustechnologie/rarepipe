"""The four capability gaps this phase was asked to run, and the universe they are searched in.

Three are bypass gaps: supply a checkpoint function without depending on the altered protein. One is
a chain-closing gap: find anything that raises the intracellular cofactor pool, the single step the
previous phase showed nothing in this repository grounds.

The two kinds are both needed. If only the bypass gaps were run and nothing was found, there would
be no way to tell a weak discovery mechanism from a genuinely hard space. If only the chain-closing
gap were run, the phase could demonstrate retrieval without demonstrating discovery.

**Mechanism hypotheses here name classes of mechanism, never entities.** That is what the type is
for, and it is the only honest thing an agent can contribute without a source: proposing that a
function might be supplied by a localisation module, or by a phosphatase-recruitment module, is a
direction to search. Proposing a named protein would be asserting biology, and this module does not
hold a corpus that could support one.
"""
from __future__ import annotations

from rarepipe.stages.control.discovery.candidates import MechanismHypothesis
from rarepipe.stages.control.discovery.compiler import GapProblem
from rarepipe.stages.control.discovery.gaps import CapabilityGap, RequiredContext
from rarepipe.stages.control.discovery.providers import (
    CuratedFileProvider, RepositoryProvider,
)
from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.realization import mva_realization
from rarepipe.stages.control.realization.evidence import inventory_from_repo
from rarepipe.stages.control.realization.kinds import Effect, EpistemicBurden

DISCOVERY_MODEL_VERSION = "mva-discovery-v1"
FORBIDDEN = "bubr1_residual_function"
SYSTEM = "patient-derived cells"
PROPOSER = "rarepipe discovery compiler, MVA capability gaps (prepared by AI; no human review)"


def _hypothesis(hid: str, gap_id: str, mechanism_class: str, statement: str,
                rationale: str) -> MechanismHypothesis:
    return MechanismHypothesis(
        hypothesis_id=hid, gap_id=gap_id, mechanism_class=mechanism_class, statement=statement,
        avoids=(FORBIDDEN,), rationale=rationale,
        provenance=Provenance(epistemic_type=EpistemicType.MECHANISM_HYPOTHESIS,
                              source="capability gap reasoning over the required interface",
                              proposed_by=PROPOSER,
                              rationale="a class of mechanism to search for, not an entity claim"))


def _bypass_gap(gap_id: str, output: str, burden: EpistemicBurden, meaning: str,
                missing: str) -> CapabilityGap:
    return CapabilityGap(
        gap_id=gap_id, required_transformation=f"{output}->normal", required_output=output,
        required_value="normal", required_direction=Effect.SET,
        forbidden_dependencies=(FORBIDDEN,),
        required_context=RequiredContext(compartment="", system=SYSTEM),
        biological_scale="intracellular",
        forbidden_states=("cell_death=increased", "viability=decreased",
                          "division_rate=decreased"),
        epistemic_burden=burden,
        observables_needed=(output, "cell_death", "viability"),
        current_known_paths=(f"{FORBIDDEN} -> {output}, the only claim the inventory holds for it",),
        current_missing_reason=missing, rationale=meaning)


def gaps() -> tuple[CapabilityGap, ...]:
    return (
        _bypass_gap(
            "GAP_A_CHECKPOINT_ACTIVATION_WITHOUT_BUBR1", "checkpoint_activation",
            EpistemicBurden.BYPASSES_ESTABLISHED_RELATIONSHIP,
            meaning=("the cell must be able to hold division when the chromosomes are not yet "
                     "correctly attached, by something that is not the altered protein"),
            missing=("the only claim the inventory holds about this output attributes it to the "
                     "altered protein, and the relationship is recorded as established, so a "
                     "substitute carries the highest burden in the scheme")),
        _bypass_gap(
            "GAP_B_CHECKPOINT_SILENCING_WITHOUT_BUBR1", "checkpoint_silencing",
            EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP,
            meaning=("the checkpoint must also switch off correctly once it is safe to continue "
                     "dividing, by something that is not the altered protein"),
            missing=("the only claim the inventory holds about this output attributes it to the "
                     "altered protein, from a source adjudicated from its abstract alone")),
        _bypass_gap(
            "GAP_C_CHROMOSOME_ALIGNMENT_WITHOUT_BUBR1", "chromosome_alignment",
            EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP,
            meaning=("chromosomes must reach correct alignment before they separate, by something "
                     "that is not the altered protein"),
            missing=("the only claim the inventory holds about this output attributes it to the "
                     "altered protein. The previous phase decomposed this gap towards phosphatase "
                     "recruitment, and the inventory holds no claim at all about that node, so the "
                     "decomposition does not move the problem into better-evidenced territory")),
        CapabilityGap(
            gap_id="GAP_D_INTRACELLULAR_COFACTOR_ENTRY",
            required_transformation="nad_intracellular->increased",
            required_output="nad_intracellular", required_direction=Effect.INCREASE,
            forbidden_dependencies=(),
            required_context=RequiredContext(compartment="intracellular pool", system=SYSTEM),
            biological_scale="intracellular",
            forbidden_states=("cell_death=increased", "viability=decreased"),
            epistemic_burden=EpistemicBurden.BYPASSES_UNRESOLVED_RELATIONSHIP,
            observables_needed=("nad_intracellular",),
            current_known_paths=("nad_whole_blood -> nad_intracellular, which the chain records as "
                                 "a different compartment from the one the mechanism needs",),
            current_missing_reason=(
                "the previous phase found that no chain in this repository grounds raising the "
                "intracellular pool: the one claim about it measured the circulating pool instead. "
                "This gap is the methodological control, because the steps after it are already "
                "grounded, so a success here would close a nearly complete chain"),
            rationale=("find any actuator whose evidence supports raising the intracellular "
                       "cofactor pool in the required system")),
    )


def hypotheses() -> tuple[MechanismHypothesis, ...]:
    """Classes of mechanism to search for. No entity is named, because none could be cited."""
    return (
        _hypothesis("MH_A1", "GAP_A_CHECKPOINT_ACTIVATION_WITHOUT_BUBR1",
                    "kinetochore signalling module",
                    "A module that generates the arrest signal at unattached kinetochores without "
                    "requiring the altered protein as a scaffold could supply arrest competence.",
                    "the required output is a signalling state, so a different generator of the "
                    "same signal is the structurally distinct option"),
        _hypothesis("MH_A2", "GAP_A_CHECKPOINT_ACTIVATION_WITHOUT_BUBR1",
                    "anaphase-promoting inhibition module",
                    "Holding the downstream degradation machinery inhibited for long enough would "
                    "produce the same arrest without reconstructing the upstream signal.",
                    "acting downstream of the lesion is the other way to avoid depending on it"),
        _hypothesis("MH_B1", "GAP_B_CHECKPOINT_SILENCING_WITHOUT_BUBR1",
                    "phosphatase-recruitment module",
                    "A module that recruits the opposing phosphatase activity could allow timely "
                    "silencing without the altered protein mediating the recruitment.",
                    "silencing requires reversal of a signal, so supplying the reversing activity "
                    "is the direct interface"),
        _hypothesis("MH_C1", "GAP_C_CHROMOSOME_ALIGNMENT_WITHOUT_BUBR1",
                    "attachment-error correction module",
                    "A module that corrects incorrect attachments independently of the altered "
                    "protein could produce alignment competence.",
                    "alignment is the outcome of error correction, which is a separable function"),
        _hypothesis("MH_D1", "GAP_D_INTRACELLULAR_COFACTOR_ENTRY",
                    "transport or salvage module",
                    "Any actuator whose evidence measures the intracellular pool itself, rather "
                    "than a circulating pool, would close this step.",
                    "the gap is a compartment problem, so the discriminating property of a "
                    "candidate is what compartment its evidence measured"),
    )


def problem() -> GapProblem:
    inventory = inventory_from_repo()
    control = mva_realization.problem().synthesis.problem
    return GapProblem(
        problem_id="MVA_CAPABILITY_GAPS", case_ref="MVA_001", gaps=gaps(), inventory=inventory,
        space=control.space,
        providers=(RepositoryProvider(inventory), CuratedFileProvider(None)),
        discovery_model_version=DISCOVERY_MODEL_VERSION, hypotheses=hypotheses())


def targets():
    return (mva_realization.problem(), mva_realization.abundance_problem())
