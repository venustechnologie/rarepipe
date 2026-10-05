#!/usr/bin/env python3
"""Validate the MVA contingent route map and render it. Case data in, document out.

No new generic machinery: the map is a YAML artifact beside the other MVA case data, and this script
checks its integrity and computes what the PRD asks of every route. The one computation that matters is
`required()`: the SET of unresolved branch nodes a route still needs, unioned at AND nodes and
minimised at OR nodes. Sets rather than counts, because two routes can share an experiment and summing
would invent work that does not exist. No probabilities are computed, because none is grounded.

    uv run python tools/control/compile_route_map.py [--check]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "docs/control/MVA_CONTINGENT_ROUTE_MAP.yaml"
OUT = ROOT / "docs/control/MVA_CONTINGENT_ROUTE_MAP.md"


def load() -> dict:
    return yaml.safe_load(MAP.read_text())


def goal(d: dict) -> str:
    """The cell-level goal, read from the map rather than hard-coded.

    It was `TARGET` until reasoning was continued past the cell, and a literal in the tool would have
    quietly made the rename a lie.
    """
    return d["target"]["id"]


def ultimate(d: dict) -> str | None:
    return (d.get("ultimate_target") or {}).get("id")


def validate(d: dict) -> list[str]:
    """Integrity, not plausibility. A map that lies about its own shape proves nothing."""
    problems: list[str] = []
    nodes = {n["id"]: n for n in d["nodes"]}
    if len(nodes) != len(d["nodes"]):
        problems.append("duplicate node id")
    labels, terminals = set(d["label_vocabulary"]), set(d["terminal_vocabulary"])

    for n in d["nodes"]:
        kind = n.get("kind")
        if kind not in ("state", "branch", "all_of", "terminal"):
            problems.append(f"{n['id']}: unknown kind {kind!r}")
        if kind == "terminal":
            if n.get("terminal") not in terminals:
                problems.append(f"{n['id']}: terminal {n.get('terminal')!r} not in the closed vocabulary")
            if n.get("terminal") == "UNKNOWN":
                problems.append(f"{n['id']}: UNKNOWN is never a terminal state")
        if kind == "branch":
            outcomes = n.get("outcomes") or {}
            if len(outcomes) < 2:
                problems.append(f"{n['id']}: a branch node must enumerate at least two admissible outcomes")
            if not n.get("why_unresolved"):
                problems.append(f"{n['id']}: a branch node must say why it is unresolved")
            if n.get("requires") not in set(d["requires_vocabulary"]):
                problems.append(f"{n['id']}: requires {n.get('requires')!r} not in the closed "
                                "vocabulary — a branch must say whether it needs only a cell model, a "
                                "tissue or organism model, or governance that does not exist")
            if n.get("resolves_by") not in set(d["resolves_by_vocabulary"]):
                problems.append(f"{n['id']}: resolves_by {n.get('resolves_by')!r} not in the closed "
                                "vocabulary — a branch must declare whether it is a measurement or a "
                                "component discovery, because counting them as one unit misleads")
            for name, target in outcomes.items():
                if target not in nodes:
                    problems.append(f"{n['id']}: outcome {name!r} points at unknown node {target!r}")
        if kind == "all_of":
            for member in n.get("of") or []:
                if member not in nodes:
                    problems.append(f"{n['id']}: AND member {member!r} does not exist")
            if len(n.get("of") or []) < 2:
                problems.append(f"{n['id']}: an AND node needs at least two members")

    for e in d["edges"]:
        for end in ("from", "to"):
            if e[end] not in nodes:
                problems.append(f"edge {e['from']}->{e['to']}: {end} node does not exist")
        if e["label"] not in labels:
            problems.append(f"edge {e['from']}->{e['to']}: label {e['label']!r} not in the closed vocabulary")

    # Every branch outcome must be reachable as an edge or recorded in `outcomes`; and every
    # non-terminal node must have somewhere to go, which is the PRD's "unknowns are never terminal".
    out_edges: dict[str, list[dict]] = {}
    for e in d["edges"]:
        out_edges.setdefault(e["from"], []).append(e)
    for n in d["nodes"]:
        if n["kind"] in ("state", "all_of") and not out_edges.get(n["id"]):
            problems.append(f"{n['id']}: a {n['kind']} node with no outgoing transition is a dead end, not a terminal")

    # ---- invariant: an observation cannot create an intervention state ----
    roles = set(d.get("branch_role_vocabulary") or [])
    classes = set(d.get("state_class_vocabulary") or [])
    for n in d["nodes"]:
        if n["kind"] == "branch":
            if n.get("branch_role") not in roles:
                problems.append(f"{n['id']}: branch_role {n.get('branch_role')!r} not in the closed "
                                "vocabulary — a branch must say whether it intervenes or observes")
                continue
            if n["branch_role"] != "OBSERVATION":
                continue
            for name, target in (n.get("outcomes") or {}).items():
                t = nodes.get(target) or {}
                cls = t.get("state_class", "SYSTEM")
                if t.get("kind") == "state" and cls != "KNOWLEDGE":
                    problems.append(
                        f"{n['id']} is an OBSERVATION and outcome {name!r} lands on {target} "
                        f"(state_class {cls}). Observing the system cannot improve it; an observation's "
                        "outcomes may only reach KNOWLEDGE states or terminals")
        if n["kind"] == "state" and n.get("state_class", "SYSTEM") not in classes:
            problems.append(f"{n['id']}: state_class {n.get('state_class')!r} not in the closed vocabulary")

    # ---- invariant: a mechanistic intermediate cannot imply a terminal endpoint ----
    for e in d["edges"]:
        src, dst = nodes.get(e["from"]) or {}, nodes.get(e["to"]) or {}
        if src.get("state_class") == "MECHANISTIC_INTERMEDIATE" and \
                dst.get("state_class") == "TERMINAL_ENDPOINT" and not e.get("establishing_measurement"):
            problems.append(
                f"edge {e['from']}->{e['to']}: a mechanistic intermediate may not imply the terminal "
                "endpoint without an edge that names the establishing measurement. Improving alignment "
                "is not lowering missegregation until missegregation is measured")
    for n in d["nodes"]:
        if n["kind"] != "branch":
            continue
        for name, target in (n.get("outcomes") or {}).items():
            src_cls = None
            for e in d["edges"]:
                if e["to"] == n["id"]:
                    src_cls = (nodes.get(e["from"]) or {}).get("state_class")
                    break
            dst = nodes.get(target) or {}
            if src_cls == "MECHANISTIC_INTERMEDIATE" and dst.get("state_class") == "TERMINAL_ENDPOINT" \
                    and not n.get("establishes"):
                problems.append(
                    f"{n['id']} carries a mechanistic intermediate to the terminal endpoint via "
                    f"{name!r} without declaring what it establishes")

    # ---- invariant: a terminal endpoint may not backfill a canonical mechanism ----
    # The forward direction was already enforced. The reverse is the same error read backwards:
    # reaching the endpoint says nothing about which mechanism delivered it, least of all in a state
    # several candidates converge on.
    for e in d["edges"]:
        src, dst = nodes.get(e["from"]) or {}, nodes.get(e["to"]) or {}
        if src.get("state_class") == "TERMINAL_ENDPOINT" and \
                dst.get("state_class") == "MECHANISTIC_INTERMEDIATE" and \
                not e.get("establishing_measurement"):
            problems.append(
                f"edge {e['from']}->{e['to']}: endpoint achievement may not backfill a canonical "
                "mechanism. Lowering missegregation does not establish that alignment was supplied, "
                "and this state is reached by routes that never measure it")

    # ---- invariant: a shared retry node must preserve control-variable identity ----
    for n in d["nodes"]:
        if n["kind"] != "branch" or not n.get("preserves_variable_identity"):
            continue
        mapping = n.get("actuator_retry_map") or {}
        if not mapping:
            problems.append(f"{n['id']}: claims to preserve variable identity with no retry map")
            continue
        for cv, outcome in mapping.items():
            if cv not in (d.get("control_variables") or {}):
                problems.append(f"{n['id']}: retry map names unknown control variable {cv}")
            if outcome not in (n.get("outcomes") or {}):
                problems.append(f"{n['id']}: retry map points at missing outcome {outcome!r}")
        incoming = [e["from"] for e in d["edges"] if e["to"] == n["id"]]
        for src in incoming:
            cv = (nodes.get(src) or {}).get("closes_for")
            if cv and cv not in mapping:
                problems.append(
                    f"{n['id']}: {src} closes an actuator of {cv}, which the retry map does not "
                    "cover, so a working alternate actuator would resolve into the wrong biology")

    # ---- invariant: positive efficacy is neutral with respect to independence ----
    for n in d["nodes"]:
        if n["kind"] != "branch":
            continue
        for name, target in (n.get("outcomes") or {}).items():
            if not (nodes.get(target) or {}).get("dependency_established"):
                continue
            if not n.get("dependency_tested"):
                problems.append(
                    f"{n['id']} outcome {name!r} reaches {target}, which asserts dependency was "
                    "established, but the branch does not declare dependency_tested. Positive efficacy "
                    "alone says nothing about independence")
            elif name not in (n.get("dependency_outcomes") or []):
                problems.append(
                    f"{n['id']} outcome {name!r} reaches {target}, which asserts dependency was "
                    f"established, but {name!r} is not one of the branch's dependency_outcomes. The "
                    "branch testing dependency is not enough: the particular result has to be the one "
                    "that encodes the dependency finding, or an efficacy result rides in on it")

    for c in (d.get("campaigns") or []):
        for name, mapping in (c.get("outcomes") or {}).items():
            for bid, outcome in mapping.items():
                if bid not in nodes or nodes[bid]["kind"] != "branch":
                    problems.append(f"campaign {c['id']} outcome {name}: {bid} is not a branch")
                elif outcome not in (nodes[bid].get("outcomes") or {}):
                    problems.append(f"campaign {c['id']} outcome {name}: {bid} has no outcome "
                                    f"{outcome!r}")
        if c.get("outcomes"):
            touched = {b for m in c["outcomes"].values() for b in m}
            missing = set(c["resolves"]) - touched
            if missing:
                problems.append(f"campaign {c['id']}: declares joint outcomes that never decide "
                                f"{sorted(missing)}, so a branch it claims to resolve is left open")
    # ---- firewall: a latent-variable hypothesis may not become part of the city ----
    node_ids = set(nodes)
    for h in (d.get("latent_variable_hypotheses") or []):
        if h.get("status") != "NOT_TRAVERSABLE":
            problems.append(f"{h['id']}: a latent-variable hypothesis must be NOT_TRAVERSABLE")
        if h["id"] in node_ids:
            problems.append(f"{h['id']} is a node, so it is traversable")
        if h.get("kind") not in ("STRUCTURAL_COMMONALITY", "BIOLOGICAL_LATENT_VARIABLE"):
            problems.append(f"{h['id']}: kind {h.get('kind')!r} is not one of the two allowed")
        if h.get("kind") != "BIOLOGICAL_LATENT_VARIABLE":
            continue
        # the rule that separates an explanation from a renaming
        if not h.get("new_predictions"):
            problems.append(f"{h['id']}: a biological latent variable must predict something that was "
                            "not used to construct it, or it is only a new name for the pattern")
        for field in ("neighbourhoods_explained", "why_one_variable_could_generate_all",
                      "existing_evidence", "evidence_against_or_incompatibilities",
                      "smallest_discriminating_experiment", "promotion_requires"):
            if not h.get(field):
                problems.append(f"{h['id']}: missing {field}")
        hoods = h.get("neighbourhoods_explained") or []
        if isinstance(hoods, list):
            unknown = [x for x in hoods if x.startswith("CV_") and x not in (d.get("control_variables") or {})]
            if unknown:
                problems.append(f"{h['id']}: names unknown control variables {unknown}")

    for g in (d.get("grounded_facts") or []):
        if not g.get("evidence") and not g.get("derivation"):
            problems.append(f"{g['id']}: a grounded fact needs either evidence or a stated derivation; "
                            "with neither it is an assertion wearing the word 'grounded'")
    problems += cycles(d, nodes, out_edges)
    return problems


def successors(d: dict, nid: str, nodes: dict, out_edges: dict, *, follow_reentry: bool) -> list[str]:
    node = nodes.get(nid)
    if node is None:
        return []      # a dangling reference is reported by validate(); it must not crash the walk
    if node["kind"] == "branch":
        return list((node.get("outcomes") or {}).values())
    return [e["to"] for e in out_edges.get(nid, []) if follow_reentry or not e.get("reentry")]


def cycles(d: dict, nodes: dict, out_edges: dict) -> list[str]:
    """Acyclic once deliberate re-entry edges are removed; a cycle anywhere else is a modelling error.

    Iterative rather than recursive: the recursive form blew Python's stack once the map grew past a
    hundred nodes, which is the wrong way for a validator to fail.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(nodes, WHITE)
    found: list[str] = []
    for root in nodes:
        if colour[root] != WHITE:
            continue
        stack: list[tuple[str, list[str]]] = [(root, [])]
        while stack:
            nid, path = stack.pop()
            if nid == "__pop__":
                colour[path[0]] = BLACK
                continue
            if colour.get(nid) == GREY:
                continue
            colour[nid] = GREY
            stack.append(("__pop__", [nid]))
            for nxt in successors(d, nid, nodes, out_edges, follow_reentry=False):
                if nxt not in nodes:
                    continue
                if colour.get(nxt) == GREY:
                    found.append(f"cycle through non-reentry edges: {' -> '.join(path + [nid, nxt])}")
                elif colour.get(nxt) == WHITE:
                    stack.append((nxt, path + [nid]))
    return sorted(set(found))


PARETO_CAP = 8      # candidate sets kept per node; bounds the cross-product at AND nodes


def _prune(sets: list[frozenset[str]]) -> list[frozenset[str]]:
    """Keep only the minimal sets: a set that contains another is never a better route."""
    out: list[frozenset[str]] = []
    for s in sorted(set(sets), key=lambda x: (len(x), sorted(x))):
        if not any(o <= s for o in out):
            out.append(s)
    return out[:PARETO_CAP]


def frontier(d: dict, *, known: set[str] | None = None, drop: str | None = None,
             decided: dict[str, str] | None = None) -> dict[str, list[frozenset[str]]]:
    """For each node, the minimal SETS of branch nodes that would establish it from the case state.

    Forward relaxation, because an AND node's members are preconditions to be established rather than
    waypoints with their own onward path — the backward form reports the target unreachable whenever a
    conjunct sits on the chain feeding it.

    A frontier of incomparable sets rather than one smallest set, because conjuncts share experiments:
    keeping only the per-node minimum can discard the set that makes a downstream union cheap, and then
    the reported distance is an overestimate. Sets, never counts, for the same reason — summing two
    routes that share an experiment invents work that does not exist. No probabilities are computed,
    because none is grounded.
    """
    nodes = {n["id"]: n for n in d["nodes"] if n["id"] != drop}
    known, decided = known or set(), decided or {}
    incoming: dict[str, list[tuple[str, bool]]] = {nid: [] for nid in nodes}
    for n in d["nodes"]:
        if n["id"] == drop or n["kind"] != "branch":
            continue
        outcomes = n.get("outcomes") or {}
        if n["id"] in decided:
            # A branch returns exactly one result. Its other outcomes are not merely uncosted, they
            # are unavailable — without this, a negative result never closes the family it rules out.
            outcomes = {k: v for k, v in outcomes.items() if k == decided[n["id"]]}
        # A decided branch has been run: restricting it to one outcome is not enough, it must also
        # stop counting as unresolved work, or "what remains after this result" keeps charging for
        # the experiment that produced the result.
        charge = n["id"] not in decided
        for target in outcomes.values():
            if target in nodes:
                incoming[target].append((n["id"], charge))
    for e in d["edges"]:
        if e["from"] not in nodes or e["to"] not in nodes or nodes[e["from"]]["kind"] == "branch":
            continue                                           # a branch leaves only by its outcomes
        incoming[e["to"]].append((e["from"], False))

    best: dict[str, list[frozenset[str]]] = {nid: [] for nid in nodes}
    for seed in ("S0_CASE", *known):
        if seed in best:
            best[seed] = [frozenset()]

    for _ in range(len(nodes) + 2):
        changed = False
        for nid, node in nodes.items():
            if nid == "S0_CASE" or nid in known:
                continue
            if node["kind"] == "all_of":
                combos: list[frozenset[str]] = [frozenset()]
                for member in node.get("of", []):
                    member_sets = best.get(member) or []
                    if not member_sets:
                        combos = []
                        break
                    combos = _prune([c | m for c in combos for m in member_sets])
                candidates = combos
            else:
                candidates = _prune([s | ({src} if is_branch else set())
                                     for src, is_branch in incoming[nid]
                                     for s in best.get(src) or []])
            if candidates != best[nid]:
                best[nid] = candidates
                changed = True
        if not changed:
            break
    return best


def cost(d: dict, *, known: set[str] | None = None, drop: str | None = None,
         decided: dict[str, str] | None = None) -> dict[str, frozenset[str] | None]:
    """The single cheapest set per node, read off the frontier. None means it cannot be established."""
    return {nid: (sets[0] if sets else None)
            for nid, sets in frontier(d, known=known, drop=drop, decided=decided).items()}


def required(d: dict) -> dict[str, frozenset[str] | None]:
    """Back-compatible view: what each node still needs, read from the forward computation."""
    return cost(d)


def dominators_for(d: dict, target: str) -> set[str]:
    """Branch nodes every route to `goal` must pass through, tested by deletion.

    Family-scoped, because with two families a globally unavoidable branch is rare while the branch
    that gates one whole family is the decision-relevant fact.
    """
    if cost(d).get(target) is None:
        return set()
    return {b["id"] for b in d["nodes"] if b["kind"] == "branch"
            and cost(d, drop=b["id"]).get(target) is None}


def dominators(d: dict) -> set[str]:
    """Branch nodes every route to the target must pass through: the unavoidable experiments.

    Tested by deletion — remove the branch and ask whether the target can still be established. That
    is the honest test and it needs no probability.
    """
    return dominators_for(d, goal(d))


def campaign_cover(d: dict, branches: frozenset[str]) -> tuple[list[str], list[str]]:
    """The fewest campaigns that cover a route's branches, plus any branch no campaign covers.

    Branch nodes are units of ignorance; campaigns are units of work. Counting branches alone
    overstates how many experiments a route needs, because one set of observations can settle several.
    Brute-forced over the declared campaigns — there are a handful, and an exact answer beats a
    heuristic nobody can check. No time, cost or probability is involved.
    """
    camps = d.get("campaigns") or []
    by_id = {c["id"]: frozenset(c["resolves"]) & branches for c in camps}
    useful = {k: v for k, v in by_id.items() if v}
    covered_any = frozenset().union(*useful.values()) if useful else frozenset()
    uncovered = sorted(branches - covered_any)
    best: list[str] | None = None
    ids = sorted(useful)
    for size in range(len(ids) + 1):
        from itertools import combinations
        for combo in combinations(ids, size):
            got = frozenset().union(*(useful[c] for c in combo)) if combo else frozenset()
            if got >= covered_any:
                best = list(combo)
                break
        if best is not None:
            break
    return (best or []), uncovered


def blocking_outcomes(d: dict, dest: str) -> list[tuple[str, str]]:
    """Single branch outcomes that make `dest` unreachable.

    This is SINGLE_OUTCOME_RESILIENCE, and the name matters. It perturbs one branch at a time, so an
    empty list means no *single* admissible result closes the destination. It does not establish
    robust reachability, which would require every admissible combination of outcomes across all
    branches — a policy space this function does not search. Calling it "robust" overstated it, so
    ROBUST_REACHABILITY is reported as NOT_ESTABLISHED rather than inferred from this.
    """
    out = []
    for b in d["nodes"]:
        if b["kind"] != "branch":
            continue
        for name in (b.get("outcomes") or {}):
            if cost(d, decided={b["id"]: name}).get(dest) is None:
                out.append((b["id"], name))
    return sorted(out)


def motifs(d: dict) -> dict:
    """Structural patterns in the graph. Computed, never asserted, and never traversable.

    A motif is a reason to ask a question, not a reason to draw an edge. Nothing here feeds cost(),
    frontier() or dominators_for(), so an interesting pattern cannot shorten a route.
    """
    import collections

    branches = [n for n in d["nodes"] if n["kind"] == "branch"]
    sig = collections.defaultdict(list)
    for b in branches:
        sig[tuple(sorted(b.get("outcomes") or {}))].append(b["id"])
    inbound: collections.Counter = collections.Counter()
    for e in d["edges"]:
        inbound[e["to"]] += 1
    for b in branches:
        for t in (b.get("outcomes") or {}).values():
            inbound[t] += 1
    actuators = collections.defaultdict(set)
    for cv, spec in (d.get("control_variables") or {}).items():
        for a in spec.get("actuators_tried", []) + spec.get("actuators_identified_not_tried", []):
            actuators[a].add(cv)
    limiting = [b["id"] for b in branches
                if "limiting" in (str(b.get("why_unresolved", "")) + str(b.get("label", ""))).lower()]
    return {
        "repeated_shapes": {k: v for k, v in sig.items() if len(v) > 1},
        "convergence": inbound.most_common(10),
        "shared_actuators": {a: sorted(c) for a, c in actuators.items() if len(c) > 1},
        "shared_prerequisite_limiting_system": sorted(limiting),
    }


def gaps(d: dict) -> dict[str, list[dict]]:
    """Edges grouped by label, which is what the PRD's per-route gap counts are built from."""
    by: dict[str, list[dict]] = {}
    for e in d["edges"]:
        by.setdefault(e["label"], []).append(e)
    return by


def render(d: dict) -> str:
    nodes = {n["id"]: n for n in d["nodes"]}
    G, U = goal(d), ultimate(d)
    base = cost(d).get(G)
    doms = dominators(d)
    cache: dict[tuple, frozenset[str] | None] = {}

    def remaining(nid: str, decided: dict[str, str] | None = None) -> frozenset[str] | None:
        """What still has to be resolved to establish the target, once `nid` is a known state.

        `decided` also closes the branch's other outcomes, because a branch returns one result.
        """
        key = (nid, tuple(sorted((decided or {}).items())))
        if key not in cache:
            cache[key] = cost(d, known={nid}, decided=decided).get(G)
        return cache[key]
    by_label = gaps(d)
    branches = [n for n in d["nodes"] if n["kind"] == "branch"]

    KIND = {"MEASUREMENT": "runnable measurement", "COMPONENT_DISCOVERY": "component discovery"}

    def branch_kind(bid: str) -> str:
        """Declared on the node, not inferred from incoming edges.

        Counting branches alone would price "run a cycloheximide chase" and "find a component nobody
        has described" the same, which is the one way this map could mislead. Deriving the distinction
        from edge labels looked cheaper and got BYPASS_ALIGN wrong, because one incidental incoming
        edge changed the answer. It is case data now.
        """
        return KIND.get(nodes[bid].get("resolves_by"), "unclassified")

    def runnable(sets) -> int:
        return sum(1 for x in sets if branch_kind(x) == "runnable measurement")

    def fmt(nid: str, decided: dict[str, str] | None = None) -> str:
        r = remaining(nid, decided)
        if r is None:
            return "**target not reachable from here**"
        if not r:
            return "**nothing further unresolved — the remaining chain is grounded**"
        return f"{len(r)} still unresolved: {', '.join('`' + x + '`' for x in sorted(r))}"

    # The canonical artifact reads City -> frontiers -> control variables -> families -> contingent
    # experiments -> motif hypotheses. Route-optimisation views still compute, but they are appendices:
    # they answer "where to act", which is a question for a downstream user and not what this is.
    SECTIONS: dict[str, list[str]] = {}
    cur = ["head"]

    def A(line: str = "") -> None:
        SECTIONS.setdefault(cur[0], []).append(line)

    def S(name: str) -> None:
        cur[0] = name
    A("# MVA_001 — contingent route map")
    A("")
    A("Generated by `tools/control/compile_route_map.py` from `MVA_CONTINGENT_ROUTE_MAP.yaml`. Case data")
    A("and a renderer, not a new compiler layer: the existing machinery represents causal chains and")
    A("per-experiment decision rules, neither of which branches on admissible experimental outcome.")
    A("")
    A("This is a city, not a route. It records every biological state the case can be in, every")
    A("experiment or observation that moves between them, every admissible outcome of each, and where")
    A("reasoning genuinely runs out. It does not say where to act: that is a downstream question, and")
    A("the views that answer it are in an appendix. No probabilities appear anywhere, because none is")
    A("grounded, and no leaf exists merely because reasoning stopped after an experiment.")
    A("")
    S("target")
    A("## Two cell-level states, and they are not the same thing")
    A("")
    A("Both are computed throughout, and conflating them was the error the target audit fixed.")
    A("")
    A(f"**`{G}`** — the terminal state actually wanted, open to any physically valid route:")
    A("")
    for k in d["target"]["conjunction"]:
        A(f"- `{k}` — {d['target']['components'][k]}")
    A("")
    A(f"**`{d['target']['canonical_state']}`** — the full trajectory a normal cell takes, which is one")
    A("route to that state rather than the definition of it:")
    A("")
    for k in d["target"]["canonical_conjunction"]:
        A(f"- `{k}` — {d['target']['components'][k]}")
    A("")
    A("The difference is the whole point. A synthetic route that safely produces faithful segregation")
    A("is not failed for leaving the canonical BubR1 trajectory unreproduced; the endpoints it skips")
    A("are retained as mechanistic diagnostics, and the audit below records why each was reclassified.")
    A("Neither state is the disease: the organism scale is further out and carries its own unknowns.")
    A("")
    S("target")
    A("## Target semantics audit")
    A("")
    A("The cell-level endpoints were audited individually, because a target built from the canonical")
    A("BubR1 trajectory would reject any synthetic route that reaches the same terminal state another")
    A("way. Nothing was removed: every endpoint keeps its node, and the canonical state is still")
    A("computed beside the functional one.")
    A("")
    A("| endpoint | verdict | retained as |")
    A("|---|---|---|")
    for k, v in (d.get("target_audit") or {}).items():
        A(f"| `{k}` | `{v['verdict']}` | {v.get('retained_as', 'target conjunct')} |")
    A("")
    A("| destination | is `BYPASS_ACT` an unavoidable gate? |")
    A("|---|---|")
    for dest in ("CANONICAL_CELLULAR_STATE", G, U):
        if dest in nodes:
            A(f"| `{dest}` | {'**yes**' if 'BYPASS_ACT' in dominators_for(d, dest) else 'no'} |")
    A("")
    A("Distances and unavoidable-branch counts for each destination are in the appendix; the finding")
    A("that matters here is semantic rather than numeric.")
    A("")
    A("**`BYPASS_ACT` is not an unavoidable gate to either cell-level destination.** Checkpoint")
    A("activation is therefore a route-specific requirement and a mechanistic diagnostic, not a")
    A("universal target conjunct — several iterations were spent hunting a component a synthetic")
    A("architecture may not need. It stays in the map and in the canonical state; it no longer gates")
    A("the functional target.")
    A("")
    A("What replaced it is narrower and honest: `ACT_SAFETY01`. Checkpoint deficiency predisposes to")
    A("tumours by a route the missegregation endpoint cannot see, and this disorder already carries")
    A("embryonal tumour risk. So the question is not \"must the checkpoint signal\" but \"does this case")
    A("need checkpoint competence for reasons other than fidelity\" — and that is now the one")
    A("unavoidable branch on the functional target.")
    A("")
    S("experiments")
    A("## Campaigns: units of work, not units of ignorance")
    A("")
    A("A branch is something unknown; a campaign is a set of observations that can legitimately be")
    A("collected together. Counting branches alone overstates how many experiments a route needs.")
    A("")
    A("| campaign | resolves | needs | question |")
    A("|---|---|---|---|")
    # ---- invariant: an observation cannot create an intervention state ----
    roles = set(d.get("branch_role_vocabulary") or [])
    classes = set(d.get("state_class_vocabulary") or [])
    for n in d["nodes"]:
        if n["kind"] == "branch":
            if n.get("branch_role") not in roles:
                problems.append(f"{n['id']}: branch_role {n.get('branch_role')!r} not in the closed "
                                "vocabulary — a branch must say whether it intervenes or observes")
                continue
            if n["branch_role"] != "OBSERVATION":
                continue
            for name, target in (n.get("outcomes") or {}).items():
                t = nodes.get(target) or {}
                cls = t.get("state_class", "SYSTEM")
                if t.get("kind") == "state" and cls != "KNOWLEDGE":
                    problems.append(
                        f"{n['id']} is an OBSERVATION and outcome {name!r} lands on {target} "
                        f"(state_class {cls}). Observing the system cannot improve it; an observation's "
                        "outcomes may only reach KNOWLEDGE states or terminals")
        if n["kind"] == "state" and n.get("state_class", "SYSTEM") not in classes:
            problems.append(f"{n['id']}: state_class {n.get('state_class')!r} not in the closed vocabulary")

    # ---- invariant: a mechanistic intermediate cannot imply a terminal endpoint ----
    for e in d["edges"]:
        src, dst = nodes.get(e["from"]) or {}, nodes.get(e["to"]) or {}
        if src.get("state_class") == "MECHANISTIC_INTERMEDIATE" and \
                dst.get("state_class") == "TERMINAL_ENDPOINT" and not e.get("establishing_measurement"):
            problems.append(
                f"edge {e['from']}->{e['to']}: a mechanistic intermediate may not imply the terminal "
                "endpoint without an edge that names the establishing measurement. Improving alignment "
                "is not lowering missegregation until missegregation is measured")
    for n in d["nodes"]:
        if n["kind"] != "branch":
            continue
        for name, target in (n.get("outcomes") or {}).items():
            src_cls = None
            for e in d["edges"]:
                if e["to"] == n["id"]:
                    src_cls = (nodes.get(e["from"]) or {}).get("state_class")
                    break
            dst = nodes.get(target) or {}
            if src_cls == "MECHANISTIC_INTERMEDIATE" and dst.get("state_class") == "TERMINAL_ENDPOINT" \
                    and not n.get("establishes"):
                problems.append(
                    f"{n['id']} carries a mechanistic intermediate to the terminal endpoint via "
                    f"{name!r} without declaring what it establishes")

    # ---- invariant: a terminal endpoint may not backfill a canonical mechanism ----
    # The forward direction was already enforced. The reverse is the same error read backwards:
    # reaching the endpoint says nothing about which mechanism delivered it, least of all in a state
    # several candidates converge on.
    for e in d["edges"]:
        src, dst = nodes.get(e["from"]) or {}, nodes.get(e["to"]) or {}
        if src.get("state_class") == "TERMINAL_ENDPOINT" and \
                dst.get("state_class") == "MECHANISTIC_INTERMEDIATE" and \
                not e.get("establishing_measurement"):
            problems.append(
                f"edge {e['from']}->{e['to']}: endpoint achievement may not backfill a canonical "
                "mechanism. Lowering missegregation does not establish that alignment was supplied, "
                "and this state is reached by routes that never measure it")

    # ---- invariant: a shared retry node must preserve control-variable identity ----
    for n in d["nodes"]:
        if n["kind"] != "branch" or not n.get("preserves_variable_identity"):
            continue
        mapping = n.get("actuator_retry_map") or {}
        if not mapping:
            problems.append(f"{n['id']}: claims to preserve variable identity with no retry map")
            continue
        for cv, outcome in mapping.items():
            if cv not in (d.get("control_variables") or {}):
                problems.append(f"{n['id']}: retry map names unknown control variable {cv}")
            if outcome not in (n.get("outcomes") or {}):
                problems.append(f"{n['id']}: retry map points at missing outcome {outcome!r}")
        incoming = [e["from"] for e in d["edges"] if e["to"] == n["id"]]
        for src in incoming:
            cv = (nodes.get(src) or {}).get("closes_for")
            if cv and cv not in mapping:
                problems.append(
                    f"{n['id']}: {src} closes an actuator of {cv}, which the retry map does not "
                    "cover, so a working alternate actuator would resolve into the wrong biology")

    # ---- invariant: positive efficacy is neutral with respect to independence ----
    for n in d["nodes"]:
        if n["kind"] != "branch":
            continue
        for name, target in (n.get("outcomes") or {}).items():
            if not (nodes.get(target) or {}).get("dependency_established"):
                continue
            if not n.get("dependency_tested"):
                problems.append(
                    f"{n['id']} outcome {name!r} reaches {target}, which asserts dependency was "
                    "established, but the branch does not declare dependency_tested. Positive efficacy "
                    "alone says nothing about independence")
            elif name not in (n.get("dependency_outcomes") or []):
                problems.append(
                    f"{n['id']} outcome {name!r} reaches {target}, which asserts dependency was "
                    f"established, but {name!r} is not one of the branch's dependency_outcomes. The "
                    "branch testing dependency is not enough: the particular result has to be the one "
                    "that encodes the dependency finding, or an efficacy result rides in on it")

    for c in (d.get("campaigns") or []):
        A(f"| `{c['id']}` | {', '.join('`' + x + '`' for x in c['resolves'])} | {c['requires']} "
          f"| {' '.join(c['question'].split())} |")
    A("")
    if d.get("campaign_note"):
        A(" ".join(d["campaign_note"].split()))
        A("")
    A("| destination | unresolved branches | campaigns needed | not covered by any campaign |")
    A("|---|---|---|---|")
    for dest in ("CANONICAL_CELLULAR_STATE", G, U):
        if dest not in nodes:
            continue
        c = cost(d).get(dest)
        if c is None:
            A(f"| `{dest}` | unreachable | — | — |")
            continue
        cov, unc = campaign_cover(d, c)
        A(f"| `{dest}` | {len(c)}: " + ", ".join("`" + x + "`" for x in sorted(c))
          + f" | {len(cov) + len(unc)}: " + ", ".join("`" + x + "`" for x in cov + unc)
          + " | " + (", ".join("`" + x + "`" for x in unc) or "none") + " |")
    A("")
    S("appendix_reachability")
    A("## Reachability")
    A("")
    A("Three distinct claims, and only two of them are computed here.")
    A("")
    A("- `CONDITIONAL_REACHABLE` — reachable if the branches fall a particular way.")
    A("- `SINGLE_OUTCOME_RESILIENT` — no *single* admissible result closes it. One branch is perturbed")
    A("  at a time.")
    A("- `ROBUST_REACHABILITY` — **`NOT_ESTABLISHED`.** It would require every admissible combination")
    A("  of outcomes across all branches, and this tool searches no such policy space. An earlier")
    A("  version of this section called single-outcome resilience \"robust\", which overstated it.")
    A("")
    A("No probability is attached to any of them, and none is available.")
    A("")
    A("| destination | `CONDITIONAL_REACHABLE` | `SINGLE_OUTCOME_RESILIENT` | single results that close it |")
    A("|---|---|---|---|")
    for dest in ("CANONICAL_CELLULAR_STATE", G, U):
        if dest not in nodes:
            continue
        c = cost(d).get(dest)
        blockers = blocking_outcomes(d, dest)
        cond = "NO" if c is None else (f"YES, {len(c)} branch(es)")
        rob = "**YES**" if (c is not None and not blockers) else "NO"
        shown = ", ".join(f"`{b}`=`{o}`" for b, o in blockers[:6]) or "none"
        if len(blockers) > 6:
            shown += f", and {len(blockers) - 6} more"
        A(f"| `{dest}` | {cond} | {rob} | {shown} |")
    A("")
    A("`ROBUST_REACHABILITY` is `NOT_ESTABLISHED` for every row above.")
    A("")
    S("experiments")
    A("## Every FLUX01 result, decided in advance")
    A("")
    flux = next((c for c in (d.get("campaigns") or []) if c["id"] == "FLUX01"), None)
    if flux and flux.get("outcomes"):
        A("A campaign resolves two branches at once, so its results are joint ones. Each is mapped to")
        A("the branch outcomes it implies, and the continuation is computed rather than waited for.")
        A("")
        A("| FLUX01 result | cell state after it | organism target after it | what happens next |")
        A("|---|---|---|---|")
        NEXT = {
         "lower_missegregation_population_preserved":
            "the cell-level functional state is reached by a non-canonical route; the risk gate "
            "`ACT_SAFETY01` becomes live and the tissue scale opens",
         "lower_missegregation_population_harmed":
            "`SAFE01` closes on safety grounds; no benefit verdict overrides it, and the flux "
            "component is out as a route whatever it did to missegregation",
         "no_reduction":
            "flux is not the controllable physics for this state; `C_KIF18A` remains the other named "
            "alignment candidate and the abundance family is untouched",
         "effect_requires_residual_bubr1":
            "the bypass premise fails for this component — it is not independent of the protein it "
            "was meant to work around",
         "insufficient_or_invalid":
            "nothing moves; the named validity gate is repeated at BubR1-limiting",
        }
        for name, mapping in flux["outcomes"].items():
            c_cell = cost(d, decided=mapping).get(G)
            c_org = cost(d, decided=mapping).get(U) if U else None
            def show(x):
                if x is None:
                    return "**closed**"
                return "**reached**" if not x else f"{len(x)} left"
            A(f"| `{name}` | {show(c_cell)} | {show(c_org)} | {NEXT.get(name, '')} |")
        A("")
    S("appendix_priority")
    A("## Priorities, reported separately")
    A("")
    A("The two families are not competing for one slot, so they get one line each.")
    A("")
    A("- **Global non-canonical experiment: `FLUX01`** — `FLUX01_EXECUTION_PACKET.md`. Resolves both")
    A("  branches on the shortest route to the cell-level functional state, in one set of observations,")
    A("  in a human cell line, against the terminal endpoint rather than a canonical intermediate.")
    A("- **First abundance-family experiment: `CHAR01`** — `CHAR01_EXECUTION_PACKET.md`. Unavoidable")
    A("  for F1, upstream of every other F1 branch, cheapest, no patient material.")
    A("")
    A("**Neither replaces the other.** They ask different questions: `CHAR01` asks whether the")
    A("destabilised-protein premise is true for this allele at all, and `FLUX01` asks whether that")
    A("repair can be skipped by correcting chromosome fidelity through other physics. A negative on")
    A("one does not settle the other, and they share no equipment-level dependency.")
    A("")
    fc = cost(d).get(G)
    if fc is not None:
        cov, unc = campaign_cover(d, fc)
        blocked = [x for x in unc if nodes[x].get("requires") != "CELL_MODEL"]
        A("**Do not read the campaign count as an experiment count.** The functional route is")
        A(f"{len(cov)} runnable campaign(s) — {', '.join('`' + x + '`' for x in cov) or 'none'} — plus")
        A(f"{len(blocked)} gate(s) that no cell experiment can answer: "
          + ", ".join(f"`{x}` ({nodes[x].get('requires')})" for x in blocked) + ".")
        A("")
        A("That asymmetry is the current state of the non-canonical route: the biology it needs is one")
        A("experiment away, and the risk question it needs is not in a dish at all.")
        A("")
    S("appendix_priority")
    A("## Where the route map says to look first")
    A("")
    if base is None:
        A("**No route currently establishes the target**, even conditionally: every family terminates in a")
        A("missing physical actuator or an unestablished context transfer before the target is reached.")
    else:
        A("From today, the smallest set of unresolved branch nodes that would establish the target is")
        A(f"**{len(base)}**: " + ", ".join("`" + x + "`" for x in sorted(base)) + ".")
        A("")
        A("**That count alone would mislead, so it is split by kind.** A branch entered only through a")
        A("missing physical actuator is a *component discovery* — find something nobody has described —")
        A("while a branch entered as an experimental unknown is a *runnable measurement*. They are not")
        A("interchangeable units of work, and the shortest route by count is not the shortest by effort.")
        A("")
        A("| branch | kind |")
        A("|---|---|")
        for x in sorted(base):
            A(f"| `{x}` | {branch_kind(x)} |")
        A("")
        A(f"Runnable measurements on that route: **{runnable(base)} of {len(base)}**.")
    A("")
    A("Unavoidable experiments — every route from the case state to the target passes through these:")
    A("")
    for b in sorted(doms):
        A(f"- **`{b}`** — {nodes[b]['label']}")
    A("")
    if not doms:
        A("- none: no single branch gates every route")
        A("")
    A("Distance to target from each branch's best admissible outcome, counting unresolved branch nodes")
    A("still required. Fewer is closer; the set is shown because routes share experiments and summing")
    A("them would invent work that does not exist.")
    A("")
    A("Distances are to `" + G + "` unless stated otherwise.")
    A("")
    A("| branch | kind | needs | best outcome | what remains after it | runnable |")
    A("|---|---|---|---|---|---|")
    for b in branches:
        best, best_r = None, None
        for name, target in (b.get("outcomes") or {}).items():
            r = remaining(target, {b["id"]: name})
            if r is not None and (best_r is None or len(r) < len(best_r)):
                best, best_r = name, r
        if best is None:
            A(f"| `{b['id']}` | {branch_kind(b['id'])} | {b.get('requires','?')} | — "
              f"| no admissible outcome reaches the target | — |")
        else:
            rest = ", ".join("`" + x + "`" for x in sorted(best_r)) if best_r else "**nothing further**"
            A(f"| `{b['id']}` | {branch_kind(b['id'])} | {b.get('requires','?')} | `{best}` "
              f"| {len(best_r)}: {rest} | {runnable(best_r)} |")
    A("")
    near = [b for b in branches
            if any((remaining(t) is not None and len(remaining(t)) <= 1)
                   for t in (b.get("outcomes") or {}).values())]
    A("### Highest-leverage opportunities")
    A("")
    if near:
        A("Branches with an admissible outcome that leaves **one or no** further experiment between the case")
        A("state and a chain whose remaining steps are grounded:")
        A("")
        for b in near:
            for name, t in (b.get("outcomes") or {}).items():
                r = remaining(t)
                if r is not None and len(r) <= 1:
                    tail = "the remaining chain is grounded" if not r else f"then only `{sorted(r)[0]}` remains"
                    A(f"- `{b['id']}` = `{name}` → {tail}")
        A("")
    else:
        A("No branch has an outcome that leaves one or fewer experiments. Every route to the target still")
        A("requires at least two unresolved results.")
        A("")
    S("experiments")
    A("## Branch nodes: every admissible outcome, continued")
    A("")
    for b in branches:
        A(f"### `{b['id']}`")
        A("")
        A(f"{b['label']}")
        A("")
        A(f"*Why unresolved:* {b['why_unresolved']}")
        A("")
        A("| outcome | leads to | route state from there |")
        A("|---|---|---|")
        for name, t in (b.get("outcomes") or {}).items():
            tn = nodes[t]
            kind = f"`{tn.get('terminal')}`" if tn["kind"] == "terminal" else tn["kind"]
            A(f"| `{name}` | `{t}` ({kind}) | {fmt(t)} |")
        A("")
    S("city")
    A("## Transitions by grounding label")
    A("")
    A("| label | count | meaning for the route |")
    A("|---|---|---|")
    meanings = {
        "GROUNDED": "traversed directly; no branch created",
        "CONTEXT_TRANSFER_REQUIRED": "the relation holds somewhere else and the transfer is unestablished",
        "EXPERIMENTAL_UNKNOWN": "a branch node; outcomes enumerated above",
        "PHYSICAL_ACTUATOR_MISSING": "the requirement is grounded and no component is known to supply it",
        "CONCEPTUALLY_SUFFICIENT_ONLY": "sufficient in model; not a physical claim",
        "UNSAFE": "closed on safety grounds",
    }
    for label in d["label_vocabulary"]:
        n = len(by_label.get(label, []))
        A(f"| `{label}` | {n} | {meanings[label]} |")
    A("")
    for label in ("PHYSICAL_ACTUATOR_MISSING", "CONTEXT_TRANSFER_REQUIRED"):
        if by_label.get(label):
            A(f"**`{label}` transitions:**")
            A("")
            for e in by_label[label]:
                A(f"- `{e['from']}` → `{e['to']}`" + (f" — {e['note']}" if e.get("note") else ""))
            A("")
    S("city")
    A("## Grounded facts traversed without branching")
    A("")
    A("Per the PRD: a sufficiently grounded transition is traversed directly, with its applicability")
    A("boundary recorded, rather than being split into alternative worlds because it has caveats.")
    A("")
    for g in d["grounded_facts"]:
        src = (", ".join(g["evidence"]) if g.get("evidence")
               else "derived: " + g["derivation"] if g.get("derivation") else "")
        A(f"- **`{g['id']}`** — {g['statement']} [{src}]")
        if g.get("consequence"):
            A(f"  - *consequence:* {g['consequence']}")
    A("")
    S("city")
    A("## Deliberate loops and family transitions")
    A("")
    A("The map is acyclic except where a negative result re-enters a branch on a different arm, and")
    A("terminals may close one family while opening another — the PRD's \"a negative experiment closes one")
    A("edge and opens another branch\".")
    A("")
    for e in d["edges"]:
        if e.get("reentry") or e.get("family_transition"):
            tag = "re-entry" if e.get("reentry") else "family transition"
            A(f"- *{tag}:* `{e['from']}` → `{e['to']}` — {e.get('note', '')}")
    A("")
    S("city")
    A("## The graph")
    A("")
    A("```mermaid")
    A("graph TD")
    shape = {"state": ('["', '"]'), "branch": ('{{"', '"}}'), "all_of": ('[/"', '"/]'), "terminal": ('(("', '"))')}
    for n in d["nodes"]:
        o, c = shape[n["kind"]]
        short = n["id"] if n["kind"] != "terminal" else f"{n['id']}<br/>{n.get('terminal')}"
        A(f"  {n['id']}{o}{short}{c}")
    for b in branches:
        for name, t in (b.get("outcomes") or {}).items():
            A(f"  {b['id']} -->|{name}| {t}")
    for e in d["edges"]:
        if nodes[e["from"]]["kind"] == "branch":
            continue
        style = "-.->" if (e.get("reentry") or e.get("family_transition")) else "-->"
        A(f"  {e['from']} {style}|{e['label']}| {e['to']}")
    for n in d["nodes"]:
        if n["kind"] == "all_of":
            for m in n["of"]:
                A(f"  {m} --> {n['id']}")
    A("```")
    A("")
    A("Diamonds are unresolved branches, circles terminals, trapezoids AND nodes. Dotted edges are")
    A("deliberate loops or family transitions.")
    A("")
    S("appendix_priority")
    A("## If EXP01 returned each result tomorrow")
    A("")
    A("Every outcome continues; none terminates in a bare unknown. The headline count is the same under")
    A("all seven, because the shortest route by count does not pass through EXP01 — so the decision-useful")
    A("view is per family. `F1` is the abundance family (restore the child's own protein); `F2` is the")
    A("composite bypass (supply each lost function independently).")
    A("")
    A("| EXP01 result | F1 abundance family | F2 bypass family | what it decides |")
    A("|---|---|---|---|")
    exp01 = next(n for n in d["nodes"] if n["id"] == "EXP01")
    fam_cache: dict[str, tuple] = {}

    def families(t: str, outcome: str) -> tuple[str, str]:
        if t not in fam_cache:
            c = cost(d, known={t}, decided={"EXP01": outcome})
            # A bounded frontier closes nothing: the question is unanswered, not answered negatively,
            # and reporting it as "closed" would turn a failed assay into a biological conclusion.
            frontier_only = (nodes[t]["kind"] == "terminal"
                             and nodes[t].get("terminal") == "BOUNDED_FRONTIER")

            def show(fid):
                r = c.get(fid)
                if r is None:
                    return "unresolved — the result decides nothing" if frontier_only else "**closed**"
                return "reached" if not r else f"{len(r)} left ({runnable(r)} runnable)"
            fam_cache[t] = (show("F1_COMPLETE"), show("F2_COMPLETE"))
        return fam_cache[t]

    decides = {
        "full_function": "the abundance premise survives for this allele; the whole question becomes physical",
        "alignment_defect": "F1 cannot be a complete solution; alignment must be supplied independently",
        "silencing_defect": "F1 cannot be a complete solution; silencing must be supplied independently",
        "segregation_defect": "the failing upstream function must be identified before a route is chosen",
        "multiple_defects": "F1 is closed as a complete solution; composite replacement is the only route",
        "matched_not_achieved": "the function question is unanswerable until the protein can be held up at all",
        "confounded_invalid": "nothing; the named validity gate is repeated",
    }
    for name, t in exp01["outcomes"].items():
        f1, f2 = families(t, name)
        A(f"| `{name}` | {f1} | {f2} | {decides.get(name, '')} |")
    A("")
    A("Then, recursively, at each branch the same question. The per-branch distance table above is that")
    A("answer in aggregate: it is the remaining-unknown set after every branch's best admissible outcome.")
    A("")
    A("### What the map says about priority")
    A("")
    f1_dom = sorted(dominators_for(d, "F1_COMPLETE"))
    f2_dom = sorted(dominators_for(d, "F2_COMPLETE"))
    A("No single branch gates every route, because the two families are genuinely alternative. The")
    A("decision-relevant fact is which branch gates a whole family:")
    A("")
    A("| family | unavoidable branches |")
    A("|---|---|")
    A(f"| F1 abundance | {', '.join('`' + x + '`' for x in f1_dom) or 'none'} |")
    A(f"| F2 bypass | {', '.join('`' + x + '`' for x in f2_dom) or 'none'} |")
    A("")
    f1_runnable = sum(1 for x in f1_dom if branch_kind(x) == "runnable measurement")
    f2_disc = [x for x in f2_dom if branch_kind(x) == "component discovery"]
    A(f"The two families are blocked by different kinds of thing. **F1** is a strict chain: all")
    A(f"{len(f1_dom)} of its branches are unavoidable and {f1_runnable} are runnable measurements, so it")
    A("is long but every step is work someone can do. **F2** is gated by")
    A(("`" + "`, `".join(f2_disc) + "`, which is a component discovery — the one hole the external search"
       " could not fill." if f2_disc else "runnable measurements only."))
    A("")
    A("So the bypass family is not blocked by effort but by the absence of a thing. A route cannot be")
    A("assembled from two supplied functions and a missing one.")
    A("")
    if base:
        disc = [x for x in sorted(base) if branch_kind(x) == "component discovery"]
        A(f"The shortest route holds **{runnable(base)} runnable measurements of {len(base)}**"
          + (f", with `{'`, `'.join(disc)}` still a component discovery." if disc else ", and no discovery."))
        A("")
    A("Two readings, and where they disagree is the useful part. **By branch count** the bypass family")
    A("is shorter. **By kind**, what matters is how many of those branches are measurements someone can")
    A("run rather than components nobody has described — which is why the external search mattered more")
    A("than another pass over the graph.")
    A("")
    if "CHAR01" in f1_dom:
        A("`CHAR01` remains the leading runnable experiment on the abundance family: the corrected graph")
        A("still makes it unavoidable for F1, it is the cheapest branch on that family, and it needs no")
        A("patient material — one construct, a cycloheximide chase with HSP90 inhibition and MG132, a")
        A("strict subset of what STAB01 already specifies.")
    else:
        A("`CHAR01` is no longer unavoidable for the abundance family under the corrected graph, so its")
        A("priority rests on cost rather than on dominance.")
    A("")
    A("It is not EXP01, and the reason is about the premise rather than the question. `EXP01` asks whether")
    A("the altered protein works at matched abundance. `CHAR01` asks whether the premise underneath that")
    A("question holds for this allele at all — and the premise is class-level inference: `MC_0006` is")
    A("`UNRESOLVED` on zero establishing records, `MC_0005` rests on 0 establishing and 11 indirect, and")
    A("Q921H is a kinase-domain substitution normal in both level and function. If this allele is not")
    A("destabilised, EXP01's matched-abundance framing is miscast before it is run.")
    A("")
    A("### What the external search changed")
    A("")
    A("The three component-discovery diamonds were the map's biggest holes. Function-first discovery")
    A("against external literature, followed by dependency adjudication, replaced two of the three with")
    A("named candidates:")
    A("")
    A("- **alignment** — `CENP-E` is **closed by evidence**, which is the most useful single result: it")
    A("  has a BubR1-independent route to the outer corona, while the mechanism by which it initiates")
    A("  congression is explicitly BubR1-dependent. Localisation is not function, the same distinction")
    A("  Y155C forces. `KIF18A` and microtubule `poleward flux` survive as named candidates with their")
    A("  dependency unestablished.")
    A("- **silencing** — `TRIP13` with `APC15` survives as a named candidate. It carries a specific extra")
    A("  risk the map records as its own outcome: the same protein maintains open-state Mad2 for")
    A("  checkpoint activation, so augmenting it for silencing may trade one broken function for another.")
    A("- **activation** — nothing survived function-first discovery. This stays a bounded external")
    A("  frontier, not an impossibility: `NOT_FOUND_IN_SEARCHED_EXTERNAL_UNIVERSE`, with the searched")
    A("  universe recorded in `data/literature/mva-bypass-v1`.")
    A("")
    A("Absence of a known BubR1 link was never recorded as independence. Every surviving candidate's")
    A("dependency branch has an `unestablished` outcome, and that is where they all sit today.")
    A("")
    S("appendix_priority")
    A("## What can actually be done now")
    A("")
    A("The branches sort into three kinds of work, and treating them as one pool of \"unknowns\" was the")
    A("thing this map was built to stop.")
    A("")
    groups = {}
    for b in branches:
        groups.setdefault(b.get("requires", "?"), []).append(b["id"])
    NEED = {"CELL_MODEL": "runnable now — a human cell line and standard assays",
            "TISSUE_MODEL": "needs a tissue-level model that does not exist for this case",
            "ORGANISM_MODEL": "needs organism-level or longitudinal data",
            "GOVERNANCE_ABSENT": "blocked by governance, not biology: no patient material is available and none may be acquired"}
    A("| needs | branches | meaning |")
    A("|---|---|---|")
    for k in ("CELL_MODEL", "TISSUE_MODEL", "ORGANISM_MODEL", "GOVERNANCE_ABSENT"):
        if groups.get(k):
            A(f"| `{k}` | {', '.join('`' + x + '`' for x in sorted(groups[k]))} | {NEED[k]} |")
    A("")
    runnable_now = sorted(groups.get("CELL_MODEL", []))
    on_route = [x for x in runnable_now if base and x in base]
    A(f"{len(runnable_now)} of {len(branches)} branches need nothing but a cell line. Of those, "
      f"{len(on_route)} sit on the shortest route to `{G}`"
      + (": " + ", ".join("`" + x + "`" for x in on_route) if on_route else "") + ".")
    A("")
    A("`CHAR01` remains the first bench experiment on the abundance family: cheapest, upstream of every")
    A("other F1 branch, and no patient material.")
    A("")
    S("experiments")
    A("## Beyond the cell")
    A("")
    A("Reaching the cell-level state is not the disease being addressed, so the map continues past it.")
    A("Three questions follow, and the third bounds the other two whatever they return.")
    A("")
    A("| scale question | branch | state |")
    A("|---|---|---|")
    for bid in ("XSCALE01", "IRREV01", "SAFE_ORG", "XSCALE02"):
        if bid in nodes:
            r = cost(d).get(bid)
            where = "unreachable today" if r is None else f"{len(r)} branch(es) upstream"
            A(f"| {nodes[bid]['label']} | `{bid}` | {where} |")
    A("")
    if U:
        ur = cost(d).get(U)
        A(f"`{U}`: " + ("**not reachable by any route in this map today.**" if ur is None
                        else f"{len(ur)} unresolved branch(es)."))
        A("")
        A((d.get("ultimate_target") or {}).get("note", ""))
        A("")
    A("`IRREV01` is the one that should temper everything above it. Mosaic variegated aneuploidy is")
    A("constitutional: much of the burden is developmental and already laid down, and improving")
    A("fidelity prospectively does not undo an aneuploid cell that already exists. Which part of the")
    A("phenotype is still ahead of this child is unestablished, and it bounds what any route here can")
    A("address. Cell-level reachability is not disease resolution, and this map does not claim it.")
    A("")
    S("frontiers")
    A("## Frontier audit")
    A("")
    A("Every leaf, and why it is allowed to be one. The acceptance criterion is that no leaf exists")
    A("merely because reasoning stopped one step after an experiment.")
    A("")
    ALLOWED = {
      "FUNCTIONAL_TARGET_REACHED": "the cell-level state is reached",
      "ORGANISM_TARGET_REACHED_IN_MODEL": "the organism-level state is reached in model",
      "UNSAFE": "closed on safety grounds; no benefit verdict overrides it",
      "GOVERNANCE_BLOCKED": "blocked by governance, not biology — no material, no intervention, no recontact",
      "PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE": "the continuation contradicts evidence already in hand",
      "SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED": "bounded external search ran and returned nothing",
      "DECLARED_SCIENTIFIC_FRONTIER": "no next experiment or search is currently identifiable",
      "BOUNDED_FRONTIER": "a validity failure: the same condition is repeated, so reasoning has not stopped",
      "NOT_IN_LOCAL_CASE_CORPUS": "absent from the case corpus only",
      "CONTEXT_TRANSFER_REQUIRED": "the transfer is unestablished and named",
      "UNEXPANDED_FRONTIER": "**NOT ALLOWED** — reasoning stopped one step after an experiment",
    }
    continues = {e["from"] for e in d["edges"]}
    by_kind: dict[str, list[dict]] = {}
    carries_on: list[str] = []
    for n in d["nodes"]:
        if n["kind"] != "terminal":
            continue
        if n["id"] in continues:
            carries_on.append(n["id"])     # closes one family and opens another: not a leaf
            continue
        by_kind.setdefault(n["terminal"], []).append(n)
    A(f"{len(carries_on)} node(s) typed as terminal are not leaves at all — they close one family and")
    A("open another, so they are excluded from the audit below: "
      + ", ".join("`" + x + "`" for x in sorted(carries_on)) + ".")
    A("")
    A("| terminal kind | count | why a leaf may remain | leaves |")
    A("|---|---|---|---|")
    for kind in d["terminal_vocabulary"]:
        got = by_kind.get(kind, [])
        if not got:
            continue
        A(f"| `{kind}` | {len(got)} | {ALLOWED.get(kind, '')} "
          f"| {', '.join('`' + x['id'] + '`' for x in sorted(got, key=lambda y: y['id']))} |")
    A("")
    bad = by_kind.get("UNEXPANDED_FRONTIER", [])
    A(f"**Unexpanded frontiers remaining: {len(bad)}.**"
      + (" " + ", ".join('`' + x["id"] + '`' for x in bad) if bad else
         " The acceptance criterion is met: every leaf is a target, a safety closure, a governance"
         " block, an evidence incompatibility, an exhausted search, a declared frontier, or a validity"
         " repeat."))
    A("")
    A("### What the audit retired")
    A("")
    A("`NO_KNOWN_CONTINUATION` is gone from the vocabulary. All thirteen nodes that carried it were")
    A("branches nobody had expanded — not impossibilities, not safety closures, not exhausted searches.")
    A("Each became a state with a real next question, and that is where most of this map's growth came")
    A("from.")
    A("")
    S("city")
    A("## The city")
    A("")
    A("### Distinct biological states")
    A("")
    states = sorted((n for n in d["nodes"] if n["kind"] == "state"), key=lambda n: n["id"])
    A(f"{len(states)} states. Each is a condition the case can be in, not a step in a protocol.")
    A("")
    for n in states:
        A(f"- `{n['id']}` — {n['label']}")
    A("")
    A("### Experiment and observation nodes")
    A("")
    A(f"{len(branches)} branches, carrying "
      f"{sum(len(b.get('outcomes') or {}) for b in branches)} admissible outcomes between them.")
    A("")
    A("| branch | needs | outcomes |")
    A("|---|---|---|")
    for b in sorted(branches, key=lambda n: n["id"]):
        A(f"| `{b['id']}` | {b.get('requires','?')} "
          f"| {', '.join('`' + k + '`' for k in (b.get('outcomes') or {}))} |")
    A("")
    A("### Convergence points")
    A("")
    A("States several different worlds arrive at. These are where the map collapses rather than")
    A("branching, and they are why this is not a tree.")
    A("")
    inbound: dict[str, int] = {}
    for e in d["edges"]:
        inbound[e["to"]] = inbound.get(e["to"], 0) + 1
    for b in branches:
        for t in (b.get("outcomes") or {}).values():
            inbound[t] = inbound.get(t, 0) + 1
    conv = sorted(((v, k) for k, v in inbound.items() if v >= 3), reverse=True)
    A("| state | worlds arriving |")
    A("|---|---|")
    for v, k in conv:
        A(f"| `{k}` | {v} |")
    A("")
    A("### External-search frontiers")
    A("")
    A("Branches whose resolution needs knowledge from outside this case, with what has been searched.")
    A("")
    A("| branch | status |")
    A("|---|---|")
    for b in sorted(branches, key=lambda n: n["id"]):
        if b.get("resolves_by") == "COMPONENT_DISCOVERY" or "search" in (b.get("why_unresolved") or "").lower():
            A(f"| `{b['id']}` | {' '.join((b.get('why_unresolved') or '').split())[:200]} |")
    A("")
    A("### Grounded direct transitions")
    A("")
    g_edges = [e for e in d["edges"] if e["label"] == "GROUNDED"]
    A(f"{len(g_edges)} transitions are traversed directly rather than branched, because the evidence")
    A("settles them. A caveat is recorded as an applicability boundary, not as a fork.")
    A("")
    for e in g_edges:
        if e.get("note"):
            A(f"- `{e['from']}` → `{e['to']}` — {e['note']}"
              + (f" [{', '.join(e['evidence'])}]" if e.get("evidence") else ""))
    A("")
    S("variables")
    A("## Control variables and actuators")
    A("")
    A("A failed or unsafe actuator closes the actuator. It closes the control variable only when the")
    A("evidence speaks to the variable itself.")
    A("")
    A("| control variable | actuators tried | identified, untried | intrinsically unsafe? |")
    A("|---|---|---|---|")
    for cv, spec in (d.get("control_variables") or {}).items():
        tried = ", ".join("`" + x + "`" for x in spec.get("actuators_tried", [])) or "none"
        untried = ", ".join("`" + x + "`" for x in spec.get("actuators_identified_not_tried", [])) or "none"
        unsafe = str(spec.get("intrinsically_unsafe", "NOT_ESTABLISHED"))
        A(f"| `{cv}` | {tried} | {untried} | {' '.join(unsafe.split())[:150]} |")
    A("")
    S("families")
    A("## Strategy families")
    A("")
    for fid, text in (d.get("families") or {}).items():
        A(f"- **`{fid}`** — {text}")
    A("")
    A("`F4_REMOVE` is new, and it arrived from the frontier audit rather than from a search: asking why")
    A("\"the established burden is fixed\" was allowed to be a leaf produced the only family that can act")
    A("on aneuploidy which already exists.")
    A("")
    S("city")
    A("## City size")
    A("")
    kinds: dict[str, int] = {}
    for n in d["nodes"]:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    A("| | count |")
    A("|---|---|")
    for k in ("state", "branch", "all_of", "terminal"):
        A(f"| {k} nodes | {kinds.get(k, 0)} |")
    A(f"| edges | {len(d['edges'])} |")
    A(f"| admissible outcomes across all branches | "
      f"{sum(len(n.get('outcomes') or {}) for n in d['nodes'] if n['kind'] == 'branch')} |")
    A(f"| control variables | {len(d.get('control_variables') or {})} |")
    A(f"| strategy families | {len(d.get('families') or {})} |")
    A(f"| campaigns | {len(d.get('campaigns') or [])} |")
    A("")
    A("---")
    A("")
    S("motifs")
    A("# Analysis pass")
    A("")
    A("Separate from the city by construction, and run after it rather than during it. Motifs are")
    A("patterns in the graph; a pattern is a reason to ask a question, never a reason to draw an edge.")
    A("Nothing in this section feeds the reachability computation, and no hypothesis below is")
    A("traversable until it is grounded and promoted into `edges` by hand.")
    A("")
    mo = motifs(d)
    A("## Motifs found")
    A("")
    A("### Shared prerequisite")
    A("")
    lim = mo["shared_prerequisite_limiting_system"]
    A(f"**{len(lim)} branches sit behind one system**: a human-cell model held at measured, limiting")
    A("BubR1 with missegregation readouts.")
    A("")
    A("" + ", ".join("`" + x + "`" for x in lim) + ".")
    A("")
    A("The expensive object in this map is not any experiment; it is the platform, and it is shared. A")
    A("view that ranked experiments one at a time would not surface this.")
    A("")
    A("### Repeated subgraphs")
    A("")
    A("| branches | identical outcome signature |")
    A("|---|---|")
    for k, v in sorted(mo["repeated_shapes"].items(), key=lambda kv: -len(kv[1])):
        A(f"| {', '.join('`' + x + '`' for x in sorted(v))} | {', '.join('`' + x + '`' for x in k)} |")
    A("")
    A("One design, parameterised by candidate, resolves a class of branches. The repetition is")
    A("structure rather than redundancy.")
    A("")
    A("### Convergence")
    A("")
    A("| node | worlds arriving |")
    A("|---|---|")
    for k, v in mo["convergence"]:
        if v >= 3:
            A(f"| `{k}` | {v} |")
    A("")
    A("### Shared actuators across control variables")
    A("")
    A(("None. " if not mo["shared_actuators"] else
       ", ".join(f"`{a}` in {c}" for a, c in mo["shared_actuators"].items()) + ". ")
      + ("No actuator moves two control variables, so a combination route needs a combination of "
         "perturbations and there is no accidental two-for-one. This is a negative motif: it "
         "constrains the combination branches rather than enabling them."
         if not mo["shared_actuators"] else ""))
    A("")
    A("## Hypotheses the motifs generate")
    A("")
    A("Each is **`NOT_TRAVERSABLE`**. A structural hypothesis is a claim about this graph and can be")
    A("checked by reading it; a biological hypothesis is a claim about the world and needs evidence or")
    A("an experiment before it may be believed, let alone traversed.")
    A("")
    for h in (d.get("hypotheses") or []):
        A(f"### `{h['id']}` — {h['kind']}")
        A("")
        A(f"*Motif:* {h['motif']}")
        A("")
        A(" ".join(h["claim"].split()))
        A("")
        A(f"**Consequence.** {' '.join(h['consequence'].split())}")
        A("")
        if h.get("what_would_promote_it"):
            A(f"**What would promote it.** {' '.join(h['what_would_promote_it'].split())}")
            A("")
        if h.get("evidence_so_far"):
            A(f"*Evidence so far:* {', '.join(h['evidence_so_far'])}")
            A("")
    S("tail")
    A("## Latent control variable sweep")
    A("")
    A("The motif pass asked what repeats in the graph. This asks something harder: whether three or")
    A("more neighbourhoods the city treats as distinct could be generated by one variable it does not")
    A("model. No control variable is merged, no causal edge is drawn, and reachability is untouched —")
    A("deleting this whole section leaves the city byte-identical, which is under test.")
    A("")
    A("**The governing rule.** A candidate must predict something that was not used to construct it.")
    A("Without that it is a new name for a pattern already in hand, and renaming is not explaining.")
    A("")
    A("A `STRUCTURAL_COMMONALITY` is a fact about this graph. A `BIOLOGICAL_LATENT_VARIABLE` is a claim")
    A("about the world. The first is never upgraded into the second.")
    A("")
    for h in (d.get("latent_variable_hypotheses") or []):
        A(f"### `{h['id']}` — {h['kind']}")
        A("")
        A(f"**Candidate variable.** {' '.join(str(h['candidate_variable']).split())}")
        A("")
        hoods = h.get("neighbourhoods_explained")
        if isinstance(hoods, list):
            A("**Neighbourhoods explained:** " + ", ".join("`" + x + "`" for x in hoods) + ".")
        else:
            A(f"**Neighbourhoods explained:** {hoods}")
        A("")
        if h.get("shared_features"):
            A("*Shared:* " + ", ".join(str(x).replace("_", " ") for x in h["shared_features"]) + ".")
            A("")
        if h.get("why_it_is_not_a_latent_biological_variable"):
            A("**Why this is not a biological explanation.** "
              + " ".join(h["why_it_is_not_a_latent_biological_variable"].split()))
            A("")
            continue
        A("**Why one variable could generate all of them.** "
          + " ".join(h["why_one_variable_could_generate_all"].split()))
        A("")
        A("**Existing evidence.**")
        A("")
        for e in h["existing_evidence"]:
            A(f"- {' '.join(e.split())}")
        A("")
        if h.get("retrodiction_not_used_to_build_it"):
            A("**Retrodiction, from data not used to build the city's variables.** "
              + " ".join(h["retrodiction_not_used_to_build_it"].split()))
            A("")
        A("**New predictions** — none of these was used to construct the hypothesis.")
        A("")
        for e in h["new_predictions"]:
            A(f"- {' '.join(e.split())}")
        A("")
        A("**Evidence against, and incompatibilities.**")
        A("")
        for e in h["evidence_against_or_incompatibilities"]:
            A(f"- {' '.join(e.split())}")
        A("")
        A("**Smallest discriminating experiment.** "
          + " ".join(h["smallest_discriminating_experiment"].split()))
        A("")
        A(f"**Status.** `{h['status']}`. Promotion requires: "
          + " ".join(h["promotion_requires"].split()))
        A("")
    A("### Negative results")
    A("")
    A("Neighbourhood sets for which no plausible common variable can currently be identified. Reported")
    A("because a sweep that only published its hits would be a generator of coincidences.")
    A("")
    for n in (d.get("negative_latent_results") or []):
        A(f"- **{', '.join('`' + str(x) + '`' for x in n['neighbourhood_set'])}** — "
          + " ".join(n["finding"].split()))
    A("")
    A("## What this map does not claim")
    A("")
    A("No probability is attached to any branch, because none is grounded. A route that \"conditionally")
    A("reaches the target\" reaches it *in model*, under the labelled transitions, and every")
    A("`CONCEPTUALLY_SUFFICIENT_ONLY` edge into the target means the population endpoints still have to be")
    A("observed rather than assumed. Nothing here is a treatment recommendation, and the terminal")
    A("`T_XFER_BLOCKED` is a governance boundary rather than a biological one: no patient-derived material")
    A("is available and none may be acquired.")
    ORDER = [("head", None),
             ("target", None),
             ("city", "# The city"),
             ("frontiers", "# Frontiers"),
             ("variables", "# Control variables and actuators"),
             ("families", "# Strategy families"),
             ("experiments", "# Contingent experiments"),
             ("motifs", None),
             ("tail", None)]
    out: list[str] = []
    for name, heading in ORDER:
        if name not in SECTIONS:
            continue
        if heading:
            out += ["---", "", heading, ""]
        out += SECTIONS[name]
    appendices = [k for k in SECTIONS if k.startswith("appendix_")]
    if appendices:
        out += ["---", "", "# Appendix: optional views", "",
                "These answer *where to act*, which is a question for a downstream user rather than",
                "the purpose of this artifact. They are kept because the computation is sound and",
                "someone will want them, and they are an appendix because ranking routes by length or",
                "leverage is not what this map is for. Nothing above depends on them.", ""]
        for k in appendices:
            out += SECTIONS[k]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate and compare the committed document")
    args = ap.parse_args()
    d = load()
    problems = validate(d)
    if problems:
        print("ROUTE_MAP_INVALID")
        for p in problems:
            print("  -", p)
        return 1
    text = render(d)
    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run uv run python tools/control/compile_route_map.py")
            return 1
        print("ROUTE_MAP_VALID and the committed document is current")
        return 0
    OUT.write_text(text)
    c, doms = cost(d), dominators(d)
    G, U = goal(d), ultimate(d)
    print("ROUTE_MAP_VALID")
    print(f"  nodes {len(d['nodes'])}, edges {len(d['edges'])}, "
          f"branches {sum(1 for n in d['nodes'] if n['kind'] == 'branch')}")
    print(f"  unavoidable branches: {', '.join(sorted(doms)) or 'none'}")
    for name in [x for x in (G, U) if x]:
        r = c.get(name)
        print(f"  to establish {name}: " + ("not reachable on any route" if r is None
              else f"{len(r)} unresolved branch(es) minimum -> {', '.join(sorted(r))}"))
    print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
