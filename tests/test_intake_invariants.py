"""Cross-cutting guarantees: input immutability, idempotence, privacy, network isolation, artifact immutability."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from rarepipe.stages.intake.stage import IntakeUsageError
from rarepipe.testing import fixtures
from tests.conftest import tree_state

ALL_CASES = list(fixtures.CASES)


# ── §41 input immutability ───────────────────────────────────────────────────


@pytest.mark.parametrize("name", ALL_CASES)
def test_intake_does_not_mutate_inputs(build_case, intake, name):
    case = build_case(name)
    before = tree_state(case)
    intake(case)
    assert tree_state(case) == before  # same files, same bytes, same mtimes, nothing created (e.g. no .fai/.bai)


def test_output_inside_case_root_is_refused(build_case, intake):
    case = build_case("A_healthy")
    with pytest.raises(IntakeUsageError):
        intake(case, output=case / "intake")


# ── §40 idempotence ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["A_healthy", "J_trio_with_pedigree", "I_cram_with_reference", "K_sample_mismatch"])
def test_rerun_is_semantically_identical(build_case, intake, tmp_path, name):
    case = build_case(name)
    first = intake(case, output=tmp_path / "fresh", checksum_cache=False)
    intake(case, output=tmp_path / "cached")
    second = intake(case, output=tmp_path / "cached")  # resumes every digest from cache — must not change semantics
    assert first.run_dir != second.run_dir
    assert first.manifest.execution.run_id != second.manifest.execution.run_id
    assert second.manifest.execution.checksum_cache_hits == len(second.manifest.assets)
    assert first.manifest.semantic_digest == second.manifest.semantic_digest
    assert first.sanitized.semantic_digest == second.sanitized.semantic_digest
    a = json.loads((first.run_dir / "case_manifest.private.json").read_text())
    b = json.loads((second.run_dir / "case_manifest.private.json").read_text())
    a.pop("execution"), b.pop("execution")
    assert a == b


def test_input_fingerprint_tracks_content_not_names(build_case, intake, tmp_path):
    case = build_case("A_healthy")
    fp1 = intake(case).manifest.provenance.fingerprints
    (case / "phenotype" / "hpo_terms.txt").rename(case / "phenotype" / "renamed.txt")
    fp2 = intake(case, output=tmp_path / "out2").manifest.provenance.fingerprints
    assert fp1.input_fingerprint == fp2.input_fingerprint
    assert fp1.inventory_fingerprint != fp2.inventory_fingerprint
    with (case / "phenotype" / "renamed.txt").open("a") as fh:
        fh.write("HP:0000001\n")
    fp3 = intake(case, output=tmp_path / "out3").manifest.provenance.fingerprints
    assert fp3.input_fingerprint != fp2.input_fingerprint


# ── §8 artifact immutability ─────────────────────────────────────────────────


def test_run_directory_is_sealed_and_read_only(build_case, intake):
    result = intake(build_case("A_healthy"))
    files = sorted(p.name for p in result.run_dir.iterdir())
    assert files == ["SHA256SUMS", "case_manifest.private.json", "case_manifest.sanitized.json", "intake.log", "intake_report.md"]
    for p in result.run_dir.iterdir():
        assert not p.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    assert not list(result.run_dir.parent.glob(".incomplete-*"))
    from typer.testing import CliRunner

    from rarepipe.cli import app

    assert CliRunner().invoke(app, ["verify-run", str(result.run_dir)]).exit_code == 0


# ── §42 privacy ──────────────────────────────────────────────────────────────

SEQ_RE = re.compile(r"[ACGTN]{20,}")
VARIANT_ROW_RE = re.compile(r"(chr)?[0-9XYM]{1,2}\t\d+\t")


@pytest.mark.parametrize("name", ALL_CASES)
def test_shareable_outputs_leak_nothing_restricted(build_case, intake, tmp_path, name):
    case = build_case(name)
    result = intake(case)
    forbidden = [str(tmp_path), str(tmp_path.resolve()), str(case), str(case.resolve())]
    for f in ("intake_report.md", "case_manifest.sanitized.json", "intake.log"):
        text = (result.run_dir / f).read_text()
        for label in fixtures.ALL_SOURCE_LABELS:
            assert label.lower() not in text.lower(), f"{f} leaks a source sample label"
        for path in forbidden:
            assert path not in text, f"{f} leaks an absolute path"
        assert not SEQ_RE.search(text), f"{f} contains sequence-like content"
        assert not VARIANT_ROW_RE.search(text), f"{f} contains variant-row-like content"
        for rel in (p.relative_to(case).as_posix() for p in case.rglob("*") if p.is_file()):
            if "/" in rel or len(Path(rel).name) > 8:
                assert rel not in text, f"{f} leaks a case-relative filename"


def test_private_manifest_does_contain_what_sanitized_removes(build_case, intake):
    """Guards the privacy test against passing vacuously."""
    result = intake(build_case("J_trio_with_pedigree"))
    private = (result.run_dir / "case_manifest.private.json").read_text()
    assert fixtures.PROBAND in private and "trio.vcf.gz" in private
    sanitized = json.loads((result.run_dir / "case_manifest.sanitized.json").read_text())
    assert sanitized["redaction"]["visibility"] == "sanitized"
    assert all(a["relative_path"] is None for a in sanitized["assets"])


# ── §43 network isolation ────────────────────────────────────────────────────


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("intake attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.mark.parametrize("name", ["A_healthy", "H_cram_without_reference", "I_cram_with_reference"])
def test_runs_with_python_networking_disabled(build_case, intake, no_network, name):
    intake(build_case(name))


@pytest.mark.skipif(not shutil.which("sandbox-exec") and not shutil.which("unshare"), reason="no OS-level network sandbox available")
def test_runs_inside_os_network_sandbox(build_case, tmp_path):
    """Catches C-level (htslib/libcurl) access that a Python socket patch cannot see."""
    case = build_case("H_cram_without_reference")
    cmd = [sys.executable, "-m", "rarepipe", "intake", "--case-root", str(case), "--case-id", "SANDBOXED", "--output", str(tmp_path / "sbx"), "--quiet"]
    if shutil.which("sandbox-exec"):
        cmd = ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)", *cmd]
    else:
        probe = subprocess.run(["unshare", "-rn", "true"], capture_output=True)
        if probe.returncode != 0:
            pytest.skip("unprivileged network namespaces unavailable")
        cmd = ["unshare", "-rn", *cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert proc.returncode == 0, proc.stderr[-2000:]
    run_dir = Path(proc.stdout.strip().splitlines()[-1])
    assert (run_dir / "case_manifest.private.json").exists()
