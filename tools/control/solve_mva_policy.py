#!/usr/bin/env python3
"""Adapt the MVA_001 contingent route map onto the domain-neutral policy engine, and solve it.

This file is the *only* place where MVA's vocabulary meets the solver. The dependency runs one way
and must keep running one way: this adapter imports
``rarepipe.stages.control.policy``, and nothing in that package imports anything from here or knows
that biology exists. ``tests/test_policy_boundary.py`` enforces it, so that the engine can later be
lifted out behind a package boundary without the algorithm being rewritten.

Everything case-specific is decided here and declared, never inferred by the solver:

* which terminal kinds are unsafe, blocked, impossible or merely unreached;
* which capabilities are treated as available (by default a human cell model and nothing else,
  which is what every declared campaign actually needs);
* which outcomes are invalid runs rather than results about biology;
* the four declared campaigns, their arms and the actuator registry.

Two **map consistency findings** are reported rather than silently repaired, because repairing a
case's data from inside a solver is how a tool starts inventing its own inputs. See
``consistency_findings``.

Usage: uv run python tools/control/solve_mva_policy.py [--check] [--horizon N] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from rarepipe.stages.control.policy import (  # noqa: E402
    ALL_OF, BLOCKED, BRANCH, COMPONENT_DISCOVERY, Constraints, Edge, FRONTIER, GOAL, IMPOSSIBLE,
    KnowledgeState, MEASUREMENT, Node, PolicyGraph, STATE, TERMINAL, UNSAFE, Action, Arm,
    seed_actuators, solve_policy,
)
from rarepipe.stages.control.policy.actions import DECLARED_CAMPAIGN  # noqa: E402

MAP = ROOT / "docs/control/MVA_CONTINGENT_ROUTE_MAP.yaml"
OUT = ROOT / "docs/control/MVA_ROBUST_POLICY.md"

# How MVA's terminal vocabulary maps onto the five roles the mathematics distinguishes. Declared in
# full, so that a terminal kind added to the map fails loudly here instead of defaulting to
# something convenient.
TERMINAL_ROLES = {
    "UNSAFE": UNSAFE,
    "GOVERNANCE_BLOCKED": BLOCKED,
    "PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE": IMPOSSIBLE,
    "BOUNDED_FRONTIER": FRONTIER,
    "DECLARED_SCIENTIFIC_FRONTIER": FRONTIER,
    "SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED": FRONTIER,
    "CONTEXT_TRANSFER_REQUIRED": FRONTIER,
    "FUNCTIONAL_TARGET_REACHED": GOAL,
    "ORGANISM_TARGET_REACHED_IN_MODEL": GOAL,
}

# What this run treats as available. Every declared campaign needs a human cell model and nothing
# more; tissue and organism models, and anything needing an absent governance boundary, are not
# available, and the branches behind them are reported as unavailable actions with their reason
# rather than quietly dropped.
DEFAULT_AVAILABLE = ("CELL_MODEL",)


class AdapterError(ValueError):
    """The map no longer matches what this adapter was written against. Never worked around."""


def load() -> dict:
    return yaml.safe_load(MAP.read_text())


def digest() -> str:
    """The frozen map's content digest, computed from the file rather than written by hand."""
    return "sha256:" + hashlib.sha256(MAP.read_bytes()).hexdigest()


# ---------------------------------------------------------------- non-informative outcomes


def non_informative_outcomes(d: dict) -> dict[str, tuple[str, ...]]:
    """Outcomes that record an invalid run rather than a result, derived and then verified.

    The signal is the destination, not the outcome's name: every one of these lands on a terminal
    the map declares as a repeat condition — "repeat under a valid condition", "the failed validity
    gate is named and the condition repeated". Nineteen are named ``insufficient`` and one
    ``confounded_invalid``, so matching on the name would have missed one.

    The derivation is then checked for totality: every repeat terminal must be reached, and only by
    such an outcome. If the map grows a repeat terminal nobody routes to, or routes to one by an
    outcome that *is* a finding, this raises rather than guessing.
    """
    nodes = {n["id"]: n for n in d["nodes"]}
    repeat_terminals = {
        n["id"] for n in d["nodes"]
        if n["kind"] == "terminal" and n["id"].endswith("_REPEAT")
    }
    found: dict[str, list[str]] = {}
    reached: set[str] = set()
    for node in d["nodes"]:
        for name, target in (node.get("outcomes") or {}).items():
            if target in repeat_terminals:
                found.setdefault(node["id"], []).append(name)
                reached.add(target)

    if orphans := sorted(repeat_terminals - reached):
        raise AdapterError(
            f"repeat terminals that no outcome reaches: {', '.join(orphans)}. The invalid-run "
            f"derivation is no longer total; classify them explicitly before solving.")
    for terminal in sorted(repeat_terminals):
        kind = nodes[terminal].get("terminal")
        if TERMINAL_ROLES.get(kind) != FRONTIER:
            raise AdapterError(
                f"{terminal} is a repeat condition but its kind {kind!r} is not a frontier; "
                f"an invalid run must not be classified as a finding.")
    return {branch: tuple(sorted(names)) for branch, names in sorted(found.items())}


# ---------------------------------------------------------------- graph


def build_graph(d: dict, available=DEFAULT_AVAILABLE) -> PolicyGraph:
    invalid = non_informative_outcomes(d)
    kinds = {"state": STATE, "branch": BRANCH, "all_of": ALL_OF, "terminal": TERMINAL}
    nodes: list[Node] = []
    for raw in d["nodes"]:
        kind = kinds.get(raw["kind"])
        if kind is None:
            raise AdapterError(f"{raw['id']}: unknown node kind {raw['kind']!r}")
        role = None
        closes = None
        if kind == TERMINAL:
            declared = raw.get("terminal")
            role = TERMINAL_ROLES.get(declared)
            if role is None:
                raise AdapterError(
                    f"{raw['id']}: terminal kind {declared!r} has no declared role. Add it to "
                    f"TERMINAL_ROLES deliberately; defaulting would decide a safety question.")
            if raw.get("closes"):
                closes = (str(raw["closes"]), str(raw.get("closes_for", "")))
        nodes.append(Node(
            id=raw["id"], kind=kind, label=str(raw.get("label", "")),
            outcomes=tuple((raw.get("outcomes") or {}).items()),
            requires=raw.get("requires"),
            resolves_by=raw.get("resolves_by") or MEASUREMENT,
            members=tuple(raw.get("of") or ()),
            role=role, closes=closes,
            non_informative=invalid.get(raw["id"], ()),
        ))
    edges = tuple(
        Edge(source=e["from"], target=e["to"], label=str(e.get("label", "")),
             reentry=bool(e.get("reentry")))
        for e in d["edges"]
    )
    return PolicyGraph.build(nodes=nodes, edges=edges, root="S0_CASE",
                             goal=d["target"]["id"], available_requirements=available)


# ---------------------------------------------------------------- campaigns and actuators


UNPROMOTABLE = "nothing"


def _annotation(raw, field: str) -> tuple[frozenset[str], str | None]:
    """Read a provenance-wrapped annotation: ``{value: [...], basis: DECLARED|DERIVED}``.

    Returns the empty set when absent, so a missing annotation makes its Δ component unavailable
    rather than zero. A value without a basis is refused: an annotation whose provenance nobody
    recorded is indistinguishable from a guess.
    """
    entry = (raw or {}).get(field)
    if entry is None:
        return frozenset(), None
    if not isinstance(entry, dict) or "value" not in entry:
        raise AdapterError(f"{field} must be a mapping with `value` and `basis`, got {entry!r}")
    basis = entry.get("basis")
    if basis not in ("DECLARED", "DERIVED"):
        raise AdapterError(f"{field}: basis must be DECLARED or DERIVED, got {basis!r}")
    return frozenset(entry["value"] or ()), basis


def node_families(d: dict) -> dict[str, frozenset[str]]:
    """``{node: {family, ...}}`` from each node's ``analysis.family_membership``.

    Set-valued, because a node shared between two strategies is the normal case. Analysis metadata
    only: it reaches the guaranteed-progress vector and nothing else, and ``build_graph`` never
    looks at it, so no annotation can move what is reachable.
    """
    declared = set(d.get("families") or {})
    out: dict[str, frozenset[str]] = {}
    for raw in d["nodes"]:
        families, _ = _annotation(raw.get("analysis"), "family_membership")
        if not families:
            continue
        if unknown := sorted(families - declared):
            raise AdapterError(
                f"{raw['id']}: family_membership names undeclared families {unknown}")
        out[raw["id"]] = families
    return out


def hypothesis_discriminators(d: dict) -> dict[str, frozenset[str]]:
    """``{hypothesis: {branch, ...}}`` from ``discriminated_by`` — never from ``related_branches``.

    The two are different claims. ``related_branches`` says what a hypothesis is *about*;
    ``discriminated_by`` says what would *settle* it. A hypothesis about three branches is not
    settled by resolving those three, and letting relatedness stand in for discrimination would
    report a hypothesis eliminated by experiments that cannot speak to it.

    A hypothesis that declares itself unpromotable is excluded whatever it carries: if nothing can
    promote it, nothing can eliminate it either, and counting it as progress would be a fiction.
    """
    branches = {n["id"] for n in d["nodes"] if n["kind"] == "branch"}
    out: dict[str, frozenset[str]] = {}
    for group in ("hypotheses", "latent_variable_hypotheses"):
        for raw in d.get(group) or []:
            discriminators, basis = _annotation(raw, "discriminated_by")
            if not discriminators:
                continue
            if basis != "DECLARED":
                raise AdapterError(
                    f"{raw['id']}: discriminated_by must be DECLARED — which experiments settle a "
                    f"hypothesis is not derivable from the graph")
            if unknown := sorted(discriminators - branches):
                raise AdapterError(f"{raw['id']}: discriminated_by names unknown branches {unknown}")
            promote = str(raw.get("what_would_promote_it")
                          or raw.get("promotion_requires") or "").strip().lower()
            if promote.startswith(UNPROMOTABLE):
                raise AdapterError(
                    f"{raw['id']} declares that nothing would promote it, yet names branches that "
                    f"would settle it. One of the two is wrong, and the engine will not choose.")
            out[raw["id"]] = discriminators
    return out


def actuator_aliases(d: dict) -> dict[str, str]:
    """``{alias: canonical}`` from the declared registry, validated on the way through.

    Entity canonicalisation is a **preprocessing invariant**: it happens before anything computes,
    so no downstream result can depend on which spelling a reference happened to use. The failure
    it prevents is specific — a control variable closes only when every one of its actuators has
    failed conclusively, so an actuator present twice under two names is an arm nothing can ever
    close, and the variable is then uncloseable too.

    Aliases are DECLARED only. Inferring them from spelling would risk merging two genuinely
    different regimes, which is the one mistake here that destroys information rather than just
    duplicating it.
    """
    canonical: dict[str, str] = {}
    problems: list[str] = []
    for entry in d.get("actuators") or []:
        target = entry.get("id")
        if not target:
            problems.append("an actuator registry entry has no id")
            continue
        if entry.get("basis") != "DECLARED":
            problems.append(f"{target}: an alias set must be DECLARED, not "
                            f"{entry.get('basis')!r} — identity is never inferred from spelling")
        canonical[target] = target
        for alias in entry.get("aliases") or []:
            if alias in canonical and canonical[alias] != target:
                problems.append(f"{alias!r} is claimed by both {canonical[alias]} and {target}")
            canonical[alias] = target
    if problems:
        raise AdapterError("; ".join(problems))
    return canonical


def canonical_actuator(name: str, aliases: dict[str, str]) -> str:
    return aliases.get(name, name)


def build_campaigns(d: dict) -> tuple[Action, ...]:
    aliases = actuator_aliases(d)
    out: list[Action] = []
    for raw in d.get("campaigns") or []:
        resolves = raw["resolves"] if isinstance(raw["resolves"], list) else [raw["resolves"]]
        arms = tuple(
            Arm(id=arm_id, control_variable=spec["control_variable"],
                actuator=canonical_actuator(spec["actuator"], aliases),
                engagement_readout=str(spec.get("engagement_readout", "")))
            for arm_id, spec in sorted((raw.get("arms") or {}).items())
        )
        requires = raw.get("requires")
        out.append(Action(
            id=raw["id"], kind=DECLARED_CAMPAIGN, resolves=tuple(resolves),
            requires=(requires,) if requires else (), arms=arms,
            question=str(raw.get("question", "")),
        ))
    return tuple(out)


def actuator_registry(d: dict, campaigns) -> dict[str, list[str]]:
    """Every actuator the map names per control variable, resolved to canonical identities.

    Both places the map names actuators feed this, and both are canonicalised, so the same
    actuator written two ways collapses to one entry instead of surviving as a phantom arm that
    nothing can close.
    """
    aliases = actuator_aliases(d)
    registry: dict[str, set[str]] = {}
    for cv, spec in (d.get("control_variables") or {}).items():
        named = list(spec.get("actuators_tried") or ()) + \
            list(spec.get("actuators_identified_not_tried") or ())
        registry.setdefault(cv, set()).update(
            canonical_actuator(name, aliases) for name in named)
    for action in campaigns:
        for arm in action.arms:
            registry.setdefault(arm.control_variable, set()).add(
                canonical_actuator(arm.actuator, aliases))
    return {cv: sorted(actuators) for cv, actuators in sorted(registry.items())}


# ---------------------------------------------------------------- consistency findings


def consistency_findings(d: dict, campaigns) -> list[dict]:
    """Things wrong with the map that only showed up once something computed on it.

    Reported, never repaired. A solver that corrects its own input has stopped being checkable, and
    two of these are claims only the case's authors can make.
    """
    findings: list[dict] = []

    # 1. The same physical actuator under two names. Paclitaxel and taxol are one drug, so the
    #    registry carries five entries for a control variable with four actuators — and a control
    #    variable whose closure requires closing a duplicate can never be correctly closed.
    aliases = actuator_aliases(d)
    declared = {
        cv: {canonical_actuator(name, aliases)
             for name in (list(spec.get("actuators_tried") or ())
                          + list(spec.get("actuators_identified_not_tried") or ()))}
        for cv, spec in (d.get("control_variables") or {}).items()
    }
    for action in campaigns:
        for arm in action.arms:
            known = declared.get(arm.control_variable, set())
            resolved = canonical_actuator(arm.actuator, aliases)
            if known and resolved not in known:
                findings.append({
                    "kind": "ACTUATOR_NAME_NOT_IN_CONTROL_VARIABLE_REGISTRY",
                    "campaign": action.id,
                    "arm": arm.id,
                    "arm_actuator": arm.actuator,
                    "resolved_to": resolved,
                    "control_variable": arm.control_variable,
                    "registry": sorted(known),
                    "consequence": (
                        "The actuator registry gains an entry that the control variable's own list "
                        "does not have, so closing every listed actuator still leaves this one "
                        "open and the control variable can never be reported closed."),
                    "resolution": (
                        "Only the case's authors may declare two names the same actuator. This "
                        "adapter will not alias them."),
                })

    # 2. A control variable the map treats as closable by a single actuator's failure. The map's own
    #    closure vocabulary includes CONTROL_VARIABLE, and no terminal uses it — which is correct,
    #    and worth asserting so a future edit cannot quietly introduce one.
    scopes = [n.get("closes") for n in d["nodes"] if n.get("closes")]
    if "CONTROL_VARIABLE" in scopes:
        findings.append({
            "kind": "TERMINAL_CLOSES_A_WHOLE_CONTROL_VARIABLE",
            "consequence": (
                "A single terminal closing an entire control variable contradicts the map's own "
                "arm-level rule: one unsafe actuator is not an unsafe control variable."),
            "resolution": "Narrow the terminal's scope to ACTUATOR, or justify the wider closure.",
        })

    # 3. Progress components with no data behind them. Not a defect, but the reason two of the five
    #    declared measures come back unavailable, and the schema addition that would fix it.
    findings.append({
        "kind": "PROGRESS_COMPONENTS_WITHOUT_DATA",
        "components": ["hypotheses_eliminated", "families_resolved"],
        "consequence": (
            "Guaranteed-progress ranking is computed on three of its five declared components. "
            "The other two are reported unavailable rather than assumed zero, and begin "
            "computing as soon as the annotations are declared."),
        "resolution": (
            "The schema and the engine's consumption of it are in place; the values are the "
            "authors' to declare. hypotheses_eliminated reads `discriminated_by` on a hypothesis "
            "(DECLARED only, and never `related_branches`, which records what a hypothesis is "
            "about rather than what settles it); the four latent-variable hypotheses describe "
            "their smallest discriminating experiment in prose and are the ones to supply. "
            "families_resolved reads `analysis.family_membership` on a node, set-valued with a "
            "DECLARED or DERIVED basis; membership is not derivable here, because there are no "
            "family entry nodes and the only remaining signal is identifier spelling, which this "
            "repository has already been wrong about once."),
    })
    return findings


# ---------------------------------------------------------------- solve


def solve(d: dict, horizon: int = 6, *, available=DEFAULT_AVAILABLE,
          include_non_informative: bool = False, max_states: int = 3_000_000):
    graph = build_graph(d, available)
    campaigns = build_campaigns(d)
    registry = actuator_registry(d, campaigns)
    state = KnowledgeState.initial(seed_actuators(registry))
    constraints = Constraints(include_non_informative=include_non_informative,
                              max_states=max_states,
                              hypothesis_discriminators=hypothesis_discriminators(d),
                              node_families=node_families(d))
    result = solve_policy(graph, state, target=graph.goal, constraints=constraints,
                          horizon=horizon, campaigns=campaigns, model_id=d.get("case_ref", ""))
    return graph, campaigns, registry, result


COMPARISON_BUDGET = 300_000


def report(d: dict, horizon: int = 6) -> dict:
    """Both answers — invalid runs excluded and included — plus the findings.

    The comparison run quantifies over assay-validity failures, which multiplies the joint
    outcome space and makes it far more expensive than the primary solve. It is given a smaller
    budget at the *same* horizon rather than a shallower horizon: a different horizon would be a
    different question, whereas a smaller budget is the same question possibly left less
    settled — and the report states which of the two it got.
    """
    graph, campaigns, registry, primary = solve(d, horizon)
    _, _, _, strict = solve(d, horizon, include_non_informative=True,
                            max_states=COMPARISON_BUDGET)
    return {
        "map": {
            "path": str(MAP.relative_to(ROOT)),
            "map_version": d.get("map_version"),
            "case_ref": d.get("case_ref"),
            "digest": digest(),
        },
        "available_requirements": list(DEFAULT_AVAILABLE),
        "actuator_registry": registry,
        "consistency_findings": consistency_findings(d, campaigns),
        "invalid_runs_excluded": primary.describe(),
        "invalid_runs_included": {
            "robust_reachable": strict.robust_reachable.describe(),
            "no_robust_policy_within": strict.no_robust_policy_within,
            "budget": COMPARISON_BUDGET,
            "budget_exhausted": strict.budget_exhausted,
            "note": ("The same question, at the same horizon, with assay-validity failures "
                     "quantified over. Reported so that the modelling choice is a number rather "
                     "than an argument. Run under a smaller budget, so a less settled verdict "
                     "here means the search stopped earlier, not that the answer differs."),
        },
    }


# ---------------------------------------------------------------- rendering


def _verdict(value) -> str:
    return value if isinstance(value, str) else f"{value['value']} ({value['reason']})"


def render(data: dict) -> str:
    """The committed document. Deterministic: no timestamps, no run identifiers, no ordering by set."""
    answer = data["invalid_runs_excluded"]
    certificates = answer["failure_certificates"]
    space = answer["action_space"]
    out: list[str] = []
    A = out.append

    A("# MVA_001 — robust contingent policy")
    A("")
    A("Generated by `tools/control/solve_mva_policy.py` from the frozen contingent route map.")
    A("Regenerating it must be a no-op, or this document has drifted from the computation.")
    A("")
    A(f"- map: `{data['map']['path']}` version `{data['map']['map_version']}`")
    A(f"- digest: `{data['map']['digest']}`")
    A(f"- capabilities treated as available: {', '.join(f'`{r}`' for r in data['available_requirements'])}")
    A("")
    A("## What this adds")
    A("")
    A("The route map computes two reachability claims and reports the third as `NOT_ESTABLISHED`,")
    A("because it searches no policy space. This document computes the third.")
    A("")
    A("| claim | meaning | verdict |")
    A("|---|---|---|")
    A(f"| `CONDITIONAL_REACHABLE` | some assignment of results establishes the target "
      f"| {'YES' if answer['conditional_reachable'] else 'NO'} |")
    A(f"| `SINGLE_OUTCOME_RESILIENT` | no *single* result closes it "
      f"| {'YES' if answer['single_outcome_resilient'] else 'NO'} |")
    A(f"| `ROBUST_REACHABLE` | a policy that wins under **every** admissible combination "
      f"| **{_verdict(answer['robust_reachable'])}** |")
    A("")
    if answer.get("no_robust_policy_within") is not None:
        A(f"**No robust policy exists using {answer['no_robust_policy_within']} campaigns or "
          f"fewer.** That space was searched exhaustively, so it is a result rather than a")
        A("failure to find one. Whether a deeper policy exists is a separate question, and the")
        A("verdict above says which of the two answers the search was able to reach.")
        A("")
    A("`ROBUST_REACHABLE` is three-valued on purpose. `NOT_ESTABLISHED` carries a reason —")
    A("`HORIZON` means no policy was found within the campaign budget, `BUDGET` means the search")
    A("stopped before it could tell. Neither is `FALSE`, and reporting either as `FALSE` would")
    A("repeat the overstatement that got single-outcome resilience renamed.")
    A("")

    A("## Tied minimal routes")
    A("")
    A("Every smallest set of unresolved branches that would establish the target — all of them.")
    A("")
    tied = answer["tied_minimal_branch_sets"]
    for branch_set in tied["optimal_sets"]:
        A(f"- {', '.join(f'`{b}`' for b in branch_set)}")
    A("")
    A(f"Reported in full: **{tied['count']}** optimal set(s), "
      f"`truncated: {str(tied['truncated']).lower()}`.")
    A("The mathematical layer never drops a tied optimum. Only a renderer may show fewer, and then")
    A("it reports its own `display_truncated` rather than letting the maths say fewer exist.")
    A("")
    if tied["count"] > 1:
        A(f"There are **{tied['count']} tied minimal routes**, not one.")
        A("Naming any single one of them as \"the\" shortest route would be the specific ambiguity")
        A("this computation exists to remove.")
        A("")

    A("## Action space")
    A("")
    A(f"- declared campaigns: **{space['declared_campaigns']}**")
    A(f"- undeclared resolvers: **{space['undeclared_resolvers']}** — a branch resolvable in")
    A("  principle with no experiment specified for it. Tagged `UNDECLARED_CAMPAIGN`: a")
    A("  recommendation resting on one of these is a recommendation to go and design an experiment.")
    A(f"- unavailable: **{len(space['unavailable'])}**, listed with the capability each needs.")
    A("")
    if space["unavailable"]:
        A("| branch | requires | why |")
        A("|---|---|---|")
        for entry in space["unavailable"]:
            A(f"| `{entry['branch']}` | `{entry['requires']}` | {entry['reason']} |")
        A("")

    A("## The answer")
    A("")
    if answer["robust_reachable"] == "TRUE" or (
            isinstance(answer["robust_reachable"], dict)
            and answer["robust_reachable"]["value"] == "TRUE"):
        A(f"A robust policy exists at horizon **{answer['minimal_robust_horizon']}**, with a")
        A(f"worst-case depth of **{answer['worst_case_depth']}** campaigns.")
        A("")
        A("Optimal first actions, all tied:")
        A("")
        for action in answer["recommended_actions"]:
            A(f"- `{action}`")
    else:
        A("No robust policy was established, so the engine reports the experiment whose **worst**")
        A("admissible outcome still guarantees the most progress. This is a discovery-mode answer:")
        A("it is the best next question, not a route to the target.")
        A("")
        for action in answer["recommended_actions"]:
            A(f"- `{action}`")
        A("")
        A("**On the agreement with the route map's own appendix.** Where this selection coincides")
        A("with the priority a human reading of the map arrived at, that is *convergent internal")
        A("validation* — two different methods over the same formal model reaching the same answer —")
        A("and not a benchmark result. It says the model and the computation are coherent with each")
        A("other. It says nothing about whether this engine beats a language model, with or without")
        A("generic tools, because no such comparison has been run. The competitive question needs")
        A("the baselines and an oracle, and those are a separate deliverable.")
    A("")
    A(f"Ranking compared on: {', '.join(f'`{c}`' for c in answer['ranking']['compared_on'])}.")
    if answer["ranking"].get("skipped"):
        A("")
        A("Components **not** compared, because no data in the map supports them:")
        A("")
        for name in answer["ranking"]["skipped"]:
            A(f"- `{name}` — {answer['ranking']['skipped_reason'][name]}")
    A("")

    A("## Failure certificates")
    A("")
    A("### Minimal closing combinations")
    A("")
    A("Sets of results that leave the target structurally unreachable, smallest first.")
    A("")
    combos = certificates.get("minimal_closing_combinations") or []
    if combos:
        for combo in combos:
            parts = [f"`{entry['branch']}`=`{entry['outcome']}`" for entry in combo]
            A(f"- {' + '.join(parts)}")
    else:
        A("None at the searched size.")
    A("")
    A(certificates.get("note", ""))
    A("")
    cuts = certificates.get("cut_set_analysis")
    if cuts:
        A("### Minimal cut sets and minimal success sets")
        A("")
        A("The two questions a fault tree asks, asked of a decision graph: which minimal")
        A("combinations of future results destroy every route to the target, and which minimal")
        A(f"combinations establish it. Scope: {cuts['scope']}.")
        A("")
        A("| kind | combination |")
        A("|---|---|")
        for combo in cuts["minimal_target_cut_sets"]:
            members = " + ".join(f"`{c['branch']}`=`{c['outcome']}`" for c in combo)
            A(f"| cut | {members} |")
        for combo in cuts["minimal_target_success_sets"]:
            members = " + ".join(f"`{c['branch']}`=`{c['outcome']}`" for c in combo)
            A(f"| success | {members} |")
        A("")
        for member in cuts["common_cut_members"]:
            A(f"- `{member['branch']}`=`{member['outcome']}` appears in **{member['frequency']}** "
              f"of the minimal cut sets found — {member['scope']}.")
        for member in cuts["common_success_members"]:
            A(f"- `{member['branch']}`=`{member['outcome']}` appears in **{member['frequency']}** "
              f"of the minimal success sets found — {member['scope']}.")
        A("")
        A(cuts["note"])
        A("")
    if certificates.get("robust_subset", {}).get("goal_is_conjunction"):
        A("### Which conjuncts of the target are robustly reachable")
        A("")
        A("| conjunct | verdict |")
        A("|---|---|")
        for member, value in sorted(certificates["robust_subset"]["conjuncts"].items()):
            A(f"| `{member}` | {value} |")
        A("")

    A("## Unsafe routes")
    A("")
    A("Every result in the map that ends on an `UNSAFE` terminal. Nothing in a returned policy")
    A("routes through one, which is what makes \"an unsafe branch was offered as acceptable\" a")
    A("measurable error rather than a judgement call.")
    A("")
    A("| branch | outcome | terminal |")
    A("|---|---|---|")
    for route in answer["unsafe_routes"]:
        A(f"| `{route['branch']}` | `{route['outcome']}` | `{route['terminal']}` |")
    A("")

    A("## Invalid runs are excluded from the quantifier")
    A("")
    A(f"{len(answer['excluded_non_informative_outcomes'])} of the outcomes reachable in this")
    A("target's action space record an invalid run rather")
    A("than a result about biology — an unengaged target, a voided validity gate, a condition to be")
    A("repeated. They are excluded from the ∀ quantifier, because a run that did not happen")
    A("validly tells us nothing, and quantifying over it would make every policy fail robustness on")
    A("the grounds that any assay can break.")
    A("")
    A(f"- with them excluded (reported above): **{_verdict(answer['robust_reachable'])}**")
    comparison = data["invalid_runs_included"]
    A(f"- with them included: **{_verdict(comparison['robust_reachable'])}**"
      f" (budget {comparison['budget']:,}"
      f"{', exhausted' if comparison['budget_exhausted'] else ''})")
    A("")
    A("Both are given so that the modelling choice is a number rather than an argument.")
    A("")

    A("## Map consistency findings")
    A("")
    A("Reported, never repaired. A solver that corrects its own input has stopped being checkable.")
    A("")
    for finding in data["consistency_findings"]:
        A(f"### `{finding['kind']}`")
        A("")
        for key, value in finding.items():
            if key == "kind":
                continue
            rendered = ", ".join(f"`{v}`" for v in value) if isinstance(value, list) else value
            A(f"- **{key}**: {rendered}")
        A("")

    A("## What this does not establish")
    A("")
    A("- Nothing about this child. The target is a cell-level functional state in a model system.")
    A("- No probability. None is computed, and none is available.")
    A("- No claim that an undeclared resolver is a runnable experiment.")
    A("- Reaching the cell-level target says nothing about the organism-level target, which keeps")
    A("  its own gates and is not solved here.")
    A("")
    A("## Trace")
    A("")
    A(f"- states considered: {answer['trace']['states_considered']}")
    A(f"- budget exhausted: {answer['trace']['budget_exhausted']}")
    A(f"- frontier truncated at: {len(answer['trace']['frontier_truncated_at'])} node(s)")
    A(f"- constraints: `{answer['trace']['constraints']}`")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="regenerate and compare the committed document")
    ap.add_argument("--horizon", type=int, default=6)
    ap.add_argument("--json", action="store_true", help="print the machine-readable answer")
    args = ap.parse_args()

    document = load()
    data = report(document, horizon=args.horizon)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    text = render(data)
    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run "
                  f"uv run python tools/control/solve_mva_policy.py")
            return 1
        print("ROBUST_POLICY current")
        return 0
    OUT.write_text(text)
    answer = data["invalid_runs_excluded"]
    print("ROBUST_POLICY")
    print(f"  conditional_reachable  {answer['conditional_reachable']}")
    print(f"  robust_reachable       {_verdict(answer['robust_reachable'])}")
    print(f"  tied minimal routes    {answer['tied_minimal_branch_sets']['count']}")
    print(f"  recommended            {', '.join(answer['recommended_actions']) or 'none'}")
    print(f"  states considered      {answer['trace']['states_considered']}")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
