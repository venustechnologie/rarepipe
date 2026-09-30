"""Evaluation runner over the world split: learner + both baselines (PRD §13.4, A19–A21).

Follows the `tools/m5/sim/run.py` pattern: deterministic CRC32/hashlib seeding, recorded
provenance, and two digests so a changed commit does not break a science-content comparison.
Reward figures come only from ``RewardScorer.reward_step`` — never recomputed here.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

from rarepipe.core.provenance import source_control
from rarepipe.stages.network.model import CampaignScope, ClaimDirection, ImmutableModel
from rarepipe.stages.network.policy_q import (
    FEATURE_CONTRACT_VERSION, POLICY_ALGORITHM, ActionKind, PairedPolicyRunner,
    TabularQPolicy, run_declared_reward_training,
)
from rarepipe.stages.network.sim import scenarios as _scenarios
from rarepipe.stages.network.sim.baselines import (
    EligibleNodeHeuristicBaseline, EpisodeConstraints, FixedExpertSequenceBaseline,
    SharedResourceBudget, default_constraints, default_shared_budget,
)
from rarepipe.stages.network.sim.reward import (
    ResolutionAttempt, RewardScorer, ReportedRate, default_mva_declaration,
)
from rarepipe.stages.network.sim.splits import (
    KeyedExogenousRNG, WorldFamily, WorldSplit, catalogue_world_families, check_split_leakage,
    default_world_split,
)
from rarepipe.stages.network.sim.world import EffectDirection, ResidualFunction
from rarepipe.stages.prospective import rules
SCIENCE_DIGEST_COVERAGE = (
    "the full 64-character SHA256 of the simulated content only: canonical configuration, "
    "master seed, seed derivation, keyed stream registry, world split id/digest, leakage report, "
    "policy algorithm/feature-contract/parameter digest, and every episode reward breakdown; "
    "serialised with sorted keys. Excludes code_revision, dirty state, runtime/dependency "
    "versions, wall-clock fields, and the digests themselves, so two fresh-process runs of the "
    "same configuration agree here even when the recording commit differs."
)

RESULTS_DIGEST_COVERAGE = (
    "the full 64-character SHA256 of the whole evaluation document as written by "
    "json.dumps(indent=2, sort_keys=True), including provenance (code revision, dirty state, "
    "runtime and dependency versions), before science_digest and results_digest were added. "
    "It changes when the recording commit or environment changes, even if every simulated "
    "number is identical."
)

SEED_DERIVATION = (
    "KeyedExogenousRNG: zlib.crc32(f'{master}|exogenous|{world}|{node}|{question}|{event}') "
    "& 0xFFFFFFFF; family instance seeds via WorldFamily.instance_seed (CRC32). "
    "Never Python's per-process hash()."
)

# Family → synthetic latent kwargs. Construction goes through scenarios' latent-allowed helpers
# so this module never names the hidden-truth type (invariant scan).
_FAMILY_LATENT: dict[str, dict[str, Any]] = {
    "family-favourable": {
        "residual_function": ResidualFunction.RETAINED,
        "abundance_normalized": True,
        "nad_intracellular": EffectDirection.INCREASED,
        "functional_outcome": EffectDirection.INCREASED,
    },
    "family-informative-null": {
        "residual_function": ResidualFunction.DEFECTIVE,
        "abundance_normalized": True,
        "nad_intracellular": EffectDirection.UNCHANGED,
        "functional_outcome": EffectDirection.UNCHANGED,
    },
    "family-correlated-reports": {
        "residual_function": ResidualFunction.RETAINED,
        "abundance_normalized": True,
        "nad_intracellular": EffectDirection.INCREASED,
        "functional_outcome": EffectDirection.UNRESOLVED,
        "evidence_family_overlap": "family-correlated-shared",
    },
    "family-attractive-irrelevant": {
        "residual_function": ResidualFunction.UNKNOWN,
        "abundance_normalized": False,
        "nad_intracellular": EffectDirection.NOT_MEASURED,
        "functional_outcome": EffectDirection.UNRESOLVED,
    },
    "family-costly-high-value": {
        "residual_function": ResidualFunction.RETAINED,
        "abundance_normalized": True,
        "nad_intracellular": EffectDirection.INCREASED,
        "functional_outcome": EffectDirection.INCREASED,
    },
    "family-changed-response": {
        "residual_function": ResidualFunction.DEFECTIVE,
        "abundance_normalized": False,
        "nad_intracellular": EffectDirection.DECREASED,
        "functional_outcome": EffectDirection.DECREASED,
    },
    "family-unfavourable": {
        "residual_function": ResidualFunction.UNKNOWN,
        "abundance_normalized": False,
        "nad_intracellular": EffectDirection.NOT_MEASURED,
        "functional_outcome": EffectDirection.UNRESOLVED,
        "assay_valid": False,
    },
}

_QUESTION_EVENT: dict[str, str] = {
    "Q01": "residual_retained",
    "Q02": "intracellular_nad_up",
    "Q04": "coherent_benefit",
}


class EvaluationConfig(ImmutableModel):
    """Canonical evaluation settings. Algorithm counts are engineering, not scientific N."""

    master_seed: int = 20260930
    train_episodes_per_family: int = 2
    development_episodes_per_family: int = 1
    held_out_episodes_per_family: int = 1
    max_steps_per_episode: int = 4
    split_id: str | None = None  # None → default_world_split()

    def canonical(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def capture_provenance() -> dict[str, Any]:
    """Code revision, dirty state, runtime and dependency versions (A20 provenance half)."""
    sc = source_control()
    return {
        "code_revision": sc.commit,
        "dirty": sc.dirty,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}",
        "implementation": platform.python_implementation(),
        "dependencies": {
            "pydantic": _pkg_version("pydantic"),
            "typer": _pkg_version("typer"),
            "numpy": _pkg_version("numpy"),
        },
        "rules_version": rules.RULES_VERSION,
        "policy_algorithm": POLICY_ALGORITHM,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
    }


def make_family_world(family: WorldFamily, *, replicate: int = 0):
    """Build a synthetic ResearchWorld for a catalogue family without naming hidden-truth types."""
    kwargs = dict(_FAMILY_LATENT.get(family.family_id, _FAMILY_LATENT["family-favourable"]))
    seed = family.instance_seed(replicate)
    latent = _scenarios._base_latent(**kwargs)
    return _scenarios._world(
        CampaignScope.MVA_SCIENTIFIC, latent, seed=seed, suffix=f"{family.family_id}-r{replicate}",
    )


def _resolve_claim_for_question(question_id: str) -> ClaimDirection:
    if question_id in ("Q01", "Q02", "Q04"):
        return ClaimDirection.SUPPORTS
    return ClaimDirection.UNRESOLVED


def _apply_action_to_world(world, scorer: RewardScorer, action) -> None:
    """Deterministic synthetic reveal + score for request-like actions. Scorer owns the verdict."""
    kind = action.kind
    qid = action.question_id
    if kind not in (
        ActionKind.REQUEST_EXISTING_FINDING.value,
        ActionKind.ASK_CLARIFICATION.value,
        ActionKind.FOLLOW_UP.value,
    ):
        return
    event_key = _QUESTION_EVENT.get(qid)
    if event_key is None:
        return
    try:
        contrib = world.reveal_scientific(
            node_id=action.node_id, question_id=qid, event_key=event_key,
            question_decision=f"synthetic eval {qid}",
        )
    except ValueError:
        # Unfavourable / invalid assay worlds may refuse some event keys — leave unresolved.
        return
    scorer.score_attempt(ResolutionAttempt(
        question_id=qid, evidence_family_id=contrib.evidence_family_id,
        claimed_direction=_resolve_claim_for_question(qid),
        contribution_ids=(contrib.id,),
    ))


def _select(
    agent: Any,
    *,
    kind: Literal["learner", "expert", "heuristic"],
    observation,
    budget: SharedResourceBudget,
    constraints: EpisodeConstraints,
    mode: Literal["train", "development", "held_out"],
    step: int,
    total_steps: int,
):
    if kind == "learner":
        return agent.select(
            observation, budget, constraints, mode=mode, step=step, total_steps=total_steps,
        )
    return agent.select(observation, budget, constraints)


def _action_of(decision, *, kind: Literal["learner", "expert", "heuristic"]):
    if kind == "learner":
        return decision.selected
    return decision.action


def run_episode(
    *,
    agent: Any,
    agent_kind: Literal["learner", "expert", "heuristic"],
    agent_id: str,
    world,
    scorer: RewardScorer,
    budget: SharedResourceBudget,
    constraints: EpisodeConstraints,
    mode: Literal["train", "development", "held_out"],
    family_id: str,
    episode_index: int,
    max_steps: int,
    total_train_steps: int,
    rng: KeyedExogenousRNG,
) -> dict[str, Any]:
    """One episode. Reward breakdowns are taken from the scorer — never recomputed here."""
    # Register a keyed stream for this episode so the run record can list every derived key.
    rng.stream(node_id=agent_id, question_id=family_id, event=f"episode|{episode_index}|{mode}")
    steps: list[dict[str, Any]] = []
    prev_v = scorer.value_state.total_V
    live_budget = budget.remaining()
    training_transitions: list[tuple] = []
    terminal = False
    for step in range(max_steps):
        obs = world.policy_observation(
            prompts=(f"{mode}:{family_id}:{episode_index}:{step}",),
            feature_tensor=(("budget_remaining", float(live_budget.max_cost_units - live_budget.cost_used)),),
        )
        scorer.assert_no_policy_leak(obs)
        decision = _select(
            agent, kind=agent_kind, observation=obs, budget=live_budget,
            constraints=constraints, mode=mode, step=step, total_steps=total_train_steps,
        )
        action = _action_of(decision, kind=agent_kind)
        stopped = bool(getattr(decision, "stopped", False))
        if action is None or stopped:
            terminal = True
            breakdown = scorer.reward_step(
                previous_V=prev_v, elapsed_ticks=1, cost_units=0.0,
                contact_units=0, unsupported_decisions=0,
            )
            steps.append({
                "step": step,
                "observation_digest": obs.content_digest,
                "action": None,
                "stopped": True,
                "stop_reason": getattr(decision, "stop_reason", None),
                "reward_breakdown": breakdown.model_dump(mode="json"),
                "epsilon": getattr(decision, "epsilon", None),
            })
            break
        _apply_action_to_world(world, scorer, action)
        cost = float(action.cost_units)
        contacts = 0 if action.kind in (ActionKind.WAIT.value, ActionKind.PAUSE.value) else 1
        requests = 0 if action.kind in (ActionKind.WAIT.value, ActionKind.PAUSE.value) else 1
        breakdown = scorer.reward_step(
            previous_V=prev_v, elapsed_ticks=1, cost_units=cost,
            contact_units=contacts, unsupported_decisions=0,
            contacted_nodes=(action.node_id,) if contacts else (),
        )
        prev_v = scorer.value_state.total_V
        live_budget = live_budget.consume(ticks=1, cost=cost, contacts=contacts, requests=requests)
        steps.append({
            "step": step,
            "observation_digest": obs.content_digest,
            "action": action.model_dump(mode="json"),
            "stopped": False,
            "reward_breakdown": breakdown.model_dump(mode="json"),
            "epsilon": getattr(decision, "epsilon", None),
            "selection_probability": getattr(decision, "selection_probability", None),
        })
        if mode in ("train", "development"):
            training_transitions.append((obs, live_budget, constraints, breakdown.reward, False))
        if action.kind in (ActionKind.STOP_ROUTE.value, ActionKind.PAUSE.value):
            terminal = True
            break
        if not live_budget.can_afford(cost=0.0, contacts=0, requests=0):
            terminal = True
            break
    if training_transitions and mode in ("train", "development"):
        # Mark last transition terminal for the training loop.
        last = training_transitions[-1]
        training_transitions[-1] = (last[0], last[1], last[2], last[3], True)
    resolution = scorer.resolution_rate()
    return {
        "agent_id": agent_id,
        "agent_kind": agent_kind,
        "family_id": family_id,
        "split_role": mode,
        "episode_index": episode_index,
        "terminal": terminal,
        "steps": steps,
        "resolution_rate": resolution.model_dump(mode="json"),
        "final_V": scorer.value_state.total_V,
        "training_transitions": training_transitions,
        "budget_end": live_budget.model_dump(mode="json"),
    }


def _families_by_id() -> dict[str, WorldFamily]:
    return {f.family_id: f for f in catalogue_world_families()}


def _fit_learner(
    policy: TabularQPolicy,
    *,
    families: tuple[str, ...],
    episodes_per_family: int,
    mode: Literal["train", "development"],
    config: EvaluationConfig,
    budget: SharedResourceBudget,
    constraints: EpisodeConstraints,
    rng: KeyedExogenousRNG,
    episode_log: list[dict[str, Any]],
) -> None:
    """Fit on train/development only. Held-out families must never reach this function."""
    if mode == "held_out":  # type: ignore[comparison-overlap]
        raise ValueError("cannot fit on held-out families")
    catalogue = _families_by_id()
    total_steps = max(episodes_per_family * max(len(families), 1) * config.max_steps_per_episode, 1)
    for family_id in families:
        family = catalogue[family_id]
        for ep in range(episodes_per_family):
            world = make_family_world(family, replicate=ep)
            scorer = RewardScorer(world, default_mva_declaration())
            record = run_episode(
                agent=policy, agent_kind="learner", agent_id=policy.policy_id,
                world=world, scorer=scorer, budget=budget, constraints=constraints,
                mode=mode, family_id=family_id, episode_index=ep,
                max_steps=config.max_steps_per_episode, total_train_steps=total_steps, rng=rng,
            )
            transitions = record.pop("training_transitions")
            episode_log.append(record)
            if transitions:
                run_declared_reward_training(
                    policy, transitions=transitions, split_role=mode, total_steps=total_steps,
                )


def _evaluate_agent(
    agent: Any,
    *,
    agent_kind: Literal["learner", "expert", "heuristic"],
    agent_id: str,
    families: tuple[str, ...],
    episodes_per_family: int,
    config: EvaluationConfig,
    budget: SharedResourceBudget,
    constraints: EpisodeConstraints,
    rng: KeyedExogenousRNG,
) -> list[dict[str, Any]]:
    catalogue = _families_by_id()
    out: list[dict[str, Any]] = []
    total_steps = max(episodes_per_family * max(len(families), 1) * config.max_steps_per_episode, 1)
    for family_id in families:
        family = catalogue[family_id]
        for ep in range(episodes_per_family):
            if agent_kind == "expert":
                agent.reset()
            elif agent_kind == "heuristic":
                agent.reset()
            world = make_family_world(family, replicate=ep + 1000)
            scorer = RewardScorer(world, default_mva_declaration())
            record = run_episode(
                agent=agent, agent_kind=agent_kind, agent_id=agent_id,
                world=world, scorer=scorer, budget=budget, constraints=constraints,
                mode="held_out", family_id=family_id, episode_index=ep,
                max_steps=config.max_steps_per_episode, total_train_steps=total_steps, rng=rng,
            )
            record.pop("training_transitions", None)
            out.append(record)
    return out


def _mean_episode_reward(episodes: list[dict[str, Any]]) -> ReportedRate:
    """Count episodes whose cumulative reward is strictly positive (replicate-level binary)."""
    n = len(episodes)
    wins = 0
    for ep in episodes:
        total = sum(float(s["reward_breakdown"]["reward"]) for s in ep["steps"])
        if total > 0:
            wins += 1
    return ReportedRate(
        name="episodes_with_positive_cumulative_reward",
        numerator=wins,
        denominator=n,
    )


def run_evaluation(config: EvaluationConfig | None = None) -> dict[str, Any]:
    """Train on train_families, tune on development, evaluate held-out with epsilon zero."""
    config = config or EvaluationConfig()
    split: WorldSplit = default_world_split()
    if config.split_id is not None and config.split_id != split.split_id:
        raise ValueError(f"unknown split_id {config.split_id!r}; only {split.split_id!r} is shipped")
    leakage = check_split_leakage(split)
    budget = default_shared_budget()
    constraints = default_constraints()
    rng = KeyedExogenousRNG(config.master_seed, world_id="evaluation-runner")
    # Master stream registration for the run itself.
    rng.stream(node_id="runner", question_id="eval", event="master")

    policy = TabularQPolicy(master_seed=config.master_seed, world_id="eval-learner")
    expert = FixedExpertSequenceBaseline()
    heuristic = EligibleNodeHeuristicBaseline()

    train_log: list[dict[str, Any]] = []
    _fit_learner(
        policy, families=split.train_families,
        episodes_per_family=config.train_episodes_per_family, mode="train",
        config=config, budget=budget, constraints=constraints, rng=rng, episode_log=train_log,
    )
    families_fit = list(split.train_families)
    if split.development_families and config.development_episodes_per_family > 0:
        _fit_learner(
            policy, families=split.development_families,
            episodes_per_family=config.development_episodes_per_family, mode="development",
            config=config, budget=budget, constraints=constraints, rng=rng, episode_log=train_log,
        )
        families_fit.extend(split.development_families)

    # Held-out must never appear in families_fit.
    held_out_fit = sorted(set(families_fit) & set(split.held_out_families))
    if held_out_fit:
        raise RuntimeError(f"held-out families were fit on: {held_out_fit}")

    params = policy.persist()
    held_learner = _evaluate_agent(
        policy, agent_kind="learner", agent_id=policy.policy_id,
        families=split.held_out_families,
        episodes_per_family=config.held_out_episodes_per_family,
        config=config, budget=budget, constraints=constraints, rng=rng,
    )
    held_expert = _evaluate_agent(
        expert, agent_kind="expert", agent_id=expert.baseline_id,
        families=split.held_out_families,
        episodes_per_family=config.held_out_episodes_per_family,
        config=config, budget=budget, constraints=constraints, rng=rng,
    )
    held_heur = _evaluate_agent(
        heuristic, agent_kind="heuristic", agent_id=heuristic.baseline_id,
        families=split.held_out_families,
        episodes_per_family=config.held_out_episodes_per_family,
        config=config, budget=budget, constraints=constraints, rng=rng,
    )

    # A19: one shared observation + budget snapshot for the three agents.
    probe_family = _families_by_id()[split.held_out_families[0]]
    probe_world = make_family_world(probe_family, replicate=0)
    probe_obs = probe_world.policy_observation(prompts=("a19-shared-probe",))
    paired = PairedPolicyRunner(policy=policy, budget=budget, constraints=constraints)
    learner_d, expert_d, heur_d = paired.decide_all(probe_obs)
    a19 = {
        "observation_digest": probe_obs.content_digest,
        "learner_observation_digest": learner_d.observation_digest,
        "expert_observation_digest": expert_d.observation_digest,
        "heuristic_observation_digest": heur_d.observation_digest,
        "shared_budget": budget.model_dump(mode="json"),
        "shared_constraints": constraints.model_dump(mode="json"),
        "learner_epsilon_held_out": learner_d.epsilon,
        "learner_mode": learner_d.mode,
        "families_fit": tuple(families_fit),
        "held_out_families": tuple(split.held_out_families),
        "held_out_families_fit": False,
        "same_observation_contract": (
            learner_d.observation_digest == expert_d.observation_digest
            == heur_d.observation_digest == probe_obs.content_digest
        ),
        "same_budget": (
            expert_d.budget.model_dump() == heur_d.budget.model_dump()
            == budget.model_dump()
        ),
    }

    rates = {
        "learner_held_out": _mean_episode_reward(held_learner).model_dump(mode="json"),
        "expert_held_out": _mean_episode_reward(held_expert).model_dump(mode="json"),
        "heuristic_held_out": _mean_episode_reward(held_heur).model_dump(mode="json"),
        "leakage": leakage.leakage_rate(),
    }

    provenance = capture_provenance()
    results: dict[str, Any] = {
        "generated_by": "rarepipe.stages.network.evaluate",
        "configuration": config.canonical(),
        "seed_derivation": SEED_DERIVATION,
        "master_seed": config.master_seed,
        "keyed_streams": rng.registered(),
        "world_split": {
            "split_id": split.split_id,
            "content_digest": split.content_digest,
            "train_families": list(split.train_families),
            "development_families": list(split.development_families),
            "held_out_families": list(split.held_out_families),
        },
        "leakage_report": leakage.model_dump(mode="json"),
        "policy_version": {
            "policy_id": policy.policy_id,
            "algorithm": params.algorithm,
            "feature_contract_version": params.feature_contract_version,
            "parameter_digest": params.content_digest,
            "update_count": params.update_count,
            "training_events": params.training_events,
        },
        "a19_equivalence": a19,
        "train_episodes": train_log,
        "held_out_episodes": {
            "learner": held_learner,
            "fixed_expert_sequence": held_expert,
            "eligible_node_heuristic": held_heur,
        },
        "rates": rates,
        "caveat": (
            "Every reward and rate below is conditional on the synthetic world families and the "
            "toy benchmark reward declaration. A simulated improvement is not a clinical benefit, "
            "not a measured institutional response probability, and not evidence about any patient."
        ),
        **provenance,
    }
    return attach_digests(results)


def attach_digests(results: dict[str, Any]) -> dict[str, Any]:
    """Two digests, as in tools/m5/sim/run.py — science content vs whole document with provenance."""
    science_body = {
        "configuration": results["configuration"],
        "master_seed": results["master_seed"],
        "seed_derivation": results["seed_derivation"],
        "keyed_streams": results["keyed_streams"],
        "world_split": results["world_split"],
        "leakage_report": results["leakage_report"],
        "policy_version": {
            "policy_id": results["policy_version"]["policy_id"],
            "algorithm": results["policy_version"]["algorithm"],
            "feature_contract_version": results["policy_version"]["feature_contract_version"],
            "parameter_digest": results["policy_version"]["parameter_digest"],
            "update_count": results["policy_version"]["update_count"],
            "training_events": results["policy_version"]["training_events"],
        },
        "a19_equivalence": {
            k: results["a19_equivalence"][k]
            for k in (
                "observation_digest", "shared_budget", "shared_constraints",
                "learner_epsilon_held_out", "learner_mode", "families_fit",
                "held_out_families", "held_out_families_fit",
                "same_observation_contract", "same_budget",
            )
        },
        "train_episodes": results["train_episodes"],
        "held_out_episodes": results["held_out_episodes"],
        "rates": results["rates"],
        "caveat": results["caveat"],
    }
    science_text = json.dumps(science_body, indent=2, sort_keys=True)
    # Whole document before digests are attached (m5 pattern).
    pre_digest = {k: v for k, v in results.items() if k not in ("science_digest", "results_digest")}
    whole_text = json.dumps(pre_digest, indent=2, sort_keys=True)
    results["science_digest"] = {
        "sha256": hashlib.sha256(science_text.encode()).hexdigest(),
        "covers": SCIENCE_DIGEST_COVERAGE,
    }
    results["results_digest"] = {
        "sha256": hashlib.sha256(whole_text.encode()).hexdigest(),
        "covers": RESULTS_DIGEST_COVERAGE,
    }
    return results


PROVENANCE_FIELDS_THAT_MAY_DIFFER = (
    "code_revision",
    "dirty",
    "python",
    "platform",
    "implementation",
    "dependencies",
    "results_digest",
)


def science_digests_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a["science_digest"]["sha256"] == b["science_digest"]["sha256"]


def write_run_record(path: Path, results: dict[str, Any] | None = None) -> Path:
    results = results or run_evaluation()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    """CLI entry used by the A20 cross-process test and the typer group."""
    argv = list(sys.argv[1:] if argv is None else argv)
    out: Path | None = None
    seed = 20260930
    train_eps = 2
    held_eps = 1
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out = Path(argv[i + 1]); i += 2; continue
        if argv[i] == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--train-episodes" and i + 1 < len(argv):
            train_eps = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--held-out-episodes" and i + 1 < len(argv):
            held_eps = int(argv[i + 1]); i += 2; continue
        if argv[i] in ("-h", "--help"):
            print("usage: evaluate [--out PATH] [--seed N] [--train-episodes N] [--held-out-episodes N]")
            return 0
        print(f"unknown argument: {argv[i]}", file=sys.stderr)
        return 2
    cfg = EvaluationConfig(
        master_seed=seed,
        train_episodes_per_family=train_eps,
        development_episodes_per_family=1 if train_eps > 0 else 0,
        held_out_episodes_per_family=held_eps,
    )
    results = run_evaluation(cfg)
    text = json.dumps(results, indent=2, sort_keys=True) + "\n"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"wrote {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
