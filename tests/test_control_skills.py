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
    target = M.cost(d)["TARGET"]
    assert target is not None
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
