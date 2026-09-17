"""Synthetic fixtures for Stage 02. Entirely invented content.

The ontology and assembly report are miniature stand-ins with the same *format*
as the real resources; identifiers are real HPO/GRCh38 identifiers but labels
and scaffold lengths are synthetic. No MVA data is used anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pysam

from rarepipe.core.console import Console
from rarepipe.resources.lock import ResourceKind, register
from rarepipe.stages.intake.stage import IntakeRequest, run_intake
from rarepipe.testing.fixtures import PROBAND, write_fastq_gz

SECRET_PATH = "/synthetic/secret/workdir"

SYNTH_OBO = """format-version: 1.2
data-version: hp/releases/2099-01-01
ontology: hp

[Term]
id: HP:0000001
name: All

[Term]
id: HP:0000118
name: Phenotypic abnormality
is_a: HP:0000001 ! All

[Term]
id: HP:0000005
name: Mode of inheritance
is_a: HP:0000001 ! All

[Term]
id: HP:0000007
name: Synthetic inheritance pattern
is_a: HP:0000005 ! Mode of inheritance

[Term]
id: HP:0001250
name: Synthetic phenotype A
alt_id: HP:0002099
is_a: HP:0000118 ! Phenotypic abnormality

[Term]
id: HP:0001263
name: Synthetic phenotype B
is_a: HP:0000118 ! Phenotypic abnormality

[Term]
id: HP:0000252
name: Synthetic phenotype C
is_a: HP:0001263 ! Synthetic phenotype B

[Term]
id: HP:0000009
name: obsolete synthetic phenotype D
is_obsolete: true
replaced_by: HP:0001263

[Term]
id: HP:0000010
name: obsolete synthetic phenotype E
is_obsolete: true
consider: HP:0001250
consider: HP:0000252
"""

_ASM_COLUMNS = ("# Sequence-Name\tSequence-Role\tAssigned-Molecule\tAssigned-Molecule-Location/Type\tGenBank-Accn\tRelationship\t"
                "RefSeq-Accn\tAssembly-Unit\tSequence-Length\tUCSC-style-name")
_ASM_ROWS = [
    ("1", "assembled-molecule", "1", "Chromosome", "CM000663.2", "NC_000001.11", "Primary Assembly", 248956422, "chr1"),
    ("2", "assembled-molecule", "2", "Chromosome", "CM000664.2", "NC_000002.12", "Primary Assembly", 242193529, "chr2"),
    ("X", "assembled-molecule", "X", "Chromosome", "CM000685.2", "NC_000023.11", "Primary Assembly", 156040895, "chrX"),
    ("Y", "assembled-molecule", "Y", "Chromosome", "CM000686.2", "NC_000024.10", "Primary Assembly", 57227415, "chrY"),
    ("MT", "assembled-molecule", "MT", "Mitochondrion", "J01415.2", "NC_012920.1", "non-nuclear", 16569, "chrM"),
    ("HSCHR1_CTG1_UNLOCALIZED", "unlocalized-scaffold", "1", "Chromosome", "KI270706.1", "NT_187361.1", "Primary Assembly", 175055, "chr1_KI270706v1_random"),
    ("HSCHRUN_CTG1", "unplaced-scaffold", "na", "na", "KI270302.1", "NT_187395.1", "Primary Assembly", 2274, "chrUn_KI270302v1"),
    ("HSCHR1_1_CTG3", "alt-scaffold", "1", "Chromosome", "KI270762.1", "NT_187515.1", "ALT_REF_LOCI_1", 354444, "chr1_KI270762v1_alt"),
]


def synth_assembly_report() -> str:
    lines = ["# SYNTHETIC TEST FIXTURE — mimics the NCBI assembly report format",
             "# Assembly name:  GRCh38.p14", "# GenBank assembly accession: GCA_000001405.29",
             "# RefSeq assembly accession: GCF_000001405.40", _ASM_COLUMNS]
    for name, role, mol, loc, gb, rs, unit, length, ucsc in _ASM_ROWS:
        lines.append("\t".join([name, role, mol, loc, gb, "=", rs, unit, str(length), ucsc]))
    return "\n".join(lines) + "\n"


# ── VCF ─────────────────────────────────────────────────────────────────────

NUMERIC = {"1": 248956422, "2": 242193529, "X": 156040895, "Y": 57227415, "MT": 16569,
           "KI270706.1": 175055, "KI270302.1": 2274, "KI270762.1": 354444,
           "JTFH01000001.1": 25139, "HLA-A*01:01:01:01": 3503, "mystery_contig": 5000}
UCSC = {"chr1": 248956422, "chr2": 242193529, "chrX": 156040895, "chrY": 57227415, "chrM": 16569,
        "chr1_KI270706v1_random": 175055, "chrUn_KI270302v1": 2274, "chr1_KI270762v1_alt": 354444,
        "chrUn_JTFH01000001v1_decoy": 25139, "HLA-A*01:01:01:01": 3503, "mystery_contig": 5000}

HEADER_META = [
    "##fileformat=VCFv4.2",
    '##FILTER=<ID=LowQual,Description="Low quality">',
    '##FILTER=<ID=QD2,Description="QD < 2.0">',
    '##FILTER=<ID=FS60,Description="FS > 60.0">',
    '##FILTER=<ID=SOR3,Description="SOR > 3.0 (declared, never applied)">',
    '##INFO=<ID=DP,Number=1,Type=Integer,Description="Depth">',
    '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
    '##FORMAT=<ID=AD,Number=R,Type=Integer,Description="Allelic depths">',
    '##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Depth">',
    '##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Genotype quality">',
    '##FORMAT=<ID=PL,Number=G,Type=Integer,Description="Phred likelihoods">',
    '##FORMAT=<ID=PS,Number=1,Type=Integer,Description="Phase set">',
    '##FORMAT=<ID=PGT,Number=1,Type=String,Description="Read-backed phasing genotype (declared, never populated)">',
    "##source=HaplotypeCaller",
    f'##GATKCommandLine=<ID=VariantFiltration,CommandLine="VariantFiltration --output {SECRET_PATH}/{PROBAND}.filtered.vcf.gz",Version="4.5.0.0",Date="2099-01-01">',
    "##bcftools_viewVersion=1.17+htslib-1.17",
    f"##bcftools_viewCommand=view -Oz -o {SECRET_PATH}/out.vcf.gz; Date=Fri Jan  1 00:00:00 2099",
]

# (contig key, pos, ref, alt, qual, filter, format, sample)
RECORDS = [
    (0, 10001, "A", "G", "50", "PASS", "GT:AD:DP:GQ:PL:PS", "0|1:15,15:30:99:0,1,2:10001"),
    (0, 10005, "C", "CT", "40", "PASS", "GT:AD:DP:GQ:PL", "0/1:10,10:20:80:0,1,2"),
    (0, 10010, "GTA", "G", "30", "LowQual", "GT:AD:DP:GQ:PL", "1/1:0,10:10:30:2,1,0"),
    (0, 10020, "AC", "GT", "30", "PASS", "GT:AD:DP:GQ:PL", "0/1:6,6:12:50:0,1,2"),
    (0, 10030, "ACG", "TT", "20", "QD2;FS60", "GT:AD:DP:GQ:PL", "0/1:5,4:9:20:0,1,2"),
    (0, 10040, "A", "G,T", "60", "PASS", "GT:AD:DP:GQ:PL", "1/2:0,12,13:25:60:9,9,9,9,0,9"),
    (0, 10050, "G", "A,*", "60", "PASS", "GT:AD:DP:GQ:PL", "0/1:12,13,0:25:60:0,1,2,3,4,5"),
    (0, 10060, "T", "<DEL>", "10", ".", "GT:AD:DP:GQ:PL", "./.:.:.:.:."),
    (1, 20000, "G", "A", ".", "PASS", "GT", "0/0"),
    (2, 30000, "C", "T", "50", "PASS", "GT:AD:DP:GQ:PL", "1:0,15:15:60:9,0"),
    (5, 100, "A", "C", "30", "PASS", "GT:AD:DP:GQ:PL", "0/1:4,4:8:30:0,1,2"),
    (7, 200, "T", "G", "30", "LowQual", "GT:AD:DP:GQ:PL", "0/1:3,4:7:25:0,1,2"),
]


def vcf_text(scheme: str = "numeric", *, malformed_late: bool = False, unsorted: bool = False) -> str:
    contigs = NUMERIC if scheme == "numeric" else UCSC
    names = list(contigs)
    lines = list(HEADER_META)
    lines += [f"##contig=<ID={n},length={l}>" for n, l in contigs.items()]
    lines.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + PROBAND)
    records = list(RECORDS)
    if unsorted:
        records[1], records[2] = records[2], records[1]
    for ci, pos, ref, alt, qual, filt, fmt, sample in records:
        lines.append("\t".join([names[ci], str(pos), ".", ref, alt, qual, filt, "DP=10", fmt, sample]))
    if malformed_late:  # last data line: sample column missing entirely
        lines.append("\t".join([names[7], "300", ".", "A", "G", "30", "PASS", "DP=10", "GT:AD:DP:GQ:PL"]))
    return "\n".join(lines) + "\n"


def write_vcf(path: Path, text: str, index: bool = True) -> Path:
    plain = path.with_suffix("")
    plain.write_text(text)
    pysam.tabix_compress(str(plain), str(path), force=True)
    plain.unlink()
    if index:
        pysam.tabix_index(str(path), preset="vcf", force=True)
    return path


CLEAN_HPO = ["HP:0001250", "HP:0001263", "HP:0000252"]
EDGE_HPO = ["HP:0001250", "HP:0002099", "HP:0000009", "HP:0000010", "HP:9999999", "HP:0000007"]


def build_resources(root: Path, *, hpo: bool = True, assembly: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if hpo:
        p = root / "hpo" / "v2099-01-01" / "hp.obo"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(SYNTH_OBO)
        register(root, ResourceKind.HPO_ONTOLOGY, p, name="Human Phenotype Ontology (hp.obo)", version="2099-01-01",
                 source_url="synthetic://fixture")
    if assembly:
        p = root / "assembly" / "GRCh38.p14" / "GCF_000001405.40_GRCh38.p14_assembly_report.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(synth_assembly_report())
        register(root, ResourceKind.ASSEMBLY_REPORT, p, name="NCBI assembly report GRCh38.p14", version="GRCh38.p14",
                 source_url="synthetic://fixture")
    return root


def build_case(root: Path, *, scheme: str = "numeric", malformed_late: bool = False, unsorted: bool = False,
               hpo_terms: list[str] | None = None, with_fastq: bool = False, empty: bool = False) -> Path:
    """A synthetic case directory as Stage 01 would find it."""
    root.mkdir(parents=True, exist_ok=True)
    if not empty:
        write_vcf(root / "case.vcf.gz", vcf_text(scheme, malformed_late=malformed_late, unsorted=unsorted), index=not unsorted)
    (root / "hpo_terms.txt").write_text("".join(t + "\n" for t in (hpo_terms if hpo_terms is not None else CLEAN_HPO)))
    if with_fastq:
        write_fastq_gz(root / "SYNTHLIB_S1_L001_R1_001.fastq.gz", lane=1, read=1, block_gzip=True, n=200)
        write_fastq_gz(root / "SYNTHLIB_S1_L001_R2_001.fastq.gz", lane=1, read=2, block_gzip=True, n=200)
    return root


def run_intake_for(case_root: Path, output: Path, case_id: str = "SYNTH_CASE") -> Path:
    """Returns the path of the private CaseManifest produced by the real Stage 01."""
    result = run_intake(IntakeRequest(case_root=case_root, case_id=case_id, output=output), Console(quiet=True))
    return result.run_dir / "case_manifest.private.json"
