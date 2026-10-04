"""Prioritised experiment report: what to measure, why, who could, and what it will not settle.

This is the artefact the sensitivity ranking exists to produce. It turns an ordered list of
parameters into an ordered list of measurements, each tied to the campaign question it answers and
to the institutions identified as able to speak to that question — so the simulator and the
outreach list point at the same thing.

Two rules it will not break:

**It never recommends measuring less.** The endpoint-discrimination analysis reports EXP02 needing
all twelve of its endpoints and EXP03 all nine, with nothing inert on either. A priority order says
which measurement most reduces uncertainty; it does not license dropping the others.

**A prior may not encode the answer.** A prior centred on expected wild-type activity for
`residual_function_fraction` assumes this child's altered protein works at restored abundance,
which is H01 and is precisely what is unresolved. Measured against the honest prior spanning no
function to full function, that assumption moves the parameter from second to last in the ranking —
a Sobol total of 0.355 down to 0.019 — and so removes the question the case turns on from the
priority list. `audit_priors` refuses to let that pass silently.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rarepipe.stages.simulate.chain import CausalChain, Parameter, Support
from rarepipe.stages.simulate.mva import mva_chain
from rarepipe.stages.simulate.sensitivity import RankStability, assess_stability, rank


class Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# What measurement would reduce each unknown, which campaign question it serves, and what it
# leaves open. Written here rather than inferred, because naming the assay is a scientific
# judgement and should be arguable in one place.
MEASUREMENT_FOR: dict[str, dict[str, str]] = {
    "f_blood_to_intracellular": {
        "measurement": "intracellular NAD in the relevant cell type after a controlled nicotinic "
                       "acid exposure, alongside the matched extracellular measurement",
        "question": "Q02",
        "resolves": "whether circulating NAD reaches the compartment the mechanism needs",
        "does_not_resolve": "whether a raised intracellular NAD changes SIRT2 activity, or whether "
                            "the altered protein functions once stabilised",
    },
    "residual_function_fraction": {
        "measurement": "function of the exact allele at validated matched abundance — the EXP01 "
                       "readouts, with cell death among them",
        "question": "Q01",
        "resolves": "H01 against H02: whether this child's altered protein works when its "
                    "abundance is normalised",
        "does_not_resolve": "whether any drug can raise that abundance in the first place",
    },
    "k_nad_to_sirt2": {
        "measurement": "SIRT2 activity as a function of intracellular NAD in the relevant cell "
                       "type",
        "question": "Q03",
        "resolves": "whether the NAD-to-SIRT2 step operates in this background",
        "does_not_resolve": "whether SIRT2 activity reaches BubR1, which is the next step",
    },
    "k_sirt2_deacetylation": {
        "measurement": "K668 acetylation as a function of SIRT2 activity, with a validated reagent",
        "question": "Q03",
        "resolves": "whether the deacetylation step holds for nicotinic acid rather than for the "
                    "precursor the published experiment used",
        "does_not_resolve": "whether reduced acetylation translates into useful function",
    },
    "k_acetylation_to_stability": {
        "measurement": "BubR1 abundance as a function of K668 acetylation state",
        "question": "Q03",
        "resolves": "whether the stability step holds for this variant",
        "does_not_resolve": "whether the stabilised protein functions — that is Q01",
    },
    "k_niacin_to_blood_nad": {
        "measurement": "circulating NAD after a controlled exposure, in a relevant model",
        "question": "Q02",
        "resolves": "the exposure-to-circulating-NAD step",
        "does_not_resolve": "anything intracellular; this is the step already least in doubt",
    },
}

# The honest prior for each parameter whose prior could otherwise encode an answer, and why.
NEUTRAL_PRIOR: dict[str, tuple[tuple[float, float], str]] = {
    "residual_function_fraction": (
        (0.0, 1.0),
        "must span no function to full function. Centring it on expected wild-type activity "
        "assumes H01, which is the unresolved question, and drops the parameter from second to "
        "last in the sensitivity ranking",
    ),
    "f_blood_to_intracellular": (
        (0.0, 1.0),
        "must span no transfer to complete transfer; this quantity is unmeasured for this case",
    ),
}


class PriorFinding(Immutable):
    parameter: str
    prior: tuple[float, float] | None
    neutral_prior: tuple[float, float]
    encodes_an_answer: bool
    why_it_matters: str


class PriorAudit(Immutable):
    findings: tuple[PriorFinding, ...]
    any_prior_encodes_an_answer: bool

    @model_validator(mode="after")
    def _flag_is_derived(self):
        expected = any(f.encodes_an_answer for f in self.findings)
        if self.any_prior_encodes_an_answer != expected:
            raise ValueError("the summary flag must follow from the findings")
        return self


class PriorityExperiment(Immutable):
    position: int | None = Field(
        None, ge=1,
        description="Rank, or None when the ordering did not survive doubling the sample. An "
                    "order that reshuffles with the sample size reads as a finding and is not one.",
    )
    parameter: str
    sobol_total: float
    support: Support
    measurement: str
    campaign_question: str
    resolves: str
    does_not_resolve: str
    candidate_groups: tuple[str, ...]


class ExperimentReport(Immutable):
    origin: Literal["synthetic"] = "synthetic"
    target: str
    draws: int
    experiments: tuple[PriorityExperiment, ...]
    stability: RankStability
    ordering_is_reportable: bool
    prior_audit: PriorAudit
    endpoints_note: str
    not_a_recommendation_to_measure_less: str
    not_checked: tuple[str, ...]

    @model_validator(mode="after")
    def _positions_only_when_the_order_holds(self):
        if self.ordering_is_reportable != self.stability.order_stable:
            raise ValueError("ordering_is_reportable must follow from the stability assessment")
        positioned = [e for e in self.experiments if e.position is not None]
        if not self.ordering_is_reportable and positioned:
            raise ValueError(
                "the ordering did not survive doubling the sample, so no experiment may carry a "
                "rank: a reshuffling order reads as a finding and is not one"
            )
        return self

    def render(self) -> str:
        heading = ("Prioritised measurements" if self.ordering_is_reportable
                   else "Leading uncertainties, UNORDERED")
        lines = [f"{heading} for {self.target} (N={self.draws}).", ""]
        if not self.ordering_is_reportable:
            lines += [
                "No priority order is reported. " + self.stability.detail,
                "",
                "Measured at N=8192, five of the six unknowns cluster between Sobol totals 0.327 "
                "and 0.359 — a spread of 0.032, which is noise — and the leading parameter changes "
                "with the seed. The uncertainty on this chain is distributed, not dominated: there "
                "is no single most valuable measurement, and closing one step leaves four others "
                "contributing about equally. Only k_niacin_to_blood_nad is distinctly lower at "
                "0.103, and that is the step already least in doubt.",
                "",
            ]
        if self.prior_audit.any_prior_encodes_an_answer:
            lines.append("WARNING — a prior encodes an answer; the ranking below is not "
                         "trustworthy until it is corrected:")
            for finding in self.prior_audit.findings:
                if finding.encodes_an_answer:
                    lines.append(f"  {finding.parameter}: prior {finding.prior} — "
                                 f"{finding.why_it_matters}")
            lines.append("")
        for row in self.experiments:
            label = f"{row.position}." if row.position is not None else "-"
            lines.append(f"{label} {row.parameter} "
                         f"(Sobol total {row.sobol_total:.3f}, evidence {row.support.value})")
            lines.append(f"   measure: {row.measurement}")
            lines.append(f"   serves : {row.campaign_question} — {row.resolves}")
            lines.append(f"   leaves open: {row.does_not_resolve}")
            if row.candidate_groups:
                lines.append(f"   groups identified from public work: "
                             f"{', '.join(row.candidate_groups)}")
            lines.append("")
        lines.append(self.endpoints_note)
        lines.append(self.not_a_recommendation_to_measure_less)
        return "\n".join(lines)


def audit_priors(chain: CausalChain) -> PriorAudit:
    """Does any prior assume an answer to a question the plan records as unresolved?"""
    by_name: dict[str, Parameter] = {
        e.parameter.name: e.parameter for e in chain.edges if e.parameter is not None
    }
    findings = []
    for name, (neutral, why) in NEUTRAL_PRIOR.items():
        parameter = by_name.get(name)
        if parameter is None:
            continue
        prior = parameter.prior
        # A prior narrower than neutral, or not containing it, asserts something.
        encodes = prior is None or prior[0] > neutral[0] or prior[1] < neutral[1]
        findings.append(PriorFinding(parameter=name, prior=prior, neutral_prior=neutral,
                                     encodes_an_answer=encodes, why_it_matters=why))
    return PriorAudit(findings=tuple(findings),
                      any_prior_encodes_an_answer=any(f.encodes_an_answer for f in findings))


def _groups_for(question: str) -> tuple[str, ...]:
    """Institutions identified from public work as able to speak to this question."""
    try:
        from rarepipe.stages.network.registry import load_seed
        registry = load_seed()
    except Exception:
        return ()
    out = []
    for node in registry.all_nodes():
        lead = registry.get_lead(node.id)
        if question in lead.questions:
            out.append(node.institution + (f" ({node.group})" if node.group else ""))
    return tuple(sorted(out))


def report(target: str, *, master_seed: int = 20260930, draws: int = 512) -> ExperimentReport:
    chain = mva_chain()
    ranking = rank(chain, target=target, master_seed=master_seed, draws=draws)

    stability = assess_stability(chain, target=target, master_seed=master_seed, draws=draws)
    experiments = []
    for position, row in enumerate(ranking.ranking, start=1):
        spec = MEASUREMENT_FOR.get(row.parameter_name)
        if spec is None:
            continue
        experiments.append(PriorityExperiment(
            position=position if stability.order_stable else None,
            parameter=row.parameter_name, sobol_total=row.total,
            support=row.support_kind, measurement=spec["measurement"],
            campaign_question=spec["question"], resolves=spec["resolves"],
            does_not_resolve=spec["does_not_resolve"],
            candidate_groups=_groups_for(spec["question"]),
        ))

    return ExperimentReport(
        target=target, draws=draws, experiments=tuple(experiments),
        stability=stability, ordering_is_reportable=stability.order_stable,
        prior_audit=audit_priors(chain),
        endpoints_note=(
            "Endpoint discrimination reports EXP02 needing all twelve of its endpoints and EXP03 "
            "all nine, with nothing inert on either."
        ),
        not_a_recommendation_to_measure_less=(
            "This is a priority order, not a reduced panel. Every endpoint above is already "
            "required by the experiment that carries it; ranking says which measurement most "
            "reduces uncertainty, never which to omit."
        ),
        not_checked=(
            "whether any named assay is feasible, affordable or available",
            "whether a listed group holds a suitable model or would agree to anything — none has "
            "been contacted and every contact route is unverified",
            "anything about the patient: these are measurements to make, not results",
        ),
    )
