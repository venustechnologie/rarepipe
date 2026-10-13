"""Development / validation / locked splits, assigned by content and sealed.

The specification requires the test set to be frozen *before* prompts or algorithms are tuned. A
promise to do that is not a control; these two mechanisms are:

**Assignment is by content, not by order.** An episode's split comes from a digest of its own id
and the split salt, so it cannot drift when episodes are added, removed or reordered. Adding a
hundred new episodes leaves every existing assignment exactly where it was — which is what makes
it safe to grow the benchmark without quietly reshuffling what is locked.

**The locked split carries a seal.** A digest over the locked episodes and their oracle answers,
recorded when the split is created. If anyone regenerates, re-splits or edits the locked set, the
seal stops matching and ``verify`` says so. The seal is computed from the content, never written by
hand — a digest somebody typed is a claim nothing checked, and this repository has had one of those
reach a reviewer.

What the seal cannot do is stop someone looking at the locked episodes. Nothing in a repository
can. What it does is make a changed locked set detectable, so a competitive number can be traced to
the exact set it was measured on.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from rarepipe.stages.control.benchmark.episodes import Episode

DEVELOPMENT, VALIDATION, LOCKED = "development", "validation", "locked"
SPLITS = (DEVELOPMENT, VALIDATION, LOCKED)

# Deliberately not 1/3 each. Development is where iteration happens and wants the most episodes;
# the locked set only has to be large enough to measure, and every episode in it is one that can
# never inform a design decision.
DEFAULT_WEIGHTS = {DEVELOPMENT: 0.5, VALIDATION: 0.2, LOCKED: 0.3}


class SealError(ValueError):
    pass


def assign(episode_identifier: str, *, salt: str,
           weights: dict[str, float] | None = None) -> str:
    """Which split an episode belongs to, from its own id. Stable across processes and runs.

    sha256 rather than the builtin ``hash``, which is randomised per process: a split built on it
    would move episodes between development and locked on every run, which is the one thing a
    locked split must never do.
    """
    weights = weights or DEFAULT_WEIGHTS
    total = sum(weights[name] for name in SPLITS)
    digest = hashlib.sha256(f"{salt}:{episode_identifier}".encode()).digest()
    # 8 bytes of the digest as a fraction of its range: a uniform point in [0, 1).
    point = int.from_bytes(digest[:8], "big") / float(1 << 64) * total
    running = 0.0
    for name in SPLITS:
        running += weights[name]
        if point < running:
            return name
    return SPLITS[-1]


@dataclass(frozen=True)
class Split:
    name: str
    episodes: tuple[Episode, ...]

    def ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.episodes)


@dataclass(frozen=True)
class SplitSet:
    salt: str
    weights: dict[str, float]
    development: Split
    validation: Split
    locked: Split
    locked_seal: str

    def by_name(self, name: str) -> Split:
        return {DEVELOPMENT: self.development, VALIDATION: self.validation,
                LOCKED: self.locked}[name]

    def describe(self) -> dict:
        return {
            "salt": self.salt,
            "weights": self.weights,
            "counts": {name: len(self.by_name(name).episodes) for name in SPLITS},
            "locked_seal": self.locked_seal,
            "locked_episode_ids": list(self.locked.ids()),
            "note": ("The locked split is sealed over its episodes and their oracle answers. A "
                     "number measured on it can be traced to exactly this set; if the set changes, "
                     "the seal stops matching."),
        }

    def verify(self) -> None:
        """Raise if the locked split no longer matches the seal recorded when it was created."""
        recomputed = seal_of(self.locked.episodes)
        if recomputed != self.locked_seal:
            raise SealError(
                f"the locked split does not match its seal: recorded {self.locked_seal}, "
                f"recomputed {recomputed}. It has been regenerated, re-split or edited, so any "
                f"number measured against the recorded seal is not a number about this set.")


def seal_of(episodes: tuple[Episode, ...]) -> str:
    """A content digest over the episodes and their oracle answers, in a canonical order."""
    payload = json.dumps(
        [episode.describe() for episode in sorted(episodes, key=lambda e: e.id)],
        sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def split_episodes(episodes: tuple[Episode, ...], *, salt: str,
                   weights: dict[str, float] | None = None) -> SplitSet:
    weights = dict(weights or DEFAULT_WEIGHTS)
    if set(weights) != set(SPLITS):
        raise SealError(f"weights must name exactly {SPLITS}, got {sorted(weights)}")
    if any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise SealError("weights must be non-negative and sum to more than zero")

    buckets: dict[str, list[Episode]] = {name: [] for name in SPLITS}
    for episode in episodes:
        buckets[assign(episode.id, salt=salt, weights=weights)].append(episode)
    made = {
        name: Split(name=name, episodes=tuple(sorted(buckets[name], key=lambda e: e.id)))
        for name in SPLITS
    }
    return SplitSet(
        salt=salt, weights=weights,
        development=made[DEVELOPMENT], validation=made[VALIDATION], locked=made[LOCKED],
        locked_seal=seal_of(made[LOCKED].episodes),
    )
