"""Small, fully specified systems for the synthesis compiler's proof gates. Not collected by pytest.

Each toy exists to make one claim falsifiable. They use explicit domains rather than the binary
ones in control_toys because several gates need a three-valued variable — an overshoot or a warning
region cannot be expressed with two values.
"""
from __future__ import annotations

from itertools import product

from rarepipe.stages.control.compiler import Problem
from rarepipe.stages.control.controls import BiologicalControlKind, Feasibility, RouteClass
from rarepipe.stages.control.dynamics import Model, Plausibility, Relationship, RelationshipKind
from rarepipe.stages.control.observability import ObservationModel
from rarepipe.stages.control.provenance import (
    Approval, ApprovalStatus, EpistemicType, Provenance,
)
from rarepipe.stages.control.safety_constraints import SafetyConstraint, UnsafeRegion
from rarepipe.stages.control.state_space import StateSpace, Variable, VariableKind
from rarepipe.stages.control.synthesis.building_blocks import (
    BlockTransformation, BuildingBlock, BuildingBlockRegistry,
)
from rarepipe.stages.control.synthesis.compiler import SynthesisProblem
from rarepipe.stages.control.synthesis.feedback import (
    FeedbackAction, FeedbackPolicy, FeedbackRule,
)
from rarepipe.stages.control.synthesis.kinds import (
    BlockClass, Direction, Reversibility, TransformationScale,
)
from rarepipe.stages.control.synthesis.population import PopulationLayer
from rarepipe.stages.control.target_constraints import Membership, TargetConstraint, TargetRegion
from rarepipe.stages.control.uncertainty import StateEvidence

BIN = ("0", "1")
PROPOSED = Approval(status=ApprovalStatus.PROPOSED, note="toy; no scientist has approved it")
INTRA = TransformationScale.INTRACELLULAR
POP = TransformationScale.POPULATION


def prov(kind=EpistemicType.MODEL_ASSUMPTION, **kw):
    if kind is EpistemicType.MODEL_ASSUMPTION:
        kw.setdefault("rationale", "toy network built for one proof gate")
    if kind in {EpistemicType.BUILDING_BLOCK_CAPABILITY, EpistemicType.FEEDBACK_POLICY,
                EpistemicType.POPULATION_CONTROL, EpistemicType.INFERRED_HYPOTHESIS}:
        kw.setdefault("rationale", "toy capability declared for a proof gate")
    return Provenance(epistemic_type=kind, source="toy", proposed_by="test", **kw)


def var(name, domain=BIN, *, exogenous=False, latent=False, meaning=""):
    return Variable(name=name, kind=VariableKind.CATEGORICAL, domain=domain,
                    meaning=meaning or f"toy {name}", latent=latent, exogenous=exogenous,
                    exogenous_reason="toy input with no upstream mechanism in this model"
                    if exogenous else "")


def rel(rid, inputs, output, fn, space, *, status="established"):
    domains = [space.variable(i).domain for i in inputs]
    table = tuple((combo, fn(*combo)) for combo in product(*domains))
    return Relationship(relationship_id=rid, inputs=tuple(inputs), output=output,
                        kind=RelationshipKind.TABLE, table=table, epistemic_status=status,
                        provenance=prov(), validity_domain="toy")


def model(rels, model_id="M", plausibility=Plausibility.ACCEPTED):
    return Model(model_id=model_id, plausibility=plausibility, statement="toy model",
                 relationships=tuple(rels), provenance=prov())


def tf(variable, to, *, direction=Direction.SET, scale=INTRA, intended=True, released_to=None,
       rationale="", kind=BiologicalControlKind.PATHWAY_ACTIVATION, magnitude=""):
    return BlockTransformation(
        variable=variable, to=to, direction=direction, scale=scale, control_kind=kind,
        intended=intended, released_to=released_to,
        release_rationale=rationale or ("the toy variable decays to its baseline with no "
                                        "maintaining mechanism" if released_to else ""),
        magnitude_if_known=magnitude)


def block(bid, *transformations, feasibility=Feasibility.ESTABLISHED, route=RouteClass.BYPASS,
          scale=INTRA, reversibility=Reversibility.UNKNOWN, requires=(),
          kind=BlockClass.CELLULAR_PROCESS, epistemic=EpistemicType.BUILDING_BLOCK_CAPABILITY,
          refs=()):
    return BuildingBlock(
        building_block_id=bid, block_class=kind,
        mechanism=f"toy capability {bid}: holds its declared variables at their declared values",
        route_class=route, input_state_requirements=tuple(requires),
        state_transformations=tuple(transformations), scale=scale, reversibility=reversibility,
        cell_type="toy cell", tissue_context="toy tissue",
        delivery_requirements="none; this is a toy capability",
        evidence="declared by the toy for a proof gate; no biological support is claimed",
        evidence_refs=refs, validity_domain="toy", uncertainty="toy capability, not a real one",
        feasibility_status=feasibility,
        feasibility_note=("established by construction for this gate"
                          if feasibility is Feasibility.ESTABLISHED
                          else f"{feasibility.value} by construction for this gate"),
        provenance=prov(epistemic, references=refs),
    )


def policy(policy_id, *rules):
    return FeedbackPolicy(
        policy_id=policy_id,
        rules=tuple(FeedbackRule(rule_id=f"R{i}", when=Membership(variable=v, allowed=(val,)),
                                 action=action, control_id=cid,
                                 rationale="toy policy rule for a proof gate")
                    for i, (v, val, action, cid) in enumerate(rules, start=1)),
        sampling="one reading per decision point; no interval is claimed",
        provenance=prov(EpistemicType.FEEDBACK_POLICY))


ACTIVATE, DEACTIVATE = FeedbackAction.ACTIVATE, FeedbackAction.DEACTIVATE


def evidence_at(**values):
    return tuple(StateEvidence(evidence_id=f"E_{k}", variable=k, allowed=(v,), provenance=prov(),
                               generated_under="toy")
                 for k, v in sorted(values.items()))


def build(space_vars, models, *, target_on, unsafe_on=(), start, observed=None,
          extra_observed=(), max_depth=3):
    space = StateSpace(variables=tuple(space_vars))
    target = TargetRegion(constraints=tuple(
        TargetConstraint(constraint_id=f"T_{v}", meaning=f"{v} reaches {val}",
                         predicate=Membership(variable=v, allowed=(val,)),
                         provenance=prov(EpistemicType.TARGET_CONSTRAINT), approval=PROPOSED)
        for v, val in target_on))
    unsafe = UnsafeRegion(constraints=tuple(
        SafetyConstraint(constraint_id=f"S_{v}", meaning=f"{v} reaches {val}",
                         unsafe_when=Membership(variable=v, allowed=(val,)),
                         provenance=prov(EpistemicType.SAFETY_CONSTRAINT), approval=PROPOSED)
        for v, val in unsafe_on))
    obs = ObservationModel(
        name="Y", observed=tuple(observed if observed is not None else space.names) + tuple(extra_observed),
        provenance=prov(EpistemicType.DECISION_RULE), generated_under="toy")
    return Problem(problem_id="toy", case_ref="TOY", space=space, evidence=evidence_at(**start),
                   target=target, unsafe=unsafe, models=tuple(models), controls=(),
                   observation=obs, state_model_version="toy-state-v1", rule_version="toy-rules-v1",
                   case_context_version="toy-context-v1", max_depth=max_depth)


def synthesis(problem, blocks, *, population=None, policies=(), proposed=(), families=(),
              max_depth=2, max_per_step=2):
    return SynthesisProblem(
        problem=problem, registry=BuildingBlockRegistry(blocks=tuple(blocks)),
        population=population or PopulationLayer(), policies=tuple(policies),
        proposed=tuple(proposed), families=tuple(families),
        synthesis_model_version="toy-synthesis-v1", max_depth=max_depth, max_per_step=max_per_step)


# ---------------------------------------------------------------- the toys

def repair_only(feasibility=Feasibility.ESTABLISHED, drop_relationship=False):
    """Gate 1 / 10 / 12: the lesion is the only way to the target."""
    space_vars = [var("lesion", exogenous=True), var("func")]
    space = StateSpace(variables=tuple(space_vars))
    rels = [] if drop_relationship else [rel("R_FUNC", ("lesion",), "func", lambda g: g, space)]
    problem = build(space_vars, [model(rels)], target_on=(("func", "1"),),
                    start={"lesion": "0", "func": "0"})
    blocks = [block("B_REPAIR", tf("lesion", "1", direction=Direction.INCREASE),
                    feasibility=feasibility, route=RouteClass.REPAIR)]
    return problem, blocks


def bypass():
    """Gate 2: the damaged node cannot be touched; another input reaches the same output."""
    space_vars = [var("lesion", exogenous=True), var("func"), var("alt_input", exogenous=True),
                  var("output")]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_FUNC", ("lesion",), "func", lambda g: g, space),
            rel("R_OUT", ("func", "alt_input"), "output",
                lambda f, a: "1" if f == "1" or a == "1" else "0", space)]
    problem = build(space_vars, [model(rels)], target_on=(("output", "1"),),
                    start={"lesion": "0", "func": "0", "alt_input": "0", "output": "0"})
    blocks = [block("B_ALT", tf("alt_input", "1"), route=RouteClass.BYPASS)]
    return problem, blocks


def two_needed():
    """Gate 3: neither component alone reaches the target; together they do."""
    space_vars = [var("a", exogenous=True), var("b", exogenous=True), var("t")]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_T", ("a", "b"), "t", lambda a, b: "1" if a == "1" and b == "1" else "0", space)]
    problem = build(space_vars, [model(rels)], target_on=(("t", "1"),),
                    start={"a": "0", "b": "0", "t": "0"})
    blocks = [block("B_A", tf("a", "1")), block("B_B", tf("b", "1"))]
    return problem, blocks


def unsafe_shortcut():
    """Gate 4: the cheapest way to the target reading is to kill the cells that carry it."""
    space_vars = [var("func", exogenous=True), var("dead", ("baseline", "increased"), exogenous=True),
                  var("aneuploid", ("high", "low"))]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_ANEU", ("func", "dead"), "aneuploid",
                lambda f, d: "low" if f == "1" or d == "increased" else "high", space)]
    problem = build(space_vars, [model(rels)], target_on=(("aneuploid", "low"),),
                    unsafe_on=(("dead", "increased"),),
                    start={"func": "0", "dead": "baseline", "aneuploid": "high"})
    blocks = [block("B_KILL", tf("dead", "increased", scale=POP), route=RouteClass.SUPPRESSION,
                    scale=POP),
              block("B_FIX", tf("func", "1"), route=RouteClass.REPAIR)]
    return problem, blocks


def population_rescue(*, confounder=False, declare_mechanism=True, observe_marker=False):
    """Gates 5 and 6: no cell is corrected, yet the population-level function is reached."""
    from rarepipe.stages.control.synthesis.population import (
        ConfoundingProcess, PopulationMechanism,
    )
    space_vars = [var("lesion", exogenous=True), var("cell_function"),
                  var("selective_pressure", exogenous=True),
                  var("functional_fraction", ("low", "adequate")),
                  var("cellularity", ("baseline", "depleted"), exogenous=True)]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_CELL", ("lesion",), "cell_function", lambda g: g, space),
            rel("R_FRACTION", ("selective_pressure", "cell_function"), "functional_fraction",
                lambda p, f: "adequate" if (p == "1" or f == "1") else "low", space)]
    problem = build(space_vars, [model(rels)], target_on=(("functional_fraction", "adequate"),),
                    unsafe_on=(("cellularity", "depleted"),),
                    start={"lesion": "0", "cell_function": "0", "selective_pressure": "0",
                           "functional_fraction": "low", "cellularity": "baseline"},
                    extra_observed=("apoptosis_marker",) if observe_marker else ())
    blocks = [block("B_SELECT", tf("selective_pressure", "1", scale=POP), scale=POP,
                    route=RouteClass.COMPENSATION, kind=BlockClass.CELL_POPULATION)]
    mechanisms = ()
    if declare_mechanism:
        mechanisms = (PopulationMechanism(
            mechanism_id="M_SELECT", produces="competition", drives="functional_fraction",
            source_of_differential=("the toy declares that pressure-competent cells outgrow the "
                                    "rest, which is what makes the effect selective"),
            provenance=prov(EpistemicType.POPULATION_CONTROL)),)
    confounders = ()
    if confounder:
        confounders = (ConfoundingProcess(
            process_id="P_SELECTIVE_DEATH", could_produce="functional_fraction",
            reading=("adequate",),
            mechanism=("losing the dysfunctional cells raises the functional share without "
                       "improving any surviving cell"),
            excluded_by=("apoptosis_marker",), represented_in_model=False,
            provenance=prov(EpistemicType.MODEL_ASSUMPTION)),)
    return problem, blocks, PopulationLayer(
        population_variables=("functional_fraction", "cellularity"),
        mechanisms=mechanisms, confounders=confounders)


def order_matters():
    """Gate 7: the first component opens a window that the second one would have closed.

    Memory is carried by a two-variable cycle rather than a self-loop, which the dynamics layer
    forbids: a relationship is a constraint on a state, not an update rule, so `m` and `n` hold
    each other up once either of them is driven high.
    """
    space_vars = [var("a", exogenous=True), var("c", exogenous=True), var("m"), var("n"), var("t")]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_M", ("a", "c", "n"), "m",
                lambda a, c, n: "1" if n == "1" or (a == "1" and c == "0") else "0", space),
            rel("R_N", ("m",), "n", lambda m: m, space),
            rel("R_T", ("n", "c"), "t",
                lambda n, c: "1" if n == "1" and c == "1" else "0", space)]
    problem = build(space_vars, [model(rels)], target_on=(("t", "1"),),
                    start={"a": "0", "c": "0", "m": "0", "n": "0", "t": "0"})
    blocks = [block("B_A", tf("a", "1")), block("B_C", tf("c", "1"))]
    return problem, blocks


def feedback_needed():
    """Gate 8: holding the push settles outside the target; pushing then releasing settles inside it.

    The push latches a downstream state (`m`, `n`) that persists after withdrawal, and the readout
    is in the target only while the push is off. A static strategy cannot express that, because
    controls accumulate and are never released; a policy can.
    """
    space_vars = [var("u", ("off", "on"), exogenous=True), var("m"), var("n"),
                  var("x", ("low", "ok", "high"))]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_M", ("u", "n"), "m", lambda u, n: "1" if u == "on" or n == "1" else "0", space),
            rel("R_N", ("m",), "n", lambda m: m, space),
            rel("R_X", ("u", "n"), "x",
                lambda u, n: "ok" if (n == "1" and u == "off")
                else ("high" if (n == "1" and u == "on") else "low"), space)]
    problem = build(space_vars, [model(rels)], target_on=(("x", "ok"),),
                    start={"u": "off", "m": "0", "n": "0", "x": "low"})
    blocks = [block("B_PUSH", tf("u", "on", direction=Direction.INCREASE, released_to="off",
                                 rationale="the toy push has no maintaining mechanism, so the "
                                           "input returns to off when it stops"),
                    reversibility=Reversibility.REVERSIBLE, route=RouteClass.STABILIZATION)]
    loop = policy("PI_HOLD_OK",
                  ("x", "low", ACTIVATE, "B_PUSH::u"),
                  ("x", "high", DEACTIVATE, "B_PUSH::u"))
    return problem, blocks, loop


def disagreeing_models():
    """Gate 9: two evidence-compatible models, two different verdicts on the same component."""
    space_vars = [var("a", exogenous=True), var("t")]
    space = StateSpace(variables=tuple(space_vars))
    m1 = model([rel("R_T", ("a",), "t", lambda a: a, space)], model_id="M_RESPONSIVE")
    m2 = model([rel("R_T", ("a",), "t", lambda a: "0", space)], model_id="M_UNRESPONSIVE",
               plausibility=Plausibility.PLAUSIBLE_ALTERNATIVE)
    problem = build(space_vars, [m1, m2], target_on=(("t", "1"),), start={"a": "0", "t": "0"})
    blocks = [block("B_A", tf("a", "1"))]
    return problem, blocks


def unsafe_downstream():
    """The toxic state is not what the component sets — it is caused by what the component sets.

    Distinct from `unsafe_shortcut`, where the control pins the unsafe variable itself and the
    violation is visible in the very first state. Here the harm appears only after the causal
    relationships fire, so it is the per-successor safety check that has to catch it.
    """
    space_vars = [var("push", exogenous=True), var("alt", exogenous=True), var("effect"),
                  var("toxicity", ("baseline", "high")), var("benefit")]
    space = StateSpace(variables=tuple(space_vars))
    rels = [rel("R_EFFECT", ("push",), "effect", lambda p: p, space),
            rel("R_TOX", ("effect",), "toxicity",
                lambda e: "high" if e == "1" else "baseline", space),
            rel("R_BENEFIT", ("effect", "alt"), "benefit",
                lambda e, a: "1" if e == "1" or a == "1" else "0", space)]
    problem = build(space_vars, [model(rels)], target_on=(("benefit", "1"),),
                    unsafe_on=(("toxicity", "high"),),
                    start={"push": "0", "alt": "0", "effect": "0", "toxicity": "baseline",
                           "benefit": "0"})
    blocks = [block("B_PUSH", tf("push", "1"), route=RouteClass.REPAIR),
              block("B_SAFE", tf("alt", "1"), route=RouteClass.BYPASS)]
    return problem, blocks
