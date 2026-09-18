"""Operator-invoked resource provisioning. The ONLY module in rarepipe that uses the network.

Never imported by any stage. Downloads public reference metadata (no case data
is sent anywhere), then pins it in resources.lock.json.
"""

from __future__ import annotations

import json
import re
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


# ── evidence resources for Stage 04 (bulk or gene-level only) ───────────────

CLINVAR_VCF_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
CLINGEN_VALIDITY_URL = "https://search.clinicalgenome.org/kb/gene-validity/download"
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{accession}.json"
EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_literature(resources_dir: Path, query: str, *, page_size: int = 200, pages: int = 3) -> Path:
    """Gene-level literature search. The query passes the disclosure guard before it is sent."""
    import urllib.parse

    from rarepipe.stages.adjudicate.disclosure import check_query

    check_query(query)
    records: list[dict] = []
    for page in range(1, pages + 1):
        params = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": page_size, "page": page,
                                         "resultType": "core"})
        with urllib.request.urlopen(urllib.request.Request(f"{EUROPEPMC_URL}?{params}", headers=UA), timeout=120) as resp:
            payload = json.load(resp)
        batch = payload.get("resultList", {}).get("result", [])
        records += batch
        if len(batch) < page_size:
            break
    dest = resources_dir / "literature" / (re.sub(r"[^A-Za-z0-9]+", "_", query)[:60] + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps([{k: r.get(k) for k in ("id", "pmid", "doi", "title", "journalTitle", "pubYear", "abstractText", "keywordList")}
                                for r in records], indent=1))
    return dest
