"""Toy gaps, corpora and candidates for the capability-discovery gates. Not collected by pytest.

The toys supply their own corpus so a gate can state exactly what evidence exists and what it
should therefore entitle. With the real inventory the answer would depend on the case's literature
rather than on the validator under test.
"""
from __future__ import annotations

from rarepipe.stages.control.discovery.candidates import CapabilityCandidate
from rarepipe.stages.control.discovery.compiler import GapProblem
from rarepipe.stages.control.discovery.gaps import CapabilityGap, RequiredContext
from rarepipe.stages.control.discovery.providers import (
    CuratedFileProvider, RepositoryProvider,
)
from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.realization.evidence import (
    ContextRecord, EvidenceEdge, EvidenceInventory,
)
from rarepipe.stages.control.realization.kinds import Effect, EpistemicBurden
from rarepipe.stages.simulate.chain import Support
from tests import synthesis_toys as S

SYSTEM = "toy system"
OTHER_SYSTEM = "a different toy system"
AGENT = "toy agent"
OTHER_AGENT = "a different toy agent"
COMPARTMENT = "toy intracellular pool"
OTHER_COMPARTMENT = "toy circulating pool"
REF = "PMID:00000001"


def prov(kind=EpistemicType.LITERATURE_EVIDENCE, **kw):
    kw.setdefault("rationale", "toy declaration for a proof gate")
    if kind in {EpistemicType.LITERATURE_EVIDENCE}:
        kw.setdefault("references", (REF,))
    return Provenance(epistemic_type=kind, source="toy", proposed_by="test", **kw)


def edge(source, target, *, effect=Effect.SET, support=Support.MODEL_EXPERIMENTAL, ref=REF,
         verified=True, caveat=""):
    return EvidenceEdge(edge_id=f"{source}->{target}", source=source, target=target, effect=effect,
                        mechanism=f"toy claim that {source} sets {target}", support=support,
                        ref=ref, verified=verified, scope="toy scope", caveat=caveat)


def inventory(edges, *, agent=AGENT, compartment=COMPARTMENT, system=SYSTEM, ref=REF):
    return EvidenceInventory(
        edges=tuple(sorted(edges, key=lambda e: e.edge_id)),
        contexts=(ContextRecord(ref=ref, measured_with=agent, measured_in_compartment=compartment,
                                measured_in_system=system, transcribed_from="toy"),))


def gap(gap_id="GAP_TOY", *, output="func", value="normal", direction=Effect.SET,
        forbidden=(), agent="", compartment="", system=SYSTEM, required_input="",
        burden=EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP, forbidden_states=()):
    return CapabilityGap(
        gap_id=gap_id, required_transformation=f"{output}->{value}", required_output=output,
        required_value=value, required_direction=direction, required_input=required_input,
        forbidden_dependencies=tuple(forbidden),
        required_context=RequiredContext(agent=agent, compartment=compartment, system=system),
        biological_scale="cell", forbidden_states=tuple(forbidden_states),
        epistemic_burden=burden, observables_needed=(output,),
        current_known_paths=(), current_missing_reason="declared by the toy for a proof gate",
        rationale="declared by the toy for a proof gate")


def candidate(cid, *, gap_id="GAP_TOY", entity="dose", inputs=("dose",), output="func",
              value="normal", direction=Effect.SET, refs=(), agent="", compartment="",
              system=SYSTEM, safety=()):
    return CapabilityCandidate(
        candidate_id=cid, gap_id=gap_id,
        proposed_mechanism=f"toy proposal that {entity} sets {output} to {value}",
        proposed_entity_or_process=entity, required_inputs=tuple(inputs), claimed_output=output,
        claimed_direction=direction, claimed_value=value,
        context=RequiredContext(agent=agent, compartment=compartment, system=system),
        biological_scale="cell", possible_safety_effects=tuple(safety),
        supporting_evidence_refs=tuple(refs), provenance=prov())


def problem(gaps, inv, *, space=None, candidates=(), curated=None):
    space = space or S.StateSpace(variables=(S.var("dose", exogenous=True),
                                            S.var("func", ("normal", "other"))))
    return GapProblem(
        problem_id="toy-gaps", case_ref="TOY", gaps=tuple(gaps), inventory=inv, space=space,
        providers=(RepositoryProvider(inv), CuratedFileProvider(curated)),
        discovery_model_version="toy-discovery-v1", agent_candidates=tuple(candidates))


# ---------------------------------------------------------------- the toys

def exact():
    """Gate 1 / 12: the corpus contains exactly the claim the gap asks for."""
    return problem([gap()], inventory([edge("dose", "func")]))


def no_evidence():
    """Gate 12: the same gap with the grounding claim removed from the corpus."""
    return problem([gap()], inventory([edge("dose", "other_node")]))


def wrong_input():
    """Gate 2: the right output from the wrong input, which must not count as the claim."""
    inv = inventory([edge("other_input", "func")])
    return problem([gap(required_input="dose")], inv,
                   candidates=[candidate("CC_BORROWED", inputs=("dose",),
                                         refs=("other_input->func",))])


def wrong_direction():
    """Gate 3: the output matches and the sign is opposite."""
    inv = inventory([edge("dose", "level", effect=Effect.DECREASE)])
    space = S.StateSpace(variables=(S.var("dose", exogenous=True), S.var("level")))
    return problem([gap(output="level", value="1", direction=Effect.INCREASE)], inv, space=space)


def forbidden_dependency():
    """Gate 4: the candidate looks independent and its mechanism runs through the forbidden node."""
    inv = inventory([edge("blocked_node", "func"), edge("dose", "blocked_node")])
    space = S.StateSpace(variables=(S.var("dose", exogenous=True), S.var("blocked_node"),
                                    S.var("func", ("normal", "other"))))
    return problem([gap(forbidden=("blocked_node",))], inv, space=space)


def wrong_system():
    """Gate 5: right mechanism, incompatible system."""
    return problem([gap()], inventory([edge("dose", "func")], system=OTHER_SYSTEM))


def wrong_agent():
    """Gate 6: the effect was shown with a different agent, which is not inherited."""
    return problem([gap(agent=AGENT)], inventory([edge("dose", "func")], agent=OTHER_AGENT))


def wrong_compartment():
    """Gate 7: the circulating pool is not the intracellular pool."""
    return problem([gap(compartment=COMPARTMENT)],
                   inventory([edge("dose", "func")], compartment=OTHER_COMPARTMENT))


def unsupported_intermediate():
    """Gate 8: A -> B is grounded, B -> C has no source, and C is what is claimed."""
    inv = inventory([edge("dose", "middle")])
    space = S.StateSpace(variables=(S.var("dose", exogenous=True), S.var("middle"),
                                    S.var("func", ("normal", "other"))))
    return problem([gap()], inv, space=space,
                   candidates=[candidate("CC_CHAIN", inputs=("dose",), output="func",
                                         refs=("dose->middle",))])


def contradicted():
    """Gate 9: the most relevant claim is a null or opposite result."""
    return problem([gap()], inventory([edge("dose", "func", support=Support.CONTRADICTED)]))


def fabricated():
    """Gate 10: an agent invents an entity, a claim and a reference."""
    inv = inventory([edge("dose", "func")])
    return problem([gap()], inv, candidates=[
        candidate("CC_INVENTED_SOURCE", entity="invented_protein", inputs=("invented_protein",),
                  refs=("invented_protein->func",)),
        candidate("CC_INVENTED_ENTITY", entity="invented_protein", inputs=("invented_protein",),
                  refs=("dose->func",)),
        candidate("CC_NO_SOURCE", entity="dose", inputs=("dose",), refs=()),
    ])


def unverified():
    """A corpus whose citation has no retrieval record caps the result at conditional."""
    return problem([gap()], inventory([edge("dose", "func", verified=False)]))


def recompile_target(inv):
    """Gate 11: a realization problem whose required function has no declared mechanism."""
    from tests import realization_toys as R
    return R.build("func", "normal", R.PhysicalPrimitiveRegistry(primitives=()), inv, [],
                   system=SYSTEM)
