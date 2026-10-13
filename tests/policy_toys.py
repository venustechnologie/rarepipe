"""Small, fully known AND/OR graphs for the policy engine's gates. Not collected by pytest.

Each graph is small enough that the right answer can be worked out by hand, which is the only kind
of fixture that can check a solver. Where a graph exists to pin one of the specification's required
behaviours, the docstring says which.
"""
from __future__ import annotations

from rarepipe.stages.control.policy import (ALL_OF, BLOCKED, BRANCH, COMPONENT_DISCOVERY, FRONTIER,
                                            GOAL, IMPOSSIBLE, MEASUREMENT, STATE, TERMINAL, UNSAFE,
                                            Action, Arm, Edge, Node, PolicyGraph)
from rarepipe.stages.control.policy.actions import DECLARED_CAMPAIGN

CELL = "CELL_MODEL"
ORGANISM = "ORGANISM_MODEL"


def branch(bid, outcomes, *, requires=CELL, resolves_by=MEASUREMENT, non_informative=()):
    return Node(id=bid, kind=BRANCH, outcomes=tuple(outcomes.items()), requires=requires,
                resolves_by=resolves_by, non_informative=tuple(non_informative))


def build(nodes, edges, *, root="ROOT", goal="GOAL", available=(CELL,)):
    return PolicyGraph.build(nodes=nodes, edges=edges, root=root, goal=goal,
                             available_requirements=available)


def campaign(cid, resolves, *, arms=(), requires=(CELL,), resolves_by=MEASUREMENT):
    return Action(id=cid, kind=DECLARED_CAMPAIGN, resolves=tuple(resolves), requires=tuple(requires),
                  arms=tuple(arms), resolves_by=resolves_by, question=f"toy campaign {cid}")


# ── 1. a deterministic single route reaches the target ───────────────────────────────────────

def deterministic_route():
    """One branch, every outcome leads on. Robust at horizon 1."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B", {"a": "S_OK", "b": "S_OK"}),
         Node(id="S_OK", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_OK",))],
        [Edge("ROOT", "B"), Edge("S_OK", "GOAL")],
    )


def grounded_route():
    """No branch at all: the goal is already established, so the horizon-0 answer is TRUE."""
    return build(
        [Node(id="ROOT", kind=STATE),
         Node(id="S_OK", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_OK",))],
        [Edge("ROOT", "S_OK"), Edge("S_OK", "GOAL")],
    )


# ── 2. one safe outcome and one unsafe ───────────────────────────────────────────────────────

def safe_and_unsafe_outcome():
    """``harm`` ends on an UNSAFE terminal, so no policy through this branch alone is robust."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("SAFE", {"preserved": "S_OK", "harm": "T_UNSAFE"}),
         Node(id="S_OK", kind=STATE),
         Node(id="T_UNSAFE", kind=TERMINAL, role=UNSAFE),
         Node(id="GOAL", kind=ALL_OF, members=("S_OK",))],
        [Edge("ROOT", "SAFE"), Edge("S_OK", "GOAL")],
    )


# ── 3. two alternative families ──────────────────────────────────────────────────────────────

def two_families():
    """Two independent families, each on its own sufficient, each able to fail outright.

    Not robust, and that is the honest shape of this situation rather than a defect in the fixture:
    an alternative family is only a hedge against the *first* one failing, and if every route can
    fail then no policy survives every combination. This graph is here to pin that both families
    are enumerated, that each is a tied minimal route, and that losing one leaves the other live.
    """
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("F1", {"works": "S_F1", "fails": "T_F1_DEAD"}),
         branch("F2", {"works": "S_F2", "fails": "T_F2_DEAD"}),
         Node(id="S_F1", kind=STATE), Node(id="S_F2", kind=STATE),
         Node(id="T_F1_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="T_F2_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",)),
         Node(id="S_DONE", kind=STATE)],
        [Edge("ROOT", "F1"), Edge("ROOT", "F2"),
         Edge("S_F1", "S_DONE"), Edge("S_F2", "S_DONE"), Edge("S_DONE", "GOAL")],
    )


# ── 4. an AND node needs every member ────────────────────────────────────────────────────────

def conjunction():
    """Two independent branches, both required. A conjunct left unresolved leaves the goal unmet."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B1", {"a": "S_ONE", "b": "S_ONE"}),
         branch("B2", {"a": "S_TWO", "b": "S_TWO"}),
         Node(id="S_ONE", kind=STATE), Node(id="S_TWO", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_ONE", "S_TWO"))],
        [Edge("ROOT", "B1"), Edge("ROOT", "B2")],
    )


# ── 5. one campaign resolves two branches ────────────────────────────────────────────────────

def campaign_resolves_two():
    """The conjunction graph, plus a campaign settling both branches in one action."""
    return conjunction(), (campaign("JOINT01", ("B1", "B2")),)


# ── 6. a negative result closes one family and opens another ─────────────────────────────────

def negative_opens_alternative():
    """``F1=fails`` closes the repair family and routes to the replace family, which still works."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("REPAIR", {"stabilised": "S_REPAIRED", "no_stabilisation": "S_REPAIR_DEAD"}),
         branch("REPLACE", {"supplies": "S_REPLACED", "does_not": "T_NO_ROUTE"}),
         Node(id="S_REPAIRED", kind=STATE), Node(id="S_REPAIR_DEAD", kind=STATE),
         Node(id="S_REPLACED", kind=STATE), Node(id="S_DONE", kind=STATE),
         Node(id="T_NO_ROUTE", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "REPAIR"), Edge("S_REPAIR_DEAD", "REPLACE"),
         Edge("S_REPAIRED", "S_DONE"), Edge("S_REPLACED", "S_DONE"), Edge("S_DONE", "GOAL")],
    )


# ── 7. two tied optimal policies ─────────────────────────────────────────────────────────────

def tied_optima():
    """Two symmetric branches, each on its own sufficient. Both are optimal first actions."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("LEFT", {"a": "S_DONE", "b": "S_DONE"}),
         branch("RIGHT", {"a": "S_DONE", "b": "S_DONE"}),
         Node(id="S_DONE", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "LEFT"), Edge("ROOT", "RIGHT"), Edge("S_DONE", "GOAL")],
    )


# ── 8/9. conditional true with robust false, and robust true ─────────────────────────────────

def conditional_not_robust():
    """``bad`` ends the only route. Reachable if the result is favourable; not robust."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B", {"ok": "S_OK", "bad": "T_DEAD"}),
         Node(id="S_OK", kind=STATE),
         Node(id="T_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_OK",))],
        [Edge("ROOT", "B"), Edge("S_OK", "GOAL")],
    )


def robust_under_every_outcome():
    """Three outcomes, three different continuations, all of which arrive. Robust at horizon 2."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B", {"x": "S_X", "y": "S_Y", "z": "S_Z"}),
         branch("FIXUP", {"a": "S_DONE", "b": "S_DONE"}),
         Node(id="S_X", kind=STATE), Node(id="S_Y", kind=STATE), Node(id="S_Z", kind=STATE),
         Node(id="S_DONE", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "B"), Edge("S_X", "S_DONE"), Edge("S_Y", "S_DONE"),
         Edge("S_Z", "FIXUP"), Edge("S_DONE", "GOAL")],
    )


# ── 10. a safety closure is never overridden by benefit ──────────────────────────────────────

def benefit_behind_unsafe():
    """The only route to the goal runs through an unsafe terminal. No benefit may buy it."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B", {"great_benefit": "T_UNSAFE", "nothing": "T_DEAD"}),
         Node(id="T_UNSAFE", kind=TERMINAL, role=UNSAFE),
         Node(id="T_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="S_NEVER", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_NEVER",))],
        [Edge("ROOT", "B"), Edge("S_NEVER", "GOAL")],
    )


# ── 11. governance block is not biological impossibility ─────────────────────────────────────

def governance_versus_impossible():
    """One route is barred on authorisation grounds, the other ruled out by evidence.

    The two must stay distinguishable in the output: an administrative limit is not a finding about
    the world, and reporting it as one would make a policy decision look like biology.
    """
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("GOV", {"blocked": "T_GOV"}, requires=ORGANISM),
         branch("BIO", {"incompatible": "T_IMPOSSIBLE"}),
         Node(id="T_GOV", kind=TERMINAL, role=BLOCKED),
         Node(id="T_IMPOSSIBLE", kind=TERMINAL, role=IMPOSSIBLE),
         Node(id="S_NEVER", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_NEVER",))],
        [Edge("ROOT", "GOV"), Edge("ROOT", "BIO"), Edge("S_NEVER", "GOAL")],
    )


# ── 12. re-entry terminates through state canonicalisation ───────────────────────────────────

def reentry_loop():
    """A deliberate loop back to an earlier state. The search must terminate, not spin."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B", {"forward": "S_DONE", "retry": "S_BACK"}),
         Node(id="S_BACK", kind=STATE), Node(id="S_DONE", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "B"), Edge("S_BACK", "ROOT", reentry=True), Edge("S_DONE", "GOAL")],
    )


# ── the non-informative outcome, and component discovery ─────────────────────────────────────

def invalid_run_outcome():
    """``insufficient`` is an invalid run, not a result. Declared, so it leaves ∀ alone.

    Without the declaration every policy fails robustness on the grounds that any assay can void
    its own validity gates, which is true and tells nobody anything.
    """
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("B", {"works": "S_OK", "insufficient": "T_REPEAT"},
                non_informative=("insufficient",)),
         Node(id="S_OK", kind=STATE),
         Node(id="T_REPEAT", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_OK",))],
        [Edge("ROOT", "B"), Edge("S_OK", "GOAL")],
    )


def component_discovery_route():
    """Two routes to the goal: one a measurement, one requiring a component nobody has described."""
    return build(
        [Node(id="ROOT", kind=STATE),
         branch("MEASURE", {"a": "S_DONE", "b": "S_DONE"}),
         branch("DISCOVER", {"a": "S_DONE", "b": "S_DONE"}, resolves_by=COMPONENT_DISCOVERY),
         Node(id="S_DONE", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "MEASURE"), Edge("ROOT", "DISCOVER"), Edge("S_DONE", "GOAL")],
    )


# ── arms: one unsafe actuator is not an unsafe control variable ───────────────────────────────

def three_armed_campaign():
    """A campaign with three independent actuators on one control variable."""
    graph = build(
        [Node(id="ROOT", kind=STATE),
         branch("EFFECT", {"lowers": "S_OK", "no_reduction": "T_NULL"}),
         branch("POP", {"preserved": "S_SAFE", "harm": "T_UNSAFE"}),
         Node(id="S_OK", kind=STATE), Node(id="S_SAFE", kind=STATE),
         Node(id="T_NULL", kind=TERMINAL, role=FRONTIER),
         Node(id="T_UNSAFE", kind=TERMINAL, role=UNSAFE),
         Node(id="GOAL", kind=ALL_OF, members=("S_OK", "S_SAFE"))],
        [Edge("ROOT", "EFFECT"), Edge("ROOT", "POP")],
    )
    action = campaign("FLUX01", ("EFFECT", "POP"), arms=(
        Arm(id="F_a", control_variable="CV_FLUX", actuator="paclitaxel_low_dose"),
        Arm(id="F_b", control_variable="CV_FLUX", actuator="HAUS8_depletion"),
        Arm(id="F_c", control_variable="CV_FLUX", actuator="NuMA_depletion"),
    ))
    return graph, (action,)
