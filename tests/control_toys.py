"""Small, fully known networks for the control compiler's proof gates. Not collected by pytest."""
from __future__ import annotations

from itertools import product

from rarepipe.stages.control.compiler import Problem
from rarepipe.stages.control.controls import (
    BiologicalControlKind, ControlVariable, Feasibility, RouteClass,
)
from rarepipe.stages.control.dynamics import Model, Plausibility, Relationship, RelationshipKind
from rarepipe.stages.control.observability import ObservationModel
from rarepipe.stages.control.provenance import Approval, ApprovalStatus, EpistemicType, Provenance
from rarepipe.stages.control.safety_constraints import SafetyConstraint, UnsafeRegion
from rarepipe.stages.control.state_space import StateSpace, Variable, VariableKind
from rarepipe.stages.control.target_constraints import Membership, TargetConstraint, TargetRegion
from rarepipe.stages.control.uncertainty import StateEvidence

BIN = ("0", "1")
PROPOSED = Approval(status=ApprovalStatus.PROPOSED, note="toy")


def prov(kind=EpistemicType.MODEL_ASSUMPTION, **kw):
    if kind is EpistemicType.MODEL_ASSUMPTION:
        kw.setdefault("rationale", "toy network for a proof gate")
    return Provenance(epistemic_type=kind, source="toy", proposed_by="test", **kw)


def var(name, exogenous=False, latent=False):
    return Variable(name=name, kind=VariableKind.CATEGORICAL, domain=BIN, meaning=f"toy {name}",
                    latent=latent, exogenous=exogenous,
                    exogenous_reason="toy control input" if exogenous else "")


def table(fn, k):
    return tuple((ins, fn(*ins)) for ins in product(BIN, repeat=k))


def rel(rid, inputs, output, fn=None, *, unknown=False):
    if unknown:
        return Relationship(relationship_id=rid, inputs=inputs, output=output,
                            kind=RelationshipKind.UNKNOWN_FUNCTION, epistemic_status="unresolved",
                            provenance=prov(EpistemicType.INFERRED_HYPOTHESIS), validity_domain="toy")
    return Relationship(relationship_id=rid, inputs=inputs, output=output, kind=RelationshipKind.TABLE,
                        table=table(fn, len(inputs)), epistemic_status="established",
                        provenance=prov(), validity_domain="toy")


def model(rels, model_id="M", plausibility=Plausibility.ACCEPTED):
    return Model(model_id=model_id, plausibility=plausibility, statement="toy",
                 relationships=tuple(rels), provenance=prov())


def control(cid, variable, to="1", feasibility=Feasibility.ESTABLISHED):
    return ControlVariable(control_id=cid, sets=variable, to=to,
                           kind=BiologicalControlKind.PATHWAY_ACTIVATION, route_class=RouteClass.BYPASS,
                           interpretation=f"drive the toy variable {variable} to {to} directly",
                           feasibility=feasibility, feasibility_note="toy",
                           provenance=prov(EpistemicType.CONTROL_VARIABLE))


def start_at(**values):
    return tuple(StateEvidence(evidence_id=f"e_{k}", variable=k, allowed=(v,), provenance=prov(),
                               generated_under="toy") for k, v in values.items())


def problem(space_vars, models, controls, *, target_on, unsafe_on=(), evidence=(), observed=None,
            target_approval=PROPOSED, max_depth=3):
    space = StateSpace(variables=tuple(space_vars))
    target = TargetRegion(constraints=tuple(
        TargetConstraint(constraint_id=f"T_{v}", meaning=f"{v} reaches {val}",
                         predicate=Membership(variable=v, allowed=(val,)),
                         provenance=prov(EpistemicType.TARGET_CONSTRAINT), approval=target_approval)
        for v, val in target_on))
    unsafe = UnsafeRegion(constraints=tuple(
        SafetyConstraint(constraint_id=f"S_{v}", meaning=f"{v} reaches {val}",
                         unsafe_when=Membership(variable=v, allowed=(val,)),
                         provenance=prov(EpistemicType.SAFETY_CONSTRAINT), approval=PROPOSED)
        for v, val in unsafe_on))
    obs = ObservationModel(name="Y", observed=tuple(observed if observed is not None else space.names),
                           provenance=prov(EpistemicType.DECISION_RULE), generated_under="toy")
    return Problem(problem_id="toy", case_ref="TOY", space=space, evidence=tuple(evidence),
                   target=target, unsafe=unsafe, models=tuple(models), controls=tuple(controls),
                   observation=obs, state_model_version="toy", rule_version="toy",
                   case_context_version="toy", max_depth=max_depth)
