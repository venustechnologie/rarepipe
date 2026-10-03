"""Synthetic fixtures for tests and the completion demonstration (PRD §19).

Everything here is labelled synthetic. The category labels (improved, unchanged, worsened, ...) are
software test inputs, not biological thresholds. None of it is evidence, and a synthetic observation
cannot enter a real plan.
"""

from __future__ import annotations

from rarepipe.stages.prospective.model import (
    AnalysisSpec,
    BaselineRef,
    EvaluationMode,
    Knowledge,
    OutcomeAvailability,
    ProspectivePlan,
    Quantity,
)
from rarepipe.stages.prospective.seed import seed_plan

FIXTURE_LABEL = "fixture label (software test input, not a biological threshold)"


def synthetic_baseline(status: str = "FROZEN") -> BaselineRef:
    return BaselineRef(package_path="synthetic", package_sha256="sha256:" + "0" * 64, manifest_entries=23,
                       manifest_verified=True,
                       stage_runs={"stage06": "RUN_SYN_06", "stage07": "RUN_SYN_07", "stage08": "RUN_SYN_08",
                                   "stage09": "RUN_SYN_09"},
                       semantic_digests={"stage09": "sha256:" + "1" * 64}, status=status,
                       known_limitations=["synthetic fixture baseline"])


def draft_plan(synthetic: bool = True) -> ProspectivePlan:
    plan = seed_plan(synthetic_baseline())
    if synthetic:
        plan.synthetic_fixture = True
        plan.evaluation_mode = EvaluationMode.SYNTHETIC_DEMO
        plan.plan_id = "PP_SYNTHETIC_DEMO"
    return plan


def complete_plan() -> ProspectivePlan:
    """Every field a scientific freeze needs, filled with labelled fixture values. Reviews are added separately."""
    plan = draft_plan()
    for e in plan.experiments:
        for m in e.model_requirements:
            m.availability = "AVAILABLE"
        e.feasibility = "FEASIBLE"
        e.analysis = AnalysisSpec(
            experimental_unit="independent culture (fixture)", replication="3 biological x 2 technical (fixture)",
            allocation_and_blinding="randomised, blinded scoring (fixture)",
            primary_endpoints=[ep for ep in e.endpoints if ep.endswith(("_MIS", "_EXPR"))],
            effect_scale="ratio to comparator (fixture)", analysis_population="all assessable cells (fixture)",
            denominators="per viable assessable division (fixture)", time_windows="48 h (fixture)",
            missing_data_and_exclusions="prespecified (fixture)", multiplicity="Holm (fixture)",
            meaningful_effect="fixture criterion", uncertainty_method="95% CI (fixture)",
            repeat_or_termination="repeat once if controls fail (fixture)")
    for ep in plan.endpoints:
        ep.method = "fixture method"
        ep.validity_criteria = "fixture validity"
        ep.threshold_version = "fixture-thresholds-1"
        ep.effect_criterion = Quantity(value=1.0, unit="ratio", note=FIXTURE_LABEL)
    plan.outcome_availability = OutcomeAvailability(planned_start="2026-10-01",
                                                    timestamp_evidence=["synthetic timestamp"])
    plan.blockers = []
    return plan


def value(key: str, category: str, **extra) -> dict:
    out = {"endpoint_key": key, "category": category, "derivation": FIXTURE_LABEL}
    if key == "missegregation":
        out.update(denominator="per viable assessable division", denominator_n=200)
    out.update(extra)
    return out


def observation(experiment: str, values: dict[str, str], *, qc: dict | None = None, context: dict | None = None,
                applicability: str = "GENERIC_BUB1B_DEFICIENT", origin: str = "SYNTHETIC",
                execution: str = "SYN_EXEC_1") -> dict:
    if experiment == "EXP01" and applicability == "GENERIC_BUB1B_DEFICIENT":
        applicability = "EXACT_ALLELE_ENGINEERED"
    return {"experiment_id": experiment, "execution_ref": execution, "origin": origin,
            "evaluation_mode": "SYNTHETIC_DEMO" if origin == "SYNTHETIC" else "PROSPECTIVE_NEW_RESULT",
            "raw_result_sha256": "0" * 64, "values": [value(k, c) for k, c in values.items()],
            "qc": {"identity_verified": True, "provenance_verified": True, "controls_valid": True,
                   "precision_adequate": True, **(qc or {})},
            "model_identity": {"applicability": applicability, "genotype_verified_locally": True},
            "context": context or {}}


# cell_death joined EXP01's required readouts in rules 1.2.0: without it B08, B09, B10 and B16 all
# declared they applied to EXP01 and none could fire, so a result with every function normal but
# viability and division falling read as a success. Fixtures that omit it are now incomplete, which
# is the point — such an observation cannot exclude selective loss.
EXP01_ALL = {"expression_comparability": "matched", "checkpoint_activation": "normal", "checkpoint_silencing": "normal",
             "chromosome_alignment": "normal", "missegregation": "normal", "viability": "unchanged",
             "division_rate": "unchanged", "cell_death": "unchanged"}
EXP02_BASE = {"nad_intracellular": "increased", "bubr1_abundance": "increased", "sirt2_activity": "increased",
              "k668_acetylation": "decreased", "checkpoint_activation": "improved", "checkpoint_silencing": "improved",
              "chromosome_alignment": "improved", "missegregation": "improved", "viability": "unchanged",
              "cell_death": "unchanged", "division_rate": "unchanged",
              # The disease phenotype. It was always in EXP02's endpoint list and always absent
              # here; no rule read it, so a "complete" observation could omit the measurement that
              # defines the disease. B17/B18 read it in rules 1.2.0, so the omission now shows.
              "total_aneuploidy": "decreased"}


def exp03(**changes: str) -> dict[str, str]:
    """EXP03's readouts. It does not measure total_aneuploidy, so that key is dropped.

    Previously EXP03 observations were built from exp02() and the difference was invisible because
    nothing read aneuploidy. Now that B17/B18 do, reusing the EXP02 base here is rejected by the
    workflow — correctly, since the key is not an endpoint of EXP03.
    """
    out = {k: v for k, v in EXP02_BASE.items() if k != "total_aneuploidy"}
    for key, value in changes.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def exp02(**changes: str) -> dict[str, str]:
    out = dict(EXP02_BASE)
    for k, v in changes.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


# Scenario library for the explorer: positive, negative, partial, adverse, inconclusive and unexpected.
SCENARIOS: dict[str, dict] = {
    "exp01_matched_normal": {"experiment_id": "EXP01", "values": EXP01_ALL},
    "exp01_expression_unknown": {"experiment_id": "EXP01", "values": {**EXP01_ALL,
                                                                      "expression_comparability": Knowledge.UNKNOWN}},
    "exp01_defect_persists": {"experiment_id": "EXP01", "values": {**EXP01_ALL, "checkpoint_silencing": "impaired"}},
    "exp02_positive": {"experiment_id": "EXP02", "values": exp02()},
    "exp02_no_upstream": {"experiment_id": "EXP02", "values": exp02(nad_intracellular="unchanged",
                                                                    bubr1_abundance="unchanged",
                                                                    sirt2_activity="unchanged",
                                                                    k668_acetylation="unchanged",
                                                                    checkpoint_activation="unchanged",
                                                                    checkpoint_silencing="unchanged",
                                                                    chromosome_alignment="unchanged",
                                                                    missegregation="unchanged")},
    "exp02_partial_abundance_only": {"experiment_id": "EXP02", "values": exp02(
        checkpoint_activation="unchanged", checkpoint_silencing="unchanged", chromosome_alignment="unchanged",
        missegregation="unchanged")},
    "exp02_adverse": {"experiment_id": "EXP02", "values": exp02(checkpoint_silencing="worsened",
                                                                missegregation="worsened")},
    "exp02_selection": {"experiment_id": "EXP02", "values": exp02(cell_death="increased", division_rate="decreased")},
    "exp02_inconclusive": {"experiment_id": "EXP02", "values": exp02(missegregation=Knowledge.INCONCLUSIVE),
                           "qc": {"precision_adequate": False}},
    "exp02_unexpected_mechanism": {"experiment_id": "EXP02", "values": exp02(
        bubr1_abundance="unchanged", sirt2_activity="unchanged", k668_acetylation="unchanged")},
}
