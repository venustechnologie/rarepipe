"""Operator-invoked resource provisioning. The ONLY module in rarepipe that uses the network.

Never imported by any stage. Downloads public reference metadata (no case data
is sent anywhere), then pins it in resources.lock.json.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from rarepipe.resources.hpo import load_obo, release_date
from rarepipe.resources.lock import ResourceEntry, ResourceKind, register

HPO_LATEST_API = "https://api.github.com/repos/obophenotype/human-phenotype-ontology/releases/latest"
HPO_OBO_URL = "https://github.com/obophenotype/human-phenotype-ontology/releases/download/{tag}/hp.obo"
ASSEMBLY_REPORTS = {
    "GRCh38.p14": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/405/GCF_000001405.40_GRCh38.p14/GCF_000001405.40_GRCh38.p14_assembly_report.txt",
}
UA = {"User-Agent": "rarepipe-resource-fetch"}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1024 * 1024):
            out.write(chunk)
    tmp.replace(dest)


def fetch_hpo(resources_dir: Path, release: str = "latest") -> ResourceEntry:
    tag = release
    if release == "latest":
        with urllib.request.urlopen(urllib.request.Request(HPO_LATEST_API, headers=UA), timeout=60) as resp:
            tag = json.load(resp)["tag_name"]
    url = HPO_OBO_URL.format(tag=tag)
    dest = resources_dir / "hpo" / tag / "hp.obo"
    retrieved = datetime.now(UTC).replace(microsecond=0).isoformat()
    _download(url, dest)
    version = release_date(load_obo(dest)) or tag
    return register(resources_dir, ResourceKind.HPO_ONTOLOGY, dest, name="Human Phenotype Ontology (hp.obo)", version=version,
                    source_url=url, retrieved_at=retrieved)


def fetch_assembly_report(resources_dir: Path, assembly: str = "GRCh38.p14") -> ResourceEntry:
    url = ASSEMBLY_REPORTS[assembly]
    dest = resources_dir / "assembly" / assembly / url.rsplit("/", 1)[-1]
    retrieved = datetime.now(UTC).replace(microsecond=0).isoformat()
    _download(url, dest)
    return register(resources_dir, ResourceKind.ASSEMBLY_REPORT, dest, name=f"NCBI assembly report {assembly}", version=assembly,
                    source_url=url, retrieved_at=retrieved)
