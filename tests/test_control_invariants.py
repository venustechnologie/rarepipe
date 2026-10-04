"""Invariants I1-I12. Each fails CI if violated."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))

from control_toys import control, model, prov, problem, rel, start_at, var  # noqa: E402

from rarepipe.stages.control.compiler import ControlCompilationReport, compile_problem  # noqa: E402
from rarepipe.stages.control.controllability import StrategyAssessment  # noqa: E402
from rarepipe.stages.control.controls import (  # noqa: E402
    BiologicalControlKind, ControlVariable, Feasibility, RouteClass,
)
from rarepipe.stages.control.dynamics import Plausibility  # noqa: E402
from rarepipe.stages.control.mva import problem as mva_problem  # noqa: E402
from rarepipe.stages.control.objective import rank  # noqa: E402
from rarepipe.stages.control.proposals import Proposal, ProposalKind, gate  # noqa: E402
from rarepipe.stages.control.provenance import (  # noqa: E402
    Approval, ApprovalStatus, EpistemicType, Provenance,
)
from rarepipe.stages.control.result_types import SOLUTION_CLASSES, ResultClass  # noqa: E402
from rarepipe.stages.control.target_constraints import Membership, TargetConstraint  # noqa: E402
from rarepipe.stages.control.uncertainty import StateEvidence  # noqa: E402
from rarepipe.stages.prospective.model import Actor, ActorType, Role  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "src/rarepipe/stages/control"
AGENT = Actor(actor_type=ActorType.AGENT, identity="control-causal-dynamics")
LEAD = Actor(actor_type=ActorType.HUMAN, identity="a-scientific-lead", roles=(Role.SCIENTIFIC_LEAD,))


def test_i1_no_fabricated_parameters():
    """No float literal in the case definition, and no qualitative value turned into a number."""
    tree = ast.parse((CONTROL / "mva.py").read_text())
    floats = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
    assert floats == [], floats
    for variable in mva_problem().space.variables:
        assert all(not v.replace(".", "").isdigit() for v in variable.domain)
    with pytest.raises(ValidationError, match="anonymous constant"):
        Provenance(epistemic_type=EpistemicType.MODEL_ASSUMPTION, source="x", proposed_by="y")


def test_i2_simulation_is_not_observation():
    with pytest.raises(ValueError, match="simulation is not observation"):
        from rarepipe.stages.control.uncertainty import evidence_domains
        evidence_domains(mva_problem().space, (StateEvidence(
            evidence_id="sim", variable="missegregation", allowed=("normal",),
            provenance=Provenance(epistemic_type=EpistemicType.SIMULATED_PREDICTION, source="engine",
                                  proposed_by="compiler"), generated_under="toy"),))
    report = compile_problem(mva_problem())
    assert report.origin == "simulated_prediction"
    with pytest.raises(ValidationError, match="never an observation"):
        ControlCompilationReport(**{**report.model_dump(), "origin": "observed_empirical"})


def _assessment(strategy, works, unsafe):
    return StrategyAssessment(
        strategy=strategy, controls=tuple(c for s in strategy for c in s), outcomes=(),
        works_in=works, unsafe_in=unsafe, per_model=(("M", "ALL"),), blocking_relationships=(),
        irrelevant_unknowns=(), model_disagreement=False, feasibility_blockers=(), relies_on=(),
        unresolved_relied_on=())


def test_i3_safety_cannot_be_optimised_away():
    """A strategy unsafe under any variant ranks below every strategy safe under all of them,
    however much more it achieves. Safety is a lexicographic first key, never a weighted term."""
    greedy = _assessment((("a",),), works=("v1", "v2", "v3", "v4"), unsafe=("v5",))
    careful = _assessment((("b",),), works=("v1",), unsafe=())
    assert rank([greedy, careful])[0] is careful
    source = (CONTROL / "objective.py").read_text()
    assert "alpha" not in source and "weight" not in source.split('"""', 2)[2]


def test_i4_unknown_relationships_remain_unknown():
    p = mva_problem()
    before = next(r for r in p.models[0].relationships if r.relationship_id == "REL_BUBR1_ABUNDANCE_FUNCTION")
    report = compile_problem(p)
    after = next(r for r in p.models[0].relationships if r.relationship_id == "REL_BUBR1_ABUNDANCE_FUNCTION")
    assert before == after and after.kind.value == "unknown_function"
    assert report.result not in SOLUTION_CLASSES


def test_i5_agents_cannot_alter_frozen_objects_or_promote_their_own_claims():
    p = mva_problem()
    with pytest.raises(ValidationError):
        p.target.constraints[0].approval = None  # type: ignore[misc]
    with pytest.raises(ValidationError, match="agent cannot"):
        Approval(status=ApprovalStatus.APPROVED, approver=AGENT, note="self-approved")
    claimed = gate(Proposal(
        proposal_id="P1", skill_id="control-causal-dynamics", skill_version="0.1.0", proposer=AGENT,
        kind=ProposalKind.RELATIONSHIP, claimed_epistemic_type=EpistemicType.OBSERVED_EMPIRICAL,
        rationale="I am confident", payload={
            "relationship_id": "R_NEW", "inputs": ["bubr1_abundance"], "output": "bubr1_function",
            "kind": "table", "epistemic_status": "established", "validity_domain": "claimed",
            "table": [[["low"], "insufficient"], [["restored"], "sufficient"]]}))
    assert claimed.accepted
    assert claimed.assigned_epistemic_type is EpistemicType.INFERRED_HYPOTHESIS
    assert claimed.accepted_object["epistemic_status"] == "assumed"
    verdict = gate(Proposal(
        proposal_id="P2", skill_id="control-strategy-generator", skill_version="0.1.0",
        proposer=AGENT, kind=ProposalKind.CONTROL, rationale="done",
        payload={"note": "CONTROL_SOLUTION_FOUND"}))
    assert not verdict.accepted and "result class" in verdict.reason
    feasible = gate(Proposal(
        proposal_id="P3", skill_id="control-strategy-generator", skill_version="0.1.0",
        proposer=AGENT, kind=ProposalKind.CONTROL, rationale="easy",
        payload={"control_id": "C_X", "sets": "bubr1_abundance", "to": "restored",
                 "kind": "protein_stability", "route_class": "stabilization",
                 "interpretation": "hold the altered protein at restored abundance",
                 "feasibility": "established", "feasibility_note": "trust me"}))
    assert feasible.accepted and feasible.accepted_object["feasibility"] == "unassessed"


def test_i6_every_solution_names_the_model_it_holds_under():
    p = problem([var("a", True), var("t")], [model([rel("R_t", ("a",), "t", lambda a: a)])],
                [control("u", "a")], target_on=[("t", "1")], evidence=start_at(a="0"))
    report = compile_problem(p)
    assert report.result in SOLUTION_CLASSES
    for s in report.control_strategy_candidates:
        if s.assessment.works_in:
            assert s.holds_under and all(v in report.candidate_models for v in s.holds_under)


def test_i7_every_external_model_declares_a_validity_domain():
    from rarepipe.stages.control.model_registry import ModelRegistryEntry
    entry = mva_problem().registry[0].model_dump()
    entry["validity_domain"] = ""
    with pytest.raises(ValidationError):
        ModelRegistryEntry(**entry)


def test_i8_every_target_constraint_has_accountable_provenance():
    good = prov(EpistemicType.TARGET_CONSTRAINT)
    with pytest.raises(ValidationError, match="TARGET_CONSTRAINT provenance"):
        TargetConstraint(constraint_id="T", meaning="m", predicate=Membership(variable="t", allowed=("1",)),
                         provenance=prov(), approval=Approval(status=ApprovalStatus.PROPOSED, note="n"))
    with pytest.raises(ValidationError, match="scientific lead or treating clinician"):
        Approval(status=ApprovalStatus.APPROVED,
                 approver=Actor(actor_type=ActorType.HUMAN, identity="engineer", roles=(Role.ENGINEER,)),
                 note="n")
    approved = TargetConstraint(constraint_id="T", meaning="m",
                                predicate=Membership(variable="t", allowed=("1",)), provenance=good,
                                approval=Approval(status=ApprovalStatus.APPROVED, approver=LEAD, note="n"))
    assert approved.approval.approver.actor_type is ActorType.HUMAN


def test_i9_every_control_has_a_biological_interpretation():
    with pytest.raises(ValidationError):
        ControlVariable(control_id="C", sets="a", to="1", kind=BiologicalControlKind.PROTEIN_ABUNDANCE,
                        route_class=RouteClass.REPAIR, interpretation="niacin",
                        feasibility=Feasibility.UNASSESSED, feasibility_note="n",
                        provenance=prov(EpistemicType.CONTROL_VARIABLE))


def test_i10_observations_stay_attached_to_the_version_that_generated_them():
    with pytest.raises(ValidationError):
        StateEvidence(evidence_id="e", variable="a", allowed=("1",), provenance=prov(), generated_under="")
    assert all(e.generated_under for e in mva_problem().evidence)
    assert all(x.observation.generated_under for x in mva_problem().experiments)


def test_i11_no_robust_claim_while_plausible_models_disagree():
    m1 = model([rel("R_t", ("a",), "t", lambda a: a)], "M1")
    m2 = model([rel("R_t", ("a",), "t", lambda a: "0")], "M2", plausibility=Plausibility.PLAUSIBLE_ALTERNATIVE)
    report = compile_problem(problem([var("a", True), var("t")], [m1, m2], [control("u", "a")],
                                     target_on=[("t", "1")], evidence=start_at(a="0", t="0")))
    assert report.result is not ResultClass.ROBUST_CONTROL_SOLUTION_CANDIDATE
    assert report.result not in SOLUTION_CLASSES


def test_i12_compilation_is_reproducible_across_processes():
    """Hash randomisation changes set iteration order per process; outputs must not depend on it."""
    code = ("from rarepipe.stages.control.mva import problem;"
            "from rarepipe.stages.control.compiler import compile_problem;"
            "print(compile_problem(problem()).content_digest)")
    digests = set()
    for seed in ("1", "2", "777"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=600)
        assert out.returncode == 0, out.stderr
        digests.add(out.stdout.strip())
    assert len(digests) == 1, digests


def test_a_report_cannot_claim_a_result_its_contents_do_not_support():
    """No result by prose: a hand-built report claiming a solution is refused."""
    report = compile_problem(mva_problem())
    with pytest.raises(ValidationError, match="prose cannot supply one"):
        ControlCompilationReport(**{**report.model_dump(),
                                    "result": ResultClass.ROBUST_CONTROL_SOLUTION_CANDIDATE})
