"""Contradiction checks over the hypothesis set.

For each hypothesis: what would invalidate it, which chain edges must hold or fail for it
to remain live, and whether anyone has looked for opposing evidence. The report never ranks
likelihood and never picks a winner among mutually exclusive alternatives.

Every output carries origin="synthetic". Nothing here is evidence about a patient, and nothing
written here may enter a campaign store, a plan version, or reward feedback.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from rarepipe.stages.prospective.model import Hypothesis, Knowledge
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.seed import hypotheses as seed_hypotheses
from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Immutable, Support
from rarepipe.stages.simulate.mva import mva_chain

# Support kinds that cannot carry a hypothesis alone without being named as such.
_WEAK_ALONE = frozenset({Support.ASSERTED_ONLY, Support.DIFFERENT_AGENT})

# Assessments that mean the hypothesis has not been ruled out.
_LIVE = frozenset({"UNRESOLVED", "UNDER_INVESTIGATION", "NOT_ASSESSED", "STRENGTHENED"})


class EdgeRequirement(Immutable):
    """One chain edge that must hold or fail for the hypothesis to survive."""

    edge_key: str
    requirement: Literal["hold", "fail"]
    support: Support
    scope_note: str = ""
    caveat: str = ""


class WeakSupportEdge(Immutable):
    """An edge the hypothesis rests on that is asserted_only or different_agent."""

    edge_key: str
    support: Support
    evidence_ref: str | None = None
    scope_note: str = ""


class OpposingRecord(Immutable):
    """Recorded material that argues against the hypothesis, or an explicit absence."""

    status: Literal["opposed", "none_recorded", "none_looked_for"]
    evidence_ref: str | None = None
    edge_key: str | None = None
    note: str
    knowledge: Knowledge = Knowledge.UNKNOWN


class HypothesisContradiction(Immutable):
    """What would kill one idea, and whether anyone checked. Not a likelihood rank."""

    origin: Literal["synthetic"] = "synthetic"
    hypothesis_id: str
    statement: str
    live: bool
    assessment: str
    falsification: str = ""
    distinguished_by: str = ""
    # Three levels, not a boolean. Only H01 states an explicit falsification clause, but every
    # other hypothesis records a `distinguished_by` — a way to tell it apart, which is a
    # discriminating criterion in substance. Collapsing those together flagged six of seven rows,
    # and a flag on six of seven rows carries no information: a reader stops looking.
    criterion_kind: Literal["explicit_falsification", "discriminating_only", "none"]
    alternatives: tuple[str, ...] = ()
    separating_measurement: str | None = None
    edges_to_survive: tuple[EdgeRequirement, ...] = ()
    weak_support_edges: tuple[WeakSupportEdge, ...] = ()
    rests_only_on_weak_support: bool = False
    opposing: tuple[OpposingRecord, ...] = ()

    @property
    def unfalsifiable_as_stated(self) -> bool:
        """True only when nothing at all says how this idea could be told apart or killed."""
        return self.criterion_kind == "none"

    @model_validator(mode="after")
    def _criterion_matches_what_is_recorded(self):
        has_falsification = bool(self.falsification.strip())
        has_discriminator = bool(self.distinguished_by.strip())
        expected = (
            "explicit_falsification" if has_falsification
            else "discriminating_only" if has_discriminator
            else "none"
        )
        if self.criterion_kind != expected:
            raise ValueError(
                f"{self.hypothesis_id}: criterion_kind is {self.criterion_kind!r} but the record "
                f"carries falsification={has_falsification} distinguished_by={has_discriminator}, "
                f"which is {expected!r}. The level must be derived from what is recorded, never "
                "asserted separately."
            )
        return self


class ContradictionReport(Immutable):
    """Full audit of the hypothesis set against the causal chain."""

    origin: Literal["synthetic"] = "synthetic"
    chain_id: str
    case_ref: str
    hypotheses: tuple[HypothesisContradiction, ...]
    interval_applies: bool = False
    no_interval_reason: str = (
        "Contradiction audit enumerates logical requirements and recorded opposing evidence; "
        "it is not a sampled rate, so no binomial interval applies"
    )

    def by_id(self, hypothesis_id: str) -> HypothesisContradiction:
        for row in self.hypotheses:
            if row.hypothesis_id == hypothesis_id:
                return row
        raise KeyError(hypothesis_id)

    def narrative(self) -> str:
        """Prose generated from this record. Never concludes which hypothesis is likelier."""
        lines = [
            f"origin={self.origin}",
            f"Contradiction audit for chain {self.chain_id} (case {self.case_ref}).",
            self.no_interval_reason + ".",
            "This report does not rank hypotheses or pick a winner among alternatives.",
        ]
        for row in self.hypotheses:
            lines.append(f"— {row.hypothesis_id} ({'live' if row.live else 'not live'}): "
                         f"{row.statement}")
            if row.criterion_kind == "none":
                lines.append("  falsification: unfalsifiable-as-stated (no criterion recorded)")
            elif row.criterion_kind == "discriminating_only":
                lines.append("  falsification: no explicit falsification clause; a discriminating "
                             "criterion is recorded under distinguished_by")
            else:
                lines.append(f"  falsification: {row.falsification}")
            if row.distinguished_by:
                lines.append(f"  distinguished_by: {row.distinguished_by}")
            if row.alternatives:
                alts = ", ".join(row.alternatives)
                sep = row.separating_measurement or "not identified on the chain"
                lines.append(
                    f"  alternatives (all remain live if unresolved): {alts}; "
                    f"separating measurement: {sep}"
                )
            if row.edges_to_survive:
                for req in row.edges_to_survive:
                    lines.append(
                        f"  to survive, edge {req.edge_key} must {req.requirement} "
                        f"(support={req.support.value})"
                    )
            if row.rests_only_on_weak_support:
                named = ", ".join(
                    f"{w.edge_key} ({w.support.value})" for w in row.weak_support_edges
                )
                lines.append(
                    f"  rests only on asserted_only/different_agent edge(s): {named}"
                )
            elif row.weak_support_edges:
                named = ", ".join(
                    f"{w.edge_key} ({w.support.value})" for w in row.weak_support_edges
                )
                lines.append(f"  includes weak-support edge(s): {named}")
            for opp in row.opposing:
                ref = f" ref={opp.evidence_ref}" if opp.evidence_ref else ""
                edge = f" edge={opp.edge_key}" if opp.edge_key else ""
                lines.append(f"  opposing: {opp.status}{ref}{edge} — {opp.note}")
        return "\n".join(lines)


def audit(
    chain: CausalChain | None = None,
    *,
    hypotheses: list[Hypothesis] | None = None,
    searched_hypothesis_ids: frozenset[str] | set[str] | None = None,
) -> ContradictionReport:
    """Audit each hypothesis against the chain.

    `searched_hypothesis_ids` records which hypotheses have had opposing evidence looked for.
    Absence is reported as none_looked_for — never silently treated as clearance.
    """
    chain = chain if chain is not None else mva_chain()
    hyps = list(hypotheses) if hypotheses is not None else list(seed_hypotheses())
    searched = frozenset(searched_hypothesis_ids or ())
    by_id = {h.id: h for h in hyps}
    rows: list[HypothesisContradiction] = []
    for hyp in hyps:
        rows.append(_audit_one(hyp, chain, by_id=by_id, searched=searched))
    return ContradictionReport(
        chain_id=chain.chain_id,
        case_ref=chain.case_ref,
        hypotheses=tuple(rows),
    )


def _audit_one(
    hyp: Hypothesis,
    chain: CausalChain,
    *,
    by_id: dict[str, Hypothesis],
    searched: frozenset[str],
) -> HypothesisContradiction:
    falsification = (hyp.falsification or "").strip()
    unfalsifiable = not falsification
    live = hyp.assessment in _LIVE
    supporting = _supporting_edges(hyp, chain)
    weak = tuple(
        WeakSupportEdge(
            edge_key=e.key,
            support=e.support,
            evidence_ref=e.evidence_ref,
            scope_note=e.scope_note,
        )
        for e in supporting
        if e.support in _WEAK_ALONE
    )
    rests_only_weak = bool(supporting) and all(e.support in _WEAK_ALONE for e in supporting)
    requirements = _edge_requirements(hyp, chain)
    separating = _separating_measurement(hyp, chain, by_id=by_id)
    opposing = _opposing_records(hyp, chain, requirements=requirements, searched=searched)
    return HypothesisContradiction(
        hypothesis_id=hyp.id,
        statement=hyp.statement,
        live=live,
        assessment=hyp.assessment,
        falsification=falsification,
        distinguished_by=(hyp.distinguished_by or "").strip(),
        criterion_kind=(
            "explicit_falsification" if falsification.strip()
            else "discriminating_only" if (hyp.distinguished_by or "").strip()
            else "none"
        ),
        alternatives=tuple(hyp.alternatives),
        separating_measurement=separating,
        edges_to_survive=requirements,
        weak_support_edges=weak,
        rests_only_on_weak_support=rests_only_weak,
        opposing=opposing,
    )


def _pmid_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    tokens: set[str] = set()
    for part in text.replace(",", " ").split():
        part = part.strip().rstrip(")")
        if part.upper().startswith("PMID:") or part.startswith("VX_") or part.startswith("MC_"):
            tokens.add(part.split("(")[0])
        elif part.isdigit() and len(part) >= 7:
            tokens.add(f"PMID:{part}")
    return tokens


def _evidence_tokens(hyp: Hypothesis) -> set[str]:
    tokens: set[str] = set()
    for ev in hyp.evidence:
        tokens |= _pmid_tokens(ev.ref)
        tokens |= _pmid_tokens(ev.independence_group)
    return tokens


def _supporting_edges(hyp: Hypothesis, chain: CausalChain) -> tuple[CausalEdge, ...]:
    """Edges whose cited evidence overlaps the hypothesis evidence, excluding contradicted links.

    When a hypothesis evidence item carries a scope_note, prefer edges whose scope_note contains
    that text so a different_agent substitution is not collapsed into every co-cited edge.
    """
    if not hyp.evidence:
        # Allele-function gap with no overlapping citation still rests on the asserted edge
        # that the chain names in its H01/H02 caveat.
        return _caveat_edges(hyp, chain, include_asserted_gap=True)

    tokens = _evidence_tokens(hyp)
    scoped: list[CausalEdge] = []
    loose: list[CausalEdge] = []
    for edge in chain.edges:
        if edge.support is Support.CONTRADICTED:
            continue
        edge_tokens = _pmid_tokens(edge.evidence_ref)
        if not (tokens & edge_tokens):
            continue
        scope_match = any(
            ev.scope_note and ev.scope_note in (edge.scope_note or "")
            for ev in hyp.evidence
        )
        if scope_match:
            scoped.append(edge)
        else:
            loose.append(edge)
    chosen = scoped if scoped else loose
    # H01/H02 also require the asserted residual-function edge even when literature cites
    # restored-abundance work at a different node.
    if hyp.level == "allele_function":
        for edge in _asserted_allele_edges(chain):
            if edge not in chosen:
                chosen.append(edge)
    return tuple(chosen)


def _caveat_edges(
    hyp: Hypothesis,
    chain: CausalChain,
    *,
    include_asserted_gap: bool,
) -> tuple[CausalEdge, ...]:
    found = [e for e in chain.edges if hyp.id in (e.caveat or "")]
    if include_asserted_gap and hyp.level == "allele_function":
        for edge in _asserted_allele_edges(chain):
            if edge not in found:
                found.append(edge)
    return tuple(found)


def _asserted_allele_edges(chain: CausalChain) -> tuple[CausalEdge, ...]:
    """The unresolved abundance→function edge the chain records for H01 versus H02."""
    return tuple(
        e for e in chain.edges
        if e.support is Support.ASSERTED_ONLY
        and ("H01" in (e.caveat or "") or "H02" in (e.caveat or ""))
    )


def _edge_requirements(hyp: Hypothesis, chain: CausalChain) -> tuple[EdgeRequirement, ...]:
    reqs: list[EdgeRequirement] = []

    if hyp.level == "allele_function":
        statement = hyp.statement.lower()
        # H01 claims abundance permits function (hold); H02 claims a defect remains (fail).
        if "defect" in statement and "despite" in statement:
            must: Literal["hold", "fail"] = "fail"
        elif "permits" in statement or "adequate abundance" in statement:
            must = "hold"
        else:
            must = "fail"
        for edge in _asserted_allele_edges(chain):
            reqs.append(EdgeRequirement(
                edge_key=edge.key, requirement=must, support=edge.support,
                scope_note=edge.scope_note, caveat=edge.caveat,
            ))

    if hyp.level == "drug_upstream":
        # Survives if blood→cell transfer (or equivalent upstream) fails to deliver.
        for edge in chain.edges:
            if edge.support is Support.DIFFERENT_COMPARTMENT:
                reqs.append(EdgeRequirement(
                    edge_key=edge.key, requirement="fail", support=edge.support,
                    scope_note=edge.scope_note, caveat=edge.caveat,
                ))

    if hyp.level == "drug_mechanism":
        # Survives if the SIRT2→BubR1 connection (different agent) fails for this agent.
        for edge in chain.edges:
            if edge.support is Support.DIFFERENT_AGENT:
                reqs.append(EdgeRequirement(
                    edge_key=edge.key, requirement="fail", support=edge.support,
                    scope_note=edge.scope_note, caveat=edge.caveat,
                ))

    if hyp.level == "confounding":
        for edge in chain.edges:
            if hyp.id in (edge.caveat or ""):
                reqs.append(EdgeRequirement(
                    edge_key=edge.key, requirement="hold", support=edge.support,
                    scope_note=edge.scope_note, caveat=edge.caveat,
                ))

    if hyp.level == "alternative_mechanism":
        # Survives when the favoured chain's load-bearing links fail while benefit appears.
        for edge in chain.edges:
            if edge.support in {Support.ASSERTED_ONLY, Support.DIFFERENT_AGENT,
                                Support.DIFFERENT_COMPARTMENT}:
                reqs.append(EdgeRequirement(
                    edge_key=edge.key, requirement="fail", support=edge.support,
                    scope_note=edge.scope_note, caveat=edge.caveat,
                ))

    # Translation hypotheses are outside the cellular chain; no edge requirement invented.
    return tuple(reqs)


def _separating_measurement(
    hyp: Hypothesis,
    chain: CausalChain,
    *,
    by_id: dict[str, Hypothesis],
) -> str | None:
    if not hyp.alternatives:
        return None
    # Mutual allele-function alternatives are separated by the unresolved abundance→function edge.
    alt_levels = {
        by_id[a].level for a in hyp.alternatives if a in by_id
    }
    if hyp.level == "allele_function" or alt_levels == {"allele_function"}:
        edges = _asserted_allele_edges(chain)
        if edges:
            return edges[0].key
    # Otherwise: any edge named in both hypotheses' caveats, else the first shared weak edge.
    own = {e.key for e in _caveat_edges(hyp, chain, include_asserted_gap=False)}
    for alt_id in hyp.alternatives:
        alt = by_id.get(alt_id)
        if alt is None:
            continue
        shared = own & {e.key for e in _caveat_edges(alt, chain, include_asserted_gap=False)}
        if shared:
            return sorted(shared)[0]
    return None


def _opposing_records(
    hyp: Hypothesis,
    chain: CausalChain,
    *,
    requirements: tuple[EdgeRequirement, ...],
    searched: frozenset[str],
) -> tuple[OpposingRecord, ...]:
    """Recorded opposition, or an explicit statement that nobody has looked.

    A CONTRADICTED edge opposes a hypothesis only when the hypothesis needs that path to hold,
    or when the hypothesis itself cites the contradicted evidence while claiming the path works.
    Failure hypotheses (H03/H04) that cite a null as supporting material are not treated as
    opposed by that same null.
    """
    opposed: list[OpposingRecord] = []
    hyp_tokens = _evidence_tokens(hyp)
    needs_hold = {r.edge_key for r in requirements if r.requirement == "hold"}

    for edge in chain.edges:
        if edge.support is not Support.CONTRADICTED:
            continue
        cites = bool(hyp_tokens & _pmid_tokens(edge.evidence_ref))
        # Only a contradicted edge the hypothesis needs to hold, or one it cites while
        # claiming a hold, counts as opposition. A failure hypothesis citing a null as
        # its own support is not opposed by that same null.
        if edge.key in needs_hold or (cites and needs_hold):
            opposed.append(OpposingRecord(
                status="opposed",
                evidence_ref=edge.evidence_ref,
                edge_key=edge.key,
                note=edge.scope_note or edge.caveat or "contradicted edge on chain",
                knowledge=Knowledge.EVIDENCE_AGAINST,
            ))

    if opposed:
        return tuple(opposed)

    if hyp.id in searched:
        return (OpposingRecord(
            status="none_recorded",
            note="opposing evidence was looked for; none is recorded against this hypothesis",
            knowledge=Knowledge.NOT_REPORTED,
        ),)

    return (OpposingRecord(
        status="none_looked_for",
        note=(
            f"no opposing evidence recorded and no search marked "
            f"({ResponseState.NOT_SEARCHED.value})"
        ),
        knowledge=Knowledge.NOT_MEASURED,
    ),)
