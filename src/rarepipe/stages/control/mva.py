"""BUB1B / mosaic variegated aneuploidy, compiled as a state-control problem.

Every relationship below restates what the case's existing plan, hypothesis set and evidence review
already record. Nothing new is asserted about the biology. Where the plan records something as
unresolved, the relationship is UNKNOWN_FUNCTION and the compiler must quantify over it.

The decisive unknown is REL_BUBR1_ABUNDANCE_FUNCTION — whether this child's altered protein works
when its abundance is restored (H01 against H02). Nothing here resolves it, and nothing may.

The target is functional checkpoint success. Normal BubR1 abundance is deliberately absent from it:
restoring abundance is one possible route, not the definition of success.
"""
from __future__ import annotations

from itertools import product

from rarepipe.stages.control.actuator_registry import ActuatorCandidate, ActuatorClass
from rarepipe.stages.control.compiler import ExperimentSpec, Problem
from rarepipe.stages.control.controls import (
    BiologicalControlKind, ControlVariable, Feasibility, RouteClass,
)
from rarepipe.stages.control.dynamics import (
    CandidateConstraint, Model, NamedHypothesis, Plausibility, Relationship, RelationshipKind,
)
from rarepipe.stages.control.model_registry import Formalism, ModelRegistryEntry
from rarepipe.stages.control.observability import ObservationModel
from rarepipe.stages.control.provenance import Approval, ApprovalStatus, EpistemicType, Provenance
from rarepipe.stages.control.safety_constraints import SafetyConstraint, UnsafeRegion
from rarepipe.stages.control.state_space import StateSpace, Variable, VariableKind
from rarepipe.stages.control.target_constraints import Membership, TargetConstraint, TargetRegion
from rarepipe.stages.control.uncertainty import StateEvidence

STATE_MODEL_VERSION = "mva-control-state-v1"
CASE_CONTEXT = ("PP_MVA_001_RH_001@0002-455419f1 plan seed definitions; the frozen version on the "
                "controlled store is unchanged by anything here")

EV_RESTORED = "PMID:20516114"
EV_DOMAIN = "PMID:33207204"
PROPOSER = "rarepipe control compiler, MVA case definition (prepared by AI; no human review)"

_PROPOSED_TARGET = Approval(
    status=ApprovalStatus.PROPOSED,
    note="derived from the DRAFT plan's endpoint success criteria; no scientific lead is "
         "appointed, so no constraint is approved")
_PROPOSED_SAFETY = Approval(
    status=ApprovalStatus.PROPOSED,
    note="derived from rules B09 and B16; awaiting an accountable scientist")


def _p(kind: EpistemicType, source: str, *, refs: tuple[str, ...] = (), rationale: str = "") -> Provenance:
    return Provenance(epistemic_type=kind, source=source, proposed_by=PROPOSER,
                      references=refs, rationale=rationale)


def _binary(name, values, meaning, *, ordinal="", latent=False, exogenous_reason=""):
    return Variable(name=name, kind=VariableKind.ORDINAL if ordinal else VariableKind.CATEGORICAL,
                    domain=values, meaning=meaning, ordinal_semantics=ordinal, latent=latent,
                    exogenous=bool(exogenous_reason), exogenous_reason=exogenous_reason)


def state_space() -> StateSpace:
    population = ("intervention-induced population effects belong to the actuator layer and are not "
                  "driven by anything in this biological model; listed as a known omission")
    return StateSpace(variables=(
        _binary("bubr1_abundance", ("low", "restored"), "steady-state level of the altered BubR1 protein",
                ordinal="relative to the wild-type level",
                exogenous_reason="set by the variant's effect on protein level and by any abundance "
                                 "control; the upstream mechanism is represented in the actuator layer"),
        _binary("bubr1_function", ("insufficient", "sufficient"),
                "checkpoint-competent activity of BubR1", ordinal="capacity to support the checkpoint",
                latent=True),
        _binary("kinetochore_localization", ("impaired", "normal"), "BubR1 recruitment to kinetochores"),
        _binary("pp2a_b56_recruitment", ("impaired", "normal"), "PP2A-B56 recruitment by BubR1"),
        _binary("checkpoint_activation", ("impaired", "normal"), "arrest when spindles are disrupted"),
        _binary("checkpoint_silencing", ("impaired", "normal"), "timely exit once chromosomes attach"),
        _binary("chromosome_alignment", ("impaired", "normal"), "chromosome alignment"),
        _binary("missegregation", ("elevated", "normal"), "chromosome-missegregation rate"),
        _binary("total_aneuploidy", ("elevated", "reduced"), "fraction of aneuploid cells"),
        _binary("cell_death", ("baseline", "increased"), "cell death relative to untreated cells",
                exogenous_reason=population),
        _binary("viability", ("baseline", "decreased"), "viability relative to untreated cells",
                exogenous_reason=population),
        _binary("division_rate", ("baseline", "decreased"), "division rate relative to untreated cells",
                exogenous_reason=population),
    ))


def _table(fn, *domains):
    return tuple((ins, fn(*ins)) for ins in product(*domains))


FUNCTION_DOMAIN = ("insufficient", "sufficient")
READOUT = lambda f: "normal" if f == "sufficient" else "impaired"  # noqa: E731


def _readout(rid, output, refs, status, source, rationale=""):
    kind = EpistemicType.LITERATURE_EVIDENCE if refs else EpistemicType.MODEL_ASSUMPTION
    return Relationship(
        relationship_id=rid, inputs=("bubr1_function",), output=output,
        kind=RelationshipKind.TABLE, table=_table(READOUT, FUNCTION_DOMAIN),
        epistemic_status=status, provenance=_p(kind, source, refs=refs, rationale=rationale),
        support=refs, validity_domain="the qualitative relation, not its magnitude or timing",
        required_for=("checkpoint target",))


def _relationships() -> tuple[Relationship, ...]:
    h01 = (( ("low",), "insufficient"), (("restored",), "sufficient"))
    h02 = (( ("low",), "insufficient"), (("restored",), "insufficient"))
    return (
        Relationship(
            relationship_id="REL_BUBR1_ABUNDANCE_FUNCTION",
            inputs=("bubr1_abundance",), output="bubr1_function",
            kind=RelationshipKind.UNKNOWN_FUNCTION,
            candidate_constraint=CandidateConstraint.MONOTONE_NONDECREASING,
            candidate_constraint_rationale="more of the same protein is not assumed to lower its "
                                           "function; without this, the non-monotone candidate is "
                                           "excluded by the diagnosis anyway",
            named_hypotheses=(
                NamedHypothesis(label="H01", statement="adequate abundance of the altered protein "
                                                       "permits useful function", table=h01),
                NamedHypothesis(label="H02", statement="a functional defect remains despite "
                                                       "restored abundance", table=h02),
            ),
            epistemic_status="unresolved",
            provenance=_p(EpistemicType.INFERRED_HYPOTHESIS,
                          "prospective plan hypotheses H01 and H02; EXP01 decision question"),
            support=(EV_RESTORED,), contradictions=(EV_DOMAIN,),
            validity_domain="this child's altered allele; published references are variant-class "
                            "scope and were read for checkpoint activation only",
            required_for=("abundance-control route",)),
        _readout("REL_FUNCTION_ACTIVATION", "checkpoint_activation", (EV_RESTORED,), "established",
                 "restored-abundance reference alleles supported checkpoint activation"),
        _readout("REL_FUNCTION_SILENCING", "checkpoint_silencing", (EV_DOMAIN,), "assumed",
                 "domain loss impaired checkpoint silencing (abstract-level report)"),
        _readout("REL_FUNCTION_ALIGNMENT", "chromosome_alignment", (EV_DOMAIN,), "assumed",
                 "domain loss impaired chromosome alignment (abstract-level report)"),
        _readout("REL_FUNCTION_KINETOCHORE", "kinetochore_localization", (), "assumed",
                 "EXP01 endpoint design", rationale="the plan measures localization as a readout of "
                                                    "the allele's function; not from mechanism evidence"),
        _readout("REL_FUNCTION_PP2A", "pp2a_b56_recruitment", (), "assumed", "EXP01 endpoint design",
                 rationale="the plan measures PP2A-B56 recruitment as a readout of the allele's "
                           "function; not from mechanism evidence"),
        Relationship(
            relationship_id="REL_MISSEGREGATION",
            inputs=("checkpoint_activation", "chromosome_alignment"), output="missegregation",
            kind=RelationshipKind.TABLE,
            table=_table(lambda a, b: "normal" if a == "normal" and b == "normal" else "elevated",
                         ("impaired", "normal"), ("impaired", "normal")),
            epistemic_status="assumed",
            provenance=_p(EpistemicType.MODEL_ASSUMPTION, "causal chain edges checkpoint->"
                          "missegregation and alignment->missegregation",
                          rationale="the chain records each edge separately; combining them so that "
                                    "either defect elevates missegregation is a modelling choice"),
            support=(EV_RESTORED, EV_DOMAIN),
            validity_domain="qualitative; rates and timing are not modelled",
            required_for=("checkpoint target",)),
        Relationship(
            relationship_id="REL_ANEUPLOIDY",
            inputs=("missegregation", "cell_death"), output="total_aneuploidy",
            kind=RelationshipKind.TABLE,
            table=_table(lambda m, d: "elevated" if m == "elevated" and d == "baseline" else "reduced",
                         ("elevated", "normal"), ("baseline", "increased")),
            epistemic_status="assumed",
            provenance=_p(EpistemicType.MODEL_ASSUMPTION, "causal chain: missegregation produces "
                          "aneuploidy; H06 selective loss",
                          rationale="aneuploidy falls either because missegregation normalises or "
                                    "because aneuploid cells die — the confound rules B17/B18 "
                                    "guard against"),
            support=(EV_RESTORED,),
            validity_domain="qualitative; the fate of already-aneuploid cells is not modelled",
            required_for=("observability of the selective-loss confound",)),
    )


def model() -> Model:
    return Model(model_id="MVA_STATE_MODEL_V1", plausibility=Plausibility.ACCEPTED,
                 statement="BubR1 function drives checkpoint behaviour; abundance-to-function is "
                           "unresolved for this allele",
                 relationships=_relationships(),
                 provenance=_p(EpistemicType.MODEL_ASSUMPTION, "rarepipe MVA plan and causal chain",
                               rationale="restates recorded relationships in finite-state form"))


def target() -> TargetRegion:
    def t(cid, var, meaning, criterion):
        return TargetConstraint(
            constraint_id=cid, meaning=meaning, predicate=Membership(variable=var, allowed=("normal",)),
            provenance=_p(EpistemicType.TARGET_CONSTRAINT, f"plan endpoint criterion: {criterion}"),
            approval=_PROPOSED_TARGET)
    return TargetRegion(constraints=(
        t("T_CHECKPOINT_ACTIVATION", "checkpoint_activation", "checkpoint arrests when it should",
          "arrest comparable to the wild-type replacement arm"),
        t("T_CHECKPOINT_SILENCING", "checkpoint_silencing", "checkpoint releases when it should",
          "timely exit comparable to the wild-type replacement arm"),
        t("T_CHROMOSOME_ALIGNMENT", "chromosome_alignment", "chromosomes align",
          "comparable to the wild-type replacement arm"),
        t("T_MISSEGREGATION", "missegregation", "chromosomes segregate correctly",
          "comparable to the wild-type replacement arm"),
    ))


def unsafe() -> UnsafeRegion:
    def s(cid, var, value, meaning, rule):
        return SafetyConstraint(
            constraint_id=cid, meaning=meaning, unsafe_when=Membership(variable=var, allowed=(value,)),
            provenance=_p(EpistemicType.SAFETY_CONSTRAINT, f"decision rule {rule}"),
            approval=_PROPOSED_SAFETY)
    return UnsafeRegion(constraints=(
        s("S_CELL_DEATH", "cell_death", "increased", "more cells die", "B09/B16"),
        s("S_VIABILITY", "viability", "decreased", "fewer cells survive", "B16"),
        s("S_DIVISION", "division_rate", "decreased", "cells divide less", "B16"),
    ))


def evidence() -> tuple[StateEvidence, ...]:
    under = "case intake (stage 01) and stage10-rules-1.2.0 definitions"
    relative = _p(EpistemicType.MODEL_ASSUMPTION, "relative frame",
                  rationale="population variables are expressed relative to the untreated disease "
                            "state, so the untreated state is baseline by definition")
    return (
        StateEvidence(evidence_id="E_DIAGNOSIS", variable="total_aneuploidy", allowed=("elevated",),
                      provenance=_p(EpistemicType.OBSERVED_EMPIRICAL, "clinical diagnosis",
                                    refs=("MVA_001 diagnosis: mosaic variegated aneuploidy",)),
                      generated_under=under),
        StateEvidence(evidence_id="E_MISSEGREGATION", variable="missegregation", allowed=("elevated",),
                      provenance=_p(EpistemicType.MODEL_ASSUMPTION, "disease definition",
                                    rationale="mosaic aneuploidy arises from ongoing missegregation"),
                      generated_under=under),
        StateEvidence(evidence_id="E_DEATH_BASELINE", variable="cell_death", allowed=("baseline",),
                      provenance=relative, generated_under=under),
        StateEvidence(evidence_id="E_VIABILITY_BASELINE", variable="viability", allowed=("baseline",),
                      provenance=relative, generated_under=under),
        StateEvidence(evidence_id="E_DIVISION_BASELINE", variable="division_rate",
                      allowed=("baseline",), provenance=relative, generated_under=under),
    )


def controls() -> tuple[ControlVariable, ...]:
    return (
        ControlVariable(
            control_id="C_RESTORE_ABUNDANCE", sets="bubr1_abundance", to="restored",
            kind=BiologicalControlKind.PROTEIN_STABILITY, route_class=RouteClass.STABILIZATION,
            interpretation="hold the altered BubR1 protein at a restored steady-state abundance, by "
                           "whatever means",
            feasibility=Feasibility.UNASSESSED,
            feasibility_note="no intervention has been shown to restore this variant's abundance in "
                             "a relevant cell type; the nicotinic-acid route is capped in the causal "
                             "chain",
            provenance=_p(EpistemicType.CONTROL_VARIABLE, "plan hypothesis H01 and EXP02 premise")),
        ControlVariable(
            control_id="C_REPLACE_FUNCTION", sets="bubr1_function", to="sufficient",
            kind=BiologicalControlKind.FUNCTIONAL_REPLACEMENT, route_class=RouteClass.REPLACEMENT,
            interpretation="supply checkpoint-competent BubR1 function independently of the altered "
                           "protein's abundance",
            feasibility=Feasibility.UNASSESSED,
            feasibility_note="no evidence on whether this transformation is achievable in the "
                             "relevant cells; proposed as a route class, not as an intervention",
            provenance=_p(EpistemicType.INFERRED_HYPOTHESIS,
                          "control_strategy skill proposal, route class 'replacement'; not human-reviewed")),
    )


def _endpoint_keys() -> dict[str, tuple[str, ...]]:
    from rarepipe.stages.prospective import seed
    from rarepipe.stages.prospective.model import BaselineRef

    plan = seed.seed_plan(BaselineRef(package_path="control-compiler", package_sha256="0" * 64,
                                      manifest_entries=0, manifest_verified=False, stage_runs={},
                                      semantic_digests={}))
    by_id = {e.id: e.key for e in plan.endpoints}
    return {exp.id: tuple(by_id[i] for i in exp.endpoints if i in by_id) for exp in plan.experiments}


def observation(experiment_id: str, keys: tuple[str, ...] | None = None) -> ObservationModel:
    keys = keys if keys is not None else _endpoint_keys()[experiment_id]
    return ObservationModel(name=experiment_id, observed=tuple(keys),
                            provenance=_p(EpistemicType.DECISION_RULE,
                                          f"{experiment_id} endpoint list in the plan seed"),
                            generated_under="stage10-rules-1.2.0 plan seed")


def actuators() -> tuple[ActuatorCandidate, ...]:
    from rarepipe.stages.simulate.mva import BUBR1, NIACIN, mva_chain

    claim = mva_chain().predict(NIACIN, BUBR1)
    nad_evidence = (f"causal chain verdict {claim.verdict}, limited by {claim.weakest_link} "
                    f"({claim.weakest_support.value}); contradicted alternative route: "
                    f"{', '.join(claim.contradicted_alternatives) or 'none'}")
    none_recorded = "no evidence recorded for this variant; listed as a class only"
    return (
        ActuatorCandidate(
            actuator_id="A_NAD_SIRT2_ROUTE", implements_control="C_RESTORE_ABUNDANCE",
            actuator_class=ActuatorClass.METABOLIC_INTERVENTION,
            description="raise intracellular NAD so SIRT2 deacetylates BubR1 at K668 and stabilises "
                        "it — the case's existing nicotinic-acid hypothesis",
            evidence=nad_evidence,
            evidence_refs=("PMID:24825348", "PMID:42628241 (UNVERIFIED)", "PMID:42543917 (UNVERIFIED)"),
            feasibility=Feasibility.UNASSESSED,
            attribution_observables=("nad_intracellular", "sirt2_activity", "k668_acetylation",
                                     "bubr1_abundance")),
        ActuatorCandidate(actuator_id="A_PROTEIN_STABILIZER", implements_control="C_RESTORE_ABUNDANCE",
                          actuator_class=ActuatorClass.PROTEIN_STABILIZER,
                          description="a compound that slows degradation of the altered protein",
                          evidence=none_recorded, feasibility=Feasibility.UNASSESSED),
        ActuatorCandidate(actuator_id="A_EXPRESSION_INCREASE", implements_control="C_RESTORE_ABUNDANCE",
                          actuator_class=ActuatorClass.GENE_REGULATION,
                          description="increase expression of the altered allele",
                          evidence=none_recorded, feasibility=Feasibility.UNASSESSED),
        ActuatorCandidate(actuator_id="A_FUNCTIONAL_MRNA", implements_control="C_REPLACE_FUNCTION",
                          actuator_class=ActuatorClass.MRNA,
                          description="deliver mRNA encoding checkpoint-competent BubR1",
                          evidence=none_recorded, feasibility=Feasibility.UNASSESSED),
        ActuatorCandidate(actuator_id="A_ALLELE_CORRECTION", implements_control="C_REPLACE_FUNCTION",
                          actuator_class=ActuatorClass.GENE_EDITING,
                          description="correct the causal allele in a relevant cell population",
                          evidence=none_recorded, feasibility=Feasibility.UNASSESSED),
    )


def registry() -> tuple[ModelRegistryEntry, ...]:
    return (ModelRegistryEntry(
        model_id="BIOMODELS_SAC_KINETIC_CLASS", version="class-level entry",
        formalism=Formalism.ODE, biological_domains=("spindle assembly checkpoint signalling",),
        variables_supplied=("mcc", "mad2_cdc20", "apc_c", "kinetochore_attachment"),
        relationship_outputs_supplied=("checkpoint_activation", "missegregation"),
        organism="various", cell_type="various", experimental_context="published SAC models",
        units="concentrations and rate constants", validity_domain="checkpoint signalling downstream "
        "of BubR1 activity", known_omissions=("this child's allele", "NAD and SIRT2 biology"),
        uncertainty="model-specific", license="per entry",
        provenance=_p(EpistemicType.MODEL_ASSUMPTION, "proposal to import BioModels SAC entries",
                      rationale="evaluated for admission, not integrated"),
        adapter_version="none"),)


def known_omissions() -> tuple[str, ...]:
    return (
        "Intervention-induced effects on cell death, viability and division belong to the actuator "
        "layer. Nothing in this biological model moves them, so 'safe under the model' says nothing "
        "about any specific intervention — which is why safety variables must be measured directly.",
        "Effects of restored checkpoint function on mitotic timing or arrest are not modelled.",
        "The fate of cells already aneuploid after missegregation normalises is not modelled.",
        "Upstream mechanism (NAD, SIRT2, K668) is represented in the actuator layer, not in the "
        "control dynamics.",
        "Kinetochore localization and PP2A-B56 recruitment are readouts by endpoint design, not "
        "relationships derived from mechanism evidence.",
    )


def assumptions() -> tuple[Provenance, ...]:
    return (
        _p(EpistemicType.MODEL_ASSUMPTION, "initial state",
           rationale="the untreated cells are at steady state under the model's dynamics"),
        _p(EpistemicType.MODEL_ASSUMPTION, "REL_MISSEGREGATION",
           rationale="either a checkpoint or an alignment defect elevates missegregation"),
        _p(EpistemicType.MODEL_ASSUMPTION, "population variables",
           rationale="expressed relative to the untreated disease state"),
        _p(EpistemicType.MODEL_ASSUMPTION, "REL_BUBR1_ABUNDANCE_FUNCTION candidates",
           rationale="restricted to monotone functions; the diagnosis independently excludes the "
                     "non-monotone candidate"),
    )


def experiments(unreachable: dict[str, tuple[str, ...]] | None = None) -> tuple[ExperimentSpec, ...]:
    if unreachable is None:
        from rarepipe.stages.control._reachability_bridge import unreachable_branches
        unreachable = unreachable_branches()
    return (
        ExperimentSpec(experiment_id="EXP01", controls_held=("C_RESTORE_ABUNDANCE",),
                       observation=observation("EXP01"),
                       interpretation="whether restoring abundance is sufficient for checkpoint "
                                      "function — informs abundance -> function -> checkpoint; not "
                                      "gene therapy",
                       unreachable_branches=unreachable.get("EXP01", ())),
        ExperimentSpec(experiment_id="EXP02", controls_held=("C_RESTORE_ABUNDANCE",),
                       observation=observation("EXP02"),
                       interpretation="a control-route test of the nicotinic-acid pathway; an "
                                      "improvement with population deterioration is not control",
                       attribution_actuator="A_NAD_SIRT2_ROUTE",
                       unreachable_branches=unreachable.get("EXP02", ())),
        ExperimentSpec(experiment_id="EXP03", controls_held=("C_RESTORE_ABUNDANCE",),
                       observation=observation("EXP03"),
                       interpretation="replication and relevance of an EXP02 signal",
                       attribution_actuator="A_NAD_SIRT2_ROUTE",
                       unreachable_branches=unreachable.get("EXP03", ())),
    )


def problem() -> Problem:
    from rarepipe.stages.prospective.rules import RULES_VERSION

    return Problem(
        problem_id="MVA_001_STATE_CONTROL", case_ref="MVA_001", space=state_space(),
        evidence=evidence(), target=target(), unsafe=unsafe(), models=(model(),),
        controls=controls(), observation=observation("EXP01"), experiments=experiments(),
        actuators=actuators(), registry=registry(), assumptions=assumptions(),
        known_omissions=known_omissions(), state_model_version=STATE_MODEL_VERSION,
        rule_version=RULES_VERSION, case_context_version=CASE_CONTEXT)
