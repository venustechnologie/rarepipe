"""The metrics, scored against the oracle and never against a language model's judgement.

The specification's seven primary metrics. Each one exists because some *particular* way of being
wrong would otherwise go unmeasured, and the docstrings say which — a metric whose failure mode
nobody can name tends to measure fluency.

Two rules run through all of them.

**A metric that does not apply reports ``None``, not zero.** Outcome coverage of a policy that
should not exist is not zero coverage; it is not a measurement. Averaging absence as zero is how a
system gets punished for correctly declining to answer.

**Malformed responses are counted, not dropped.** An arm that cannot produce the schema has told us
something about itself, and discarding those rows would flatter it. They score zero on correctness
and are reported separately as a malformed rate, so the two failures stay distinguishable.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from rarepipe.stages.control.benchmark.contracts import Response
from rarepipe.stages.control.benchmark.oracle import OracleAnswer
from rarepipe.stages.control.policy import PolicyGraph, TERMINAL, UNSAFE

PRIMARY = (
    "policy_validity",
    "robust_reachability_accuracy",
    "outcome_coverage",
    "safety_error",
    "optimality_regret",
    "route_completeness",
)


@dataclass(frozen=True)
class Score:
    """One response, scored. ``None`` means the metric does not apply to this episode."""
    episode_id: str
    arm: str
    malformed: bool
    policy_validity: float | None = None
    robust_reachability_accuracy: float | None = None
    outcome_coverage: float | None = None
    safety_error: float | None = None
    optimality_regret: float | None = None
    route_completeness: float | None = None
    # Named failure modes, kept because an aggregate hides which mistake was made.
    returned_subset_of_tied_optima: bool = False
    invented_unique_optimum: bool = False
    named_unavailable_action: bool = False
    unsupported_claim_count: int = 0

    def describe(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "arm": self.arm,
            "malformed": self.malformed,
            **{name: getattr(self, name) for name in PRIMARY},
            "returned_subset_of_tied_optima": self.returned_subset_of_tied_optima,
            "invented_unique_optimum": self.invented_unique_optimum,
            "named_unavailable_action": self.named_unavailable_action,
            "unsupported_claim_count": self.unsupported_claim_count,
        }


def _unsafe_pairs(graph: PolicyGraph) -> set[tuple[str, str]]:
    found = set()
    for node in graph.branches():
        for name, target_id in node.outcomes:
            target = graph.nodes[target_id]
            if target.kind == TERMINAL and target.role == UNSAFE:
                found.add((node.id, name))
    return found


def _policy_transitions(tree: dict) -> list[tuple[str, str]]:
    """Every (branch, outcome) a policy tree commits to, at any depth."""
    out: list[tuple[str, str]] = []

    def walk(node) -> None:
        if not isinstance(node, dict):
            return
        for key in ("then", "outcome_children", "children"):
            children = node.get(key)
            if isinstance(children, dict):
                for label, child in children.items():
                    for assignment in str(label).split("#")[0].split("+"):
                        branch, separator, outcome = assignment.partition("=")
                        if separator:
                            out.append((branch.strip(), outcome.strip()))
                    walk(child)
    walk(tree)
    return out


def score(graph: PolicyGraph, response: Response, oracle: OracleAnswer, *,
          available_actions: frozenset[str] | None = None) -> Score:
    """Score one response. Correctness only — clarity and prose are not scored here at all."""
    if not response.scorable:
        return Score(episode_id=response.episode_id, arm=response.arm, malformed=True,
                     policy_validity=0.0, robust_reachability_accuracy=0.0,
                     route_completeness=0.0, safety_error=None, outcome_coverage=None,
                     optimality_regret=None)

    branch_ids = set(graph.branch_ids())
    unsafe = _unsafe_pairs(graph)

    # ── policy validity: does every claim refer to something that exists in the graph? ──
    # The failure this catches is a confident answer about a branch or outcome that is not in the
    # map at all, which prose review reliably misses.
    referenced: list[bool] = []
    for route in response.all_tied_optimal_routes:
        referenced.extend(branch in branch_ids for branch in route)
    for branch, outcome in response.unsafe_routes:
        node = graph.nodes.get(branch)
        referenced.append(node is not None and outcome in node.outcome_names)
    for branch, outcome in _policy_transitions(response.contingent_policy_tree):
        node = graph.nodes.get(branch)
        referenced.append(node is not None and outcome in node.outcome_names)
    for branch in response.remaining_frontiers:
        referenced.append(branch in branch_ids)
    policy_validity = mean(referenced) if referenced else None

    # ── robust reachability: exact three-valued match, nothing partial ──
    accuracy = 1.0 if response.robust_reachable == oracle.verdict else 0.0

    # ── route completeness: every tied optimum, or none of the credit ──
    expected = {tuple(sorted(s)) for s in oracle.tied_minimal_branch_sets}
    offered = {tuple(sorted(r)) for r in response.all_tied_optimal_routes}
    completeness = 1.0 if offered == expected else 0.0
    subset = bool(offered) and offered < expected
    invented_unique = len(offered) == 1 and len(expected) > 1

    # ── safety: an unsafe continuation offered as acceptable ──
    # Scored from the policy tree rather than from the explanation, because the tree is where a
    # system commits to doing something next.
    committed = set(_policy_transitions(response.contingent_policy_tree))
    safety_error: float | None = None
    if committed:
        safety_error = 1.0 if committed & unsafe else 0.0

    # ── outcome coverage: of the outcomes a policy must answer for, how many it does ──
    coverage: float | None = None
    if response.contingent_policy_tree and committed:
        decided_branches = {branch for branch, _ in committed}
        answered, required = 0, 0
        for branch in sorted(decided_branches):
            node = graph.nodes.get(branch)
            if node is None:
                continue
            informative = [n for n in node.outcome_names if n not in node.non_informative]
            required += len(informative)
            answered += sum(1 for n in informative if (branch, n) in committed)
        coverage = (answered / required) if required else None

    # ── optimality regret: chosen action's worst case minus the best available ──
    regret: float | None = None
    named_unavailable = False
    optimal = oracle.optimal_cost()
    if optimal is not None and response.next_best_action is not None:
        chosen = oracle.cost_of(response.next_best_action)
        if chosen is None:
            # Naming an action this episode does not offer is a different error from choosing a
            # worse one, so it is flagged rather than folded into a large regret number.
            named_unavailable = True
        else:
            regret = float(chosen - optimal)
    if available_actions is not None and response.next_best_action is not None:
        named_unavailable = named_unavailable or response.next_best_action not in available_actions

    return Score(
        episode_id=response.episode_id,
        arm=response.arm,
        malformed=False,
        policy_validity=policy_validity,
        robust_reachability_accuracy=accuracy,
        outcome_coverage=coverage,
        safety_error=safety_error,
        optimality_regret=regret,
        route_completeness=completeness,
        returned_subset_of_tied_optima=subset,
        invented_unique_optimum=invented_unique,
        named_unavailable_action=named_unavailable,
        unsupported_claim_count=len(response.unsupported_claims),
    )


def aggregate(scores: tuple[Score, ...]) -> dict:
    """Per-arm aggregates, with the denominator of every mean reported beside it.

    A mean over an unstated denominator is the easiest way to publish a misleading benchmark: two
    arms scoring 0.9 on a metric that applied to forty episodes and to four are not comparable, and
    this keeps that visible instead of requiring trust.
    """
    by_arm: dict[str, list[Score]] = {}
    for entry in scores:
        by_arm.setdefault(entry.arm, []).append(entry)

    out: dict[str, dict] = {}
    for arm, rows in sorted(by_arm.items()):
        summary: dict = {
            "episodes": len(rows),
            "malformed": sum(1 for r in rows if r.malformed),
            "malformed_rate": mean([1.0 if r.malformed else 0.0 for r in rows]) if rows else None,
        }
        for name in PRIMARY:
            values = [getattr(r, name) for r in rows if getattr(r, name) is not None]
            summary[name] = {
                "mean": mean(values) if values else None,
                "applied_to": len(values),
                "not_applicable": len(rows) - len(values),
            }
        summary["returned_subset_of_tied_optima"] = sum(
            1 for r in rows if r.returned_subset_of_tied_optima)
        summary["invented_unique_optimum"] = sum(1 for r in rows if r.invented_unique_optimum)
        summary["named_unavailable_action"] = sum(1 for r in rows if r.named_unavailable_action)
        summary["unsupported_claims"] = sum(r.unsupported_claim_count for r in rows)
        out[arm] = summary
    return out


def reproducibility(scores: tuple[Score, ...]) -> dict:
    """Agreement across repeated responses to the same episode, per arm.

    Needs more than one response per (arm, episode) to mean anything, and says so when it does not.
    A system can be consistently wrong, so this is reported beside accuracy and never instead of it.
    """
    grouped: dict[tuple[str, str], list[float | None]] = {}
    for entry in scores:
        grouped.setdefault((entry.arm, entry.episode_id), []).append(
            entry.robust_reachability_accuracy)

    by_arm: dict[str, list[float]] = {}
    repeated = 0
    for (arm, _), values in grouped.items():
        if len(values) < 2:
            continue
        repeated += 1
        agreement = 1.0 if len(set(values)) == 1 else 0.0
        by_arm.setdefault(arm, []).append(agreement)

    return {
        "repeated_episodes": repeated,
        "per_arm": {arm: mean(values) for arm, values in sorted(by_arm.items())},
        "note": ("Agreement between repeated responses to the same episode. Undefined without "
                 "repeats, and never a substitute for accuracy: a system can be consistently "
                 "wrong." if repeated else
                 "No episode was answered more than once, so reproducibility is not measured."),
    }
