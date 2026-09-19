"""The AlphaGenome adapter must add evidence without becoming a disclosure channel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rarepipe.stages.mechanism.alphagenome import (
    AlphaGenomeError,
    AtlasPrediction,
    RegionProvenance,
    cache_region,
    check_region_is_public,
    configured_provider,
    match_locally,
)

REGION = RegionProvenance(gene_symbol="BUB1B", chromosome="chr15", start=40160000, end=40170000,
                          width=10000, derived_from="Ensembl REST lookup/symbol (public gene annotation)")


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    predictions = []
    for offset in range(0, 300):
        position = REGION.start + offset
        for alt, score in (("A", 0.1 + offset / 10000), ("G", 0.4), ("T", 0.9 if offset == 150 else 0.2)):
            predictions.append(AtlasPrediction(chromosome="chr15", position=position, ref="C", alt=alt,
                                               scores={"avi": score, "splice": score / 3}))
    return cache_region(tmp_path / "cache", REGION, predictions, ["avi", "splice"], "0.9.0")


def test_a_window_narrow_enough_to_identify_a_variant_is_refused():
    narrow = RegionProvenance(chromosome="chr15", start=40210900, end=40210930, width=30, derived_from="public")
    with pytest.raises(AlphaGenomeError) as exc:
        check_region_is_public(narrow)
    assert "disclose the variant" in str(exc.value)
    check_region_is_public(REGION)


def test_an_interval_derived_from_the_case_is_refused():
    from_case = REGION.model_copy(update={"derived_from": "case variant position"})
    with pytest.raises(AlphaGenomeError):
        check_region_is_public(from_case)


def test_the_cache_records_that_nothing_private_was_sent(cache):
    payload = json.loads(cache.read_text())
    assert payload["private_variant_transmitted"] is False
    assert payload["cache_digest"].startswith("sha256:")
    assert payload["region"]["derived_from"].startswith("Ensembl")
    assert payload["package_version"] == "0.9.0"


def test_matching_happens_locally_and_places_the_allele_in_its_neighbourhood(cache):
    variants = [{"role": "variant_b", "contig": "chr15", "position": REGION.start + 150, "ref": "C", "alt": "T"}]
    [evidence] = match_locally(cache, variants)
    assert evidence.local_match_found and evidence.private_variant_transmitted is False
    assert evidence.scores["avi"] == 0.9
    neighbourhood = evidence.neighbourhood["avi"]
    assert neighbourhood["rank_in_region"] == 1 and neighbourhood["percentile"] == 100.0
    assert neighbourhood["of"] == 900
    assert any("not diploid-aware" in limit for limit in evidence.limitations)


def test_an_allele_outside_the_cached_region_is_reported_not_guessed(cache):
    variants = [{"role": "variant_a", "contig": "chr15", "position": 41000000, "ref": "C", "alt": "T"}]
    [evidence] = match_locally(cache, variants)
    assert evidence.local_match_found is False and not evidence.scores
    assert any("not present in the cached region" in limit for limit in evidence.limitations)


def test_scores_are_restricted_so_they_never_reach_a_sanitized_artifact(cache):
    from rarepipe.core.redaction import clear_restricted

    variants = [{"role": "variant_b", "contig": "chr15", "position": REGION.start + 150, "ref": "C", "alt": "T"}]
    [evidence] = match_locally(cache, variants)
    sanitized = evidence.model_copy(deep=True)
    clear_restricted(sanitized)
    assert evidence.scores and not sanitized.scores


def test_the_key_is_read_from_the_environment_only(monkeypatch):
    monkeypatch.delenv("ALPHAGENOME_API_KEY", raising=False)
    with pytest.raises(AlphaGenomeError) as exc:
        configured_provider()
    assert "never in a commit" in str(exc.value)
    monkeypatch.setenv("ALPHAGENOME_API_KEY", "test-key")
    assert configured_provider().api_key == "test-key"


def test_no_api_key_is_committed_anywhere():
    import subprocess

    out = subprocess.run(["git", "grep", "-rIl", "-e", "AIza", "-e", "ALPHAGENOME_API_KEY="],
                         capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert not out.stdout.strip(), f"possible key material committed: {out.stdout}"


def test_atlas_predictions_enter_as_computational_evidence_that_cannot_establish_function(tmp_path, cache):
    """A model output may stand beside a functional claim. It may never be the claim."""
    from rarepipe.core.artifacts import canonical_json
    from rarepipe.stages.mechanism.model import EpistemicClass, EvidenceLevel, Scope
    from rarepipe.stages.mechanism.stage import alphagenome_evidence

    variants = [{"role": "variant_b", "contig": "chr15", "position": REGION.start + 150, "ref": "C", "alt": "T"}]
    evidence = match_locally(cache, variants)
    path = tmp_path / "alphagenome_evidence.private.json"
    path.write_text(canonical_json({"evidence": [e.model_dump(mode="json") for e in evidence]}))

    records = alphagenome_evidence(path, 1)
    assert records
    for record in records:
        assert record.evidence_level is EvidenceLevel.COMPUTATIONAL
        assert record.epistemic_class is EpistemicClass.EXTERNAL_EVIDENCE
        assert record.scope is Scope.EXACT_VARIANT
        assert any("not diploid-aware" in limit for limit in record.limitations)
        assert record.source_id.startswith("ALPHAGENOME_ATLAS:")
    assert any("percentile" in r.statement for r in records)


def test_atlas_scores_are_restricted_in_the_dossier(tmp_path, cache):
    from rarepipe.core.artifacts import canonical_json
    from rarepipe.core.redaction import clear_restricted
    from rarepipe.stages.mechanism.stage import alphagenome_evidence

    variants = [{"role": "variant_b", "contig": "chr15", "position": REGION.start + 150, "ref": "C", "alt": "T"}]
    path = tmp_path / "alphagenome_evidence.private.json"
    path.write_text(canonical_json({"evidence": [e.model_dump(mode="json") for e in match_locally(cache, variants)]}))
    record = alphagenome_evidence(path, 1)[0]
    assert record.case_specific_detail
    clear_restricted(record)
    assert record.case_specific_detail is None
