"""Disjoint train/development/held-out world families (PRD §13.4).

Splits are over world FAMILIES or parameter regions, not merely distinct seeds. A split that
differs only by seed is rejected. Keyed exogenous randomness is indexed by world, node,
question and event so action order does not silently change the underlying institution.
"""

from __future__ import annotations

import hashlib
import zlib
from enum import StrEnum
from typing import Any

from pydantic import model_validator

from rarepipe.stages.network.model import ImmutableModel
from rarepipe.stages.network.sim.institution import AssumptionLabel, LabeledParam
from rarepipe.stages.prospective.store import content_digest

SPLIT_DIGEST_COVERAGE = (
    "family ids, parameter-region keys, role assignments, scenario traits, keyed stream "
    "names; excludes content_digest itself, wall-clock timestamps, and process paths"
)


class SplitRole(StrEnum):
    TRAIN = "train"
    DEVELOPMENT = "development"
    HELD_OUT = "held_out"


class ScenarioTrait(StrEnum):
    """Required diversity traits across the split catalogue."""

    INFORMATIVE_NULL = "informative_null"
    ATTRACTIVE_IRRELEVANT = "attractive_irrelevant_reply"
    CORRELATED_REPORTS = "correlated_reports"
    COSTLY_HIGH_VALUE = "costly_high_value_answer"
    CHANGED_RESPONSE_PATTERN = "changed_response_pattern"


class ParameterRegion(ImmutableModel):
    """A region in assumption-parameter space — distinct from a random seed."""

    region_id: str
    family_id: str
    params: tuple[LabeledParam, ...]
    traits: tuple[ScenarioTrait, ...] = ()

    def fingerprint(self) -> str:
        """Stable identity of the parameter region (family-name and seed independent)."""
        body = {
            "region_id": self.region_id,
            "params": [p.model_dump(mode="json") for p in self.params],
            "traits": [t.value for t in self.traits],
        }
        return content_digest(body)


class WorldFamily(ImmutableModel):
    """Named world family. Members share a parameter region; seeds vary within the family."""

    family_id: str
    description: str
    region: ParameterRegion
    default_master_seed: int
    scenario_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _region_matches_family(self):
        if self.region.family_id != self.family_id:
            raise ValueError("parameter region family_id must match the world family")
        return self

    def instance_seed(self, replicate: int) -> int:
        """Derive a replicate seed without making seed the split axis."""
        material = f"{self.family_id}|{self.default_master_seed}|rep|{replicate}".encode()
        return zlib.crc32(material) & 0xFFFFFFFF


class SeedOnlySplitError(ValueError):
    """Raised when a proposed split differs only by seed — holding out seeds alone is insufficient."""


class WorldSplit(ImmutableModel):
    """Disjoint assignment of world families to train / development / held-out roles."""

    split_id: str
    train_families: tuple[str, ...]
    development_families: tuple[str, ...]
    held_out_families: tuple[str, ...]
    regions: tuple[ParameterRegion, ...]
    content_digest: str | None = None

    @model_validator(mode="after")
    def _disjoint_and_not_seed_only(self):
        roles = {
            SplitRole.TRAIN: set(self.train_families),
            SplitRole.DEVELOPMENT: set(self.development_families),
            SplitRole.HELD_OUT: set(self.held_out_families),
        }
        if not roles[SplitRole.TRAIN] or not roles[SplitRole.HELD_OUT]:
            raise ValueError("split requires non-empty train and held_out family sets")
        for a, b in (
            (SplitRole.TRAIN, SplitRole.DEVELOPMENT),
            (SplitRole.TRAIN, SplitRole.HELD_OUT),
            (SplitRole.DEVELOPMENT, SplitRole.HELD_OUT),
        ):
            overlap = roles[a] & roles[b]
            if overlap:
                raise ValueError(f"family overlap between {a.value} and {b.value}: {sorted(overlap)}")

        region_by_family = {r.family_id: r for r in self.regions}
        missing = (roles[SplitRole.TRAIN] | roles[SplitRole.DEVELOPMENT] | roles[SplitRole.HELD_OUT]) - set(
            region_by_family
        )
        if missing:
            raise ValueError(f"split references families without parameter regions: {sorted(missing)}")

        # Seed-only rejection: every role-pair must differ in parameter-region fingerprint,
        # not merely in family_id strings that alias the same region.
        fps = {fid: region_by_family[fid].fingerprint() for fid in region_by_family}
        train_fps = {fps[f] for f in roles[SplitRole.TRAIN]}
        held_fps = {fps[f] for f in roles[SplitRole.HELD_OUT]}
        if train_fps == held_fps and roles[SplitRole.TRAIN] != roles[SplitRole.HELD_OUT]:
            raise SeedOnlySplitError(
                "held-out families share identical parameter-region fingerprints with train; "
                "holding out random seeds / renamed aliases alone is insufficient"
            )
        if train_fps & held_fps:
            raise SeedOnlySplitError(
                "train and held-out share a parameter-region fingerprint; "
                "splits must separate families or parameter regions, not seeds alone"
            )
        if roles[SplitRole.DEVELOPMENT]:
            dev_fps = {fps[f] for f in roles[SplitRole.DEVELOPMENT]}
            if dev_fps & train_fps or dev_fps & held_fps:
                raise SeedOnlySplitError(
                    "development shares a parameter-region fingerprint with train or held-out"
                )
        return self

    def with_digest(self) -> WorldSplit:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return WorldSplit(**data)

    def role_of(self, family_id: str) -> SplitRole:
        if family_id in self.train_families:
            return SplitRole.TRAIN
        if family_id in self.development_families:
            return SplitRole.DEVELOPMENT
        if family_id in self.held_out_families:
            return SplitRole.HELD_OUT
        raise KeyError(family_id)


class LeakageReport(ImmutableModel):
    """Result of checking that held-out regions do not leak into train."""

    passed: bool
    shared_family_ids: tuple[str, ...] = ()
    shared_region_fingerprints: tuple[str, ...] = ()
    shared_traits_only_ok: bool = True
    details: tuple[str, ...] = ()
    numerator_held_out_families: int = 0
    denominator_held_out_families: int = 0

    def leakage_rate(self) -> dict[str, Any]:
        """A21: rates carry numerator and denominator."""
        leaked = len(self.shared_family_ids) + len(self.shared_region_fingerprints)
        # Denominator is held-out family count; numerator is families that leaked.
        n = self.numerator_held_out_families
        d = self.denominator_held_out_families
        return {
            "name": "held_out_family_leakage",
            "numerator": n,
            "denominator": d,
            "point": (n / d) if d else None,
            "interval_applies": d > 0,
            "no_interval_reason": None if d > 0 else "no held-out families",
            "passed": self.passed,
            "raw_overlap_tokens": leaked,
        }


def check_split_leakage(split: WorldSplit) -> LeakageReport:
    """Leakage check: train/dev/held-out family ids and region fingerprints must be disjoint."""
    train = set(split.train_families)
    dev = set(split.development_families)
    held = set(split.held_out_families)
    shared_families = sorted((train & held) | (train & dev) | (dev & held))
    region_by_family = {r.family_id: r for r in split.regions}
    train_fp = {region_by_family[f].fingerprint() for f in train if f in region_by_family}
    held_fp = {region_by_family[f].fingerprint() for f in held if f in region_by_family}
    dev_fp = {region_by_family[f].fingerprint() for f in dev if f in region_by_family}
    shared_fps = sorted((train_fp & held_fp) | (train_fp & dev_fp) | (dev_fp & held_fp))
    leaked_held = sum(
        1 for f in held
        if f in train or f in dev
        or (f in region_by_family and region_by_family[f].fingerprint() in (train_fp | dev_fp))
    )
    passed = not shared_families and not shared_fps
    details: list[str] = []
    if shared_families:
        details.append(f"shared_family_ids={shared_families}")
    if shared_fps:
        details.append(f"shared_region_fingerprints={len(shared_fps)}")
    if passed:
        details.append("no family or parameter-region leakage detected")
    return LeakageReport(
        passed=passed,
        shared_family_ids=tuple(shared_families),
        shared_region_fingerprints=tuple(shared_fps),
        numerator_held_out_families=leaked_held,
        denominator_held_out_families=len(held),
        details=tuple(details),
    )


def refuse_seed_only_split(
    *,
    train_seeds: tuple[int, ...],
    held_out_seeds: tuple[int, ...],
    shared_region: ParameterRegion,
) -> None:
    """Explicit API: a seed-only holdout with one shared parameter region is refused."""
    # Build aliased families that differ only by seed / name, then reject before construct.
    train_families = []
    held_families = []
    regions = []
    for i, seed in enumerate(train_seeds):
        fid = f"alias-train-{i}-seed-{seed}"
        train_families.append(fid)
        regions.append(ParameterRegion(
            region_id=shared_region.region_id, family_id=fid,
            params=shared_region.params, traits=shared_region.traits,
        ))
    for i, seed in enumerate(held_out_seeds):
        fid = f"alias-held-{i}-seed-{seed}"
        held_families.append(fid)
        regions.append(ParameterRegion(
            region_id=shared_region.region_id, family_id=fid,
            params=shared_region.params, traits=shared_region.traits,
        ))
    train_fps = {r.fingerprint() for r in regions if r.family_id in train_families}
    held_fps = {r.fingerprint() for r in regions if r.family_id in held_families}
    if train_fps & held_fps:
        raise SeedOnlySplitError(
            "held-out families share identical parameter-region fingerprints with train; "
            "holding out random seeds / renamed aliases alone is insufficient"
        )
    # If fingerprints somehow differ, still construct — WorldSplit enforces the same rule.
    WorldSplit(
        split_id="seed-only-rejected",
        train_families=tuple(train_families),
        development_families=(),
        held_out_families=tuple(held_families),
        regions=tuple(regions),
    )


class KeyedExogenousRNG:
    """Exogenous randomness indexed by world, node, question and event.

    A different action ORDER must not silently generate a different underlying institution.
    Time-dependent capacity remains allowed when the world declares it explicitly.
    """

    def __init__(self, master_seed: int, *, world_id: str):
        self.master_seed = master_seed
        self.world_id = world_id
        self._streams: dict[str, int] = {}
        self._values: dict[int, str] = {}

    def key(self, *, node_id: str, question_id: str, event: str) -> str:
        return f"{self.world_id}|{node_id}|{question_id}|{event}"

    def stream(self, *, node_id: str, question_id: str, event: str) -> int:
        name = self.key(node_id=node_id, question_id=question_id, event=event)
        if name in self._streams:
            return self._streams[name]
        material = f"{self.master_seed}|exogenous|{name}".encode()
        seed = zlib.crc32(material) & 0xFFFFFFFF
        owner = self._values.get(seed)
        if owner is not None and owner != name:
            raise ValueError(f"exogenous stream collision between {owner!r} and {name!r}")
        self._streams[name] = seed
        self._values[seed] = name
        return seed

    def draw_u01(self, *, node_id: str, question_id: str, event: str) -> float:
        """Deterministic unit interval draw; independent of action order."""
        seed = self.stream(node_id=node_id, question_id=question_id, event=event)
        # Hash the seed to a float in [0, 1). Same key ⇒ same draw regardless of call order.
        digest = hashlib.sha256(f"u01|{seed}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def registered(self) -> dict[str, int]:
        return dict(self._streams)


def _param(name: str, value: Any, label: AssumptionLabel, note: str = "") -> LabeledParam:
    return LabeledParam(name=name, value=value, label=label, note=note)


def catalogue_world_families() -> tuple[WorldFamily, ...]:
    """Canonical families covering the required diversity traits."""
    favourable = ParameterRegion(
        region_id="region-favourable-response",
        family_id="family-favourable",
        params=(
            _param("response_pattern", "prompt_existing_finding", AssumptionLabel.ASSUME),
            _param("cost_scale", 1.0, AssumptionLabel.ASSUME),
        ),
        traits=(ScenarioTrait.INFORMATIVE_NULL,),
    )
    nulls = ParameterRegion(
        region_id="region-informative-null",
        family_id="family-informative-null",
        params=(
            _param("response_pattern", "measured_no_effect", AssumptionLabel.ASSUME,
                   note="informative null; not a missing reply"),
            _param("null_endpoint", "cellular_function", AssumptionLabel.ASSUME),
        ),
        traits=(ScenarioTrait.INFORMATIVE_NULL,),
    )
    attractive = ParameterRegion(
        region_id="region-attractive-irrelevant",
        family_id="family-attractive-irrelevant",
        params=(
            _param("response_pattern", "partner_availability_only", AssumptionLabel.STRESS),
            _param("attractive_but", "no_mva_evidence", AssumptionLabel.STRESS),
        ),
        traits=(ScenarioTrait.ATTRACTIVE_IRRELEVANT,),
    )
    correlated = ParameterRegion(
        region_id="region-correlated-reports",
        family_id="family-correlated-reports",
        params=(
            _param("response_pattern", "shared_evidence_family", AssumptionLabel.ASSUME),
            _param("evidence_overlap", True, AssumptionLabel.ASSUME),
        ),
        traits=(ScenarioTrait.CORRELATED_REPORTS,),
    )
    costly = ParameterRegion(
        region_id="region-costly-high-value",
        family_id="family-costly-high-value",
        params=(
            _param("response_pattern", "valid_functional_benefit", AssumptionLabel.ASSUME),
            _param("cost_scale", 5.0, AssumptionLabel.STRESS, note="costly high-value answer"),
            _param("value_units", 1.0, AssumptionLabel.ASSUME,
                   note="SYNTHETIC BENCHMARK CONVENTION value, not clinical utility"),
        ),
        traits=(ScenarioTrait.COSTLY_HIGH_VALUE,),
    )
    changed = ParameterRegion(
        region_id="region-changed-response",
        family_id="family-changed-response",
        params=(
            _param("response_pattern", "workload_defer_then_reply", AssumptionLabel.UNFAVOURABLE),
            _param("latency_ticks", 12, AssumptionLabel.UNFAVOURABLE),
        ),
        traits=(ScenarioTrait.CHANGED_RESPONSE_PATTERN,),
    )
    unfavourable = ParameterRegion(
        region_id="region-unfavourable-refusal",
        family_id="family-unfavourable",
        params=(
            _param("response_pattern", "refusal_and_nonresponse", AssumptionLabel.UNFAVOURABLE),
            _param("response_probability", 0.05, AssumptionLabel.UNFAVOURABLE),
        ),
        traits=(ScenarioTrait.CHANGED_RESPONSE_PATTERN, ScenarioTrait.INFORMATIVE_NULL),
    )
    return (
        WorldFamily(family_id="family-favourable", description="prompt existing findings",
                    region=favourable, default_master_seed=101,
                    scenario_ids=("S01", "S04", "S07")),
        WorldFamily(family_id="family-informative-null", description="informative null results",
                    region=nulls, default_master_seed=102,
                    scenario_ids=("S02", "S03")),
        WorldFamily(family_id="family-attractive-irrelevant",
                    description="attractive irrelevant replies",
                    region=attractive, default_master_seed=103,
                    scenario_ids=("S16",)),
        WorldFamily(family_id="family-correlated-reports",
                    description="correlated / overlapping reports",
                    region=correlated, default_master_seed=104,
                    scenario_ids=("S08", "S09")),
        WorldFamily(family_id="family-costly-high-value",
                    description="costly high-value answers",
                    region=costly, default_master_seed=105,
                    scenario_ids=("S07",)),
        WorldFamily(family_id="family-changed-response",
                    description="changed response patterns under stress",
                    region=changed, default_master_seed=106,
                    scenario_ids=("S11", "S15")),
        WorldFamily(family_id="family-unfavourable",
                    description="refusals and near-nonresponse",
                    region=unfavourable, default_master_seed=107,
                    scenario_ids=("S11", "S12", "S13")),
    )


def default_world_split() -> WorldSplit:
    """Canonical disjoint family split defined before evaluation."""
    families = {f.family_id: f for f in catalogue_world_families()}
    split = WorldSplit(
        split_id="network-sim-split-v1",
        train_families=("family-favourable", "family-informative-null", "family-correlated-reports"),
        development_families=("family-attractive-irrelevant",),
        held_out_families=("family-costly-high-value", "family-changed-response", "family-unfavourable"),
        regions=tuple(families[fid].region for fid in (
            "family-favourable", "family-informative-null", "family-correlated-reports",
            "family-attractive-irrelevant", "family-costly-high-value",
            "family-changed-response", "family-unfavourable",
        )),
    )
    return split.with_digest()


def required_traits_present(families: tuple[WorldFamily, ...] | None = None) -> dict[str, Any]:
    """Verify the catalogue covers every required diversity trait; returns a counted rate."""
    families = families or catalogue_world_families()
    present = {trait for fam in families for trait in fam.region.traits}
    required = set(ScenarioTrait)
    missing = sorted(t.value for t in (required - present))
    found = len(required & present)
    total = len(required)
    return {
        "name": "required_scenario_traits_present",
        "numerator": found,
        "denominator": total,
        "point": found / total if total else None,
        "missing": missing,
        "interval_applies": False,
        "no_interval_reason": "catalogue coverage is a fixed design check, not a sampling rate",
    }
