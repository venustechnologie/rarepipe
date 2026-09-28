"""The outcome-branch engine: three-valued predicates over an observation vector (PRD §10).

Every predicate is TRUE, FALSE or UNKNOWN (Kleene logic; UNKNOWN is `None`). Missing required data
yields UNKNOWN and an information request, never a default. All matching branches are kept. Integrity
and quality gates decide whether a scientific conclusion is admissible; a critical adverse flag creates
a hold-and-review task even when the result itself is unverified. When proposed actions contradict each
other the record becomes DECISION_REVIEW_REQUIRED — no branch wins by precedence alone.

No action here reaches a patient (FR-007): the furthest step is a translational-review task.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rarepipe.stages.prospective.model import (
    EndpointSpec,
    ExperimentKind,
    Knowledge,
    Observation,
    ResearchTask,
    Role,
    RuleDescriptor,
)

RULES_VERSION = "stage10-rules-1.0.0"
Tri = bool | None
T, F, U = True, False, None

FUNCTION_KEYS = ("checkpoint_activation", "checkpoint_silencing", "chromosome_alignment", "missegregation")
MECHANISM_KEYS = ("bubr1_abundance", "sirt2_activity", "k668_acetylation")
MISSING = {Knowledge.UNKNOWN, Knowledge.NOT_MEASURED, Knowledge.NOT_REPORTED, Knowledge.UNAVAILABLE,
           Knowledge.NOT_APPLICABLE}

# ── Kleene logic ─────────────────────────────────────────────────────────────


def and3(*xs: Tri) -> Tri:
    if any(x is False for x in xs):
        return F
    return U if any(x is None for x in xs) else T


def or3(*xs: Tri) -> Tri:
    if any(x is True for x in xs):
        return T
    return U if any(x is None for x in xs) else F


def not3(x: Tri) -> Tri:
    return None if x is None else (not x)


def show(x: Tri) -> str:
    return {True: "TRUE", False: "FALSE", None: "UNKNOWN"}[x]


# ── actions ──────────────────────────────────────────────────────────────────

ACTIONS = {
    "B00": ["QUARANTINE_INTERPRETATION", "RESOLVE_PROVENANCE_OR_ASSAY_ISSUES"],
    "B01": ["KEEP_AFFECTED_HYPOTHESES_UNRESOLVED", "IMPROVE_EXPERIMENT_OR_EVIDENCE"],
    "B02": ["KEEP_MATCHED_ABUNDANCE_FUNCTION_UNRESOLVED"],
    "B03": ["STRENGTHEN_H01_FOR_MEASURED_ENDPOINTS", "PERMIT_DRUG_MECHANISM_PLANNING"],
    "B04": ["WEAKEN_ABUNDANCE_ONLY_H01_IN_CONTEXT", "EXAMINE_H02"],
    "B05": ["INVESTIGATE_H03"],
    "B06": ["INVESTIGATE_H04"],
    "B07": ["RECORD_PARTIAL_MECHANISTIC_RESPONSE", "EXAMINE_RESIDUAL_FUNCTIONAL_LIMITATIONS"],
    "B08": ["HOLD_RESCUE_CONCLUSION", "INVESTIGATE_H06"],
    "B09": ["HOLD_PROGRESSION", "CREATE_SCIENTIFIC_REVIEW"],
    "B10": ["RECORD_CANDIDATE_FUNCTIONAL_SIGNAL", "PROPOSE_INDEPENDENT_REPLICATION"],
    "B11": ["PRESERVE_SIGNAL", "INVESTIGATE_H05"],
    "B12": ["HOLD_TRANSLATIONAL_PROGRESSION", "INVESTIGATE_H07"],
    "B13": ["CREATE_TRANSLATIONAL_REVIEW_TASK"],
    "B14": ["SHOW_DISAGREEMENT", "REQUIRE_EXPLICIT_INTERPRETATION", "HOLD_RESCUE_CONCLUSION"],
    "B15": ["RECORD_UNMODELLED_OBSERVATION", "CREATE_MODEL_REVISION_TASK"],
}
INCOMPATIBLE = {
    "PROPOSE_INDEPENDENT_REPLICATION": {"HOLD_PROGRESSION", "HOLD_RESCUE_CONCLUSION", "QUARANTINE_INTERPRETATION"},
    "CREATE_TRANSLATIONAL_REVIEW_TASK": {"HOLD_PROGRESSION", "HOLD_TRANSLATIONAL_PROGRESSION",
                                         "HOLD_RESCUE_CONCLUSION", "QUARANTINE_INTERPRETATION"},
    "PERMIT_DRUG_MECHANISM_PLANNING": {"HOLD_PROGRESSION", "QUARANTINE_INTERPRETATION"},
}
TASK_FOR_ACTION: dict[str, tuple[str, Role, str]] = {
    "RESOLVE_PROVENANCE_OR_ASSAY_ISSUES": ("provenance_resolution", Role.RESEARCH_OPERATIONS,
                                           "resolve source/sample identity and quality issues before interpretation"),
    "IMPROVE_EXPERIMENT_OR_EVIDENCE": ("experiment_revision", Role.ASSAY_SCIENTIST,
                                       "improve precision, controls or the missing readout"),
    "PERMIT_DRUG_MECHANISM_PLANNING": ("drug_mechanism_planning", Role.SCIENTIFIC_LEAD,
                                       "plan EXP02 for the measured endpoints only"),
    "EXAMINE_H02": ("hypothesis_investigation", Role.SCIENTIFIC_LEAD, "examine a persistent functional defect (H02)"),
    "INVESTIGATE_H03": ("hypothesis_investigation", Role.SCIENTIFIC_LEAD,
                        "investigate the intracellular upstream effect in this model (H03)"),
    "INVESTIGATE_H04": ("hypothesis_investigation", Role.SCIENTIFIC_LEAD,
                        "separate the upstream change from the SIRT2–BubR1 connection (H04)"),
    "EXAMINE_RESIDUAL_FUNCTIONAL_LIMITATIONS": ("hypothesis_investigation", Role.SCIENTIFIC_LEAD,
                                                "examine why more protein did not restore function"),
    "INVESTIGATE_H06": ("confounding_review", Role.STATISTICIAN,
                        "review death, division and selection as explanations (H06)"),
    "CREATE_SCIENTIFIC_REVIEW": ("scientific_hold_review", Role.SCIENTIFIC_LEAD,
                                 "review the adverse cellular direction before any progression"),
    "PROPOSE_INDEPENDENT_REPLICATION": ("replication_proposal", Role.SCIENTIFIC_LEAD,
                                        "propose an independent replication (EXP03); record what is independent"),
    "INVESTIGATE_H05": ("hypothesis_investigation", Role.SCIENTIFIC_LEAD,
                        "investigate a mechanism outside the proposed chain (H05)"),
    "INVESTIGATE_H07": ("translational_assessment", Role.CLINICAL_PHARMACOLOGIST,
                        "assess exposure feasibility and relevance (H07); no values are assumed"),
    "CREATE_TRANSLATIONAL_REVIEW_TASK": ("translational_review", Role.TREATING_CLINICIAN,
                                         "translational review only: decide whether further preclinical work or "
                                         "clinician-led study planning is warranted. No patient intervention."),
    "REQUIRE_EXPLICIT_INTERPRETATION": ("interpretation_review", Role.SCIENTIFIC_LEAD,
                                        "interpret conflicting endpoints explicitly"),
    "CREATE_MODEL_REVISION_TASK": ("model_revision", Role.SCIENTIFIC_LEAD,
                                   "the result fits no modelled branch: revise the model"),
}
HYPOTHESIS_UPDATES = {
    "B03": {"H01": "STRENGTHENED"}, "B04": {"H01": "WEAKENED", "H02": "UNDER_INVESTIGATION"},
    "B05": {"H03": "UNDER_INVESTIGATION"}, "B06": {"H04": "UNDER_INVESTIGATION"},
    "B07": {"H02": "UNDER_INVESTIGATION"}, "B08": {"H06": "UNDER_INVESTIGATION"},
    "B11": {"H05": "UNDER_INVESTIGATION"}, "B12": {"H07": "UNDER_INVESTIGATION"},
}
BRANCH_TEXT = {
    "B00": "source or sample identity unverified, or quality criteria failed: scientific interpretation quarantined",
    "B01": "precision inadequate, controls inconclusive or a required readout missing: affected hypotheses stay "
           "unresolved",
    "B02": "matched abundance not established: function at matched abundance stays unresolved",
    "B03": "matched abundance with the specified functional improvement: strengthens H01 for the measured "
           "endpoints only",
    "B04": "matched abundance with a persisting defect: weakens an abundance-only H01 in this context",
    "B05": "the required upstream effect is absent with adequate precision: investigate H03; this is not evidence "
           "of a general protein-function failure",
    "B06": "upstream effect present, expected mechanistic response absent: challenges the bridge in the tested "
           "context (H04); not a universal drug-failure claim",
    "B07": "abundance rises without the required functional improvement: a partial mechanistic response",
    "B08": "apparent improvement accompanied by more death, less division or selection: rescue conclusion held (H06)",
    "B09": "adverse cellular direction or predefined harm criterion: progression held for scientific review",
    "B10": "interpretable functional benefit with viability and division checks: a candidate functional signal",
    "B11": "benefit without the predicted mechanistic signature: signal preserved, original mechanism not proved (H05)",
    "B12": "replicated signal with exposure feasibility or relevance unresolved or adverse: translation held (H07)",
    "B13": "replication and relevance justify further assessment: translational-review task only",
    "B14": "valid results conflict across endpoints: disagreement shown, explicit interpretation required",
    "B15": "valid result fits no modelled branch: recorded as unmodelled, model revision required",
}


def descriptors() -> list[RuleDescriptor]:
    exp01, exp02, exp03 = (ExperimentKind.ALLELE_FUNCTION, ExperimentKind.DRUG_MECHANISM_FUNCTION,
                           ExperimentKind.REPLICATION_RELEVANCE)
    every = [exp01, exp02, exp03]
    drug = [exp02, exp03]
    required = {
        "B00": ["qc.identity_verified", "qc.provenance_verified"],
        "B01": ["qc.precision_adequate", "qc.controls_valid", "required readouts"],
        "B02": ["expression_comparability"], "B03": ["expression_comparability", *FUNCTION_KEYS],
        "B04": ["expression_comparability", *FUNCTION_KEYS], "B05": ["nad_intracellular"],
        "B06": ["nad_intracellular", *MECHANISM_KEYS], "B07": ["bubr1_abundance", *FUNCTION_KEYS],
        "B08": [*FUNCTION_KEYS, "viability", "cell_death", "division_rate"],
        "B09": ["qc.critical_adverse_flag", *FUNCTION_KEYS, "cell_death"],
        "B10": [*FUNCTION_KEYS, "viability", "cell_death", "division_rate"],
        "B11": [*FUNCTION_KEYS, *MECHANISM_KEYS], "B12": ["context.replicated", "context.exposure_feasible",
                                                          "context.relevance_review"],
        "B13": ["context.replicated", "context.exposure_feasible", "context.relevance_review"],
        "B14": [*FUNCTION_KEYS], "B15": ["all of the above"],
    }
    applies = {"B02": [exp01], "B03": [exp01], "B04": [exp01], "B05": drug, "B06": drug, "B07": drug,
               "B11": drug, "B12": drug, "B13": [exp03]}
    return [RuleDescriptor(id=f"R_{b}", version=RULES_VERSION, branch=b, applies_to=applies.get(b, every),
                           required_inputs=required[b], actions=ACTIONS[b], rationale=BRANCH_TEXT[b])
            for b in ACTIONS]


# ── evaluation ───────────────────────────────────────────────────────────────


@dataclass
class Evaluation:
    predicates: dict[str, str] = field(default_factory=dict)
    matches: list[str] = field(default_factory=list)
    inadmissible: list[str] = field(default_factory=list)
    unknown_inputs: list[str] = field(default_factory=list)
    information_requests: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    conflicts: list[list[str]] = field(default_factory=list)
    interpretation: list[str] = field(default_factory=list)
    cannot_conclude: list[str] = field(default_factory=list)
    hypothesis_updates: dict[str, str] = field(default_factory=dict)
    tasks: list[ResearchTask] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "DECISION_REVIEW_REQUIRED" if self.conflicts else "PROPOSED"


class Vector:
    """Reads categories from an observation. Anything missing or inconclusive reads as UNKNOWN."""

    def __init__(self, obs: Observation, required: list[EndpointSpec]):
        self.obs = obs
        self.values = {v.endpoint_key: v for v in obs.values}
        self.required = required
        self.unknown: list[str] = []

    def category(self, key: str):
        v = self.values.get(key)
        if v is None or v.category is None or v.category in MISSING or v.category == Knowledge.INCONCLUSIVE:
            return None
        return v.category

    def eq(self, key: str, *cats: str) -> Tri:
        c = self.category(key)
        if c is None:
            if key not in self.unknown:
                self.unknown.append(key)
            return U
        return c in cats

    def ctx(self, key: str) -> Tri:
        raw = self.obs.context.get(key)
        if raw is None or raw.lower() in ("unknown", "unresolved", "not_assessed"):
            self.unknown.append(f"context.{key}")
            return U
        return raw.lower() in ("yes", "true", "feasible", "relevant", "adequate")

    def missing_required(self) -> list[str]:
        out = []
        for ep in self.required:
            v = self.values.get(ep.key)
            if ep.required and (v is None or v.category is None or v.category in MISSING
                                or v.category == Knowledge.INCONCLUSIVE):
                out.append(ep.key)
        return out


def evaluate(obs: Observation, kind: ExperimentKind, required: list[EndpointSpec]) -> Evaluation:
    ev = Evaluation()
    v = Vector(obs, required)
    p = ev.predicates
    qc = obs.qc

    identity = and3(qc.identity_verified, qc.provenance_verified)
    p["identity_and_provenance_verified"] = show(identity)
    b00 = identity is not True
    missing = v.missing_required()
    p["required_readouts_present"] = show(not missing)
    b01 = (not b00) and (qc.precision_adequate is not True or qc.controls_valid is not True or bool(missing))
    p["precision_adequate"] = show(qc.precision_adequate)
    p["controls_valid"] = show(qc.controls_valid)
    admissible = not b00 and not b01
    if missing:
        ev.information_requests += [f"required readout missing or inconclusive: {k}" for k in missing]

    scientific: dict[str, Tri] = {}
    func = {k: v.category(k) for k in FUNCTION_KEYS}

    if kind is ExperimentKind.ALLELE_FUNCTION:
        matched = v.eq("expression_comparability", "matched")
        p["expression_matched"] = show(matched)
        any_impaired = or3(*(v.eq(k, "impaired", "partial") for k in FUNCTION_KEYS))
        all_normal = and3(*(v.eq(k, "normal") for k in FUNCTION_KEYS))
        p["function_defect_persists"] = show(any_impaired)
        p["function_normal_on_all_measured_endpoints"] = show(all_normal)
        scientific["B02"] = matched is not True
        scientific["B03"] = and3(matched, all_normal)
        scientific["B04"] = and3(matched, any_impaired)
        if v.category("wt_replacement_rescue") in ("improved", "normal", "yes"):
            ev.interpretation.append("normal-protein replacement rescued the assay: supports assay validity only")
        ev.cannot_conclude.append("normal-protein rescue validates the assay; it does not establish mutant-protein "
                                  "function")
        ev.cannot_conclude.append("construct results are not the child's endogenous protein")
        if matched is not True:
            ev.cannot_conclude.append("no conclusion about function at matched abundance: matched abundance was not "
                                      "established")
    else:
        upstream = v.eq("nad_intracellular", "increased")
        p["upstream_effect_present"] = show(upstream)
        mechanism = or3(v.eq("bubr1_abundance", "increased"), v.eq("sirt2_activity", "increased"),
                        v.eq("k668_acetylation", "decreased"))
        p["mechanistic_response_present"] = show(mechanism)
        abundance = v.eq("bubr1_abundance", "increased")
        improved_any = or3(*(v.eq(k, "improved") for k in FUNCTION_KEYS))
        worsened_any = or3(*(v.eq(k, "worsened") for k in FUNCTION_KEYS))
        none_improved = not3(improved_any)
        p["any_function_endpoint_improved"] = show(improved_any)
        p["any_function_endpoint_worsened"] = show(worsened_any)
        problematic = or3(v.eq("cell_death", "increased"), v.eq("division_rate", "decreased"),
                          v.eq("viability", "decreased"))
        p["death_division_or_viability_problematic"] = show(problematic)
        benefit = and3(improved_any, not3(worsened_any), not3(problematic))
        p["interpretable_functional_benefit"] = show(benefit)
        replicated = v.ctx("replicated") if kind is ExperimentKind.REPLICATION_RELEVANCE or \
            "replicated" in obs.context else U
        exposure = v.ctx("exposure_feasible") if "exposure_feasible" in obs.context else U
        relevance = v.ctx("relevance_review") if "relevance_review" in obs.context else U
        p["replicated"], p["exposure_feasible"], p["relevance_review_positive"] = map(show, (replicated, exposure,
                                                                                            relevance))
        scientific["B05"] = upstream is False
        scientific["B06"] = and3(upstream, not3(mechanism))
        scientific["B07"] = and3(abundance, none_improved)
        scientific["B08"] = and3(improved_any, problematic)
        scientific["B10"] = benefit
        scientific["B11"] = and3(benefit, not3(mechanism))
        scientific["B12"] = and3(benefit, replicated, not3(and3(exposure, relevance)))
        scientific["B13"] = and3(benefit, replicated, exposure, relevance) if kind is \
            ExperimentKind.REPLICATION_RELEVANCE else F
        scientific["B14"] = and3(improved_any, worsened_any)
        if benefit and mechanism is None:
            ev.information_requests.append("mechanistic readouts missing: the proposed mechanism can be neither "
                                           "confirmed nor excluded")
        if benefit and scientific["B13"] is not True:
            ev.cannot_conclude.append("no translational-ready conclusion: replication, exposure feasibility or "
                                      "relevance is not established")
            if exposure is None:
                ev.information_requests.append("exposure feasibility unresolved")
        if upstream is False:
            ev.cannot_conclude.append("no inference of a general protein-function failure, and no universal "
                                      "drug-failure claim: the upstream effect was absent in this model and exposure")
        if scientific["B06"]:
            ev.cannot_conclude.append("the missing downstream response challenges the bridge in the tested context "
                                      "only")
        if abundance and none_improved:
            ev.cannot_conclude.append("more protein alone supports only an intermediate step: no cellular-rescue "
                                      "conclusion")

    # Adverse direction: evaluated whatever the admissibility, and carried with its uncertainty.
    worsened = or3(*(v.eq(k, "worsened") for k in FUNCTION_KEYS)) if kind is not ExperimentKind.ALLELE_FUNCTION else F
    adverse = or3(qc.critical_adverse_flag, worsened, v.eq("cell_death", "increased") if "cell_death" in v.values
                  else F)
    p["adverse_direction"] = show(adverse)

    order = ["B00", "B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B10", "B11", "B12", "B13",
             "B14", "B15"]
    raw_matches = {"B00": b00, "B01": b01, **{k: bool(val) for k, val in scientific.items() if val is True},
                   "B09": adverse is True}
    for b in order:
        if not raw_matches.get(b):
            continue
        # B02 only keeps a question unresolved, so a quality gate never needs to suppress it.
        if b in ("B00", "B01", "B09") or admissible or (b == "B02" and not b00):
            ev.matches.append(b)
        else:
            ev.inadmissible.append(b)
    if admissible and not any(b in ev.matches for b in order[2:15] if b != "B09") and "B09" not in ev.matches:
        ev.matches.append("B15")
    if "B09" in ev.matches and not admissible:
        ev.interpretation.append("adverse flag raised on a result that is not yet admissible: the hold stands, and "
                                 "the uncertainty travels with it")

    for b in ev.matches:
        ev.interpretation.append(f"{b}: {BRANCH_TEXT[b]}")
        for a in ACTIONS[b]:
            if a not in ev.actions:
                ev.actions.append(a)
        for h, state in HYPOTHESIS_UPDATES.get(b, {}).items():
            ev.hypothesis_updates.setdefault(h, state)
    for a in ev.actions:
        for other in INCOMPATIBLE.get(a, ()):
            if other in ev.actions:
                ev.conflicts.append([a, other])
    ev.unknown_inputs = sorted(set(v.unknown + [f"required:{k}" for k in missing]))
    ev.cannot_conclude.append("a cellular result does not establish patient benefit or treatment readiness (FR-007)")
    seen: set[str] = set()
    for a in ev.actions:
        if a in TASK_FOR_ACTION and a not in seen:
            seen.add(a)
            kind_, owner, text = TASK_FOR_ACTION[a]
            ev.tasks.append(ResearchTask(id=f"TASK_{a}", origin="decision", type=kind_, description=text,
                                         owner=owner))
    return ev
