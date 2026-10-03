"""The MVA_001 / RH_001 seed plan (PRD §7, §8, §9).

Seeded from the corrected baseline. The biology stays unresolved: every assay method, threshold,
analysis field and model availability the PRD leaves to a named owner is left null here, and shows up
as an actionable gap. Forecasts are qualitative and conditional, with no numeric probability.
Nothing in the seed asserts that a model, a specimen or a patient cell exists.
"""

from __future__ import annotations

from rarepipe.stages.prospective import rules
from rarepipe.stages.prospective.model import (
    Applicability,
    Assumption,
    BaselineRef,
    CapabilityRequest,
    CapabilityRequestType,
    EndpointSpec,
    EvidenceRef,
    ExperimentKind,
    ExperimentSpec,
    Forecast,
    Hypothesis,
    ModelRequirement,
    ProspectivePlan,
    ResearchTask,
    Role,
    Scope,
    StatementType,
)

PLAN_ID = "PP_MVA_001_RH_001"


def _ep(id_: str, key: str, meaning: str, desired: str, *, unit: str | None = None, denominator: str | None = None,
        required: bool = True, owner: Role = Role.ASSAY_SCIENTIST) -> EndpointSpec:
    return EndpointSpec(id=id_, key=key, biological_meaning=meaning, desired=desired, unit=unit,
                        denominator=denominator, required=required, owner=owner)


def endpoints() -> list[EndpointSpec]:
    return [
        # EXP01 — exact allele residual function
        _ep("E01_EXPR", "expression_comparability", "introduced altered protein at wild-type-comparable abundance, "
            "with endogenous and introduced protein distinguishable", "matched to the wild-type replacement arm"),
        _ep("E01_ACT", "checkpoint_activation", "arrest when spindles are disrupted (nocodazole response)",
            "within the justified reference range of the wild-type replacement arm; a prolonged arrest is not "
            "automatically better"),
        _ep("E01_SIL", "checkpoint_silencing", "timely exit once chromosomes are attached", "timely exit comparable "
            "to the wild-type replacement arm"),
        _ep("E01_ALN", "chromosome_alignment", "chromosome alignment", "comparable to the wild-type replacement arm"),
        _ep("E01_MIS", "missegregation", "chromosome-missegregation rate", "comparable to the wild-type replacement "
            "arm", denominator="per assessable division"),
        _ep("E01_VIA", "viability", "cell viability", "no loss relative to comparators"),
        _ep("E01_DIV", "division_rate", "division rate", "no reduction relative to comparators"),
        _ep("E01_DEATH", "cell_death", "cell death", "no increase"),
        _ep("E01_KT", "kinetochore_localization", "kinetochore localization (mechanistic, optional)",
            "comparable to wild type", required=False),
        _ep("E01_PP2A", "pp2a_b56_recruitment", "PP2A-B56 recruitment (mechanistic, optional)",
            "comparable to wild type", required=False),
        # EXP02 — nicotinic acid mechanism and cellular function
        _ep("E02_NAD", "nad_intracellular", "intracellular NAD+", "increase relative to vehicle"),
        _ep("E02_SIRT2", "sirt2_activity", "SIRT2 activity, where a validated method exists", "increase",
            required=False),
        _ep("E02_ABUN", "bubr1_abundance", "BubR1 abundance", "increase toward the reference"),
        _ep("E02_K668", "k668_acetylation", "BubR1 K668 acetylation, where feasible", "decrease", required=False),
        _ep("E02_ACT", "checkpoint_activation", "checkpoint activation", "toward the justified reference response"),
        _ep("E02_SIL", "checkpoint_silencing", "checkpoint silencing", "timely exit toward the reference"),
        _ep("E02_ALN", "chromosome_alignment", "chromosome alignment", "improvement toward the reference"),
        _ep("E02_MIS", "missegregation", "missegregation", "fewer new errors",
            denominator="per viable assessable division"),
        _ep("E02_ANEU", "total_aneuploidy", "total aneuploidy, recorded separately from new missegregation",
            "no increase", required=False),
        _ep("E02_VIA", "viability", "cell viability", "no decrease"),
        _ep("E02_DEATH", "cell_death", "cell death", "no increase"),
        _ep("E02_DIV", "division_rate", "division rate", "no decrease"),
    ]


def hypotheses() -> list[Hypothesis]:
    ev = EvidenceRef
    return [
        Hypothesis(id="H01", level="allele_function",
                   statement="Adequate abundance of the altered protein permits useful function",
                   evidence=[ev(ref="VX_0007", statement_type=StatementType.LITERATURE_CLAIM,
                                scope_note="I909T at restored abundance, checkpoint activation only",
                                independence_group="PMID:20516114"),
                             ev(ref="VX_0008", statement_type=StatementType.LITERATURE_CLAIM,
                                scope_note="L1012P at restored abundance, checkpoint activation only",
                                independence_group="PMID:20516114", overlaps_with=["VX_0007"])],
                   scope=Scope(genotype_relationship="variant_class", endpoint="checkpoint activation"),
                   dependencies=["A01"], alternatives=["H02"],
                   distinguished_by="matched-abundance exact-allele function study (EXP01)",
                   falsification="a meaningful defect persists at validated matched abundance"),
        Hypothesis(id="H02", level="allele_function",
                   statement="A functional defect remains despite restored abundance",
                   evidence=[ev(ref="MC_IMP_LLMRS_0013_01", statement_type=StatementType.LITERATURE_CLAIM,
                                scope_note="domain mutation/removal impaired silencing and alignment (abstract)",
                                independence_group="PMID:33207204")],
                   scope=Scope(genotype_relationship="gene_level"), alternatives=["H01"],
                   distinguished_by="persistent defects under validated matched-expression conditions"),
        Hypothesis(id="H03", level="drug_upstream",
                   statement="Nicotinic acid does not produce the required intracellular upstream effect in this model",
                   evidence=[ev(ref="PMID:42628241", statement_type=StatementType.LITERATURE_CLAIM,
                                scope_note="whole-blood NAD+ in healthy humans, not intracellular")],
                   distinguished_by="relevant intracellular readouts with assay and exposure validity"),
        Hypothesis(id="H04", level="drug_mechanism",
                   statement="An upstream change occurs but does not improve the SIRT2 to BubR1 connection",
                   evidence=[ev(ref="PMID:24825348", statement_type=StatementType.LITERATURE_CLAIM,
                                scope_note="NMN, not nicotinic acid, in aged mice"),
                             ev(ref="PMID:42543917", statement_type=StatementType.LITERATURE_CLAIM,
                                scope_note="closest related nicotinic-acid experiment was null; it reported no "
                                           "measurement of the chain")],
                   distinguished_by="mechanistic measurements alongside abundance"),
        Hypothesis(id="H05", level="alternative_mechanism",
                   statement="Cellular improvement involves a mechanism outside the proposed chain",
                   distinguished_by="reproducible functional benefit without the predicted mechanistic signature",
                   assessment_note="kept even though it contradicts the favoured explanation (§7)"),
        Hypothesis(id="H06", level="confounding",
                   statement="Apparent benefit is explained by selective death, reduced division or measurement bias",
                   distinguished_by="viability, death, division and independent outcome assessments"),
        Hypothesis(id="H07", level="translation",
                   statement="Cellular benefit is real but not practically translatable",
                   distinguished_by="exposure, model relevance or safety limits identified in later review"),
    ]


def experiments() -> list[ExperimentSpec]:
    return [
        ExperimentSpec(
            id="EXP01", kind=ExperimentKind.ALLELE_FUNCTION,
            decision_question="Is an abundance-only strategy biologically coherent for the altered protein in a "
                              "defined system?",
            model_requirements=[ModelRequirement(
                applicability=Applicability.EXACT_ALLELE_ENGINEERED,
                requirement="locally verified engineered model of the exact missense allele; endogenous and "
                            "introduced protein distinguishable; transcript, isoform and construct identity in the "
                            "private layer. An allele-function experiment, not a recreation of the child's genotype.",
                private_ref="private:exp01-construct")],
            comparators=["wild-type replacement", "deficient or vector control",
                         "restored-abundance reference (I909T or L1012P)",
                         "poorly expressed reference (L844F) where suitable — not a known matched-abundance "
                         "loss-of-function control"],
            endpoints=["E01_EXPR", "E01_ACT", "E01_SIL", "E01_ALN", "E01_MIS", "E01_VIA", "E01_DIV",
                       "E01_DEATH", "E01_KT",
                       "E01_PP2A"],
            interpretation="If matched abundance is not achieved or established, residual function at matched "
                           "abundance stays unresolved. A partial functional response is not full rescue.",
            owners=[Role.SCIENTIFIC_LEAD, Role.ASSAY_SCIENTIST, Role.STATISTICIAN]),
        ExperimentSpec(
            id="EXP02", kind=ExperimentKind.DRUG_MECHANISM_FUNCTION,
            decision_question="Does nicotinic acid improve the required cellular functions in a defined "
                              "BUB1B-deficient model, and does the proposed chain explain that improvement?",
            model_requirements=[
                ModelRequirement(applicability=Applicability.EXACT_ALLELE_ENGINEERED,
                                 requirement="engineered exact-allele model, genotype verified locally",
                                 private_ref="private:exp02-exact-model"),
                ModelRequirement(applicability=Applicability.COMPLETE_GENOTYPE,
                                 requirement="model carrying the complete genotype, genotype verified locally",
                                 private_ref="private:exp02-genotype-model"),
                ModelRequirement(applicability=Applicability.PATIENT_DERIVED,
                                 requirement="patient-derived model only on legitimate availability; none is "
                                             "asserted here, and this plan authorizes no acquisition or contact"),
                ModelRequirement(applicability=Applicability.GENERIC_BUB1B_DEFICIENT,
                                 requirement="generic BUB1B-deficient model; if it is the only feasible model, the "
                                             "limitation is retained in every forecast and export")],
            intervention="nicotinic acid (not nicotinamide, not NMN); reagent identity and exposure recorded",
            comparators=["vehicle or untreated deficient cells", "isogenic or healthy reference cells"],
            endpoints=["E02_NAD", "E02_SIRT2", "E02_ABUN", "E02_K668", "E02_ACT", "E02_SIL", "E02_ALN", "E02_MIS",
                       "E02_ANEU", "E02_VIA", "E02_DEATH", "E02_DIV"],
            interpretation="An abundance increase alone supports only an intermediate step. Viability alone does not "
                           "exclude selection: death and division are recorded with their denominators.",
            owners=[Role.SCIENTIFIC_LEAD, Role.ASSAY_SCIENTIST, Role.STATISTICIAN]),
        ExperimentSpec(
            id="EXP03", kind=ExperimentKind.REPLICATION_RELEVANCE,
            decision_question="Does a reviewable functional signal replicate independently and in another relevant "
                              "context, and is exposure plausibly relevant?",
            trigger="a reviewable functional signal from EXP02, or an unexpected result needing confirmation",
            intervention="as EXP02",
            comparators=["as EXP02"],
            endpoints=["E02_NAD", "E02_ABUN", "E02_ACT", "E02_SIL", "E02_ALN", "E02_MIS", "E02_VIA", "E02_DEATH",
                       "E02_DIV"],
            interpretation="A positive result may unlock a translational-review task; no patient intervention is "
                           "unlocked. Pediatric exposure and safety need clinical pharmacology evidence.",
            owners=[Role.SCIENTIFIC_LEAD, Role.CLINICAL_PHARMACOLOGIST]),
    ]


def forecasts(baseline: BaselineRef) -> list[Forecast]:
    snap = baseline.semantic_digests.get("stage09") or "unpinned"
    cannot = ["patient benefit", "treatment readiness", "the child's endogenous protein behaviour"]
    return [
        Forecast(id="F01", hypothesis="H01", experiment="EXP01", endpoint="E01_ACT",
                 intervention_or_comparator="exact-allele construct vs wild-type replacement at matched abundance",
                 prediction="IF matched abundance is established, checkpoint activation is within the reference "
                            "range, as for other kinase-domain substitutions at restored abundance",
                 expected_direction="comparable to wild-type replacement", assumptions=["A01"],
                 evidence_snapshot=snap,
                 disconfirming_pattern="activation impaired at validated matched abundance",
                 branch_actions={"B03": "permit drug-mechanism planning", "B04": "weaken abundance-only H01"},
                 model_applicability=Applicability.EXACT_ALLELE_ENGINEERED, cannot_conclude=cannot),
        Forecast(id="F02", hypothesis="H02", experiment="EXP01", endpoint="E01_SIL",
                 intervention_or_comparator="exact-allele construct vs wild-type replacement at matched abundance",
                 prediction="UNKNOWN direction: silencing at restored abundance was never reported for any "
                            "kinase-domain substitution, and domain mutation/removal impaired it (abstract)",
                 expected_direction="no directional expectation", assumptions=["A02"], evidence_snapshot=snap,
                 disconfirming_pattern="not applicable: this forecast declares no direction",
                 branch_actions={"B04": "examine H02"},
                 model_applicability=Applicability.EXACT_ALLELE_ENGINEERED, cannot_conclude=cannot),
        Forecast(id="F03", hypothesis="H03", experiment="EXP02", endpoint="E02_NAD",
                 intervention_or_comparator="nicotinic acid vs vehicle",
                 prediction="IF exposure is adequate, intracellular NAD+ rises in the model",
                 expected_direction="increase", assumptions=["A03"], evidence_snapshot=snap,
                 disconfirming_pattern="no intracellular NAD+ rise with adequate precision and exposure",
                 branch_actions={"B05": "investigate H03"},
                 model_applicability=Applicability.GENERIC_BUB1B_DEFICIENT,
                 cannot_conclude=cannot + ["that whole-blood NAD+ findings transfer to these cells"]),
        Forecast(id="F04", hypothesis="H04", experiment="EXP02", endpoint="E02_ABUN",
                 intervention_or_comparator="nicotinic acid vs vehicle",
                 prediction="IF NAD+ rises and SIRT2 is engaged, BubR1 abundance increases",
                 expected_direction="increase", assumptions=["A03", "A04"], evidence_snapshot=snap,
                 disconfirming_pattern="NAD+ rises without any change in BubR1 abundance",
                 branch_actions={"B06": "investigate H04", "B07": "record partial mechanistic response"},
                 model_applicability=Applicability.GENERIC_BUB1B_DEFICIENT, cannot_conclude=cannot),
        Forecast(id="F05", hypothesis="H06", experiment="EXP02", endpoint="E02_MIS",
                 intervention_or_comparator="nicotinic acid vs vehicle",
                 prediction="IF BubR1 function improves, new missegregation per viable assessable division falls "
                            "without more death or slower division",
                 expected_direction="decrease in new errors; death and division unchanged",
                 assumptions=["A01", "A03", "A04"], evidence_snapshot=snap,
                 disconfirming_pattern="fewer errors accompanied by more death or slower division (selection)",
                 branch_actions={"B08": "hold rescue conclusion", "B10": "propose replication"},
                 model_applicability=Applicability.GENERIC_BUB1B_DEFICIENT, cannot_conclude=cannot),
    ]


def assumptions() -> list[Assumption]:
    return [
        Assumption(id="A01", statement="The child's substitution can be expressed at wild-type-comparable abundance",
                   depends_on=["VX_0007", "VX_0008", "VX_0009"], status="ASSUMED"),
        Assumption(id="A02", statement="Checkpoint silencing and alignment are functions of the kinase-like domain "
                                       "that restored-abundance tests did not report",
                   depends_on=["MC_IMP_LLMRS_0013_01", "VX_0016"]),
        Assumption(id="A03", statement="Nicotinic acid reaches the cells at an exposure that can raise intracellular "
                                       "NAD+", depends_on=["PMID:42628241"]),
        Assumption(id="A04", statement="NAD+-dependent SIRT2 activity stabilises BubR1 in this model",
                   depends_on=["PMID:24825348", "PMID:20516114"]),
    ]


def capability_requests() -> list[CapabilityRequest]:
    return [
        CapabilityRequest(id="CR_001", type=CapabilityRequestType.ASSESS_MODEL_AVAILABILITY,
                          extends_node_query_spec="NQS_001",
                          decision_it_could_change="whether EXP01 can run on an exact-allele model",
                          required_capability="an engineered model of the exact missense allele, or permission to "
                                              "build one",
                          permitted_scope="capability only; no variant identity is disclosed in the request",
                          useful_positive_output="a model exists and may be used for this purpose",
                          useful_negative_output="no such model, or not permitted"),
        CapabilityRequest(id="CR_002", type=CapabilityRequestType.ASSESS_ASSAY_CAPABILITY,
                          decision_it_could_change="whether silencing and matched-expression assays are feasible",
                          required_capability="checkpoint activation/silencing, alignment and missegregation assays "
                                              "with matched-expression control",
                          permitted_scope="method capability", useful_positive_output="validated assays and controls",
                          useful_negative_output="assays not available or not validated"),
        CapabilityRequest(id="CR_003", type=CapabilityRequestType.FIND_EXISTING_RESULT,
                          extends_node_query_spec="NQS_002",
                          decision_it_could_change="whether EXP02 is already answered anywhere",
                          required_capability="an existing measurement of nicotinic acid in BUB1B-deficient cells",
                          permitted_scope="aggregate result only",
                          useful_positive_output="a measured effect with its context",
                          useful_negative_output="measured with no effect (distinct from not searched or no data)"),
        CapabilityRequest(id="CR_004", type=CapabilityRequestType.REQUEST_FEASIBILITY_ESTIMATE,
                          decision_it_could_change="EXP02 cost and time",
                          required_capability="cost, time and burden estimate for EXP02",
                          permitted_scope="estimate only; no order to perform work",
                          useful_positive_output="an estimate with assumptions",
                          useful_negative_output="cannot estimate without more specification"),
    ]


def tasks() -> list[ResearchTask]:
    return [
        ResearchTask(id="T_001", origin="EXP01", type="capability_request", owner=Role.RESEARCH_OPERATIONS,
                     description="prepare CR_001 (model availability) for authorization review; do not send"),
        ResearchTask(id="T_002", origin="EXP01", type="assay_specification", owner=Role.ASSAY_SCIENTIST,
                     description="specify methods, controls, validity and effect thresholds for EXP01 endpoints"),
        ResearchTask(id="T_003", origin="EXP02", type="assay_specification", owner=Role.ASSAY_SCIENTIST,
                     description="specify methods, exposure, controls and thresholds for EXP02 endpoints"),
        ResearchTask(id="T_004", origin="EXP01", type="analysis_specification", owner=Role.STATISTICIAN,
                     description="complete the §8.4 analysis fields for EXP01 and EXP02"),
        ResearchTask(id="T_005", origin="plan", type="clinical_goal", owner=Role.TREATING_CLINICIAN,
                     description="state the patient-relevant goal and observation horizon, if known"),
    ]


def seed_plan(baseline: BaselineRef) -> ProspectivePlan:
    return ProspectivePlan(
        plan_id=PLAN_ID, case_ref="MVA_001",
        decision_question="Is it worth testing whether nicotinic acid improves BubR1-dependent cellular function, "
                          "and does this child's altered protein work when its abundance is restored?",
        baseline=baseline, hypotheses=hypotheses(), assumptions=assumptions(), endpoints=endpoints(),
        experiments=experiments(), forecasts=forecasts(baseline), rules=rules.descriptors(),
        rules_version=rules.RULES_VERSION, tasks=tasks(), capability_requests=capability_requests(),
        blockers=["exact model availability and permitted use unknown",
                  "assay methods, comparators and validity thresholds not set",
                  "meaningful effects, replication and uncertainty analysis not set",
                  "no scientific reviews recorded"])
