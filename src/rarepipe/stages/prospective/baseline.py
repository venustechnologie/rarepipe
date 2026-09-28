"""Import and verify a Stage 09 package as the plan's baseline (PRD §6.1, AT01, AT02).

Every manifest entry is re-hashed, every file must be listed, the payload must be sanitized, and the
schema versions must be ones this stage understands. A single mismatch blocks a verified import. The
candidate/frozen status and the known limitations stay visible on the BaselineRef.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from rarepipe.stages.prospective.model import BaselineRef

KNOWN_SCHEMAS = {"Track2HypothesisSet": {"1.0.0"}}
MANIFEST = "MANIFEST.sha256"


class BaselineError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("baseline did not verify: " + "; ".join(problems))
        self.problems = problems


def _read_package(path: Path) -> tuple[dict[str, bytes], str]:
    """All files, keyed by their path relative to the package folder; plus the raw package sha256."""
    if path.is_dir():
        files = {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*"))
                 if p.is_file() and not p.name.startswith("._")}
        return files, "sha256:" + hashlib.sha256(b"".join(files[k] for k in sorted(files))).hexdigest()
    raw = path.read_bytes()
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        roots = {n.split("/", 1)[0] for n in names}
        strip = len(roots) == 1 and all("/" in n for n in names)
        for name in names:
            rel = name.split("/", 1)[1] if strip else name
            if rel.split("/")[-1].startswith("._") or rel.startswith("__MACOSX"):
                continue
            files[rel] = z.read(name)
    return files, "sha256:" + hashlib.sha256(raw).hexdigest()


def verify_package(path: Path) -> tuple[dict[str, bytes], str, int]:
    files, package_sha = _read_package(path)
    problems: list[str] = []
    if MANIFEST not in files:
        raise BaselineError([f"no {MANIFEST} in the package"])
    listed: dict[str, str] = {}
    for line in files[MANIFEST].decode().splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            listed[name] = digest
    for name, digest in listed.items():
        if name not in files:
            problems.append(f"{name}: listed in the manifest but missing")
        elif hashlib.sha256(files[name]).hexdigest() != digest:
            problems.append(f"{name}: sha256 does not match the manifest")
    extra = sorted(set(files) - set(listed) - {MANIFEST})
    problems += [f"{name}: present but not listed in the manifest" for name in extra]
    private = [n for n in files if "private" in n.split("/")[-1]]
    problems += [f"{n}: a private artifact must not be in a baseline package" for n in private]
    if problems:
        raise BaselineError(problems)
    return files, package_sha, len(listed)


def import_baseline(path: Path, status: str = "CANDIDATE") -> tuple[BaselineRef, dict]:
    """Returns the pinned BaselineRef and the sanitized hypothesis set it was read from."""
    files, package_sha, entries = verify_package(path)
    problems: list[str] = []
    try:
        t2 = json.loads(files["records/track2_hypothesis_set.sanitized.json"])
    except KeyError:
        raise BaselineError(["records/track2_hypothesis_set.sanitized.json is missing"]) from None
    schema = t2.get("schema", {})
    if schema.get("version") not in KNOWN_SCHEMAS.get(schema.get("name"), set()):
        problems.append(f"unknown schema {schema}")
    if t2.get("visibility") != "sanitized":
        problems.append("the hypothesis set is not the sanitized artifact")
    if problems:
        raise BaselineError(problems)
    b = t2.get("baseline") or {}
    for key in ("mechanism_run_id", "mechanism_digest", "intervention_map_run_id", "intervention_map_digest",
                "discovery_run_id", "discovery_digest"):
        if not b.get(key):
            problems.append(f"baseline pointer missing: {key} — the provenance chain would be broken")
    if problems:
        raise BaselineError(problems)
    rf = t2.get("residual_function") or {}
    limitations = []
    if status == "CANDIDATE":
        limitations.append("candidate baseline, not tagged or frozen")
    if rf:
        limitations.append(f"exact-allele residual function: {rf.get('exact_allele')} ({rf.get('decision')})")
        if rf.get("class_level_endpoints"):
            limitations.append("class-level restored-abundance evidence covers only "
                               + ", ".join(rf["class_level_endpoints"]))
    for h in t2.get("hypotheses", []):
        limitations.append(f"{h['id']} evidence grade {h.get('evidence_grade')}; observed direction on the "
                           f"required cellular state: {h.get('observed_direction')}")
        for dep in h.get("efficacy_dependencies", []):
            if dep.get("status") == "unresolved":
                limitations.append(f"{h['id']} unresolved dependency: {dep['dependency']}")
    limitations.append("PMID:33207204 (domain function) adjudicated from its abstract only")
    corpus = json.loads(files["records/stage06/corpus_index.json"]) if "records/stage06/corpus_index.json" in files \
        else {}
    ref = BaselineRef(
        package_path=str(path), package_sha256=package_sha, manifest_entries=entries, manifest_verified=True,
        stage_runs={"stage06": b.get("mechanism_run_id"), "stage07": b.get("intervention_map_run_id"),
                    "stage08": b.get("discovery_run_id"), "stage09": t2.get("execution", {}).get("run_id")},
        semantic_digests={"stage06": b.get("mechanism_digest"), "stage07": b.get("intervention_map_digest"),
                          "stage08": b.get("discovery_digest"), "stage09": t2.get("semantic_digest")},
        code_commit=b.get("git_commit"), git_describe=b.get("git_describe"),
        corpus_snapshot=corpus.get("corpus_digest"),
        status=status, known_limitations=limitations, residual_function=rf or None,
        hypothesis_versions={h["id"]: ",".join(t2.get("provenance", {}).get("research_sessions", []))
                             for h in t2.get("hypotheses", [])})
    return ref, t2
