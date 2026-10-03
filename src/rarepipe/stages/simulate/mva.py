"""The MVA_001 causal chain, with each link carrying the evidence that actually stands behind it.

Nothing here is a new scientific claim. Every edge restates what the case's existing hypothesis
set and evidence review already record, in a form a solver and a sensitivity analysis can read.
Where the plan says a link is unresolved, the edge says so and the whole path inherits it.

Parameters are deliberately unvalued. None of the rate constants for this chain has been measured
in a relevant system for this child's variant, so each carries a wide interval and its support
kind rather than a plausible number. A sampler may draw from the interval; nothing may treat the
midpoint as an estimate.
"""
from __future__ import annotations

from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Parameter, Support

# Nodes are biological states, named to match the plan's endpoint keys where one exists.
NIACIN = "nicotinic_acid_exposure"
NAD_BLOOD = "nad_whole_blood"
NAD_CELL = "nad_intracellular"
SIRT2 = "sirt2_activity"
K668 = "k668_acetylation"
BUBR1 = "bubr1_abundance"
BUBR1_FN = "bubr1_residual_function"
CHECKPOINT = "checkpoint_activation"
SILENCING = "checkpoint_silencing"
ALIGNMENT = "chromosome_alignment"
MISSEG = "missegregation"
ANEUPLOIDY = "total_aneuploidy"
DEATH = "cell_death"
DIVISION = "division_rate"

NODES = (
    NIACIN, NAD_BLOOD, NAD_CELL, SIRT2, K668, BUBR1, BUBR1_FN,
    CHECKPOINT, SILENCING, ALIGNMENT, MISSEG, ANEUPLOIDY, DEATH, DIVISION,
)

# Evidence references carried from the case's hypothesis set. The two marked UNVERIFIED appear
# only in the plan seed with no retrieval record; they are labelled so a path through them cannot
# claim measured support. See docs/network/PRD_RESPONSE_SIMULATOR.md section 6.
EV_NIACIN_HUMAN = "PMID:42628241 (UNVERIFIED: no retrieval record)"
EV_NIACIN_NULL = "PMID:42543917 (UNVERIFIED: no retrieval record)"
EV_SIRT2_BUBR1 = "PMID:24825348"
EV_HUMAN_NIACIN_TRIAL = "PMID:32386566"
EV_RESTORED_ABUNDANCE = "PMID:20516114"
EV_DOMAIN_IMPAIRED = "PMID:33207204"


def mva_chain() -> CausalChain:
    """The niacin -> NAD -> SIRT2 -> BubR1 -> checkpoint chain, with its real gaps."""
    edges = (
        # The human NAD evidence is whole blood. That is a different compartment from the one the
        # mechanism needs, and it is the first place the chain weakens.
        CausalEdge(
            source=NIACIN, target=NAD_BLOOD, sign=1,
            mechanism="nicotinic acid raises circulating NAD precursor availability",
            support=Support.HUMAN_EXPERIMENTAL, evidence_ref=EV_NIACIN_HUMAN,
            scope_note="whole-blood NAD in healthy adults",
            parameter=Parameter(
                name="k_niacin_to_blood_nad", unit="fold-change per mM exposure",
                prior=(1.0, 3.0), support=Support.HUMAN_EXPERIMENTAL,
                evidence_ref=EV_NIACIN_HUMAN,
                note="magnitude read from a healthy-adult study; not this cell type"),
        ),
        CausalEdge(
            source=NAD_BLOOD, target=NAD_CELL, sign=1,
            mechanism="circulating precursor reaches the intracellular pool",
            support=Support.DIFFERENT_COMPARTMENT, evidence_ref=EV_NIACIN_HUMAN,
            scope_note="no intracellular measurement in the cited work; blood NAD was the readout",
            caveat="blood-to-cell transfer in the relevant cell type is unmeasured for this case",
            parameter=Parameter(
                name="f_blood_to_intracellular", unit="dimensionless",
                prior=(0.0, 1.0), support=Support.ASSERTED_ONLY,
                note="unmeasured; the interval spans no transfer to complete transfer"),
        ),
        CausalEdge(
            source=NAD_CELL, target=SIRT2, sign=1,
            mechanism="SIRT2 is NAD-dependent, so intracellular NAD gates its activity",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_SIRT2_BUBR1,
            scope_note="NAD-dependence of sirtuin activity in model systems",
            parameter=Parameter(
                name="k_nad_to_sirt2", unit="relative activity per fold NAD",
                prior=(0.0, 2.0), support=Support.MODEL_EXPERIMENTAL,
                evidence_ref=EV_SIRT2_BUBR1, note="not measured for this variant background"),
        ),
        # The decisive substitution: the SIRT2/BubR1 result used NMN, not nicotinic acid.
        CausalEdge(
            source=SIRT2, target=K668, sign=-1,
            mechanism="SIRT2 deacetylates BubR1 at K668",
            support=Support.DIFFERENT_AGENT, evidence_ref=EV_SIRT2_BUBR1,
            scope_note="NMN, not nicotinic acid, in aged mice",
            caveat="the agent that produced this effect is not the agent under consideration",
            parameter=Parameter(
                name="k_sirt2_deacetylation", unit="relative per unit SIRT2",
                prior=(0.0, 2.0), support=Support.DIFFERENT_AGENT,
                evidence_ref=EV_SIRT2_BUBR1, note="measured under a different precursor"),
        ),
        CausalEdge(
            source=K668, target=BUBR1, sign=-1,
            mechanism="reduced K668 acetylation stabilises BubR1",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_SIRT2_BUBR1,
            scope_note="stability effect reported in the same model system",
            parameter=Parameter(
                name="k_acetylation_to_stability", unit="relative abundance",
                prior=(0.0, 2.0), support=Support.MODEL_EXPERIMENTAL,
                evidence_ref=EV_SIRT2_BUBR1, note="not measured for this variant"),
        ),
        # The question the whole case turns on, and the plan records it as unresolved.
        CausalEdge(
            source=BUBR1, target=BUBR1_FN, sign=1,
            mechanism="more of the altered protein yields more residual function",
            support=Support.ASSERTED_ONLY,
            caveat="H01 versus H02: whether this child's altered protein functions at restored "
                   "abundance is unresolved. Published restored-abundance references were read "
                   "for checkpoint activation only, at variant-class rather than exact-allele "
                   "scope.",
            parameter=Parameter(
                name="residual_function_fraction", unit="dimensionless",
                prior=(0.0, 1.0), support=Support.ASSERTED_ONLY,
                note="the unresolved quantity; spans no function to full function"),
        ),
        CausalEdge(
            source=BUBR1_FN, target=CHECKPOINT, sign=1,
            mechanism="functional BubR1 supports spindle assembly checkpoint activation",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_RESTORED_ABUNDANCE,
            scope_note="restored-abundance references, checkpoint activation endpoint",
        ),
        CausalEdge(
            source=BUBR1_FN, target=SILENCING, sign=1,
            mechanism="BubR1 contributes to checkpoint silencing",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_DOMAIN_IMPAIRED,
            scope_note="domain mutation or removal impaired silencing and alignment (abstract)",
        ),
        CausalEdge(
            source=BUBR1_FN, target=ALIGNMENT, sign=1,
            mechanism="BubR1 contributes to chromosome alignment",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_DOMAIN_IMPAIRED,
            scope_note="domain mutation or removal impaired silencing and alignment (abstract)",
        ),
        CausalEdge(
            source=CHECKPOINT, target=MISSEG, sign=-1,
            mechanism="an active checkpoint delays anaphase until attachment is correct",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_RESTORED_ABUNDANCE,
            scope_note="checkpoint-to-missegregation relation in model systems",
        ),
        CausalEdge(
            source=ALIGNMENT, target=MISSEG, sign=-1,
            mechanism="correct alignment reduces missegregation",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_DOMAIN_IMPAIRED,
            scope_note="alignment defects reported alongside segregation errors",
        ),
        CausalEdge(
            source=MISSEG, target=ANEUPLOIDY, sign=1,
            mechanism="missegregation events accumulate as aneuploid cells",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_RESTORED_ABUNDANCE,
            scope_note="segregation errors produce aneuploidy in model systems",
        ),
        # The confounder the decision engine holds on. Kept in the chain so a sensitivity run
        # cannot report improvement without it being visible.
        CausalEdge(
            source=ANEUPLOIDY, target=DEATH, sign=1,
            mechanism="aneuploid cells are lost preferentially",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_RESTORED_ABUNDANCE,
            scope_note="selective loss of aneuploid cells in model systems",
            caveat="H06: apparent improvement can be explained by selective death rather than "
                   "rescue, which is why death and division are read with their denominators",
        ),
        CausalEdge(
            source=DEATH, target=DIVISION, sign=-1,
            mechanism="cell loss reduces the observed division rate",
            support=Support.MODEL_EXPERIMENTAL, evidence_ref=EV_RESTORED_ABUNDANCE,
            scope_note="population-level consequence",
        ),
        # The null result, kept because it is inconvenient.
        CausalEdge(
            source=NIACIN, target=BUBR1, sign=1,
            mechanism="direct niacin-to-BubR1 effect, as the closest related experiment tested it",
            support=Support.CONTRADICTED, evidence_ref=EV_NIACIN_NULL,
            scope_note="the closest related nicotinic-acid experiment was null and reported no "
                       "measurement of the chain",
            caveat="retained deliberately: a null result on the shortest route is evidence about "
                   "the hypothesis, not noise to drop",
        ),
    )
    return CausalChain(chain_id="MVA_001_niacin_bubr1_v1", case_ref="MVA_001",
                       nodes=NODES, edges=edges)
