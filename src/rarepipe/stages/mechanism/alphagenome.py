"""AlphaGenome Atlas as an evidence source, under the same disclosure rule as everything else.

The Atlas precomputes predictions for every possible single-nucleotide variant, and its client
exposes `query_interval`, which returns scores for *all* variants in a genomic window. That is what
makes this usable here: we ask a public question about a public gene region, cache the answer, and
match the child's allele against the cache locally. Google learns that someone is studying BUB1B.
It does not learn what this child carries.

Two commands, split the same way as the literature corpus:

    alphagenome fetch-region   networked; takes a gene or interval; never opens a case artifact
    alphagenome match          offline; opens the case; never touches the network

The output is a computational prediction, not a measurement. It enters the dossier as
`EvidenceLevel.COMPUTATIONAL`, which by construction cannot establish a functional claim — it can
only appear as indirect evidence beside one. That is the correct weight for a model that its
authors say is not validated for clinical use.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from rarepipe.core.artifacts import utc_now
from rarepipe.core.redaction import restricted

ENSEMBL_LOOKUP = "https://rest.ensembl.org/lookup/symbol/homo_sapiens/{gene}?expand=0;content-type=application/json"
PACKAGE = "alphagenome"
MIN_REGION_WIDTH = 2000  # a window narrow enough to imply a variant is not a public question


class AlphaGenomeError(RuntimeError):
    pass


class RegionProvenance(BaseModel):
    """Where the queried window came from. It must be derived from public annotation, not the case."""

    gene_symbol: str | None = None
    chromosome: str
    start: int
    end: int
    width: int
    assembly: str = "GRCh38"
    derived_from: str = Field(description="The public source the interval came from.")
    ensembl_id: str | None = None


class AtlasPrediction(BaseModel):
    """One precomputed prediction, as returned for a public hypothetical variant."""

    chromosome: str
    position: int
    ref: str
    alt: str
    scores: dict[str, float] = Field(default_factory=dict)


class AlphaGenomeEvidence(BaseModel):
    """The case-specific read-out, produced locally by matching against the cached region."""

    source: str = "AlphaGenome Atlas"
    package_version: str | None = None
    atlas_release: str | None = None
    query_scope: str
    private_variant_transmitted: bool = Field(
        False, description="Always false: the region is public and the match is local.")
    region: RegionProvenance
    variant_role: str
    local_match_found: bool = False
    scores: dict[str, float] = restricted(dict)
    neighbourhood: dict[str, Any] = Field(
        default_factory=dict,
        description="Where this variant sits among all possible substitutions in the window — rank and "
                    "percentile, which say more than a lone score.")
    evidence_type: str = "computational_prediction"
    scope: str = "exact_variant"
    limitations: list[str] = Field(default_factory=lambda: [
        "a model prediction, not an experimental measurement",
        "AlphaGenome is not validated or approved for clinical use",
        "not diploid-aware: each allele is scored independently, so this says nothing about the "
        "compound-heterozygous state",
        "tissue and cell-type coverage is the model's, not this child's",
    ])
    retrieved_at: str | None = None
    cache_digest: str | None = None


class VariantMechanismProvider(Protocol):
    """So rarepipe never becomes structurally dependent on one free research endpoint."""

    name: str

    def region_scores(self, region: RegionProvenance, scorers: list[str]) -> list[AtlasPrediction]: ...

    def available_scorers(self) -> list[str]: ...


def public_region(gene: str) -> RegionProvenance:
    """Resolve a gene's public coordinates. Called only by the networked half, never with case data."""
    with urllib.request.urlopen(ENSEMBL_LOOKUP.format(gene=gene), timeout=60) as resp:
        payload = json.load(resp)
    chromosome = f"chr{payload['seq_region_name']}"
    start, end = int(payload["start"]), int(payload["end"])
    return RegionProvenance(gene_symbol=gene, chromosome=chromosome, start=start, end=end,
                            width=end - start, assembly=payload.get("assembly_name", "GRCh38"),
                            derived_from="Ensembl REST lookup/symbol (public gene annotation)",
                            ensembl_id=payload.get("id"))


def check_region_is_public(region: RegionProvenance) -> None:
    """A window tight enough to identify one variant is not a public question any more."""
    if region.width < MIN_REGION_WIDTH:
        raise AlphaGenomeError(
            f"refusing to query a {region.width} bp window: a region this narrow would disclose the "
            f"variant it was drawn around. Query a gene or an exon, and match locally.")
    if region.derived_from.startswith("case"):
        raise AlphaGenomeError("the queried interval must come from public annotation, not from the case")


@dataclass
class AtlasProvider:
    """The real client. Imported lazily so the pipeline runs without the SDK installed."""

    api_key: str
    name: str = "alphagenome_atlas"
    timeout: float = 120.0
    _client: Any = field(default=None, repr=False)

    def client(self):
        if self._client is None:
            try:
                from alphagenome.atlas import atlas
            except ImportError as exc:  # the stage must degrade, not crash
                raise AlphaGenomeError(
                    "the alphagenome package is not installed; `uv add alphagenome` to use this adapter") from exc
            self._client = atlas.create(api_key=self.api_key, timeout=self.timeout)
        return self._client

    def available_scorers(self) -> list[str]:
        return sorted(self.client().scorer_metadata())

    def region_scores(self, region: RegionProvenance, scorers: list[str]) -> list[AtlasPrediction]:
        from alphagenome.data import genome

        check_region_is_public(region)
        interval = genome.Interval(region.chromosome, region.start, region.end)
        result = self.client().query_interval(interval, requested_scorers=scorers, progress_bar=False)
        return list(_flatten(result))


MAX_NAMED_FEATURES = 32


def _flatten(result: dict) -> list[AtlasPrediction]:
    """Turn the client's per-scorer AnnData into flat per-variant records we can cache and diff.

    A feature-attribution scorer returns a named vector — which molecular process drives the impact —
    and collapsing that to a maximum would discard the only part that distinguishes a splicing effect
    from a protein effect. Named vectors are kept per feature; wide track matrices are summarised.
    """
    import numpy as np

    by_variant: dict[tuple, AtlasPrediction] = {}
    for scorer, adata in result.items():
        if adata.shape[0] == 0:
            continue
        features = [str(x) for x in list(adata.var.get("name", adata.var.index))]
        named = len(features) <= MAX_NAMED_FEATURES
        values = np.asarray(adata.X)
        variants = list(adata.obs["variant"]) if "variant" in adata.obs else []
        for i, variant in enumerate(variants):
            key = (variant.chromosome, variant.position, variant.reference_bases, variant.alternate_bases)
            record = by_variant.setdefault(key, AtlasPrediction(
                chromosome=key[0], position=key[1], ref=key[2], alt=key[3]))
            row = np.atleast_1d(values[i])
            if named:
                for feature, value in zip(features, row, strict=False):
                    if np.isfinite(value):
                        label = scorer if len(features) == 1 else f"{scorer}:{feature}"
                        record.scores[label] = float(value)
            else:
                finite = row[np.isfinite(row)]
                if finite.size:
                    record.scores[f"{scorer}:max_abs"] = float(np.abs(finite).max())
                    record.scores[f"{scorer}:n_tracks"] = float(finite.size)
    return list(by_variant.values())


def cache_region(directory: Path, region: RegionProvenance, predictions: list[AtlasPrediction],
                 scorers: list[str], package_version: str | None) -> Path:
    """Cache the public answer with its provenance, so matching never needs the network again."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": {"name": "AlphaGenomeRegionCache", "version": "1.0.0"},
        "retrieved_at": utc_now().isoformat(),
        "package_version": package_version,
        "region": region.model_dump(mode="json"),
        "scorers": scorers,
        "private_variant_transmitted": False,
        "query_note": ("A public genomic interval was queried. No case-specific variant, coordinate or "
                       "genotype was transmitted; the child's alleles are matched against this cache locally."),
        "predictions": [p.model_dump(mode="json") for p in predictions],
    }
    body = json.dumps(payload, indent=1, sort_keys=False)
    digest = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    payload["cache_digest"] = digest
    tag = hashlib.sha256(",".join(sorted(scorers)).encode()).hexdigest()[:8]
    path = directory / f"{region.gene_symbol or region.chromosome}_{region.start}_{region.end}_{tag}.json"
    path.write_text(json.dumps(payload, indent=1) + "\n")
    return path


def match_locally(cache_path: Path, variants: list[dict]) -> list[AlphaGenomeEvidence]:
    """The only place the child's alleles meet the Atlas: on this machine, against a cached file.

    Contig naming is normalised on the way in: the Atlas speaks UCSC-style names and the case VCF
    may not, and a silent naming mismatch would look exactly like "this variant has no prediction".
    """
    from rarepipe.stages.track1.select import ucsc_contig
    payload = json.loads(cache_path.read_text())
    region = RegionProvenance(**payload["region"])
    predictions = payload["predictions"]
    index = {(p["chromosome"], int(p["position"]), p["ref"], p["alt"]): p for p in predictions}
    scorers = payload.get("scorers", [])
    out: list[AlphaGenomeEvidence] = []
    for variant in variants:
        try:
            contig = ucsc_contig(str(variant.get("contig") or ""))
        except ValueError:
            contig = str(variant.get("contig") or "")
        key = (contig, int(variant.get("position") or 0), variant.get("ref"), variant.get("alt"))
        hit = index.get(key)
        evidence = AlphaGenomeEvidence(
            package_version=payload.get("package_version"), query_scope=f"{region.gene_symbol} public region",
            region=region, variant_role=variant["role"], local_match_found=hit is not None,
            retrieved_at=payload.get("retrieved_at"), cache_digest=payload.get("cache_digest"))
        if hit:
            evidence.scores = dict(hit["scores"])
            evidence.neighbourhood = _neighbourhood(hit, predictions, scorers)
        else:
            evidence.limitations.append(
                "this allele was not present in the cached region: widen the queried interval or check the assembly")
        out.append(evidence)
    return out


def _neighbourhood(hit: dict, predictions: list[dict], scorers: list[str]) -> dict[str, Any]:
    """A lone score says little. Where the allele sits among every possible substitution says more."""
    summary: dict[str, Any] = {"variants_in_region": len(predictions)}
    for scorer in sorted(hit.get("scores", {})):
        values = sorted((p["scores"][scorer] for p in predictions if scorer in p.get("scores", {})), reverse=True)
        own = hit.get("scores", {}).get(scorer)
        if own is None or not values:
            continue
        rank = sum(1 for v in values if v > own) + 1
        summary[scorer] = {
            "rank_in_region": rank, "of": len(values),
            "percentile": round(100 * (1 - (rank - 1) / len(values)), 2),
            "region_max": values[0], "region_median": values[len(values) // 2],
        }
    return summary


def configured_provider() -> AtlasProvider:
    key = os.environ.get("ALPHAGENOME_API_KEY", "")
    if not key:
        raise AlphaGenomeError(
            "ALPHAGENOME_API_KEY is not set. Export it in your shell (never in the repo, never in a commit) "
            "and re-run; rarepipe reads it from the environment only.")
    return AtlasProvider(api_key=key)


def package_version() -> str | None:
    try:
        from importlib.metadata import version

        return version(PACKAGE)
    except Exception:
        return None
