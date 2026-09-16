from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rarepipe.core.console import Console
from rarepipe.stages.intake.stage import IntakeRequest, run_intake
from rarepipe.testing import fixtures


@pytest.fixture
def build_case(tmp_path: Path):
    def _build(name: str) -> Path:
        return fixtures.build(name, tmp_path / "cases" / name, tmp_path / "scratch" / name)

    return _build


@pytest.fixture
def intake(tmp_path: Path):
    def _run(case_root: Path, case_id: str = "TEST_CASE", output: Path | None = None, **kw):
        req = IntakeRequest(case_root=case_root, case_id=case_id, output=output or tmp_path / "out" / case_root.name, **kw)
        return run_intake(req, Console(quiet=True))

    return _run


def tree_state(root: Path) -> dict[str, tuple[str, int, int]]:
    """Content + size + mtime for every file under root (symlinks not followed)."""
    state = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            state[p.relative_to(root).as_posix()] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns)
    return state
