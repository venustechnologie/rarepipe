"""Validate the causal chain against published checkpoint behaviour.

This is the only benchmark available to this case. EXP01 and EXP02 have never run, so there are no
case outcomes to score against; what can be checked is whether the chain reproduces behaviour that
is already in the literature, and whether it claims no more support than its sources actually give.

Two checks per case, and the second is the one that matters:

1. **Direction.** Does the chain predict the trend the source reported?
2. **Entitlement.** Does the chain's support label match what the source actually covered? A chain
   that gets the direction right by over-claiming its evidence has not been validated; it has
   agreed with the literature for the wrong reason, and will agree just as confidently where the
   literature does not reach.

A case the chain cannot represent is reported as `NOT_REPRESENTABLE` — a finding about the chain's
scope, not a pass and not a failure. Mitotic checkpoint dynamics such as Mad2/Cdc20/MCC assembly
are an example: real, published, and entirely outside what this chain models.

Every case here cites evidence the repository already records. Nothing in this module invents a
citation, and the two references that carry no retrieval record keep their UNVERIFIED marker, so a
case resting on one cannot be counted as reproducing verified literature.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rarepipe.stages.simulate.chain import CausalChain, Support
from rarepipe.stages.simulate.mva import (
    BUBR1, BUBR1_FN, CHECKPOINT, EV_DOMAIN_IMPAIRED, EV_HUMAN_NIACIN_TRIAL, EV_NIACIN_HUMAN,
    EV_RESTORED_ABUNDANCE, EV_SIRT2_BUBR1, K668, NAD_BLOOD, NAD_CELL, NIACIN, SILENCING, SIRT2,
    mva_chain,
)

Outcome = Literal["REPRODUCED", "WRONG_DIRECTION", "OVER_CLAIMS_ITS_SOURCE", "NOT_REPRESENTABLE"]


class Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PublishedBehaviour(Immutable):
    """One reported trend, and what the report actually covered."""

    case_id: str
    source: str
    reported: str = Field(description="What the source reported, in its own terms.")
    scope: str = Field(description="What the source actually covered — species, agent, compartment.")
    start: str
    end: str
    expected_direction: Literal["increase", "decrease", "contradicted"]
    entitled_to_at_most: Support = Field(
        description="The strongest support a chain edge on this path may claim from this source.",
    )

    @property
    def unverified(self) -> bool:
        return "UNVERIFIED" in self.source


class CaseResult(Immutable):
    case_id: str
    outcome: Outcome
    source: str
    unverified_source: bool
    expected_direction: str
    chain_direction: str | None = None
    chain_verdict: str | None = None
    chain_weakest_support: Support | None = None
    note: str


class ValidationReport(Immutable):
    origin: Literal["synthetic"] = "synthetic"
    chain_id: str
    results: tuple[CaseResult, ...]
    reproduced: int
    reproduced_on_verified_sources: int = Field(
        description="Cases reproduced whose source carries a retrieval record. The headline count "
                    "includes cases resting on references this repository cannot verify, so it "
                    "overstates how much of this agreement is with checked literature.",
    )
    representable: int
    total: int
    unverified_sources: tuple[str, ...]
    rate_note: str
    not_checked: tuple[str, ...]

    @model_validator(mode="after")
    def _counts_are_consistent(self):
        if self.total != len(self.results):
            raise ValueError("total must count every case")
        if self.reproduced > self.representable:
            raise ValueError("a case the chain cannot represent cannot be reproduced")
        if self.reproduced_on_verified_sources > self.reproduced:
            raise ValueError("verified reproductions cannot exceed reproductions")
        return self

    def render(self) -> str:
        lines = [
            f"Chain validation against published checkpoint behaviour ({self.chain_id}).",
            f"Reproduced {self.reproduced} of {self.representable} representable cases "
            f"({self.total} cases total; {self.total - self.representable} outside the chain's "
            "scope).",
            f"Of those, {self.reproduced_on_verified_sources} rest on a source carrying a "
            f"retrieval record; {self.reproduced - self.reproduced_on_verified_sources} rest on a "
            "reference this repository cannot verify.",
            self.rate_note,
            "",
        ]
        for row in self.results:
            flag = " [UNVERIFIED SOURCE]" if row.unverified_source else ""
            lines.append(f"{row.case_id}: {row.outcome}{flag}")
            lines.append(f"  source: {row.source}")
            lines.append(f"  {row.note}")
        return "\n".join(lines)


def published_behaviours() -> tuple[PublishedBehaviour, ...]:
    """Cases drawn only from evidence this repository already records."""
    return (
        PublishedBehaviour(
            case_id="SAC01_restored_abundance_supports_activation",
            source=EV_RESTORED_ABUNDANCE,
            reported="restored abundance of published BUB1B reference alleles supported checkpoint "
                     "activation",
            scope="model systems; checkpoint activation endpoint only, variant-class scope",
            start=BUBR1_FN, end=CHECKPOINT, expected_direction="increase",
            entitled_to_at_most=Support.MODEL_EXPERIMENTAL,
        ),
        PublishedBehaviour(
            case_id="SAC02_domain_loss_impairs_silencing",
            source=EV_DOMAIN_IMPAIRED,
            reported="domain mutation or removal impaired checkpoint silencing and alignment",
            scope="abstract-level report; gene-level scope",
            start=BUBR1_FN, end=SILENCING, expected_direction="increase",
            entitled_to_at_most=Support.MODEL_EXPERIMENTAL,
        ),
        PublishedBehaviour(
            case_id="SIRT01_sirt2_deacetylation_stabilises_bubr1",
            source=EV_SIRT2_BUBR1,
            reported="SIRT2 deacetylates BubR1 at K668 and its stability rises",
            scope="NMN rather than nicotinic acid, in aged mice",
            start=SIRT2, end=BUBR1, expected_direction="increase",
            entitled_to_at_most=Support.DIFFERENT_AGENT,
        ),
        PublishedBehaviour(
            case_id="NAD01_niacin_raises_circulating_nad",
            source=EV_NIACIN_HUMAN,
            reported="nicotinic acid raised whole-blood NAD",
            scope="whole blood in healthy adults; no intracellular measurement",
            start=NIACIN, end=NAD_BLOOD, expected_direction="increase",
            entitled_to_at_most=Support.HUMAN_EXPERIMENTAL,
        ),
        # Retargeted from the whole niacin-to-intracellular path to the transfer edge itself. The
        # old form asserted a ceiling on the path, which only held while this source was the only
        # one for that relation; once a human trial measured the tissue pool the path legitimately
        # claims more, and the ceiling belonged to the edge all along. What this source entitles is
        # a statement about the blood-to-cell transfer, and that is now what is checked.
        PublishedBehaviour(
            case_id="NAD02_circulating_nad_is_not_intracellular_nad",
            source=EV_NIACIN_HUMAN,
            reported="the same work reported no intracellular NAD measurement",
            scope="whole blood only",
            start=NAD_BLOOD, end=NAD_CELL, expected_direction="increase",
            entitled_to_at_most=Support.DIFFERENT_COMPARTMENT,
        ),
        # The case that used to sit here validated the chain against a published null result. The
        # citation carrying it was retrieved and does not report one, so the benchmark was testing
        # the chain against a behaviour nobody published. It was retired rather than relaxed; see
        # REPAIR_R1. In its place, the human trial that was in the repository and connected to
        # nothing now has a benchmark of its own, at the tissue it was measured in.
        PublishedBehaviour(
            case_id="HUMAN02_niacin_raises_tissue_nad_in_human_muscle",
            source=EV_HUMAN_NIACIN_TRIAL,
            reported="administered niacin raised muscle NAD to the level of matched controls",
            scope="human skeletal muscle in adult-onset mitochondrial myopathy",
            start=NIACIN, end=NAD_CELL, expected_direction="increase",
            entitled_to_at_most=Support.HUMAN_EXPERIMENTAL,
        ),
    )


def _check(chain: CausalChain, case: PublishedBehaviour) -> CaseResult:
    from rarepipe.stages.simulate.chain import STRENGTH

    common = dict(case_id=case.case_id, source=case.source,
                  unverified_source=case.unverified, expected_direction=case.expected_direction)

    if case.expected_direction == "contradicted":
        direct = [e for e in chain.edges if e.source == case.start and e.target == case.end]
        if not direct:
            return CaseResult(**common, outcome="NOT_REPRESENTABLE",
                              note="the chain has no direct edge for the route the null result tested")
        if all(e.support is Support.CONTRADICTED for e in direct):
            return CaseResult(**common, outcome="REPRODUCED",
                              chain_weakest_support=Support.CONTRADICTED,
                              note="the chain marks this route contradicted, as the source reports")
        return CaseResult(**common, outcome="OVER_CLAIMS_ITS_SOURCE",
                          chain_weakest_support=direct[0].support,
                          note="the source reported a null result; the chain does not mark this "
                               "route contradicted")

    claim = chain.predict(case.start, case.end)
    if claim is None:
        return CaseResult(**common, outcome="NOT_REPRESENTABLE",
                          note=f"the chain has no route from {case.start} to {case.end}")
    if claim.direction != case.expected_direction:
        return CaseResult(**common, outcome="WRONG_DIRECTION", chain_direction=claim.direction,
                          chain_verdict=claim.verdict, chain_weakest_support=claim.weakest_support,
                          note=f"the source reported {case.expected_direction}; the chain predicts "
                               f"{claim.direction}")
    if STRENGTH[claim.weakest_support] > STRENGTH[case.entitled_to_at_most]:
        return CaseResult(**common, outcome="OVER_CLAIMS_ITS_SOURCE", chain_direction=claim.direction,
                          chain_verdict=claim.verdict, chain_weakest_support=claim.weakest_support,
                          note=f"direction agrees, but the chain claims {claim.weakest_support.value} "
                               f"where the source covered only {case.scope} "
                               f"({case.entitled_to_at_most.value})")
    return CaseResult(**common, outcome="REPRODUCED", chain_direction=claim.direction,
                      chain_verdict=claim.verdict, chain_weakest_support=claim.weakest_support,
                      note=f"direction agrees and the support claimed is within what the source "
                           f"covered ({case.scope})")


def validate(chain: CausalChain | None = None,
             cases: tuple[PublishedBehaviour, ...] | None = None) -> ValidationReport:
    """`cases` is injectable so the suite's own properties can be tested on a constructed case list.

    Needed once the real chain stopped resting on any unverified citation: a test that the report
    surfaces unverified sources must be able to supply one, rather than depending on the case
    happening to have some.
    """
    chain = chain or mva_chain()
    cases = cases if cases is not None else published_behaviours()
    results = tuple(_check(chain, case) for case in cases)
    representable = sum(1 for r in results if r.outcome != "NOT_REPRESENTABLE")
    reproduced = sum(1 for r in results if r.outcome == "REPRODUCED")
    verified = sum(1 for r in results
                   if r.outcome == "REPRODUCED" and not r.unverified_source)
    return ValidationReport(
        chain_id=chain.chain_id, results=results, reproduced=reproduced,
        reproduced_on_verified_sources=verified,
        representable=representable, total=len(results),
        unverified_sources=tuple(sorted({r.source for r in results if r.unverified_source})),
        rate_note=(
            f"{reproduced}/{representable} is a count over a hand-built case list, not a sampling "
            "rate, so no confidence interval applies. It says the chain agrees with the behaviour "
            "recorded here and claims no more support than those sources give. It says nothing "
            "about this child, and nothing about cases nobody has added."
        ),
        not_checked=(
            "quantitative dynamics — no timing, concentration or rate is compared",
            "any behaviour outside this chain's nodes, including Mad2/Cdc20/MCC assembly",
            "whether the cited sources say what the repository records them as saying",
            "anything about the patient: EXP01 and EXP02 have never run",
        ),
    )
