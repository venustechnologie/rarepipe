"""Claims read out of the retrieved corpus, with verbatim spans.

I read the retrieved abstracts and propose these relations. That is an agent's job and this is an
agent's output: every claim is an `INFERRED_HYPOTHESIS` until the deterministic validators decide
otherwise, and every `source_span` is checked character for character against the stored document, so
a paraphrase fails rather than passes.

Each claim records what its own source says it does **not** establish. That field is the reason three
of these cannot ground a capability, and leaving it out would have made them look stronger than the
papers do.
"""
from __future__ import annotations

from rarepipe.stages.control.discovery.external.claims import (
    CandidateClaim, CausalGrade, ContextLattice,
)
from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.realization.kinds import Effect

EXTRACTOR = "claim-extraction-scientist (AI reading of retrieved abstracts; no human review)"


def _p(reference: str) -> Provenance:
    return Provenance(
        epistemic_type=EpistemicType.INFERRED_HYPOTHESIS,
        source=f"abstract of {reference} in corpus snapshot mva-external-v1",
        proposed_by=EXTRACTOR, references=(reference,),
        rationale="a reading of a retrieved source, not a finding; the validators decide what it "
                  "establishes")


def claims() -> tuple[CandidateClaim, ...]:
    return (
        # --- Gap A: checkpoint activation without the altered protein
        CandidateClaim(
            claim_id="CL_A1_CDK46_SUSTAINS_SAC",
            gap_id="GAP_A_CHECKPOINT_ACTIVATION_WITHOUT_BUBR1",
            source_id="EPMC:PPR1083461",
            subject="mitotic CDK4/6 activity", relation="sustains checkpoint signalling",
            object="checkpoint_activation", direction=Effect.INCREASE, claimed_state="",
            causal_grade=CausalGrade.PERTURBATION_SUPPORTED,
            context=ContextLattice(species="human", cell_type="cancer and non-transformed cell lines",
                                   experimental_system="human cell lines",
                                   perturbation_type="acute CDK4/6 inhibition after G1/S"),
            declared_dependencies=("bubr1_residual_function",),
            source_span=("CDK4 phosphorylates multiple sites on key SAC regulators, including the "
                         "C-terminal tail of CENP-E, which is critical for BubR1 recruitment to "
                         "kinetochores and SAC maintenance"),
            measurement="phosphoproteomics and in vitro kinase assays; mitotic slippage rate",
            limitation=("the source states that residual SAC activity persists, suggesting that "
                        "CDK4/6 strengthens or stabilises SAC signalling rather than being essential "
                        "for its activation"),
            extracted_by=EXTRACTOR, provenance=_p("EPMC:PPR1083461")),

        # --- Gap B: checkpoint silencing without the altered protein
        CandidateClaim(
            claim_id="CL_B1_P31COMET_DISASSEMBLES_MCC",
            gap_id="GAP_B_CHECKPOINT_SILENCING_WITHOUT_BUBR1",
            source_id="PMID:21300909",
            subject="p31comet", relation="disassembles the mitotic checkpoint complex",
            object="checkpoint_silencing", direction=Effect.INCREASE, claimed_state="",
            causal_grade=CausalGrade.MECHANISTIC,
            context=ContextLattice(experimental_system="extracts from checkpoint-arrested cells",
                                   perturbation_type="in vitro reconstitution"),
            source_span=("p31(comet) causes the disassembly of MCC and that this process requires "
                         "β,γ-hydrolyzable ATP. Although p31(comet) binds to Mad2, it promotes the "
                         "dissociation of Cdc20 from BubR1 in MCC"),
            measurement="MCC disassembly in extracts",
            limitation=("the mechanism acts on a complex the source describes as containing the "
                        "forbidden component, so the span cannot establish independence from it"),
            extracted_by=EXTRACTOR, provenance=_p("PMID:21300909")),
        CandidateClaim(
            claim_id="CL_B2_KINETOCHORE_DYNEIN_SILENCING",
            gap_id="GAP_B_CHECKPOINT_SILENCING_WITHOUT_BUBR1",
            source_id="PMID:37126397",
            subject="kinetochore dynein", relation="evicts checkpoint effectors from the corona",
            object="checkpoint_silencing", direction=Effect.INCREASE, claimed_state="",
            causal_grade=CausalGrade.MECHANISTIC,
            context=ContextLattice(experimental_system="mitotic cells",
                                   perturbation_type="dynein perturbation"),
            declared_dependencies=("fibrous corona",),
            source_span=("dynein's role in checkpoint silencing is restricted to evicting checkpoint "
                         "effectors from the fibrous corona, and not the outer kinetochore"),
            measurement="eviction of Mad1 and Mad2 from the corona",
            limitation=("the source states that dynein function in checkpoint silencing becomes "
                        "largely dispensable in cells in which checkpoint effectors are excluded "
                        "from the corona, so it primes rather than produces silencing"),
            extracted_by=EXTRACTOR, provenance=_p("PMID:37126397")),

        # --- Gap C: chromosome alignment without the altered protein
        CandidateClaim(
            claim_id="CL_C1_KIF18A_CONGRESSION",
            gap_id="GAP_C_CHROMOSOME_ALIGNMENT_WITHOUT_BUBR1",
            source_id="PMID:41218610",
            subject="KIF18A", relation="promotes chromosome congression",
            object="chromosome_alignment", direction=Effect.INCREASE, claimed_state="",
            causal_grade=CausalGrade.PERTURBATION_SUPPORTED,
            context=ContextLattice(
                experimental_system="genome-wide Cas9-based functional genetics screen",
                perturbation_type="knockout in a hypomorphic CENP-C background"),
            declared_dependencies=("CENP-E", "CENP-C"),
            source_span=("KIF18A promotes chromosome alignment in cooperation with CENP-E downstream "
                         "of CENP-C during early prometaphase"),
            measurement="synthetic lethality and chromosome alignment in the screen",
            limitation=("the source states the mechanism acts in cooperation with CENP-E downstream "
                        "of CENP-C and says nothing about whether it requires the forbidden "
                        "component; the abstract also does not state the species"),
            extracted_by=EXTRACTOR, provenance=_p("PMID:41218610")),

        # --- Gap D: the chain-closing gap, and the one claim that measures the right compartment
        CandidateClaim(
            claim_id="CL_D1_NIACIN_RAISES_MUSCLE_NAD",
            gap_id="GAP_D_INTRACELLULAR_COFACTOR_ENTRY",
            source_id="PMID:32386566",
            subject="niacin", relation="raises the tissue NAD pool",
            object="nad_intracellular", direction=Effect.INCREASE, claimed_state="",
            causal_grade=CausalGrade.CAUSAL_EXPERIMENTAL,
            context=ContextLattice(
                species="human", tissue="skeletal muscle",
                disease_state="adult-onset mitochondrial myopathy",
                compartment="intracellular (tissue homogenate)",
                experimental_system="human open-label trial with matched controls",
                perturbation_type="administered niacin at an increasing dose"),
            source_span=("Blood NAD+ increased in all subjects, up to 8-fold, and muscle NAD+ of "
                         "patients reached the level of their controls"),
            measurement="muscle NAD+ relative to matched controls",
            limitation=("demonstrated in skeletal muscle of myopathy patients; the source says "
                        "nothing about the cell type this case requires"),
            extracted_by=EXTRACTOR, provenance=_p("PMID:32386566")),
    )
