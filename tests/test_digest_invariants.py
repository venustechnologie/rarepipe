"""One rule, checked for every stage's artifact: nothing run-specific inside the semantic digest.

Stage 02 and Stage 03 each shipped this bug once (stream timing; wall-clock, peak RSS and
run-specific paths). This test covers all three artifacts so the next stage cannot repeat it.
"""

from __future__ import annotations

import pytest

from rarepipe.core.console import Console
from rarepipe.core.digest import volatile_fields
from rarepipe.stages.baseline import exomiser
from rarepipe.stages.baseline.stage import BaselineRequest, run_baseline
from rarepipe.stages.normalize.stage import NormalizeRequest, run_normalize
from rarepipe.testing import baseline_fixtures as bf
from rarepipe.testing import normalize_fixtures as nf

EXECUTION_SECTIONS = {"execution"}


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("digest")
    root = nf.build_case(tmp / "case", with_fastq=True)
    manifest_path = nf.run_intake_for(root, tmp / "intake")
    res = nf.build_resources(tmp / "resources")
    norm = run_normalize(NormalizeRequest(manifest=manifest_path, output=tmp / "norm", resources=res), Console(quiet=True))
    return tmp, manifest_path, norm


def test_case_manifest_digest_has_no_run_specific_fields(artifacts):
    import json

    _, manifest_path, _ = artifacts
    data = json.loads(manifest_path.read_text())
    for section in EXECUTION_SECTIONS:
        data.pop(section, None)
    data.pop("semantic_digest", None)
    assert volatile_fields(data) == []


def test_normalized_case_digest_has_no_run_specific_fields(artifacts):
    _, _, norm = artifacts
    payload = norm.case.model_dump(mode="json", by_alias=True, exclude=EXECUTION_SECTIONS | {"semantic_digest"})
    assert volatile_fields(payload) == []


def test_raw_candidate_set_digest_has_no_run_specific_fields(artifacts, monkeypatch):
    tmp, _, norm = artifacts
    monkeypatch.setattr(exomiser, "run_job", bf.fake_run_job)
    monkeypatch.setattr(exomiser, "locate", lambda home, data: bf.fake_installation(tmp))
    result = run_baseline(BaselineRequest(normalized_case=norm.run_dir / "normalized_case.private.json",
                                          output=tmp / "baseline", exomiser_home=tmp / "exomiser"), Console(quiet=True))
    payload = result.candidate_set.model_dump(mode="json", by_alias=True, exclude=EXECUTION_SECTIONS | {"semantic_digest"})
    assert volatile_fields(payload) == []


def test_the_check_itself_catches_a_planted_field():
    assert volatile_fields({"results": [{"elapsed_seconds": 3.2}]}) == ["results[0].elapsed_seconds"]
    assert volatile_fields({"a": {"path": "/out/RUN_20260918T000000Z_abc/x.tsv"}}) == ["a.path (value contains a run id)"]


def test_allowlisted_upstream_pointers_are_actually_present(artifacts):
    """The allowlist must not rot: each allowed path should exist in some artifact."""
    from rarepipe.core.digest import UPSTREAM_POINTERS

    _, _, norm = artifacts
    payload = norm.case.model_dump(mode="json", by_alias=True)
    assert payload["provenance"]["source_manifest"]["run_id"]
    assert "provenance.source_manifest.run_id" in UPSTREAM_POINTERS
