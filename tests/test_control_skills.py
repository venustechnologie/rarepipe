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
    for state in ("NOT_IN_LOCAL_CASE_CORPUS", "NOT_FOUND_IN_SEARCHED_EXTERNAL_UNIVERSE",
                  "NO_KNOWN_PHYSICAL_REALIZATION"):
        assert state in vocab, state
    for n in d["nodes"]:
        if n["kind"] == "terminal" and n.get("terminal") == "NO_KNOWN_PHYSICAL_REALIZATION":
            assert "evidence" in n or "justification" in n, (
                f"{n['id']} claims no known physical realization without recording what justifies it; "
                "a bounded negative search belongs in NOT_FOUND_IN_SEARCHED_EXTERNAL_UNIVERSE")


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
        assert any(o.startswith("requires_bubr1") for o in outcomes), f"{n['id']}"
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
    assert "S_CHECKPOINT_RISK_RESOLVED" in functional["of"], (
        "reclassifying T_ACT must leave its tumour-predisposition question in the target, not drop it")
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
    assert "S_CHECKPOINT_RISK_RESOLVED" in nodes[M.goal(d)]["of"]
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
