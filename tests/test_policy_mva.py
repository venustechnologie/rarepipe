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


def test_cut_sets_and_success_sets_pivot_on_the_same_branch(graph):
    """The symmetric result: `SAFE01` decides the target in both directions, at size two.

    Six minimal cut sets, every one containing `SAFE01=harm`; seven minimal success sets, every one
    containing `SAFE01=preserved`. That is a far stronger statement than "SAFE01 matters", and it is
    the kind of structure a graph of 154 edges does not hand you by inspection.

    The wording of the frequency is load-bearing and is checked: it is scoped to the sets *found*
    within the searched size, not to every failure of every size.
    """
    from rarepipe.stages.control.policy.certificates import cut_set_analysis

    relevant = frozenset(graph.target_relevant_branches(graph.goal))
    analysis = cut_set_analysis(graph, destination=graph.goal, max_size=2, restrict_to=relevant)

    assert len(analysis.cut_sets) == 6
    assert all(("SAFE01", "harm") in combo for combo in analysis.cut_sets)
    assert len(analysis.success_sets) == 7
    assert all(("SAFE01", "preserved") in combo for combo in analysis.success_sets)

    cut_member = next(m for m in analysis.common_cut_members if m["branch"] == "SAFE01")
    assert cut_member["outcome"] == "harm"
    assert cut_member["frequency"] == "6/6"
    assert cut_member["in_every_set_found"] is True
    assert "size at most 2" in cut_member["scope"], (
        "the frequency must carry its own scope; a member common to every size-2 cut set is not "
        "thereby necessary to every failure of every size")

    assert analysis.exhaustive is False
    assert "bound on the search, not on the graph" in analysis.describe()["scope"]


def test_a_success_set_does_not_require_avoiding_the_altered_protein(graph):
    """Independent corroboration of the map's own target audit, from the outcome structure alone.

    `benefit_requires_residual_bubr1` appears in minimal success sets alongside
    `independent_of_bubr1`. The functional target never required avoiding the protein, and the cut
    analysis reaches that conclusion without being told it.
    """
    from rarepipe.stages.control.policy.certificates import cut_set_analysis

    relevant = frozenset(graph.target_relevant_branches(graph.goal))
    analysis = cut_set_analysis(graph, destination=graph.goal, max_size=2, restrict_to=relevant)
    outcomes = {outcome for combo in analysis.success_sets for _, outcome in combo}
    assert "benefit_requires_residual_bubr1" in outcomes
    assert "independent_of_bubr1" in outcomes


def test_the_tied_optimum_output_reports_its_own_count_and_truncation(graph, adapter, document):
    """The mathematical layer never truncates a semantic result, and says so in the output."""
    from rarepipe.stages.control.policy import Constraints, KnowledgeState, seed_actuators, solve_policy

    campaigns = adapter.build_campaigns(document)
    state = KnowledgeState.initial(seed_actuators(adapter.actuator_registry(document, campaigns)))
    answer = solve_policy(graph, state, horizon=1, campaigns=campaigns,
                          constraints=Constraints(max_states=200_000)).describe()
    tied = answer["tied_minimal_branch_sets"]
    assert tied["count"] == 4
    assert len(tied["optimal_sets"]) == 4, "every tied optimum is present, not a display subset"
    assert tied["truncated"] is False


def test_no_returned_policy_may_route_through_an_unsafe_terminal(graph):
    from rarepipe.stages.control.policy import unsafe_routes

    routes = unsafe_routes(graph)
    assert ("SAFE01", "harm", "T_UNSAFE") in routes
    assert ("SAFE02", "harm", "T_UNSAFE_F1") in routes
    assert len(routes) == 9


# ── consistency findings ────────────────────────────────────────────────────────────────────

def test_the_paclitaxel_taxol_identity_is_declared_and_resolved(adapter, document):
    """One drug, one canonical id, the historical spellings kept as declared aliases.

    Paclitaxel is taxol, and in this map both names trace to the same regime in the same source.
    The identity is DECLARED rather than inferred from spelling, because a second name carrying a
    different dose or schedule would be a different actuator and merging them would erase that.
    """
    aliases = adapter.actuator_aliases(document)
    assert aliases["low_dose_taxol"] == "low_dose_paclitaxel"
    assert aliases["Taxol"] == "low_dose_paclitaxel"
    assert aliases["low_dose_paclitaxel"] == "low_dose_paclitaxel", "canonical maps to itself"

    registry = adapter.actuator_registry(document, adapter.build_campaigns(document))
    flux = registry["CV_POLEWARD_FLUX"]
    assert "low_dose_taxol" not in flux, "the alias must not survive as a second entry"
    assert "low_dose_paclitaxel" in flux
    assert len(flux) == 4, (
        "four actuators, not five — a duplicate would be an arm nothing can close, and with it a "
        "control variable that can never be reported closed")


def test_the_duplicate_actuator_finding_is_resolved_not_suppressed(adapter, document):
    """The drift guard stays armed; it simply has nothing to report now."""
    findings = adapter.consistency_findings(document, adapter.build_campaigns(document))
    assert "ACTUATOR_NAME_NOT_IN_CONTROL_VARIABLE_REGISTRY" not in [f["kind"] for f in findings]

    # An *undeclared* mismatch must still be caught, or the guard has been disarmed rather than
    # satisfied.
    drifted = {**document, "campaigns": [
        {**c, "arms": {k: {**v, "actuator": "some_unregistered_actuator"}
                       for k, v in (c.get("arms") or {}).items()}}
        if c.get("arms") else c
        for c in document["campaigns"]]}
    kinds = [f["kind"] for f in adapter.consistency_findings(drifted,
                                                             adapter.build_campaigns(drifted))]
    assert "ACTUATOR_NAME_NOT_IN_CONTROL_VARIABLE_REGISTRY" in kinds


def test_an_alias_set_must_be_declared_never_inferred(adapter, document):
    mutated = {**document, "actuators": [
        {**entry, "basis": "DERIVED"} for entry in document["actuators"]]}
    with pytest.raises(adapter.AdapterError, match="never inferred from spelling"):
        adapter.actuator_aliases(mutated)


def test_two_registry_entries_cannot_claim_the_same_alias(adapter, document):
    mutated = {**document, "actuators": [
        *document["actuators"],
        {"id": "some_other_actuator", "aliases": ["low_dose_taxol"], "basis": "DECLARED"},
    ]}
    with pytest.raises(adapter.AdapterError, match="claimed by both"):
        adapter.actuator_aliases(mutated)


def test_alias_resolution_cannot_change_a_reachability_or_policy_result(adapter, document, graph):
    """The invariant: which spelling a reference used must not reach any computed answer.

    Canonicalisation runs before anything computes, so this holds by construction — and it is
    asserted rather than argued, because the day arms become first-class actions is the day a
    duplicate identity could start changing a verdict.
    """
    from rarepipe.stages.control.policy import (Constraints, KnowledgeState, seed_actuators,
                                                solve_policy)

    # The same map with FLUX01's arm written under the historical spelling instead.
    spelled_as_alias = {**document, "campaigns": [
        {**c, "arms": {k: {**v, "actuator": "low_dose_taxol"} if v.get(
            "actuator") == "low_dose_paclitaxel" else v
            for k, v in (c.get("arms") or {}).items()}}
        if c.get("arms") else c
        for c in document["campaigns"]]}

    def answer(doc):
        campaigns = adapter.build_campaigns(doc)
        registry = adapter.actuator_registry(doc, campaigns)
        state = KnowledgeState.initial(seed_actuators(registry))
        result = solve_policy(adapter.build_graph(doc), state, horizon=1, campaigns=campaigns,
                              constraints=Constraints(max_states=200_000))
        return registry, result.describe()

    canonical_registry, canonical_answer = answer(document)
    alias_registry, alias_answer = answer(spelled_as_alias)

    assert alias_registry == canonical_registry, "the registry resolves to one identity either way"
    assert alias_answer == canonical_answer, (
        "two spellings of one actuator produced different answers; entity canonicalisation is not "
        "acting as a preprocessing invariant")


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


# ── analysis annotations: they may move scoring, never traversability ────────────────────────

def test_the_annotation_schema_exists_and_is_unpopulated(adapter, document):
    """The mechanism is in place; the values are the authors' to supply.

    `null` rather than `0` is the correct report while they are absent, so these stay empty until
    somebody declares them.
    """
    assert document["analysis_basis_vocabulary"] == ["DECLARED", "DERIVED"]
    assert adapter.node_families(document) == {}
    assert adapter.hypothesis_discriminators(document) == {}


def test_relatedness_is_not_treated_as_discrimination(adapter, document):
    """`H_M1` names nine branches and is settled by none of them.

    It declares that nothing would promote it, so nothing eliminates it either. Reading its
    `related_branches` as discriminators would have Δ report a hypothesis eliminated by experiments
    that cannot speak to it.
    """
    hypothesis = next(h for h in document["hypotheses"] if h["id"].startswith("H_M1"))
    assert len(hypothesis["related_branches"]["value"]) == 9
    assert hypothesis["related_branches"]["basis"] == "DERIVED"
    assert "discriminated_by" not in hypothesis
    assert "H_M1_SHARED_PLATFORM" not in adapter.hypothesis_discriminators(document)


def test_a_hypothesis_that_nothing_promotes_cannot_declare_discriminators(adapter, document):
    mutated = {**document, "hypotheses": [
        {**h, "discriminated_by": {"value": ["DEP_FLUX"], "basis": "DECLARED"}}
        if h["id"].startswith("H_M1") else h
        for h in document["hypotheses"]]}
    with pytest.raises(adapter.AdapterError, match="nothing would promote it"):
        adapter.hypothesis_discriminators(mutated)


def test_discriminators_must_be_declared_never_derived(adapter, document):
    mutated = {**document, "latent_variable_hypotheses": [
        {**h, "discriminated_by": {"value": ["DEP_FLUX"], "basis": "DERIVED"}}
        for h in document["latent_variable_hypotheses"]]}
    with pytest.raises(adapter.AdapterError, match="must be DECLARED"):
        adapter.hypothesis_discriminators(mutated)


def test_an_annotation_without_a_basis_is_refused(adapter, document):
    mutated = {**document, "nodes": [
        {**n, "analysis": {"family_membership": {"value": ["F1_REPAIR"]}}}
        if n["id"] == "S0_CASE" else n
        for n in document["nodes"]]}
    with pytest.raises(adapter.AdapterError, match="basis must be DECLARED or DERIVED"):
        adapter.node_families(mutated)


def test_family_membership_must_name_declared_families(adapter, document):
    mutated = {**document, "nodes": [
        {**n, "analysis": {"family_membership": {"value": ["F9_INVENTED"], "basis": "DECLARED"}}}
        if n["id"] == "S0_CASE" else n
        for n in document["nodes"]]}
    with pytest.raises(adapter.AdapterError, match="undeclared families"):
        adapter.node_families(mutated)


def test_annotations_cannot_change_reachability_or_traversability(adapter, document):
    """The rule, enforced: these may affect scoring and analysis, never biological reachability.

    The same map annotated to the hilt — every relevant branch in two families, every latent
    hypothesis given discriminators — must produce an identical graph, identical conditional
    reachability, identical cut sets and identical tied minimal routes.
    """
    from rarepipe.stages.control.policy import (blocking_outcomes, conditionally_reachable,
                                                frontier)
    from rarepipe.stages.control.policy.certificates import cut_set_analysis

    plain = adapter.build_graph(document)
    relevant = set(plain.target_relevant_branches(plain.goal))
    annotated_doc = {
        **document,
        "nodes": [
            {**n, "analysis": {"family_membership": {
                "value": ["F2_REPLACE", "F3_EXPLOIT_AND_ALTER"], "basis": "DECLARED"}}}
            if n["id"] in relevant else n
            for n in document["nodes"]
        ],
        "latent_variable_hypotheses": [
            {**h, "discriminated_by": {"value": ["DEP_FLUX", "SAFE01"], "basis": "DECLARED"}}
            for h in document["latent_variable_hypotheses"]
        ],
    }
    annotated = adapter.build_graph(annotated_doc)

    # The annotations are read, so this is not a vacuous comparison.
    assert len(adapter.node_families(annotated_doc)) == len(relevant)
    assert len(adapter.hypothesis_discriminators(annotated_doc)) == 4

    assert annotated.nodes == plain.nodes, "an annotation must not alter a node the solver sees"
    assert annotated.edges == plain.edges, "an annotation must never create or remove an edge"
    assert conditionally_reachable(annotated) == conditionally_reachable(plain)
    assert blocking_outcomes(annotated, annotated.goal) == blocking_outcomes(plain, plain.goal)
    assert (frontier(annotated, destination=annotated.goal).tied_minimal(annotated.goal)
            == frontier(plain, destination=plain.goal).tied_minimal(plain.goal))
    scope = frozenset(relevant)
    assert (cut_set_analysis(annotated, destination=annotated.goal, max_size=2, restrict_to=scope)
            == cut_set_analysis(plain, destination=plain.goal, max_size=2, restrict_to=scope))


def test_supplying_the_annotations_makes_the_two_components_compute(adapter, document):
    """When the metadata arrives, Δ stops reporting unavailable — without anything else moving."""
    from rarepipe.stages.control.policy.ranking import progress_between

    families = {"DEP_FLUX": frozenset({"F3_EXPLOIT_AND_ALTER"}),
                "SAFE01": frozenset({"F2_REPLACE", "F3_EXPLOIT_AND_ALTER"})}
    discriminators = {"LV1": frozenset({"DEP_FLUX"})}

    without = progress_between(
        before_unresolved=frozenset({"DEP_FLUX", "SAFE01"}), after_unresolved=frozenset({"SAFE01"}),
        outcome_counts={"DEP_FLUX": 5, "SAFE01": 2}, before_distance=2, after_distance=1,
        before_resolved=frozenset(), after_resolved=frozenset({"DEP_FLUX"}))
    assert without.hypotheses_eliminated is None
    assert without.families_resolved is None

    with_metadata = progress_between(
        before_unresolved=frozenset({"DEP_FLUX", "SAFE01"}), after_unresolved=frozenset({"SAFE01"}),
        outcome_counts={"DEP_FLUX": 5, "SAFE01": 2}, before_distance=2, after_distance=1,
        before_resolved=frozenset(), after_resolved=frozenset({"DEP_FLUX"}),
        hypothesis_discriminators=discriminators, node_families=families)
    assert with_metadata.hypotheses_eliminated == 1
    # F3 is still live through SAFE01, so only nothing closes; multi-valued membership is why.
    assert with_metadata.families_resolved == 0
    assert with_metadata.worlds_eliminated == without.worlds_eliminated, "unrelated components fixed"


# ── the actuator registry ───────────────────────────────────────────────────────────────────

def test_the_actuator_registry_covers_every_control_variable(adapter, document):
    registry = adapter.actuator_registry(document, adapter.build_campaigns(document))
    assert len(registry) == 10, "one entry per declared control variable"
    assert "CV_POLEWARD_FLUX" in registry
    # Every entry is a canonical identity: no alias survives anywhere in the registry.
    aliases = adapter.actuator_aliases(document)
    pure_aliases = {name for name, target in aliases.items() if name != target}
    assert not pure_aliases & {a for actuators in registry.values() for a in actuators}


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
