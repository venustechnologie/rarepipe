"""Stage 02 cross-cutting guarantees: immutability, idempotence, privacy, network isolation, schema contract."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from rarepipe.core.console import Console
from rarepipe.stages.normalize.schema import schema_json
from rarepipe.stages.normalize.stage import NormalizeRequest, run_normalize
from rarepipe.testing import fixtures as intake_fixtures
from rarepipe.testing import normalize_fixtures as nf
from tests.conftest import tree_state

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def prepared(tmp_path):
    root = nf.build_case(tmp_path / "case", with_fastq=True, hpo_terms=nf.EDGE_HPO)
    manifest = nf.run_intake_for(root, tmp_path / "intake")
    res = nf.build_resources(tmp_path / "resources")
    return root, manifest, res


def _run(manifest, res, out, **kw):
    return run_normalize(NormalizeRequest(manifest=manifest, output=out, resources=res, **kw), Console(quiet=True))


# ── immutability ────────────────────────────────────────────────────────────


def test_normalization_mutates_nothing_it_reads(prepared, tmp_path):
    root, manifest, res = prepared
    before_case, before_run, before_res = tree_state(root), tree_state(manifest.parent), tree_state(res)
    _run(manifest, res, tmp_path / "out")
    assert tree_state(root) == before_case  # no .tbi/.fai created, no bytes changed
    assert tree_state(manifest.parent) == before_run  # Stage 01 artifact untouched
    assert tree_state(res) == before_res


def test_run_directory_is_sealed(prepared, tmp_path):
    root, manifest, res = prepared
    result = _run(manifest, res, tmp_path / "out")
    assert sorted(p.name for p in result.run_dir.iterdir()) == [
        "SHA256SUMS", "normalization.log", "normalization_report.md", "normalized_case.private.json", "normalized_case.sanitized.json"]
    from typer.testing import CliRunner

    from rarepipe.cli import app

    assert CliRunner().invoke(app, ["verify-run", str(result.run_dir)]).exit_code == 0


# ── idempotence ─────────────────────────────────────────────────────────────


def test_rerun_is_semantically_identical(prepared, tmp_path):
    root, manifest, res = prepared
    first = _run(manifest, res, tmp_path / "a")
    second = _run(manifest, res, tmp_path / "b")
    assert first.case.execution.run_id != second.case.execution.run_id
    assert first.case.semantic_digest == second.case.semantic_digest
    assert first.sanitized.semantic_digest == second.sanitized.semantic_digest
    a = json.loads((first.run_dir / "normalized_case.private.json").read_text())
    b = json.loads((second.run_dir / "normalized_case.private.json").read_text())
    a.pop("execution"), b.pop("execution")
    assert a == b


def test_ontology_version_changes_the_result_visibly(prepared, tmp_path):
    root, manifest, res = prepared
    first = _run(manifest, res, tmp_path / "a")
    newer = nf.SYNTH_OBO.replace("data-version: hp/releases/2099-01-01", "data-version: hp/releases/2099-06-01").replace(
        "id: HP:9999999", "id: HP:9999998")  # same file shape, different release
    obo = res / "hpo" / "v2099-01-01" / "hp.obo"
    obo.write_text(newer)
    from rarepipe.resources.lock import ResourceKind, register

    register(res, ResourceKind.HPO_ONTOLOGY, obo, name="Human Phenotype Ontology (hp.obo)", version="2099-06-01", source_url="synthetic://fixture")
    second = _run(manifest, res, tmp_path / "b")
    assert first.case.phenotype.ontology_release == "2099-01-01"
    assert second.case.phenotype.ontology_release == "2099-06-01"
    assert first.case.semantic_digest != second.case.semantic_digest  # a rerun on a newer ontology is distinguishable


# ── privacy ─────────────────────────────────────────────────────────────────

SEQ_RE = re.compile(r"[ACGTN]{20,}")
VARIANT_ROW_RE = re.compile(r"(chr)?[0-9XYM]{1,2}\t\d+\t")


def test_shareable_outputs_leak_nothing_restricted(prepared, tmp_path):
    root, manifest, res = prepared
    result = _run(manifest, res, tmp_path / "out")
    forbidden = [intake_fixtures.PROBAND, nf.SECRET_PATH, str(tmp_path), str(root), *nf.EDGE_HPO, "Synthetic phenotype A", "hpo_terms.txt", "case.vcf.gz"]
    for name in ("normalization_report.md", "normalized_case.sanitized.json", "normalization.log"):
        text = (result.run_dir / name).read_text()
        for secret in forbidden:
            assert secret not in text, f"{name} leaks {secret!r}"
        assert not SEQ_RE.search(text) and not VARIANT_ROW_RE.search(text)
    private = (result.run_dir / "normalized_case.private.json").read_text()
    assert intake_fixtures.PROBAND in private and "HP:0001250" in private  # the private artifact does carry them


@pytest.mark.parametrize("word", ["pathogenic", "benign", "causal", "candidate gene", "diagnosis", "compound het", "drug"])
def test_no_biological_interpretation_vocabulary(prepared, tmp_path, word):
    root, manifest, res = prepared
    result = _run(manifest, res, tmp_path / "out")
    text = (result.run_dir / "normalization_report.md").read_text().lower() + (result.run_dir / "normalized_case.sanitized.json").read_text().lower()
    assert word not in text


# ── network isolation ───────────────────────────────────────────────────────


def test_runs_with_python_networking_disabled(prepared, tmp_path, monkeypatch):
    root, manifest, res = prepared

    def refuse(*_a, **_k):
        raise AssertionError("normalization attempted network access")

    for attr in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, attr, refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    _run(manifest, res, tmp_path / "out")


@pytest.mark.skipif(not shutil.which("sandbox-exec") and not shutil.which("unshare"), reason="no OS-level network sandbox available")
def test_runs_inside_os_network_sandbox(prepared, tmp_path):
    root, manifest, res = prepared
    cmd = [sys.executable, "-m", "rarepipe", "normalize", "--manifest", str(manifest), "--resources", str(res),
           "--output", str(tmp_path / "sbx"), "--quiet"]
    if shutil.which("sandbox-exec"):
        cmd = ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)", *cmd]
    else:
        if subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode != 0:
            pytest.skip("unprivileged network namespaces unavailable")
        cmd = ["unshare", "-rn", *cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert (Path(proc.stdout.strip().splitlines()[-1]) / "normalized_case.private.json").exists()


def test_stage_code_never_imports_the_fetcher():
    """The only networked module must not be reachable from a stage."""
    src = ROOT / "src" / "rarepipe"
    for path in list((src / "stages").rglob("*.py")) + [src / "core" / c for c in ("artifacts.py", "issues.py", "hashing.py")]:
        assert "resources.fetch" not in path.read_text(), path


# ── schema contract ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("artifact,filename", [("normalized_case", "normalized_case.schema.json"), ("case_assertions", "case_assertions.schema.json")])
def test_committed_schema_matches_code(artifact, filename):
    committed = (ROOT / "schemas" / filename).read_text()
    assert committed == schema_json(artifact), f"run: uv run rarepipe schema --artifact {artifact} --output schemas/{filename}"


def test_normalized_case_round_trips(prepared, tmp_path):
    from rarepipe.stages.normalize.model import NormalizedCase

    root, manifest, res = prepared
    result = _run(manifest, res, tmp_path / "out")
    raw = (result.run_dir / "normalized_case.private.json").read_text()
    assert NormalizedCase.model_validate_json(raw).semantic_digest == result.case.semantic_digest


def test_stage01_schema_is_frozen():
    """Stage 02 must not have changed the Stage 01 contract."""
    out = subprocess.run(["git", "diff", "--name-only", "stage01-case_intake-v0.1.0", "--", "schemas/case_manifest.schema.json",
                          "src/rarepipe/stages/intake/"], cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"frozen Stage 01 files changed: {out.stdout}"
