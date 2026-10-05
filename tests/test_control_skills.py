"""The control skills must reference only what the compiler defines, and carry nothing forbidden."""
from __future__ import annotations

import re

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "control"))

from check_skills import REQUIRED, check  # noqa: E402

ROLES = ("control-state-modeler", "control-causal-dynamics", "control-strategy-generator",
         "control-falsification", "control-observability-design", "control-actuator-mapper",
         "control-provenance-auditor")


def test_all_seven_skills_exist_and_are_consistent():
    present = sorted(p.parent.name for p in (ROOT / ".claude/skills").glob("control-*/SKILL.md"))
    assert present == sorted(ROLES)
    report = check()
    assert report["findings"] == [], report["findings"]


def _skill(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "control-probe" / "SKILL.md"
    path.parent.mkdir()
    sections = "\n".join(f"## {name}\ncontent" for name in REQUIRED)
    path.write_text(f"---\nname: control-probe\ndescription: probe\n---\n{sections}\n{body}\n")
    return path


def test_an_invented_reference_is_caught(tmp_path: Path):
    report = check([_skill(tmp_path, "Use `ControlOracle.solve` to finish.")])
    assert any("ControlOracle.solve" in f["issue"] for f in report["findings"])


def test_a_dose_or_a_recommendation_is_caught(tmp_path: Path):
    report = check([_skill(tmp_path, "We recommend 500 mg daily.")])
    issues = " ".join(f["issue"] for f in report["findings"])
    assert "dose" in issues and "recommendation" in issues


def test_variant_notation_is_caught(tmp_path: Path):
    report = check([_skill(tmp_path, "Consider the c.1234G>T allele.")])
    assert any("variant notation" in f["issue"] for f in report["findings"])


def test_a_missing_section_is_caught(tmp_path: Path):
    path = tmp_path / "control-probe" / "SKILL.md"
    path.parent.mkdir()
    path.write_text("---\nname: control-probe\ndescription: probe\n---\n## scope\ncontent\n")
    report = check([path])
    assert any("missing section benchmark_cases" in f["issue"] for f in report["findings"])


def test_every_test_the_requirements_map_cites_exists():
    """The traceability map must not outlive the tests it points at."""
    import re

    text = (ROOT / "docs/control/REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 25
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_the_synthesis_requirements_map_cites_tests_that_exist():
    """The traceability map is only worth having if it cannot rot."""
    text = (ROOT / "docs/control/SYNTHESIS_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 40
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_every_synthesis_proof_gate_and_invariant_is_cited():
    """A gate or invariant the map does not mention is one nobody is tracking."""
    text = (ROOT / "docs/control/SYNTHESIS_REQUIREMENTS.md").read_text()
    for path in ("tests/test_synthesis_gates.py", "tests/test_synthesis_invariants.py"):
        source = (ROOT / path).read_text()
        defined = set(re.findall(r"^def (test_\w+)\(", source, re.M))
        cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
        missing = sorted(defined - cited)
        assert not missing, f"{path} defines tests the requirements map never cites: {missing}"


def test_the_realization_requirements_map_cites_tests_that_exist():
    text = (ROOT / "docs/control/REALIZATION_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 25
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_every_realization_gate_is_cited():
    text = (ROOT / "docs/control/REALIZATION_REQUIREMENTS.md").read_text()
    path = "tests/test_realization_gates.py"
    defined = set(re.findall(r"^def (test_\w+)\(", (ROOT / path).read_text(), re.M))
    cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
    missing = sorted(defined - cited)
    assert not missing, f"{path} defines tests the requirements map never cites: {missing}"


def test_the_discovery_requirements_map_cites_tests_that_exist():
    text = (ROOT / "docs/control/DISCOVERY_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 30
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_every_discovery_gate_is_cited():
    text = (ROOT / "docs/control/DISCOVERY_REQUIREMENTS.md").read_text()
    path = "tests/test_discovery_gates.py"
    defined = set(re.findall(r"^def (test_\w+)\(", (ROOT / path).read_text(), re.M))
    cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
    missing = sorted(defined - cited)
    assert not missing, f"{path} defines tests the requirements map never cites: {missing}"


def test_the_external_requirements_map_cites_tests_that_exist():
    text = (ROOT / "docs/control/EXTERNAL_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 30
    for path, name in cited:
        assert f"def {name}(" in (ROOT / path).read_text(), f"{path}::{name} does not exist"


def test_every_external_gate_is_cited():
    text = (ROOT / "docs/control/EXTERNAL_REQUIREMENTS.md").read_text()
    path = "tests/test_external_gates.py"
    defined = set(re.findall(r"^def (test_\w+)\(", (ROOT / path).read_text(), re.M))
    cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
    missing = sorted(defined - cited)
    assert not missing, f"{path} defines tests the requirements map never cites: {missing}"


def test_the_repair_requirements_map_cites_tests_that_exist():
    text = (ROOT / "docs/control/REPAIR_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 20
    for path, name in cited:
        assert f"def {name}(" in (ROOT / path).read_text(), f"{path}::{name} does not exist"


def test_every_repair_test_is_cited():
    text = (ROOT / "docs/control/REPAIR_REQUIREMENTS.md").read_text()
    path = "tests/test_evidence_repair.py"
    defined = set(re.findall(r"^def (test_\w+)\(", (ROOT / path).read_text(), re.M))
    cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
    missing = sorted(defined - cited)
    assert not missing, f"{path} defines tests the requirements map never cites: {missing}"


# ------------------------------------------------- the stability snapshot backs a document, not a compiler

def test_the_stability_snapshot_is_internally_consistent():
    """The stabilisation search has no compiler path, so its snapshot carries its own integrity check.

    MVA_BUBR1_STABILITY_REALIZATION.md quotes measured effects out of this snapshot. Without a digest
    check the quotes would be assertions about files nobody verified, which is the failure mode the
    whole evidence discipline exists to prevent. Every manifest entry must have its file at the
    recorded digest, and every stored file must be declared — an undeclared document is one a rejection
    could have been quietly based on.
    """
    import hashlib
    import json

    root = ROOT / "data/literature/mva-stability-v1"
    manifest = json.loads((root / "manifest.json").read_text())
    declared = {}
    for entry in manifest["documents"]:
        path = root / "docs" / f"{entry['source_id'].replace(':', '_')}.txt"
        assert path.exists(), f"{entry['source_id']} is declared but not stored"
        body = path.read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry["sha256"], f"{entry['source_id']} does not match its digest"
        assert len(body) == entry["bytes"], f"{entry['source_id']} byte count does not match"
        assert entry["matched_queries"], f"{entry['source_id']} records no query that found it"
        declared[path.name] = entry
    stored = {p.name for p in (root / "docs").glob("*.txt")}
    assert stored == set(declared), f"undeclared documents in the snapshot: {sorted(stored - set(declared))}"


def test_every_source_the_stability_document_cites_is_in_its_snapshot():
    """A citation in the document must be a document in the snapshot, so a reader can check it."""
    import json

    root = ROOT / "data/literature/mva-stability-v1"
    declared = {e["source_id"] for e in json.loads((root / "manifest.json").read_text())["documents"]}
    text = (ROOT / "docs/control/MVA_BUBR1_STABILITY_REALIZATION.md").read_text()
    cited = set(re.findall(r"PMID:\d+", text))
    assert cited, "the stability document cites nothing"
    assert cited <= declared, f"cited but not in the snapshot: {sorted(cited - declared)}"


# ------------------------------------------------- therapeutic-output governance over the case documents

def test_no_case_document_turns_a_perturbation_into_a_recommendation():
    """The other half of the search-policy split, and the half with the teeth.

    Retrieval may now look for experiments that inhibited, depleted or degraded something. The line
    that must not be crossed is the inference from "inhibiting X raised Y in a cell" to "administer an
    inhibitor of X". The dose and recommendation patterns already guard the skills; a document that
    reports a stabilisation search is exactly where that inference would surface, so it is guarded
    here too.

    The check is negation-aware, and it has to be: these documents state the prohibition explicitly,
    so "It does not say that niacin should be given to this child" contains the forbidden phrase while
    asserting its opposite. A guard that fires on its own disclaimer gets worked around, which is worse
    than no guard.

    What this does not catch: a recommendation in a sentence that happens to carry an unrelated
    negation before it. The window is one sentence, so the evasion has to be deliberate; the guard is
    a floor, not a proof.
    """
    import re as _re

    from check_skills import DOSE, RECOMMEND

    NEGATION = _re.compile(r"\b(not|never|nothing|cannot|no|without|neither|nor)\b", _re.I)
    docs = sorted((ROOT / "docs/control").glob("MVA_*.md"))
    assert docs, "no case documents found to check"
    findings = []
    for path in docs:
        text = path.read_text()
        for pattern, why in ((DOSE, "dose"), (RECOMMEND, "recommendation")):
            for match in pattern.finditer(text):
                start = max((text.rfind(c, 0, match.start()) for c in ".!?\n"), default=-1) + 1
                if NEGATION.search(text[start:match.start()]):
                    continue
                findings.append(f"{path.name} contains an un-negated {why}: {match.group(0)!r}")
    assert not findings, findings


def test_the_recommendation_guard_still_catches_an_actual_recommendation():
    """Negation-awareness must not have turned the guard off."""
    import re as _re

    from check_skills import RECOMMEND

    NEGATION = _re.compile(r"\b(not|never|nothing|cannot|no|without|neither|nor)\b", _re.I)

    def flags(text: str) -> bool:
        for match in RECOMMEND.finditer(text):
            start = max((text.rfind(c, 0, match.start()) for c in ".!?\n"), default=-1) + 1
            if not NEGATION.search(text[start:match.start()]):
                return True
        return False

    assert flags("Given the stabilisation result, nicotinic acid should be given to this child.")
    assert flags("We recommend raising BubR1 abundance in the patient.")
    assert not flags("It does not say that niacin should be given to this child.")
    assert not flags("Nothing here means a chaperone perturbation should be administered.")


# ------------------------------------------------- the contingent route map

def _route_map():
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools" / "control"))
    import compile_route_map as M
    return M, M.load()


def test_the_route_map_is_structurally_valid():
    M, d = _route_map()
    assert not M.validate(d)


def test_no_unknown_is_a_terminal_state():
    """The PRD's load-bearing rule: an unresolved node enumerates outcomes and continues from each.

    A branch that terminated would be the system saying "here is an unknown" — which is the behaviour
    this map exists to replace.
    """
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    for n in d["nodes"]:
        if n["kind"] != "branch":
            continue
        assert len(n.get("outcomes") or {}) >= 2, f"{n['id']} does not enumerate admissible outcomes"
        for name, target in n["outcomes"].items():
            t = nodes[target]
            if t["kind"] == "terminal":
                assert t["terminal"] in set(d["terminal_vocabulary"]), f"{n['id']}/{name}"
                assert t["terminal"] != "UNKNOWN"
            else:
                assert t["kind"] in ("state", "all_of", "branch"), f"{n['id']}/{name}"


def test_every_branch_declares_whether_it_is_a_measurement_or_a_discovery():
    """Counting branches alone prices a western blot and an undiscovered component the same.

    The distinction decides which route is actually shorter, so it is declared data rather than
    inferred from incoming edge labels — inference got BYPASS_ALIGN wrong when one incidental edge
    carried a different label.
    """
    M, d = _route_map()
    allowed = set(d["resolves_by_vocabulary"])
    for n in d["nodes"]:
        if n["kind"] == "branch":
            assert n.get("resolves_by") in allowed, f"{n['id']}: {n.get('resolves_by')!r}"


def test_a_decided_branch_closes_the_outcomes_it_did_not_return():
    """A branch returns one result, so the alternatives become unavailable, not merely uncosted.

    Without this the abundance family never closes on a persistent functional defect, and the map
    would report a route that the result had already ruled out.
    """
    M, d = _route_map()
    open_f1 = M.cost(d, known={"S_FUNCTION_OK"}, decided={"EXP01": "full_function"})["F1_COMPLETE"]
    shut_f1 = M.cost(d, known={"B_MULTI_DEFECT"}, decided={"EXP01": "multiple_defects"})["F1_COMPLETE"]
    assert open_f1 is not None, "full function should leave the abundance family open"
    assert shut_f1 is None, "multiple defects should close the abundance family as a complete solution"


def test_the_frontier_keeps_sets_that_make_a_conjunction_cheap():
    """Per-node minimisation is not optimal across an AND node, so a frontier is kept, not one set.

    Two conjuncts can share an experiment; keeping only each node's smallest set can discard the one
    that makes the union cheap and then the reported distance is an overestimate.
    """
    M, d = _route_map()
    f = M.frontier(d)
    assert M.cost(d)[M.goal(d)] is not None
    for nid, sets in f.items():
        for a in sets:
            for b in sets:
                if a is not b:
                    assert not (a < b), f"{nid}: frontier kept {sorted(b)}, a superset of {sorted(a)}"


def test_the_committed_route_map_document_is_not_stale():
    M, d = _route_map()
    committed = (ROOT / "docs/control/MVA_CONTINGENT_ROUTE_MAP.md").read_text()
    assert committed == M.render(d), ("docs/control/MVA_CONTINGENT_ROUTE_MAP.md is stale: run "
                                      "uv run python tools/control/compile_route_map.py")


def test_a_bounded_negative_search_is_not_biological_impossibility():
    """Three distinct frontier states, and the strongest one must earn its use.

    An empty search and an established impossibility are different claims. Calling a hole in the
    literature `NO_KNOWN_PHYSICAL_REALIZATION` would convert the limits of our searching into a fact
    about biology, which is the failure this vocabulary exists to prevent.
    """
    M, d = _route_map()
    vocab = set(d["terminal_vocabulary"])
    # Rule 7 renamed these; the distinction they encode is unchanged. An empty search, a case-corpus
    # gap and an evidence incompatibility are three different claims, and the strongest must earn it.
    for state in ("NOT_IN_LOCAL_CASE_CORPUS", "SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED",
                  "PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE"):
        assert state in vocab, state
    for n in d["nodes"]:
        if n["kind"] == "terminal" and n.get("terminal") == "PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE":
            assert len(n["label"]) > 40, (
                f"{n['id']} claims incompatibility with evidence without saying with what; a bounded "
                "negative search belongs in SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED")


def test_absence_of_a_known_bubr1_link_is_never_recorded_as_independence():
    """Every dependency adjudication keeps an `unestablished` outcome distinct from independence.

    Silence in the literature is the normal state for a candidate nobody tested against BubR1. A
    branch that offered only independent/dependent would force silence into one of them.
    """
    M, d = _route_map()
    dep = [n for n in d["nodes"] if n["kind"] == "branch" and n["id"].startswith("DEP_")]
    assert dep, "no dependency adjudication branches found"
    for n in dep:
        outcomes = set(n["outcomes"])
        assert "unestablished" in outcomes, f"{n['id']} cannot record an untested dependency"
        # Matched on meaning, not on a name prefix: DEP_FLUX now distinguishes a benefit that
        # *exploits* residual BubR1 (a compensatory route) from one that vanishes without it, and a
        # prefix check would have forced those two very different results to share a label.
        assert any("bubr1" in o for o in outcomes), (
            f"{n['id']} records no outcome in which the candidate depends on BubR1")
        assert "independence" not in n["why_unresolved"].lower() or "not independence" in \
            n["why_unresolved"].lower() or "not evidence" in n["why_unresolved"].lower(), n["id"]


def test_a_composite_bypass_is_not_credited_for_its_parts():
    """Assembling components that each supply a function does not establish the biological state.

    TRIP13 is the proof of the worry: the same protein supports checkpoint activation and drives
    mitotic exit, so a composite assembled from per-function components can conflict with itself.
    """
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    out = [e for e in d["edges"] if e["from"] == "F2_COMPLETE"]
    assert out, "F2_COMPLETE has no outgoing transition"
    for e in out:
        assert nodes[e["to"]]["kind"] == "branch", (
            "the composite must pass through a validation branch rather than reaching the target "
            f"directly; it goes to {e['to']}")


def test_abundance_route_safety_belongs_to_the_stabilisation_manipulation():
    """EXP01's safety readouts describe ectopic expression, not the actuator that finally raises it."""
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    f1 = nodes["F1_COMPLETE"]
    assert "S_POP_SAFE_F1B" in f1["of"], "F1 must require safety under the stabilisation manipulation"
    assert "S_POP_SAFE_F1" not in f1["of"], "F1 must not inherit EXP01's safety observation"
    assert M.cost(d)["S_POP_SAFE_F1B"] is not None


def test_cell_level_reachability_is_not_disease_resolution():
    """The cell-level state must not be a terminal, and the organism scale must be further away.

    Stopping at a corrected cell would let the map imply the disease was addressed. Mosaic variegated
    aneuploidy is constitutional: much of the burden is developmental and already laid down, so
    reaching the cell state is a waypoint and the irreversibility question bounds everything above it.
    """
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    cell, organism = M.goal(d), M.ultimate(d)
    assert cell and organism and cell != organism, "both scales must be named in the map, not in the tool"
    assert nodes[cell]["kind"] != "terminal", "the cell-level state must continue, not terminate"
    assert [e for e in d["edges"] if e["from"] == cell], f"{cell} has no outgoing transition"
    c = M.cost(d)
    cell_cost, org_cost = c.get(cell), c.get(organism)
    assert cell_cost is not None
    assert org_cost is None or len(org_cost) > len(cell_cost), (
        "the organism scale cannot be as close as the cell scale")
    assert "IRREV01" in nodes[organism]["of"] or "S_PROSPECTIVE_EXISTS" in nodes[organism]["of"], (
        "the organism target must require that a prospective component exists")


def test_a_prospective_component_is_not_a_modified_clinical_course():
    """Two separate states, because conflating them claims an effect from the possibility of one."""
    M, d = _route_map()
    irrev = next(n for n in d["nodes"] if n["id"] == "IRREV01")
    assert irrev["outcomes"]["prospective_component_exists"] == "S_PROSPECTIVE_EXISTS"
    nodes = {n["id"]: n for n in d["nodes"]}
    into_clinical = {e["from"] for e in d["edges"] if e["to"] == "S_CLINICAL_MODIFIED"}
    branch_sources = {b["id"] for b in d["nodes"] if b["kind"] == "branch"
                      for t in (b.get("outcomes") or {}).values() if t == "S_CLINICAL_MODIFIED"}
    assert "XSCALE02" in branch_sources, "a modified clinical course must come from the scale question"
    assert "IRREV01" not in branch_sources | into_clinical


def test_the_functional_target_is_modality_agnostic_but_not_a_loophole():
    """Two target definitions, both computed, and the functional one must not be a free pass.

    A target assembled from the canonical BubR1 trajectory would reject any synthetic route that
    reaches the same terminal state another way, which is the opposite of the project's premise. So
    alignment, activation and silencing were audited and reclassified as canonical intermediates. The
    guard against that becoming a loophole is that nothing was deleted: the canonical state is still a
    node with its full conjunction, every endpoint keeps an audit verdict, and the functional target
    still requires population safety and the checkpoint-risk question.
    """
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    audit = d["target_audit"]
    for endpoint in d["target"]["canonical_conjunction"]:
        assert endpoint in audit, f"{endpoint} was never audited"
        assert audit[endpoint].get("basis"), f"{endpoint} has a verdict with no basis"
    assert "CANONICAL_CELLULAR_STATE" in nodes, "the canonical state must still be computed"
    functional = nodes[M.goal(d)]
    assert "S_POP_SAFE_ANY" in functional["of"], "the functional target must still require safety"
    # The tumour-risk gate is preserved, but at the right scale. It is not a property of a cell's
    # mitotic phenotype and has no validated cellular surrogate, so requiring it to define the cell
    # state made a cellular claim depend on organism-level knowledge. It gates organism advancement
    # instead — still mandatory, which is what stops the reclassification being a relaxation.
    assert "S_CHECKPOINT_RISK_RESOLVED" not in functional["of"], (
        "organism-level tumour-risk knowledge must not be a conjunct of the cellular phenotype")
    assert "S_CHECKPOINT_RISK_RESOLVED" in nodes[M.ultimate(d)]["of"], (
        "the risk gate must still be required before organism-level advancement, not dropped")
    assert M.cost(d).get("CANONICAL_CELLULAR_STATE") is not None


def test_activation_is_route_specific_rather_than_a_universal_gate():
    """The audit's decisive test, pinned so a later edit cannot quietly reinstate the constraint."""
    M, d = _route_map()
    for dest in ("CANONICAL_CELLULAR_STATE", M.goal(d)):
        assert "BYPASS_ACT" not in M.dominators_for(d, dest), (
            f"BYPASS_ACT gates {dest}; if that is now true the audit verdict on T_ACT must be revisited")
    # The risk conjunct cannot be bypassed, but the branch that asks about it can be: once a result
    # makes checkpoint competence necessary, supplying competence satisfies the conjunct by meeting
    # the requirement instead of by showing it unnecessary. So the right invariant is on the conjunct,
    # not on the branch — asserting branch dominance here would forbid that continuation.
    nodes = {n["id"]: n for n in d["nodes"]}
    assert "S_CHECKPOINT_RISK_RESOLVED" in nodes[M.ultimate(d)]["of"]
    satisfiers = {e["from"] for e in d["edges"] if e["to"] == "S_CHECKPOINT_RISK_RESOLVED"}
    satisfiers |= {b["id"] for b in d["nodes"] if b["kind"] == "branch"
                   and "S_CHECKPOINT_RISK_RESOLVED" in (b.get("outcomes") or {}).values()}
    assert "ACT_SAFETY01" in satisfiers, "the risk question must be one way to satisfy the conjunct"
    assert len(satisfiers) > 1, "supplying competence must also satisfy it, or item 1's fix is undone"


def test_every_branch_says_what_it_needs_to_be_run():
    """Runnable in a cell line, needing a model that does not exist, or blocked by governance.

    Without this the map prices "transfect a cell line" the same as "observe this child's clinical
    course", and the second is not an experiment anyone here can do.
    """
    M, d = _route_map()
    allowed = set(d["requires_vocabulary"])
    for n in d["nodes"]:
        if n["kind"] == "branch":
            assert n.get("requires") in allowed, f"{n['id']}: {n.get('requires')!r}"
    assert nodes_requiring(d, "GOVERNANCE_ABSENT"), "no branch records a governance block"


def nodes_requiring(d, req):
    return [n["id"] for n in d["nodes"] if n["kind"] == "branch" and n.get("requires") == req]


def test_a_new_requirement_does_not_terminate_reasoning():
    """ACT_SAFETY01 returning "competence required" creates a requirement, not a dead end.

    Terminating there would have the map stop reasoning at the moment it learned something: the
    result says a conjunct is needed, and two families can supply it. Both must stay reachable.
    """
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    act = next(n for n in d["nodes"] if n["id"] == "ACT_SAFETY01")
    landing = act["outcomes"]["checkpoint_competence_required"]
    assert nodes[landing]["kind"] != "terminal", f"{landing} terminates a result that opens a requirement"
    onward = {e["to"] for e in d["edges"] if e["from"] == landing}
    assert "BYPASS_ACT" in onward, "the bypass route to checkpoint competence must reopen"
    assert onward - {"BYPASS_ACT"}, "the abundance family must also remain a way to supply competence"


def test_the_checkpoint_risk_gate_is_not_answerable_in_a_dish():
    """Its executability class must follow the adjudication, not convenience.

    No validated cell-level surrogate for tumour predisposition was found, and the human syndromes
    couple aneuploidy with tumour susceptibility rather than separating them. Leaving this as
    CELL_MODEL would let a negative cell assay be promoted to "checkpoint competence is not required
    for tumour risk", which the evidence does not support.
    """
    M, d = _route_map()
    act = next(n for n in d["nodes"] if n["id"] == "ACT_SAFETY01")
    assert act["requires"] != "CELL_MODEL", "a cell assay cannot settle organism-level tumour risk"
    adj = act.get("executability_adjudication")
    assert adj, "the reclassification must record the adjudication that justifies it"
    assert adj["answer_1"].startswith("NO") and adj["answer_2"].startswith("NO")
    assert adj.get("evidence_1"), "the adjudication must cite what it rests on"


def test_campaigns_cover_fewer_units_than_branches_without_hiding_any():
    """A campaign groups observations; it must not make a branch disappear.

    The point is that one set of observations can settle several unknowns, so the campaign count is
    lower than the branch count. The risk is that grouping quietly drops a branch nobody can run, so
    every branch on a route is either covered by a campaign or reported as uncovered.
    """
    M, d = _route_map()
    for c in d["campaigns"]:
        assert c["requires"] in set(d["requires_vocabulary"])
        for b in c["resolves"]:
            assert any(n["id"] == b and n["kind"] == "branch" for n in d["nodes"]), f"{c['id']} -> {b}"
    route = M.cost(d)[M.goal(d)]
    covered, uncovered = M.campaign_cover(d, route)
    resolved = {b for cid in covered for c in d["campaigns"] if c["id"] == cid for b in c["resolves"]}
    assert (resolved | set(uncovered)) >= route, "a branch on the route is neither covered nor reported"
    assert len(covered) + len(uncovered) <= len(route), "grouping must not increase the unit count"
    assert "FLUX01" in {c["id"] for c in d["campaigns"]}
    flux = next(c for c in d["campaigns"] if c["id"] == "FLUX01")
    assert set(flux["resolves"]) == {"DEP_FLUX", "SAFE01"}
    assert flux.get("diagnostics"), "alignment, activation and silencing must be kept as diagnostics"


def test_a_decided_branch_stops_counting_as_unresolved_work():
    """"What remains after this result" must not keep charging for the experiment that produced it.

    Restricting a decided branch to one outcome is not enough; it has also been run. Without this the
    favourable FLUX01 result reported the cell-level state as two branches away when it is reached.
    """
    M, d = _route_map()
    flux = next(c for c in d["campaigns"] if c["id"] == "FLUX01")
    good = flux["outcomes"]["lower_missegregation_population_preserved"]
    after = M.cost(d, decided=good).get(M.goal(d))
    assert after is not None and not after, (
        f"the favourable result should reach the cell-level state; {sorted(after or [])} still charged")


def test_the_execution_packets_exist_and_defer_decisions_to_the_map():
    """Packets are bench documents. Decision authority stays in one place.

    Two packets each restating the outcome rules would let them drift apart, and the map is where the
    continuations are computed.
    """
    for name, campaign in (("FLUX01_EXECUTION_PACKET.md", "FLUX01"),
                           ("CHAR01_EXECUTION_PACKET.md", "CHAR01")):
        text = (ROOT / "docs/control" / name).read_text()
        assert "MVA_CONTINGENT_ROUTE_MAP.md" in text, f"{name} must defer to the map"
        assert "no new decision machinery" in text.lower() or \
               "adds no decision machinery" in text.lower(), f"{name}"
        M, d = _route_map()
        declared = next((c for c in d["campaigns"] if c["id"] == campaign), None)
        assert declared, f"{campaign} is not a declared campaign"
        for outcome in (declared.get("outcomes") or {}):
            assert outcome in text, f"{name} does not carry the declared result {outcome!r}"


def test_robust_and_conditional_reachability_are_distinguished():
    """A destination no single result can close is a different claim from one that needs luck."""
    M, d = _route_map()
    cell, organism = M.goal(d), M.ultimate(d)
    assert M.cost(d)[cell] is not None, "the cell-level state must be conditionally reachable"
    assert not M.blocking_outcomes(d, cell), (
        "no single admissible result should close the cell-level state")
    assert M.blocking_outcomes(d, organism), (
        "the organism target is only conditionally reachable; if nothing closes it the map is too kind")


def test_a_bubr1_dependent_benefit_is_a_route_not_a_failure():
    """Independence classifies a route; it does not grade the result.

    The functional target is low missegregation with the population preserved — it never required the
    route to avoid BubR1. So a benefit that exploits residual protein is a compensatory route, the
    third strategy between repair and bypass, and it must still reach the target. Only a benefit that
    vanishes in the limiting regime closes, because then it needs more protein than the case has.
    """
    M, d = _route_map()
    nodes = {n["id"]: n for n in d["nodes"]}
    dep = next(n for n in d["nodes"] if n["id"] == "DEP_FLUX")
    comp = dep["outcomes"]["benefit_requires_residual_bubr1"]
    assert nodes[comp]["kind"] != "terminal", "a compensatory benefit must not terminate"
    reached = M.cost(d, decided={"DEP_FLUX": "benefit_requires_residual_bubr1",
                                 "SAFE01": "preserved"}).get(M.goal(d))
    assert reached is not None and not reached, (
        "a population-preserving, BubR1-dependent rescue must still reach the cell-level state")
    # Saturation changed this deliberately. Losing the benefit in the limiting regime no longer
    # terminates: if abundance can be raised a little, F1 and F3 in combination may meet the
    # requirement that neither meets alone. What must still hold is that it is not a free pass — the
    # functional target from there costs strictly more work than the compensatory result does.
    gone = dep["outcomes"]["benefit_absent_in_limiting_regime"]
    onward = {e["to"] for e in d["edges"] if e["from"] == gone}
    assert onward, f"{gone} must continue; a null in one regime is not the end of a combination route"
    harder = M.cost(d, decided={"DEP_FLUX": "benefit_absent_in_limiting_regime"}).get(M.goal(d))
    assert harder is None or len(harder) > 0, (
        "losing the benefit where it is needed must not reach the target for free")


def test_robust_reachability_is_not_claimed():
    """Single-outcome resilience is a weaker claim and must not be reported as robustness."""
    import inspect

    M, d = _route_map()
    doc = inspect.getdoc(M.blocking_outcomes) or ""
    assert "SINGLE_OUTCOME_RESILIENCE" in doc, "the metric must name itself honestly"
    rendered = M.render(d)
    line = next(l for l in rendered.splitlines() if "ROBUST_REACHABILITY" in l)
    assert "NOT_ESTABLISHED" in line, line
    assert "SINGLE_OUTCOME_RESILIENT" in rendered
    assert "SINGLE_OUTCOME_RESILIENT" in rendered.split("## Reachability")[1].split("##")[0]


def test_a_grounded_fact_is_evidenced_or_derived():
    """Otherwise it is an assertion wearing the word "grounded"."""
    M, d = _route_map()
    for g in d["grounded_facts"]:
        assert g.get("evidence") or g.get("derivation"), g["id"]
    assert not M.validate(d)


def test_char01_does_not_read_a_transcript_change_two_ways():
    """An altered transcript cannot be both a biological class and a validity failure.

    Protein stability cannot be read off an arm whose transcript level differs, so the condition is
    uninterpretable for this question. Letting it also name a biological result would mean the same
    observation both assigns and voids a verdict.
    """
    text = (ROOT / "docs/control/CHAR01_EXECUTION_PACKET.md").read_text()
    assert "validity failure, never a biological result" in text
    assert "altered transcript" not in text.split("## 4.")[0].split("| `destabilised_other_mechanism`")[1].split("|")[1]
    assert "simple abundance-limited instability is not demonstrated" in text


def test_no_leaf_exists_because_reasoning_stopped_after_an_experiment():
    """The saturation acceptance criterion.

    A leaf is allowed to be a target, a safety closure, a governance block, an evidence
    incompatibility, an exhausted search, a declared frontier with no identifiable next step, or a
    validity repeat. It is not allowed to be a branch nobody continued, which is what the retired
    NO_KNOWN_CONTINUATION nodes all were.
    """
    M, d = _route_map()
    assert "NO_KNOWN_CONTINUATION" not in d["terminal_vocabulary"], (
        "the kind that hid thirteen unexpanded branches must stay retired")
    continues = {e["from"] for e in d["edges"]}
    unexpanded = [n["id"] for n in d["nodes"] if n["kind"] == "terminal"
                  and n["terminal"] == "UNEXPANDED_FRONTIER" and n["id"] not in continues]
    assert not unexpanded, f"leaves that merely stopped reasoning: {unexpanded}"
    for n in d["nodes"]:
        if n["kind"] == "terminal":
            assert n["terminal"] in set(d["terminal_vocabulary"]), f"{n['id']}: {n['terminal']}"


def test_a_failed_actuator_does_not_close_a_control_variable():
    """Rule 3. Four failed mechanisms closed BubR1 abundance in the previous map; they should not have.

    A control variable is a biological quantity and an actuator is a way of moving it. The variable
    closes only on evidence about the variable — which is why chronic checkpoint activation is the one
    entry that may be called unsafe at variable level, and it cites the in vivo result that says so.
    """
    M, d = _route_map()
    cvs = d["control_variables"]
    abundance = cvs["CV_BUBR1_ABUNDANCE"]
    assert abundance["actuators_tried"], "the tried actuators must be recorded"
    assert abundance["actuators_identified_not_tried"], (
        "closing a variable while untried actuators are identified is the error Rule 3 names")
    assert abundance["intrinsically_unsafe"] == "NOT_ESTABLISHED"
    act = cvs["CV_CHECKPOINT_ACTIVATION"]
    assert act["intrinsically_unsafe"].startswith("PARTLY"), (
        "chronic activation is harmful in vivo and the variable entry must say so")
    assert act.get("unsafe_evidence"), "a variable-level safety claim must cite its evidence"


def test_all_four_strategy_families_are_present_and_reachable():
    """F4 arrived from the frontier audit rather than from a search, and it must be wired in."""
    M, d = _route_map()
    fams = d["families"]
    assert set(fams) == {"F1_REPAIR", "F2_REPLACE", "F3_EXPLOIT_AND_ALTER", "F4_REMOVE"}
    c = M.cost(d)
    # The flux-specific convergence states were merged into actuator-agnostic ones during saturation,
    # so every candidate arrives at the same biological state instead of duplicating the subtree.
    for entry in ("S_MIS_LOWERED_COMPENSATORY", "CV_CLEARANCE_ENTRY"):
        assert c.get(entry) is not None, f"{entry} is not reachable, so its family is decoration"


def test_the_campaign_arms_separate_actuator_failure_from_variable_failure():
    """Rule 4 inside a campaign: one unsafe arm is not an unsafe control variable."""
    M, d = _route_map()
    flux = next(c for c in d["campaigns"] if c["id"] == "FLUX01")
    assert len(flux["arms"]) >= 3, "the mechanistically independent arms must be retained"
    for arm in flux["arms"].values():
        assert arm["control_variable"] == "CV_POLEWARD_FLUX"
        assert arm["engagement_readout"]
    assert "arm_level_rule" in flux and "every arm fails" in flux["arm_level_rule"]
    assert set(flux["arm_divergence_outcomes"]) >= {"some_arms_effective_some_unsafe"}


def test_a_motif_hypothesis_is_never_traversable():
    """The load-bearing separation of the analysis pass.

    A motif is a pattern in the graph and a reason to ask a question. If a motif-derived connection
    could be traversed, an interesting pattern would start shortening routes and closing branches
    without anyone having grounded it — the graph would begin believing its own conjectures. So the
    hypotheses live outside `edges`, and deleting every one of them must leave reachability identical.
    """
    M, d = _route_map()
    hyps = d["hypotheses"]
    assert hyps, "the analysis pass produced nothing"
    ids = {n["id"] for n in d["nodes"]}
    for h in hyps:
        assert h["status"] == "NOT_TRAVERSABLE", h["id"]
        assert h["kind"] in ("STRUCTURAL", "BIOLOGICAL"), h["id"]
        assert h["id"] not in ids, f"{h['id']} is a node, so it is traversable"
        if h["kind"] == "BIOLOGICAL":
            assert h.get("what_would_promote_it"), (
                f"{h['id']} is a claim about the world with no stated way to ground it")

    before = M.cost(d)
    stripped = {k: v for k, v in d.items() if k != "hypotheses"}
    after = M.cost(stripped)
    assert before == after, "removing the hypotheses changed reachability, so one of them is traversable"


def test_the_motif_analysis_reads_the_graph_rather_than_asserting_it():
    """Motif counts must be computed, so a stale claim in prose cannot survive an edit."""
    M, d = _route_map()
    mo = M.motifs(d)
    assert len(mo["shared_prerequisite_limiting_system"]) >= 5, (
        "the shared-platform motif is the analysis pass's main finding and must be recomputed")
    assert mo["repeated_shapes"], "repeated branch shapes should exist once candidates are parameterised"
    assert not mo["shared_actuators"], (
        "no actuator should move two control variables; if one now does, the combination branches "
        "need revisiting and the negative motif in the report is stale")
    rendered = M.render(d)
    assert "NOT_TRAVERSABLE" in rendered
    assert str(len(mo["shared_prerequisite_limiting_system"])) in rendered


def test_the_new_control_variables_carry_evidence_and_actuators():
    """A control variable without an actuator is a wish, and without evidence it is a guess."""
    M, d = _route_map()
    for cv in ("CV_CELL_SIZE", "CV_ATTACHMENT_TURNOVER", "CV_COHESION_PROTECTION"):
        spec = d["control_variables"][cv]
        assert spec.get("evidence"), f"{cv} has no evidence"
        assert spec.get("actuators_identified_not_tried"), f"{cv} has no actuator"
        assert spec.get("intrinsically_unsafe") == "NOT_ESTABLISHED"
    c = M.cost(d)
    for cand in ("C_CELL_SIZE", "C_ATTACH_TURNOVER", "C_COHESION"):
        assert c.get(cand) is not None, f"{cand} is unreachable, so the variable is decoration"


def test_every_cross_family_combination_exists_and_is_reachable():
    """The families were enumerated as alternatives; combinations are their own routes."""
    M, d = _route_map()
    c = M.cost(d)
    for combo in ("COMBO01", "COMBO_F1_F2", "COMBO_F2_F3", "COMBO_F3_F4", "COMBO_F1_F4"):
        node = next((n for n in d["nodes"] if n["id"] == combo), None)
        assert node and node["kind"] == "branch", f"{combo} missing"
        assert c.get(combo) is not None, f"{combo} is unreachable"
