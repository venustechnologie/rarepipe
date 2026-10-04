"""Toy evidence inventories and realizations for the physical-realization gates. Not collected.

The toys build their own inventory rather than the repository's, so a gate can state exactly what
evidence exists and what it should therefore entitle. That is the only way to test an entitlement
rule: with the real inventory the answer would depend on the case's literature rather than on the
rule under test.
"""
from __future__ import annotations

from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.realization.compiler import RealizationProblem
from rarepipe.stages.control.realization.evidence import (
    ContextRecord, EvidenceEdge, EvidenceInventory,
)
from rarepipe.stages.control.realization.kinds import Effect, PrimitiveClass
from rarepipe.stages.control.realization.mechanisms import MechanisticRealization, Step
from rarepipe.stages.control.realization.primitives import (
    Capability, PhysicalPrimitive, PhysicalPrimitiveRegistry,
)
from rarepipe.stages.control.synthesis.kinds import TransformationScale
from rarepipe.stages.simulate.chain import Support
from tests import synthesis_toys as S

SYSTEM = "toy system"
OTHER_SYSTEM = "a different toy system"
AGENT = "toy agent"
OTHER_AGENT = "a different toy agent"


def prov(kind=EpistemicType.BUILDING_BLOCK_CAPABILITY, **kw):
    kw.setdefault("rationale", "toy declaration for a proof gate")
    return Provenance(epistemic_type=kind, source="toy", proposed_by="test", **kw)


def edge(source, target, *, support=Support.MODEL_EXPERIMENTAL, effect=Effect.INCREASE,
         ref="PMID:00000001", verified=True, caveat=""):
    return EvidenceEdge(edge_id=f"{source}->{target}", source=source, target=target, effect=effect,
                        mechanism=f"toy claim that {source} changes {target}", support=support,
                        ref=ref, verified=verified, scope="toy scope", caveat=caveat)


def inventory(edges, *, measured_with=AGENT, measured_in_system=SYSTEM,
              measured_in_compartment="", ref="PMID:00000001"):
    return EvidenceInventory(
        edges=tuple(sorted(edges, key=lambda e: e.edge_id)),
        contexts=(ContextRecord(ref=ref, measured_with=measured_with,
                                measured_in_compartment=measured_in_compartment,
                                measured_in_system=measured_in_system,
                                transcribed_from="toy"),))


def capability(cap_id, affects, *, acts_on="", acts_by=Effect.INCREASE, effect=Effect.INCREASE,
               to=None, edges=(), agent="", compartment="", requires=(), destroys=()):
    return Capability(capability_id=cap_id, claim=f"toy capability affecting {affects}",
                      acts_on=acts_on, acts_by=acts_by, affects=affects, effect=effect, to=to,
                      agent=agent, compartment=compartment, evidence_edges=tuple(edges),
                      requires=tuple(requires), destroys=tuple(destroys))


def primitive(pid, *capabilities, kind=PrimitiveClass.PROTEIN,
              epistemic=EpistemicType.BUILDING_BLOCK_CAPABILITY, refs=()):
    return PhysicalPrimitive(
        primitive_id=pid, primitive_class=kind, identity=f"toy piece {pid}",
        capabilities=tuple(capabilities), required_context=SYSTEM, cell_type="toy cell",
        biological_scale="cell", reversibility="unknown",
        temporal_properties="unknown; no time constant is claimed",
        delivery_requirements="none; this is a toy piece",
        evidence="declared by the toy for a proof gate", validity_domain="toy",
        uncertainty="toy piece, not a real one", feasibility_status="unassessed",
        provenance=prov(epistemic, references=refs))


def realization(rid, variable, value, *steps, effect=Effect.SET, agent=AGENT, system=SYSTEM,
                decomposes=(), unknown=(), confounds=(), epistemic=EpistemicType.BUILDING_BLOCK_CAPABILITY):
    return MechanisticRealization(
        realization_id=rid, required_transformation=f"{variable}->{value}",
        target_variable=variable, target_value=value, required_effect=effect,
        mechanism=f"toy mechanism proposed to produce {variable} = {value}",
        steps=tuple(Step(step_id=sid, uses_primitive=pid, capability_id=cid,
                         rationale="toy step for a proof gate")
                    for sid, pid, cid in steps),
        agent=agent, context_system=system, decomposes_into=tuple(decomposes),
        unknown_steps=tuple(unknown), confound_observables=tuple(confounds),
        provenance=prov(epistemic))


def synthesis_for(target_variable, target_value, *, extra_vars=(), unsafe_on=(), start=None,
                  observed=None, block_id="BB_TOY", extra_transformations=()):
    """A one-block synthesis problem whose block declares the transformation to be realized."""
    space_vars = [S.var("origin", exogenous=True), S.var(target_variable, (target_value, "other")),
                  *extra_vars]
    space = S.StateSpace(variables=tuple(space_vars))
    rels = [S.rel("R_TARGET", ("origin",), target_variable,
                  lambda o: target_value if o == "1" else "other", space)]
    problem = S.build(space_vars, [S.model(rels)], target_on=((target_variable, target_value),),
                      unsafe_on=unsafe_on,
                      start=start or {"origin": "0", target_variable: "other",
                                      **{v.name: v.domain[0] for v in extra_vars}},
                      observed=observed)
    block = S.block(block_id, S.tf(target_variable, target_value), *extra_transformations)
    return S.synthesis(problem, [block]), block_id


def build(target_variable, target_value, registry, inv, realizations, *, system=SYSTEM,
          unsafe_on=(), extra_vars=(), observed=None, extra_transformations=()):
    synthesis, block_id = synthesis_for(target_variable, target_value, unsafe_on=unsafe_on,
                                        extra_vars=extra_vars, observed=observed,
                                        extra_transformations=extra_transformations)
    return RealizationProblem(
        problem_id="toy-realization", case_ref="TOY", synthesis=synthesis,
        target_architecture=block_id, registry=registry, inventory=inv,
        realizations=tuple(realizations), required_system=system,
        realization_model_version="toy-realization-v1")


# ---------------------------------------------------------------- the toys

def grounded(*, support=Support.MODEL_EXPERIMENTAL, verified=True, cite=True, system=SYSTEM):
    """Gate 1 / 5 / 6: one step, one claim, and whatever that claim entitles."""
    inv = inventory([edge("dose", "func", support=support, verified=verified)],
                    measured_in_system=system)
    cap = capability("CAP_SET", "func", effect=Effect.SET, to="normal",
                     edges=("dose->func",) if cite else (), agent=AGENT)
    reg = PhysicalPrimitiveRegistry(primitives=(primitive("PP_ONE", cap),))
    return build("func", "normal", reg, inv,
                 [realization("MR_ONE", "func", "normal", ("S1", "PP_ONE", "CAP_SET"))])


def wrong_direction():
    """Gate 2: the component lowers what the transformation needs raised."""
    inv = inventory([edge("dose", "level", effect=Effect.DECREASE)])
    cap = capability("CAP_LOWER", "level", effect=Effect.INCREASE, edges=("dose->level",),
                     agent=AGENT)
    reg = PhysicalPrimitiveRegistry(primitives=(primitive("PP_DOWN", cap),))
    return build("level", "high", reg, inv,
                 [realization("MR_DOWN", "level", "high", ("S1", "PP_DOWN", "CAP_LOWER"),
                              effect=Effect.INCREASE)])


def wrong_agent():
    """Gate 3: the only support was obtained with a different agent than this chain administers."""
    inv = inventory([edge("dose", "func", support=Support.DIFFERENT_AGENT)],
                    measured_with=OTHER_AGENT)
    cap = capability("CAP_SET", "func", effect=Effect.SET, to="normal",
                     edges=("dose->func",), agent=OTHER_AGENT)
    reg = PhysicalPrimitiveRegistry(primitives=(primitive("PP_ONE", cap),))
    return build("func", "normal", reg, inv,
                 [realization("MR_ONE", "func", "normal", ("S1", "PP_ONE", "CAP_SET"),
                              agent=AGENT)])


def missing_link():
    """Gate 4: A -> B -> ? -> D, with nothing producing the third node."""
    inv = inventory([edge("dose", "b"), edge("c", "func")])
    reg = PhysicalPrimitiveRegistry(primitives=(
        primitive("PP_A", capability("CAP_A", "b", edges=("dose->b",), agent=AGENT)),
        primitive("PP_C", capability("CAP_C", "func", acts_on="c", effect=Effect.SET, to="normal",
                                     edges=("c->func",), agent=AGENT)),
    ))
    return build("func", "normal", reg, inv,
                 [realization("MR_GAP", "func", "normal", ("S1", "PP_A", "CAP_A"),
                              ("S2", "PP_C", "CAP_C"))])


def redundant():
    """Gate 7: an extra component that changes nothing."""
    inv = inventory([edge("dose", "func"), edge("dose", "spare")])
    reg = PhysicalPrimitiveRegistry(primitives=(
        primitive("PP_MAIN", capability("CAP_SET", "func", effect=Effect.SET, to="normal",
                                        edges=("dose->func",), agent=AGENT)),
        primitive("PP_SPARE", capability("CAP_SPARE", "spare", edges=("dose->spare",),
                                         agent=AGENT)),
    ))
    return build("func", "normal", reg, inv,
                 [realization("MR_EXTRA", "func", "normal", ("S1", "PP_MAIN", "CAP_SET"),
                              ("S2", "PP_SPARE", "CAP_SPARE"))],
                 extra_vars=[S.var("spare")])


def unsafe():
    """Gate 8: the function is produced by driving a forbidden variable into its forbidden state."""
    inv = inventory([edge("dose", "func"), edge("dose", "death")])
    reg = PhysicalPrimitiveRegistry(primitives=(
        primitive("PP_KILL",
                  capability("CAP_SET", "func", effect=Effect.SET, to="normal",
                             edges=("dose->func",), agent=AGENT),
                  capability("CAP_KILL", "death", effect=Effect.SET, to="increased",
                             edges=("dose->death",), agent=AGENT)),
    ))
    return build("func", "normal", reg, inv,
                 [realization("MR_KILL", "func", "normal", ("S1", "PP_KILL", "CAP_SET"),
                              ("S2", "PP_KILL", "CAP_KILL"))],
                 extra_vars=[S.var("death", ("baseline", "increased"), exogenous=True)],
                 unsafe_on=(("death", "increased"),),
                 # Declared as an off-target effect, not a required function: killing the cells
                 # is what the architecture does on the way, and the safety filter still has to see it.
                 extra_transformations=(S.tf("death", "increased", intended=False,
                                             scale=TransformationScale.POPULATION),))


def confounded(*, name_observable=False, observed=None):
    """Gate 9: the cited claim carries a caveat, so the reading needs what would exclude it."""
    inv = inventory([edge("dose", "func", caveat="the reading can also be produced by cell loss")])
    cap = capability("CAP_SET", "func", effect=Effect.SET, to="normal", edges=("dose->func",),
                     agent=AGENT)
    reg = PhysicalPrimitiveRegistry(primitives=(primitive("PP_ONE", cap),))
    return build("func", "normal", reg, inv,
                 [realization("MR_ONE", "func", "normal", ("S1", "PP_ONE", "CAP_SET"),
                              confounds=("death_marker",) if name_observable else ())],
                 observed=observed)
