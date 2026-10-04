"""Toy external corpora for the real-evidence gates. Not collected by pytest.

A toy corpus states exactly what a source says, so a gate tests a validator rather than the state of
somebody's literature. The documents live in memory: the provider never reads a file, and the
span-grounding check is handed the same text the provider was built from, which is the point — a span
that does not appear in it must fail.
"""
from __future__ import annotations

from pathlib import Path

from rarepipe.stages.control.discovery.compiler import GapProblem
from rarepipe.stages.control.discovery.external.claims import (
    CandidateClaim, CausalGrade, ContextLattice,
)
from rarepipe.stages.control.discovery.external.corpus import (
    CorpusSnapshot, ExternalDocument, QueryOutcome, QueryOutcomeRecord,
)
from rarepipe.stages.control.discovery.external.literature import LiteratureProvider
from rarepipe.stages.control.discovery.external.semantics import SemanticsRegistry
from rarepipe.stages.control.discovery.providers import CuratedFileProvider, RepositoryProvider
from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.realization.kinds import Effect
from tests import discovery_toys as D
from tests import synthesis_toys as S

SYSTEM = "toy cellular system"
OTHER_SYSTEM = "a different toy organism"
TOY_TEXT = (
    "A toy study of the toy pathway.\n\n"
    "We administered the toy actuator and measured the toy output directly. "
    "The toy actuator raised the toy output to the level of untreated controls in the toy cellular "
    "system. No dependence on any other component was required for this effect."
)
SPAN = ("The toy actuator raised the toy output to the level of untreated controls in the toy "
        "cellular system")
INDEPENDENCE_SPAN = "No dependence on any other component was required for this effect"


def document(source_id="PMID:00000099", title="A toy study of the toy pathway", year=2024):
    return ExternalDocument(
        source_id=source_id, source_type="journal_article", title=title, pmid="00000099",
        retrieved_at="2026-10-04T00:00:00+00:00", retrieved_by_query="toy query",
        content_digest="sha256:toy", characters_stored=len(TOY_TEXT),
        access_note="toy abstract", relative_path=f"docs/{source_id.replace(':', '_')}.txt")


def snapshot(documents, gap_id="GAP_TOY", *, outcome=QueryOutcome.RESULTS_RETURNED, results=7):
    return CorpusSnapshot(
        corpus_version="toy-external-v1", provider_id="scientific-literature-provider",
        provider_version="0.1.0", created_at="2026-10-04T00:00:00+00:00",
        index="toy index", full_text_policy="abstracts only in the toy",
        queries=(QueryOutcomeRecord(
            gap_id=gap_id, query_id="Q01", query='"toy output" AND "toy actuator"',
            dimension="the function itself", generated_by="toy planner", executed_on="toy index",
            timestamp="2026-10-04T00:00:00+00:00", outcome=outcome, results=results,
            selected=len(documents),
            source_ids=tuple(sorted(d.source_id for d in documents)),
            note="" if results else "the index returned nothing for this query"),),
        documents=tuple(documents))


def claim(claim_id="CL_TOY", *, gap_id="GAP_TOY", source_id="PMID:00000099",
          subject="toy actuator", obj="func", direction=Effect.INCREASE, state="",
          grade=CausalGrade.CAUSAL_EXPERIMENTAL, span=SPAN, lattice=None, deps=(),
          independence=(), limitation=""):
    return CandidateClaim(
        claim_id=claim_id, gap_id=gap_id, source_id=source_id, subject=subject,
        relation="raises the toy output", object=obj, direction=direction, claimed_state=state,
        causal_grade=grade,
        context=lattice or ContextLattice(species="toy", cell_type=SYSTEM, compartment="toy cell",
                                          experimental_system=SYSTEM,
                                          perturbation_type="administered toy actuator"),
        declared_dependencies=tuple(deps), asserts_independence_from=tuple(independence),
        source_span=span, measurement="toy output relative to untreated controls",
        limitation=limitation, extracted_by="toy extractor",
        provenance=Provenance(epistemic_type=EpistemicType.INFERRED_HYPOTHESIS, source="toy",
                              proposed_by="test", references=("PMID:00000099",),
                              rationale="a toy reading for a proof gate"))


def problem(gaps, inv, claims, docs, *, texts=None, space=None, semantics=None,
            snapshot_override=None, baseline=None):
    space = space or S.StateSpace(variables=(S.var("dose", exogenous=True),
                                            S.var("func", ("normal", "other"))))
    snap = snapshot_override or snapshot(docs, gap_id=gaps[0].gap_id)
    external = LiteratureProvider(Path("."), snap, tuple(claims))
    return GapProblem(
        problem_id="toy-external", case_ref="TOY", gaps=tuple(gaps), inventory=inv, space=space,
        providers=(RepositoryProvider(inv), external, CuratedFileProvider(None)),
        discovery_model_version="toy-external-v1",
        documents=texts if texts is not None else {d.source_id: TOY_TEXT for d in docs},
        semantics=semantics or SemanticsRegistry(),
        baseline_results=baseline or {}, baseline_providers=("repository_inventory",))


# ---------------------------------------------------------------- the toys

def grounds(**claim_kwargs):
    """Gates 1, 2, 11: a real source, an exact span, and a capability the validators accept."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM)
    return problem([gap], inv, [claim(**claim_kwargs)], [document()])


def bad_span():
    """Gate 2: a paraphrase is not a span."""
    return grounds(span="The toy actuator restored the toy output completely, we believe")


def invented_source():
    """Gate 3: a claim citing a document the corpus does not hold."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM)
    return problem([gap], inv, [claim(source_id="PMID:99999999")], [document()])


def association_only():
    """Gate 9: an association cannot satisfy a capability asserting a causal transformation."""
    return grounds(grade=CausalGrade.ASSOCIATION)


def wrong_system():
    """Gate 7: the right relation, demonstrated somewhere else."""
    return grounds(lattice=ContextLattice(species="toy", cell_type=OTHER_SYSTEM,
                                          compartment="toy cell",
                                          experimental_system=OTHER_SYSTEM,
                                          perturbation_type="administered toy actuator"))


def forbidden_ancestry():
    """Gate 8: an external candidate that looks independent and declares a forbidden dependency."""
    inv = D.inventory([D.edge("blocked_node", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM,
                forbidden=("blocked_node",))
    return problem([gap], inv, [claim(deps=("blocked_node",))], [document()])


def independence_unestablished():
    """No source says the mechanism works without the forbidden component, so it is not a bypass."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM,
                forbidden=("blocked_node",))
    return problem([gap], inv, [claim()], [document()])


def independence_asserted():
    """A source that states the mechanism needs nothing else can satisfy a bypass gap."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM,
                forbidden=("blocked_node",))
    return problem([gap], inv, [claim(span=INDEPENDENCE_SPAN,
                                      independence=("blocked_node",))], [document()])


def effect_is_not_state():
    """Gate 6 / semantics: a reported increase is not a restored function without a mapping."""
    from rarepipe.stages.control.discovery.external.semantics import FunctionalSemantics
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="normal", direction=Effect.SET, system=SYSTEM)
    registry = SemanticsRegistry(semantics=(FunctionalSemantics(
        variable="func", state="normal",
        requires=("the output responds when it should", "the output stands down when it should"),
        excludes=("the output held high permanently",),
        rationale="a level-only reading cannot separate an appropriate response from a stuck one"),))
    return problem([gap], inv, [claim()], [document()], semantics=registry)


def zero_results():
    """Gate 16: the search ran and the index returned nothing. Not an absence in biology."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM)
    return problem([gap], inv, [], [],
                   snapshot_override=snapshot([], gap_id=gap.gap_id,
                                              outcome=QueryOutcome.SEARCH_RETURNED_ZERO_RESULTS,
                                              results=0))


def provider_unavailable():
    """Gate 16: the provider could not run, which is not the same fact at all."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM)
    return problem([gap], inv, [], [],
                   snapshot_override=snapshot([], gap_id=gap.gap_id,
                                              outcome=QueryOutcome.PROVIDER_UNAVAILABLE, results=0))


def irrelevant_capability():
    """Gate 14: a capability that grounds and lands nowhere near the architecture."""
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="spare", value="", direction=Effect.INCREASE, system=SYSTEM)
    space = S.StateSpace(variables=(S.var("dose", exogenous=True),
                                    S.var("func", ("normal", "other")), S.var("spare")))
    return problem([gap], inv, [claim(gap_id=gap.gap_id, obj="spare")], [document()], space=space)


def target_for(inv):
    """A realization target whose required function has no declared mechanism."""
    from tests import realization_toys as R
    return R.build("func", "normal", R.PhysicalPrimitiveRegistry(primitives=()), inv, [],
                   system=SYSTEM)


def borrowed_external():
    """Gates 4 and 5: an agent candidate citing a real external source for a different claim.

    The source exists and says something true. The candidates assert a different input and a
    different output from the one the source measured, which is the error this layer refuses: a real
    paper is not evidence for a claim it did not make.
    """
    from dataclasses import replace
    inv = D.inventory([D.edge("unrelated", "other_node")])
    gap = D.gap(output="func", value="", direction=Effect.INCREASE, system=SYSTEM)
    space = S.StateSpace(variables=(S.var("dose", exogenous=True),
                                    S.var("func", ("normal", "other")), S.var("spare")))
    base = problem([gap], inv, [claim()], [document()], space=space)
    extra = (
        D.candidate("CC_WRONG_INPUT", gap_id=gap.gap_id, entity="other_actuator",
                    inputs=("other_actuator",), output="func", value="",
                    direction=Effect.INCREASE, refs=("PMID:00000099",), system=SYSTEM),
        D.candidate("CC_WRONG_OUTPUT", gap_id=gap.gap_id, entity="toy actuator",
                    inputs=("toy actuator",), output="spare", value="",
                    direction=Effect.INCREASE, refs=("PMID:00000099",), system=SYSTEM),
    )
    return replace(base, agent_candidates=extra)
