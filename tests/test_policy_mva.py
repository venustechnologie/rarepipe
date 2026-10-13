"""The adapter against the real compiled map: the findings, pinned.

These are the results that make the engine worth having, so they get a regression test rather than
living only in a generated document. Everything here is cheap — structural computations on the real
graph, no deep policy search — so it runs in CI alongside the toy gates.

If the route map changes, several of these will fail. That is the intent: the point of a frozen map
is that a computation over it moves only when the map does, and loudly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "tools/control/solve_mva_policy.py"


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location("solve_mva_policy", ADAPTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def document(adapter):
    return adapter.load()


@pytest.fixture(scope="module")
def graph(adapter, document):
    return adapter.build_graph(document)


# ── the map maps ─────────────────────────────────────────────────────────────────────────────

def test_the_real_map_builds_into_a_valid_graph(graph):
    assert len(graph.nodes) == 240, "94 state + 56 branch + 4 all_of + 86 terminal"
    assert len(graph.edges) == 154
    assert len(graph.branch_ids()) == 56
    assert graph.goal == "FUNCTIONAL_CELLULAR_TARGET"
    assert graph.root == "S0_CASE"
    assert graph.cycles() == [], "acyclic once re-entry edges are set aside"


def test_every_terminal_kind_in_the_map_has_a_declared_role(adapter, document):
    """A terminal kind with no declared role must raise, not default to something convenient.

    Defaulting would quietly decide a safety question: an unrecognised kind landing on `FRONTIER`
    turns an unsafe closure into an open question.
    """
    declared = set(adapter.TERMINAL_ROLES)
    used = {n.get("terminal") for n in document["nodes"] if n["kind"] == "terminal"}
    assert used <= declared, f"terminal kinds with no declared role: {sorted(used - declared)}"


def test_the_invalid_run_derivation_is_total(adapter, document):
    """Derived from the destination terminal, then checked for totality rather than trusted."""
    derived = adapter.non_informative_outcomes(document)
    outcomes = [(branch, name) for branch, names in derived.items() for name in names]
    assert len(outcomes) == 20, "one per declared repeat condition"
    repeats = {n["id"] for n in document["nodes"]
               if n["kind"] == "terminal" and n["id"].endswith("_REPEAT")}
    assert len(repeats) == 20
    # Matching on the outcome's *name* would have missed one: nineteen are `insufficient` and one
    # is `confounded_invalid`.
    names = {name for _, name in outcomes}
    assert names == {"insufficient", "confounded_invalid"}, names


def test_a_new_unreached_repeat_terminal_would_raise(adapter, document):
    """The derivation refuses to guess when the map stops matching what it was written against."""
    mutated = {**document, "nodes": [*document["nodes"],
                                     {"id": "T_INVENTED_REPEAT", "kind": "terminal",
                                      "terminal": "BOUNDED_FRONTIER", "label": "unreached"}]}
    with pytest.raises(adapter.AdapterError, match="no outcome reaches"):
        adapter.non_informative_outcomes(mutated)


# ── the published reachability table is reproduced ───────────────────────────────────────────

def test_conditional_reachability_and_single_outcome_resilience_match_the_published_map(graph):
    from rarepipe.stages.control.policy import blocking_outcomes, conditionally_reachable

    assert conditionally_reachable(graph) is True
    assert blocking_outcomes(graph, graph.goal) == (), (
        "the published map reports no single result closing the cellular target")


def test_the_cellular_target_has_four_tied_minimal_routes(graph):
    """The finding that motivated removing the silent cap.

    The published document names `DEP_ATTACH_TURNOVER, SAFE01` as "the smallest set" and separately
    recommends the campaign covering `DEP_FLUX, SAFE01`. Both statements are true, because there
    are four tied minimal routes — and presenting one of four as "the" smallest is exactly the
    ambiguity this computation removes.
    """
    from rarepipe.stages.control.policy import frontier

    tied = frontier(graph, destination=graph.goal).tied_minimal(graph.goal)
    assert [sorted(s) for s in tied] == [
        ["DEP_ATTACH_TURNOVER", "SAFE01"],
        ["DEP_CELL_SIZE", "SAFE01"],
        ["DEP_COHESION", "SAFE01"],
        ["DEP_FLUX", "SAFE01"],
    ]


def test_the_uncapped_frontier_finds_routes_a_cap_of_eight_would_hide(graph):
    """A cap bounds the sets kept per node; where it bites, it must be reported, never silent."""
    from rarepipe.stages.control.policy import frontier

    uncapped = frontier(graph, destination=graph.goal)
    capped = frontier(graph, destination=graph.goal, max_sets=8)
    assert uncapped.truncated == frozenset(), "the default keeps every minimal set"
    assert capped.truncated, "a cap that bites is named in the output"
    # The tied minimal answer survives a cap, but the relevant-branch count does not, which is why
    # the ranking takes that number from the graph instead.
    assert capped.tied_minimal(graph.goal) == uncapped.tied_minimal(graph.goal)
    assert len(capped.relevant_branches(graph.goal)) < \
        len(uncapped.relevant_branches(graph.goal))


# ── the action space, and what it says about the map ────────────────────────────────────────

def test_only_six_of_fifty_six_branches_have_a_declared_campaign(adapter, document, graph):
    from rarepipe.stages.control.policy import build_action_space

    campaigns = adapter.build_campaigns(document)
    assert sorted(c.id for c in campaigns) == ["CHAR01", "FLUX01", "STAB01", "TRIP13_01"]
    covered = {b for c in campaigns for b in c.resolves}
    assert len(covered) == 6, sorted(covered)

    relevant = frozenset(graph.target_relevant_branches(graph.goal))
    space = build_action_space(graph, campaigns, restrict_to=relevant)
    assert len(space.actions) == 37
    assert sum(1 for a in space.actions if a.declared) == 4
    assert sum(1 for a in space.actions if not a.declared) == 33
    # The undeclared ones are tagged, so nothing downstream can read them as runnable experiments.
    assert all(a.provenance == "UNDECLARED_CAMPAIGN"
               for a in space.actions if not a.declared)


def test_branches_needing_an_unavailable_capability_are_reported_not_dropped(adapter, document,
                                                                            graph):
    from rarepipe.stages.control.policy import build_action_space

    relevant = frozenset(graph.target_relevant_branches(graph.goal))
    space = build_action_space(graph, adapter.build_campaigns(document), restrict_to=relevant)
    unavailable = {u.branch: u.requires for u in space.unavailable}
    assert len(unavailable) == 12
    assert unavailable["XFER01"] == "GOVERNANCE_ABSENT", (
        "a governance boundary is reported as such, not as a biological dead end")
    assert set(unavailable.values()) == {"TISSUE_MODEL", "ORGANISM_MODEL", "GOVERNANCE_ABSENT"}


# ── the certificate ─────────────────────────────────────────────────────────────────────────

def test_the_target_falls_to_exactly_six_pairs_every_one_involving_the_same_safety_result(graph):
    """No single result closes the cellular target, but six pairs do — and `SAFE01=harm` is in all.

    That is the decision-relevant shape of the certificate: the bypass component's population
    safety is a necessary ingredient of every minimal way the target can be closed.
    """
    from rarepipe.stages.control.policy import minimal_closing_combinations

    relevant = frozenset(graph.target_relevant_branches(graph.goal))
    found = minimal_closing_combinations(graph, destination=graph.goal, max_size=2,
                                         restrict_to=relevant)
    assert len(found.combinations) == 6
    assert all(("SAFE01", "harm") in combo for combo in found.combinations)
    assert not found.exhaustive, "the searched size is bounded, and the output says so"
    assert found.searched_up_to == 2


def test_no_returned_policy_may_route_through_an_unsafe_terminal(graph):
    from rarepipe.stages.control.policy import unsafe_routes

    routes = unsafe_routes(graph)
    assert ("SAFE01", "harm", "T_UNSAFE") in routes
    assert ("SAFE02", "harm", "T_UNSAFE_F1") in routes
    assert len(routes) == 9


# ── consistency findings ────────────────────────────────────────────────────────────────────

def test_the_duplicated_actuator_name_is_reported_and_not_aliased(adapter, document):
    """`low_dose_paclitaxel` in FLUX01's arms against `low_dose_taxol` in the control variable.

    The same drug under two names. Left as a reported finding because declaring two names to be one
    actuator is a claim only the case's authors can make — and because a control variable whose
    closure requires closing a phantom actuator could never be reported closed.
    """
    findings = adapter.consistency_findings(document, adapter.build_campaigns(document))
    kinds = [f["kind"] for f in findings]
    assert "ACTUATOR_NAME_NOT_IN_CONTROL_VARIABLE_REGISTRY" in kinds
    naming = next(f for f in findings
                  if f["kind"] == "ACTUATOR_NAME_NOT_IN_CONTROL_VARIABLE_REGISTRY")
    assert naming["arm_actuator"] == "low_dose_paclitaxel"
    assert naming["control_variable"] == "CV_POLEWARD_FLUX"
    assert "low_dose_taxol" in naming["registry"]


def test_no_terminal_closes_a_whole_control_variable(document):
    """The map's own rule: one unsafe actuator is not an unsafe control variable.

    `CONTROL_VARIABLE` is in the declared closure vocabulary and no terminal uses it. Asserting
    that keeps a later edit from quietly introducing one.
    """
    scopes = {n.get("closes") for n in document["nodes"] if n.get("closes")}
    assert "CONTROL_VARIABLE" not in scopes, scopes
    assert scopes == {"ACTUATOR", "CONFIGURATION", "CONTEXT", "NO_NEXT_STEP"}


def test_the_two_unbacked_progress_components_are_declared_unavailable(adapter, document):
    findings = adapter.consistency_findings(document, adapter.build_campaigns(document))
    unbacked = next(f for f in findings if f["kind"] == "PROGRESS_COMPONENTS_WITHOUT_DATA")
    assert unbacked["components"] == ["hypotheses_eliminated", "families_resolved"]


# ── the actuator registry ───────────────────────────────────────────────────────────────────

def test_the_actuator_registry_covers_every_control_variable(adapter, document):
    registry = adapter.actuator_registry(document, adapter.build_campaigns(document))
    assert len(registry) == 10, "one entry per declared control variable"
    assert "CV_POLEWARD_FLUX" in registry
    # Both spellings are present, which is the finding above rather than a merge.
    assert {"low_dose_taxol", "low_dose_paclitaxel"} <= set(registry["CV_POLEWARD_FLUX"])


def test_a_single_unsafe_arm_leaves_its_control_variable_open_on_the_real_registry(adapter,
                                                                                  document):
    from rarepipe.stages.control.policy import CLOSED_UNSAFE, KnowledgeState, seed_actuators
    from dataclasses import replace

    registry = adapter.actuator_registry(document, adapter.build_campaigns(document))
    state = KnowledgeState.initial(seed_actuators(registry))
    assert state.control_variable_closed("CV_POLEWARD_FLUX") is False

    closed = replace(state, actuators=tuple(
        replace(a, status=CLOSED_UNSAFE) if a.actuator == "low_dose_paclitaxel" else a
        for a in state.actuators))
    assert closed.control_variable_closed("CV_POLEWARD_FLUX") is False, (
        "one unsafe actuator is not an unsafe control variable")
    assert "HAUS8_depletion" in closed.open_actuators("CV_POLEWARD_FLUX")
