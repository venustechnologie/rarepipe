#!/usr/bin/env python3
"""Build and freeze the policy benchmark: episodes, splits, seals, and an Arm E baseline.

The episode set is a committed artifact rather than something regenerated per run, because
"frozen before any prompt or algorithm is tuned" only means something if the set is written down
and sealed. Rebuilding it is a deliberate act: it changes the seals, and any earlier number stops
being traceable to the set it was measured on.

Real episodes are restricted to the region where the exhaustive solver is exact — a horizon of
three today — and an episode whose oracle could not be computed exactly is refused and counted.
The refusal rate is published, because it measures how far the exhaustive solver certifies, and
that is the number that decides when the symbolic solver stops being optional.

Synthetic graphs are included alongside MVA on purpose. One hand-built graph is one shape, and a
solver tuned until it passes it has learned that graph rather than the problem.

Usage:
  uv run python tools/control/build_policy_benchmark.py --count 40 --horizon 2
  uv run python tools/control/build_policy_benchmark.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import importlib.util  # noqa: E402

from rarepipe.stages.control.benchmark import arms, metrics, runner, splits, synthetic  # noqa: E402
from rarepipe.stages.control.benchmark.episodes import coverage, generate  # noqa: E402
from rarepipe.stages.control.policy import Constraints  # noqa: E402

OUT_DIR = ROOT / "data" / "policy_benchmark"
EPISODES = OUT_DIR / "episodes.json"
REPORT = ROOT / "docs" / "control" / "MVA_POLICY_BENCHMARK.md"

SPLIT_SALT = "enigma-002a"
DEFAULT_COUNT = 40
DEFAULT_HORIZON = 2
SEED = 20261013


def _adapter():
    spec = importlib.util.spec_from_file_location(
        "solve_mva_policy", ROOT / "tools/control/solve_mva_policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(count: int = DEFAULT_COUNT, horizon: int = DEFAULT_HORIZON) -> dict:
    """Generate every source's episodes, split them, seal them, and run the Arm E baseline."""
    adapter = _adapter()
    document = adapter.load()
    constraints = Constraints(
        max_states=3_000_000,
        hypothesis_discriminators=adapter.hypothesis_discriminators(document),
        node_families=adapter.node_families(document),
    )

    sources: list[dict] = []

    # ---- the real case, inside the region the exhaustive solver certifies ----
    graph = adapter.build_graph(document)
    campaigns = adapter.build_campaigns(document)
    graph_ref = f"MVA_001@{adapter.digest()}"
    episodes, refused = generate(
        graph, graph_ref=graph_ref, campaigns=campaigns, seed=SEED,
        count=count, max_depth=horizon, horizon=horizon, constraints=constraints)
    sources.append({
        "name": "MVA_001",
        "graph_ref": graph_ref,
        "horizon": horizon,
        "coverage": coverage(episodes, refused),
        "episodes": [episode.describe() for episode in episodes],
        "refused": [entry.describe() for entry in refused],
    })

    # ---- synthetic graphs, whose answers follow from their construction ----
    for case in synthetic.catalogue():
        reference = f"synthetic:{case.name}"
        found, declined = generate(
            case.graph, graph_ref=reference, campaigns=case.campaigns, seed=SEED,
            count=max(4, count // 8), max_depth=3, horizon=3)
        sources.append({
            "name": case.name,
            "graph_ref": reference,
            "horizon": 3,
            "expected": {
                "robust": case.expected_robust,
                "minimal_horizon": case.expected_minimal_horizon,
                "robust_first_actions": list(case.expected_robust_first_actions),
                "recommended_actions": list(case.expected_recommended_actions),
                "tied_minimal_route_count": case.expected_tied_minimal_route_count,
                "structures": list(case.structures),
                "note": case.note,
            },
            "coverage": coverage(found, declined),
            "episodes": [episode.describe() for episode in found],
            "refused": [entry.describe() for entry in declined],
        })

    # ---- split and seal every source separately ----
    # Separately, so that adding a source cannot move another source's locked episodes.
    sealed: dict[str, dict] = {}
    for source in sources:
        regenerated = _reload(source)
        split_set = splits.split_episodes(regenerated, salt=f"{SPLIT_SALT}:{source['name']}")
        sealed[source["name"]] = split_set.describe()

    # ---- the Arm E baseline, which is a self-test and never a competitive claim ----
    # Reuses the episodes already generated above. Regenerating them would double the most
    # expensive part of this build for an identical set.
    baseline_splits = splits.split_episodes(episodes, salt=f"{SPLIT_SALT}:MVA_001")
    baseline = runner.run(
        graph, baseline_splits, (arms.engine_only(),), campaigns=campaigns,
        split=splits.DEVELOPMENT, horizon=horizon, repeats=2,
        constraints=constraints, graph_ref=graph_ref)

    return {
        "schema": {"name": "PolicyBenchmark", "version": "0.1.0"},
        "split_salt": SPLIT_SALT,
        "seed": SEED,
        "sources": sources,
        "splits": sealed,
        "arm_e_baseline": baseline.describe(),
        "note": ("Arm E is the engine answering with the engine's own answer. It measures the "
                 "harness and the solver, never an advantage over anything — the competitive "
                 "question needs the other arms and a locked split."),
    }


def _reload(source: dict):
    """Rebuild Episode objects from a source's stored descriptions, for splitting and sealing."""
    from rarepipe.stages.control.benchmark.episodes import Episode
    from rarepipe.stages.control.benchmark.oracle import OracleAnswer

    rebuilt = []
    for raw in source["episodes"]:
        oracle = raw["oracle"]
        rebuilt.append(Episode(
            id=raw["id"], graph_ref=raw["graph_ref"], target=raw["target"],
            horizon=raw["horizon"], depth=raw["depth"],
            decided=tuple(sorted(raw["decided"].items())),
            actions_taken=tuple(raw["actions_taken"]),
            oracle=OracleAnswer(
                verdict=oracle["verdict"], verdict_reason=oracle["verdict_reason"],
                exactness=oracle["exactness"], horizon=oracle["horizon"],
                searched_exhaustively_to=oracle["searched_exhaustively_to"],
                conditional_reachable=oracle["conditional_reachable"],
                minimal_robust_horizon=oracle["minimal_robust_horizon"],
                recommended_actions=tuple(oracle["recommended_actions"]),
                tied_minimal_branch_sets=tuple(
                    tuple(s) for s in oracle["tied_minimal_branch_sets"]),
                remaining_frontiers=tuple(oracle["remaining_frontiers"]),
                cut_sets=tuple(tuple((e["branch"], e["outcome"]) for e in combo)
                               for combo in oracle["minimal_target_cut_sets"]),
                success_sets=tuple(tuple((e["branch"], e["outcome"]) for e in combo)
                                   for combo in oracle["minimal_target_success_sets"]),
                unsafe_routes=tuple((r["branch"], r["outcome"], r["terminal"])
                                    for r in oracle["unsafe_routes"]),
                worst_case_depth=oracle["worst_case_depth"],
                action_costs=tuple(sorted(oracle["action_costs"].items())),
                states_considered=oracle["states_considered"],
            ),
        ))
    return tuple(rebuilt)


def render(data: dict) -> str:
    out: list[str] = []
    A = out.append
    A("# MVA_001 — policy benchmark (ENIGMA-002A)")
    A("")
    A("Generated by `tools/control/build_policy_benchmark.py`. The episode set is committed and")
    A("sealed: a published number is traceable to the exact set it was measured on, and rebuilding")
    A("the set changes the seals on purpose.")
    A("")
    A(f"- split salt: `{data['split_salt']}`  ·  seed: `{data['seed']}`")
    A(f"- episode file: `{EPISODES.relative_to(ROOT)}`")
    A("")
    A("## What the exhaustive oracle can certify")
    A("")
    A("An episode is admitted only when its answer was computed **exactly**. Refusals are counted,")
    A("not dropped: the refusal rate is how far the exhaustive solver reaches, and that is what")
    A("decides when the symbolic solver stops being optional.")
    A("")
    A("| source | horizon | admitted | refused | admitted fraction | depths |")
    A("|---|---|---|---|---|---|")
    for source in data["sources"]:
        c = source["coverage"]
        depths = ", ".join(f"{k}:{v}" for k, v in c["admitted_by_depth"].items()) or "none"
        A(f"| `{source['name']}` | {source['horizon']} | {c['admitted']} | {c['refused']} "
          f"| {c['admitted_fraction']:.2f} | {depths} |")
    A("")
    A("## Splits")
    A("")
    A("Assignment is a digest of each episode's own content, so adding episodes never moves an")
    A("existing one. Each source is split and sealed separately, so adding a source cannot move")
    A("another source's locked episodes.")
    A("")
    A("| source | development | validation | locked | locked seal |")
    A("|---|---|---|---|---|")
    for name, entry in data["splits"].items():
        counts = entry["counts"]
        A(f"| `{name}` | {counts['development']} | {counts['validation']} | {counts['locked']} "
          f"| `{entry['locked_seal'][:23]}…` |")
    A("")
    A("## Arm E baseline — engine only")
    A("")
    A(data["note"])
    A("")
    baseline = data["arm_e_baseline"]
    summary = baseline["per_arm"].get(arms.ENGINE_ONLY, {})
    A("| metric | mean | applied to | not applicable |")
    A("|---|---|---|---|")
    for name in metrics.PRIMARY:
        row = summary.get(name) or {}
        mean = row.get("mean")
        A(f"| `{name}` | {'—' if mean is None else f'{mean:.3f}'} | {row.get('applied_to', 0)} "
          f"| {row.get('not_applicable', 0)} |")
    A("")
    A(f"- malformed responses: {summary.get('malformed', 0)} of {summary.get('episodes', 0)}")
    A(f"- returned a strict subset of the tied optima: "
      f"{summary.get('returned_subset_of_tied_optima', 0)}")
    A(f"- presented a single optimum where several were tied: "
      f"{summary.get('invented_unique_optimum', 0)}")
    A("")
    A("Arm E scoring perfectly is the harness's self-test, not a result: a metric that could not")
    A("award full marks to a known-correct answer would be broken. It recomputes rather than")
    A("echoing the stored oracle, so a broken solver would show up here.")
    A("")
    A("## What this does not establish")
    A("")
    A("- No competitive claim. Arms A–D do not exist yet, so nothing here compares the engine to a")
    A("  language model, with or without generic tools.")
    A("- Nothing about any patient. Episodes are partial knowledge states over a formal graph.")
    A("- The locked splits have not been measured. They are for once, at the end.")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed episode set's seals without rebuilding")
    args = ap.parse_args()

    if args.check:
        if not EPISODES.exists():
            print(f"{EPISODES.relative_to(ROOT)} is missing: run this tool without --check")
            return 1
        stored = json.loads(EPISODES.read_text())
        problems: list[str] = []
        for source in stored["sources"]:
            recomputed = splits.seal_of(
                splits.split_episodes(
                    _reload(source), salt=f"{stored['split_salt']}:{source['name']}"
                ).locked.episodes)
            recorded = stored["splits"][source["name"]]["locked_seal"]
            if recomputed != recorded:
                problems.append(f"{source['name']}: recorded {recorded}, recomputed {recomputed}")
        if problems:
            print("POLICY_BENCHMARK_SEAL_BROKEN")
            for problem in problems:
                print("  -", problem)
            return 1
        print(f"POLICY_BENCHMARK_SEALED  {len(stored['sources'])} source(s), seals verify")
        return 0

    data = build(count=args.count, horizon=args.horizon)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EPISODES.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    REPORT.write_text(render(data))
    total = sum(len(s["episodes"]) for s in data["sources"])
    refused = sum(len(s["refused"]) for s in data["sources"])
    print("POLICY_BENCHMARK built")
    print(f"  sources            {len(data['sources'])}")
    print(f"  episodes admitted  {total}")
    print(f"  episodes refused   {refused}")
    print(f"  wrote {EPISODES.relative_to(ROOT)}")
    print(f"  wrote {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
