"""Why the answer is no — in a form someone can check without rerunning the search.

A solver that returns ``robust_reachable: false`` and nothing else is asking to be trusted. These
are the artefacts that make the negative answer auditable:

* **An adversary witness.** For every action the planner could take, the outcome that defeats it,
  recursively. This is the counter-policy: it is what "no policy survives every outcome" *means*,
  and it can be replayed by hand against the map.
* **Minimal closing combinations.** Sets of results that leave the goal structurally unreachable,
  smallest first. Bounded by size, with the bound reported — an unbounded search over combinations
  of 51 branches does not terminate, and a certificate that quietly stopped looking is worse than
  one that says where it stopped.
* **The robust subset.** Which conjuncts of the goal *are* robustly reachable. "Nothing works" and
  "three of the four conjuncts are guaranteed and the fourth is not" are different findings, and
  the second is the one that tells you what to work on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, product

from rarepipe.stages.control.policy.graph import ALL_OF, PolicyGraph
from rarepipe.stages.control.policy.reachability import can_establish, frontier

BOUNDED = "SEARCH_BOUNDED_AT_SIZE"


@dataclass(frozen=True)
class AdversaryWitness:
    """One node of the counter-policy: every action, and the outcome that beats it."""
    state: dict
    defeats: tuple[tuple[str, str, "AdversaryWitness | None"], ...] = ()
    reason: str = ""

    def describe(self, depth: int = 3) -> dict:
        out: dict = {"state": self.state}
        if self.reason:
            out["reason"] = self.reason
        if self.defeats and depth > 0:
            out["defeated_actions"] = [
                {
                    "action": action,
                    "defeating_outcome": outcome,
                    "then": child.describe(depth - 1) if child is not None else None,
                }
                for action, outcome, child in self.defeats
            ]
        elif self.defeats:
            out["defeated_actions_count"] = len(self.defeats)
        return out


@dataclass
class ClosingCombinations:
    combinations: list[tuple[tuple[str, str], ...]] = field(default_factory=list)
    searched_up_to: int = 0
    exhaustive: bool = False

    def describe(self) -> dict:
        return {
            "minimal_closing_combinations": [
                [{"branch": b, "outcome": o} for b, o in combo] for combo in self.combinations
            ],
            "searched_up_to_size": self.searched_up_to,
            "exhaustive": self.exhaustive,
            "note": (
                "Every combination up to the stated size was tested."
                if self.exhaustive else
                f"{BOUNDED} {self.searched_up_to}. Larger combinations may also close the goal; "
                "absence from this list is not evidence that none exists."
            ),
        }


Assignment = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CutSetAnalysis:
    """Minimal cut sets and minimal success sets over branch outcomes.

    The two questions reliability engineering asks of a fault tree, asked of a decision graph:

    * **cut sets** — minimal combinations of future results that destroy *every* route to the
      target. What has to go wrong for this to be over.
    * **success sets** — minimal combinations of results that are *sufficient* to establish it.
      What has to go right for this to be done.

    Both are bounded by size, and the bound is reported rather than implied. The distinction
    matters for how a member frequency may be worded: a branch appearing in every cut set *found*
    at size ≤ 2 is not thereby necessary to every failure of every size, and
    ``common_cut_members`` says so in its own scope field rather than leaving the reader to assume.
    """
    cut_sets: tuple[Assignment, ...] = ()
    success_sets: tuple[Assignment, ...] = ()
    searched_up_to: int = 0
    exhaustive: bool = False
    common_cut_members: tuple[dict, ...] = ()
    common_success_members: tuple[dict, ...] = ()

    def describe(self) -> dict:
        scope = (f"minimal sets of size at most {self.searched_up_to}"
                 + ("" if self.exhaustive else ", which is a bound on the search, not on the graph"))
        return {
            "minimal_target_cut_sets": [
                [{"branch": b, "outcome": o} for b, o in combo] for combo in self.cut_sets
            ],
            "minimal_target_success_sets": [
                [{"branch": b, "outcome": o} for b, o in combo] for combo in self.success_sets
            ],
            "common_cut_members": list(self.common_cut_members),
            "common_success_members": list(self.common_success_members),
            "searched_up_to_size": self.searched_up_to,
            "exhaustive": self.exhaustive,
            "scope": scope,
            "note": (
                "A cut set is a combination of results after which no route to the target remains. "
                "A success set is one after which the target is established. Frequencies in "
                "common_cut_members are over the sets found within the searched size and carry "
                "that scope; a member common to every cut set of size two is not thereby "
                "necessary to every failure of every size."
            ),
        }


def _common_members(sets: tuple[Assignment, ...], searched_up_to: int, kind: str) -> tuple[dict, ...]:
    """Members shared by every set found, with the frequency and the scope that frequency has."""
    if not sets:
        return ()
    counts: dict[tuple[str, str], int] = {}
    for combo in sets:
        for member in combo:
            counts[member] = counts.get(member, 0) + 1
    total = len(sets)
    return tuple(
        {
            "branch": branch,
            "outcome": outcome,
            "frequency": f"{count}/{total}",
            "in_every_set_found": count == total,
            "scope": f"over the minimal {kind} sets of size at most {searched_up_to} that were found",
        }
        for (branch, outcome), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if count > 1
    )


def cut_set_analysis(graph: PolicyGraph, *, destination: str | None = None, max_size: int = 2,
                     restrict_to: frozenset[str] | None = None) -> CutSetAnalysis:
    """Minimal cut sets and minimal success sets, both bounded by the same declared size.

    One enumeration serves both: for every assignment of results to a combination of branches, ask
    the cheap relaxation whether the destination is still establishable (a cut set when it is not)
    and whether it is already established (a success set when it is). Minimality is in the subset
    sense, computed separately for each family, so a size-2 answer is never padded to size 3.

    Only informative outcomes take part. A cut set resting on an assay voiding its own validity
    gates is not a fact about the biology, and listing it would make every target look fragile for
    a reason no experiment can fix.
    """
    destination = destination or graph.goal
    pool = sorted(node.id for node in graph.branches()
                  if restrict_to is None or node.id in restrict_to)
    cuts: list[frozenset[tuple[str, str]]] = []
    successes: list[frozenset[tuple[str, str]]] = []
    searched = 0

    for size in range(1, max_size + 1):
        searched = size
        for branch_combo in combinations(pool, size):
            option_lists = [
                [(branch, name) for name in graph.nodes[branch].outcome_names
                 if name not in graph.nodes[branch].non_informative]
                for branch in branch_combo
            ]
            for assignment in product(*option_lists):
                candidate = frozenset(assignment)
                cut_known = any(existing <= candidate for existing in cuts)
                win_known = any(existing <= candidate for existing in successes)
                if cut_known and win_known:
                    continue
                establishable, established = can_establish(
                    graph, decided=dict(assignment), destination=destination)
                if not establishable and not cut_known:
                    cuts.append(candidate)
                elif established and not win_known:
                    successes.append(candidate)

    def order(found: list[frozenset[tuple[str, str]]]) -> tuple[Assignment, ...]:
        return tuple(tuple(sorted(combo))
                     for combo in sorted(found, key=lambda c: (len(c), sorted(c))))

    cut_sets, success_sets = order(cuts), order(successes)
    exhaustive = max_size >= len(pool)
    return CutSetAnalysis(
        cut_sets=cut_sets,
        success_sets=success_sets,
        searched_up_to=searched,
        exhaustive=exhaustive,
        common_cut_members=_common_members(cut_sets, searched, "cut"),
        common_success_members=_common_members(success_sets, searched, "success"),
    )


def minimal_closing_combinations(graph: PolicyGraph, *, destination: str | None = None,
                                 max_size: int = 2,
                                 restrict_to: frozenset[str] | None = None) -> ClosingCombinations:
    """Smallest sets of results that leave the destination structurally unreachable.

    Minimal in the subset sense: a combination is reported only if no proper subset of it already
    closes the destination, so a size-2 answer is never padded out to size 3.

    Only informative outcomes are considered. A combination that relies on an assay failing its
    validity gates is not a fact about the biology, and listing it would make every goal look
    fragile for a reason no experiment can fix.
    """
    destination = destination or graph.goal
    pool = sorted(
        node.id for node in graph.branches()
        if restrict_to is None or node.id in restrict_to
    )
    result = ClosingCombinations(searched_up_to=0, exhaustive=True)
    found: list[frozenset[tuple[str, str]]] = []

    for size in range(1, max_size + 1):
        result.searched_up_to = size
        for branch_combo in combinations(pool, size):
            option_lists = []
            for branch in branch_combo:
                node = graph.nodes[branch]
                option_lists.append([
                    (branch, name) for name in node.outcome_names
                    if name not in node.non_informative
                ])
            for assignment in product(*option_lists):
                candidate = frozenset(assignment)
                if any(existing <= candidate for existing in found):
                    continue                        # a subset already closes it; not minimal
                establishable, _ = can_establish(graph, decided=dict(assignment),
                                                 destination=destination)
                if not establishable:
                    found.append(candidate)

    result.combinations = [
        tuple(sorted(combo)) for combo in sorted(found, key=lambda c: (len(c), sorted(c)))
    ]
    result.exhaustive = max_size >= len(pool)
    return result


def robust_subset(graph: PolicyGraph, robust_check) -> dict:
    """Which conjuncts of the goal are robustly reachable, when the goal as a whole is not.

    ``robust_check`` is a callable taking a node id and returning a verdict string. It is passed in
    rather than imported so that this module does not depend on the solver, and the solver's budget
    and horizon stay under the caller's control.
    """
    goal_node = graph.nodes[graph.goal]
    members = goal_node.members if goal_node.kind == ALL_OF else ()
    if not members:
        return {"goal_is_conjunction": False, "conjuncts": {}}
    verdicts = {member: robust_check(member) for member in sorted(members)}
    return {
        "goal_is_conjunction": True,
        "conjuncts": verdicts,
        "robust_conjuncts": sorted(m for m, v in verdicts.items() if v == "TRUE"),
        "blocking_conjuncts": sorted(m for m, v in verdicts.items() if v != "TRUE"),
    }


def unreached_frontiers(graph: PolicyGraph, decided: dict[str, str],
                        destination: str | None = None) -> tuple[str, ...]:
    """Branches the destination still depends on that no result has settled.

    These are the open questions, as distinct from the closed routes and the unsafe ones. Keeping
    the three apart is the difference between "we are stuck" and "we have not asked yet".
    """
    destination = destination or graph.goal
    f = frontier(graph, decided=decided, destination=destination)
    return tuple(sorted(f.relevant_branches(destination) - set(decided)))
