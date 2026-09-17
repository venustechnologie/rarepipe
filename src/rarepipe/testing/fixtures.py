"""Synthetic case fixtures. Entirely generated: random sequence, invented sample
labels, a handful of records. No real individual's data, no real reference
sequence — only public assembly contig *lengths* are used for headers.

Generated at test time (and via ``rarepipe fixtures``) rather than committed as
binaries, so every fixture is reviewable as code.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from collections.abc import Callable
from pathlib import Path

import pysam

from rarepipe.stages.intake.manifest import GenomeBuild
from rarepipe.stages.intake.reference import BUILD_LENGTHS

# Labels deliberately distinctive so privacy tests can grep for leaks.
PROBAND = "SYNTHKID-7Q3X"
MOTHER = "SYNTHMOM-4R8Z"
FATHER = "SYNTHDAD-9K2W"
ALL_SOURCE_LABELS = [PROBAND, MOTHER, FATHER, "SYNTH-OTHER-1M5B"]


def _rng(seed: str) -> random.Random:
    return random.Random(seed)


def _contigs(build: GenomeBuild, prefix: str = "chr", names: list[str] | None = None) -> list[tuple[str, int]]:
    lengths = BUILD_LENGTHS[build]
    keys = names or ["1", "2", "3", "22", "X", "Y"]
    return [(f"{prefix}{k}", lengths[k]) for k in keys]


def write_vcf(path: Path, *, samples: list[str], contigs: list[tuple[str, int | None]], seed: str = "vcf",
              index: str | None = "tbi", extra_header: list[str] = (), n_records: int = 5) -> Path:
    """Writes bgzipped VCF (path must end .vcf.gz) and optional tbi/csi."""
    rng = _rng(seed)
    header = pysam.VariantHeader()
    for name, length in contigs:
        if length is None:
            header.add_line(f"##contig=<ID={name}>")
        else:
            header.contigs.add(name, length=length)
    header.add_line('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">')
    header.add_line('##INFO=<ID=DP,Number=1,Type=Integer,Description="Depth">')
    header.add_line('##source=synthetic-fixture-generator')
    for line in extra_header:
        header.add_line(line)
    for s in samples:
        header.add_sample(s)
    plain = path.with_suffix("")  # strip .gz
    first_contig = contigs[0][0]
    with pysam.VariantFile(str(plain), "w", header=header) as out:
        pos = 10_000
        for _ in range(n_records):
            pos += rng.randint(100, 5000)
            rec = out.new_record(contig=first_contig, start=pos - 1, alleles=(rng.choice("ACGT"), rng.choice("ACGT") + "T"))
            rec.info["DP"] = rng.randint(10, 60)
            for s in samples:
                rec.samples[s]["GT"] = (rng.randint(0, 1), 1)
            out.write(rec)
    pysam.tabix_compress(str(plain), str(path), force=True)
    plain.unlink()
    if index:
        pysam.tabix_index(str(path), preset="vcf", force=True, csi=(index == "csi"))
    return path


def _random_seq(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("ACGT") for _ in range(n))


def write_alignments(path: Path, *, contigs: list[tuple[str, int]], read_groups: list[tuple[str, str | None]],
                     seed: str = "bam", index: bool = True, reference: Path | None = None,
                     sq_extra: dict[str, dict] | None = None, n_reads: int = 20) -> Path:
    rng = _rng(seed)
    sq = []
    for name, length in contigs:
        entry = {"SN": name, "LN": length}
        entry.update((sq_extra or {}).get(name, {}))
        sq.append(entry)
    rg = []
    for rg_id, sm in read_groups:
        d = {"ID": rg_id, "PL": "ILLUMINA", "LB": f"lib-{rg_id}"}
        if sm is not None:
            d["SM"] = sm
        rg.append(d)
    header = {"HD": {"VN": "1.6", "SO": "coordinate"}, "SQ": sq, "PG": [{"ID": "synthgen", "PN": "synthetic-fixture-generator", "VN": "0"}]}
    if rg:
        header["RG"] = rg
    is_cram = path.suffix == ".cram"
    mode = "wc" if is_cram else "wb"
    kwargs = {"reference_filename": str(reference)} if reference else {}
    ref_seq = None
    if is_cram and reference:
        ref_seq = pysam.FastaFile(str(reference))
    with pysam.AlignmentFile(str(path), mode, header=header, **kwargs) as out:
        positions = sorted(rng.randint(100, 2000) for _ in range(n_reads))
        for i, pos in enumerate(positions):
            a = pysam.AlignedSegment(out.header)
            a.query_name = f"read{i:04d}"
            a.reference_id = 0
            a.reference_start = pos
            a.query_sequence = ref_seq.fetch(contigs[0][0], pos, pos + 50) if ref_seq else _random_seq(rng, 50)
            a.cigartuples = [(0, 50)]
            a.mapping_quality = 60
            a.query_qualities = pysam.qualitystring_to_array("I" * 50)
            if rg:
                a.set_tag("RG", rg[0]["ID"])
            out.write(a)
    if index:
        pysam.index(str(path))
    return path


def write_fasta(path: Path, contigs: list[tuple[str, int]], seed: str = "fasta", fai: bool = True) -> dict[str, str]:
    rng = _rng(seed)
    md5s = {}
    with path.open("w") as fh:
        for name, length in contigs:
            seq = _random_seq(rng, length)
            md5s[name] = hashlib.md5(seq.encode()).hexdigest()
            fh.write(f">{name}\n")
            for i in range(0, length, 60):
                fh.write(seq[i : i + 60] + "\n")
    if fai:
        pysam.faidx(str(path))
    return md5s


def write_hpo(path: Path, terms: list[str]) -> Path:
    path.write_text("".join(t + "\n" for t in terms))
    return path


VALID_HPO = ["HP:0001250", "HP:0001263", "HP:0000252", "HP:0001252", "HP:0002376"]


# ── named cases ─────────────────────────────────────────────────────────────


def healthy(root: Path) -> None:
    """A: GRCh38 VCF+tbi, BAM+bai (optional), valid HPO → INTAKE_COMPLETE."""
    write_vcf(root / "variants" / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    write_alignments(root / "reads" / "case.bam", contigs=_contigs(GenomeBuild.GRCH38), read_groups=[("rg1", PROBAND)])
    write_hpo(root / "phenotype" / "hpo_terms.txt", VALID_HPO)


def unknown_build(root: Path) -> None:
    """B: VCF declares contig names but no lengths and no reference claim."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=[("chr1", None), ("chr2", None)])
    write_hpo(root / "hpo.txt", VALID_HPO)


def missing_index(root: Path) -> None:
    """C: bgzipped GRCh38 VCF without .tbi/.csi."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38), index=None)
    write_hpo(root / "hpo.txt", VALID_HPO)


def reference_conflict(root: Path) -> None:
    """D: VCF on GRCh38, BAM on GRCh37 → INTAKE_BLOCKED."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    write_alignments(root / "case.bam", contigs=_contigs(GenomeBuild.GRCH37), read_groups=[("rg1", PROBAND)])
    write_hpo(root / "hpo.txt", VALID_HPO)


def malformed_hpo(root: Path) -> None:
    """E: HPO file with malformed identifiers."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    write_hpo(root / "hpo.txt", ["HP:0001250", "HP:12345", "HP_0004322", "hp:0001263", "HP:00012500", "HP:0000252"])


def unknown_auxiliary(root: Path) -> None:
    """F: healthy core plus files nobody declared."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    write_hpo(root / "hpo.txt", VALID_HPO)
    rng = _rng("aux")
    (root / "mystery.xyz").write_bytes(bytes(rng.randrange(256) for _ in range(4096)))
    (root / "notes").mkdir()
    (root / "notes" / "scratch.dat").write_bytes(b"\x00\x01\x02binary-ish\xff")


def truncated_bam(root: Path) -> None:
    """BAM with its BGZF EOF block cut off."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    bam = write_alignments(root / "case.bam", contigs=_contigs(GenomeBuild.GRCH38), read_groups=[("rg1", PROBAND)], index=False)
    data = bam.read_bytes()
    bam.write_bytes(data[: len(data) - 28])
    write_hpo(root / "hpo.txt", VALID_HPO)


def cram_without_reference(root: Path, scratch: Path) -> None:
    """CRAM whose @SQ M5 points at a reference that is not supplied."""
    ref = scratch / "synthetic_ref.fa"
    contigs = [("synth1", 5000), ("synth2", 3000)]
    md5s = write_fasta(ref, contigs)
    write_alignments(root / "case.cram", contigs=contigs, read_groups=[("rg1", PROBAND)], reference=ref,
                     sq_extra={n: {"M5": m} for n, m in md5s.items()})
    write_hpo(root / "hpo.txt", VALID_HPO)


def cram_with_reference(root: Path, scratch: Path) -> None:
    contigs = [("synth1", 5000), ("synth2", 3000)]
    md5s = write_fasta(root / "ref" / "synthetic_ref.fa", contigs)
    write_alignments(root / "case.cram", contigs=contigs, read_groups=[("rg1", PROBAND)], reference=root / "ref" / "synthetic_ref.fa",
                     sq_extra={n: {"M5": m} for n, m in md5s.items()})
    write_hpo(root / "hpo.txt", VALID_HPO)


def trio_with_pedigree(root: Path) -> None:
    write_vcf(root / "trio.vcf.gz", samples=[PROBAND, MOTHER, FATHER], contigs=_contigs(GenomeBuild.GRCH38))
    (root / "family.ped").write_text(
        "#family\tindividual\tpaternal\tmaternal\tsex\tphenotype\n"
        f"FAM1\t{PROBAND}\t{FATHER}\t{MOTHER}\t1\t2\n"
        f"FAM1\t{FATHER}\t0\t0\t1\t1\n"
        f"FAM1\t{MOTHER}\t0\t0\t2\t1\n"
    )
    (root / "phenopacket.json").write_text(json.dumps({
        "id": "synthetic",
        "phenotypicFeatures": [
            {"type": {"id": "HP:0001250", "label": "Seizure"}},
            {"type": {"id": "HP:0001263"}},
            {"type": {"id": "HP:0000252"}, "excluded": True},
        ],
    }, indent=2))


def sample_mismatch(root: Path) -> None:
    """VCF and BAM name different samples; a near-identical label is also present."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    write_alignments(root / "case.bam", contigs=_contigs(GenomeBuild.GRCH38), read_groups=[("rg1", "SYNTH-OTHER-1M5B")])
    write_alignments(root / "case2.bam", contigs=_contigs(GenomeBuild.GRCH38), read_groups=[("rg1", PROBAND.lower())], seed="b2")
    write_hpo(root / "hpo.txt", VALID_HPO)


def extension_mismatch(root: Path) -> None:
    """A VCF named .bam, and a BAM hidden as .dat."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    shutil.copy(root / "case.vcf.gz", root / "looks_like.bam")
    write_alignments(root / "reads.bam", contigs=_contigs(GenomeBuild.GRCH38), read_groups=[("rg1", PROBAND)], index=False)
    (root / "reads.bam").rename(root / "sample.dat")
    write_hpo(root / "hpo.txt", VALID_HPO)


def md5_sidecar(root: Path) -> None:
    vcf = write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38))
    (root / "case.vcf.gz.md5").write_text(hashlib.md5(vcf.read_bytes()).hexdigest() + "  case.vcf.gz\n")
    (root / "case.vcf.gz.tbi.md5").write_text("0" * 32 + "  case.vcf.gz.tbi\n")  # deliberately wrong
    write_hpo(root / "hpo.txt", VALID_HPO)


def write_fastq_gz(path: Path, *, lane: int, read: int, n: int = 50, seed: str = "fq", truncate: bool = False) -> Path:
    import gzip

    rng = _rng(f"{seed}-{lane}-{read}")
    lines = []
    for i in range(n):
        lines.append(f"@SYNTHSEQ01:7:SYNTHFLOWCELL:{lane}:1101:{1000 + i}:{2000 + i} {read}:N:0:ACGTACGT\n{_random_seq(rng, 100)}\n+\n{'F' * 100}\n")
    data = gzip.compress("".join(lines).encode())
    path.write_bytes(data[: len(data) // 2] if truncate else data)
    return path


def write_docx(path: Path, paragraphs: list[str]) -> Path:
    import zipfile
    from xml.sax.saxutils import escape

    body = "".join(f"<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    return path


def _appledouble(path: Path) -> None:
    path.write_bytes(b"\x00\x05\x16\x07\x00\x02\x00\x00" + b"Mac OS X        " + b"\x00" * 4072)


def fastq_exfat_partial(root: Path) -> None:
    """Mirrors a real-world shape: VCF+tbi, paired-end FASTQ over two lanes with one mate still
    downloading, a prose clinical .docx without HPO IDs, and macOS ._ files from an exFAT drive."""
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38, prefix=""))
    stem = "SYNTHLIB_S1"
    write_fastq_gz(root / f"{stem}_L001_R1_001.fastq.gz", lane=1, read=1)
    write_fastq_gz(root / f"{stem}_L001_R2_001.fastq.gz", lane=1, read=2)
    write_fastq_gz(root / f"{stem}_L002_R1_001.fastq.gz", lane=2, read=1)
    write_fastq_gz(root / f"{stem}_L002_R2_001.fastq.gz.download-part", lane=2, read=2, truncate=True)
    write_docx(root / "Clinical_Phenotype.docx", ["Clinical summary", "Developmental delay noted in infancy.", "No structured terms supplied."])
    for name in ("case.vcf.gz", "case.vcf.gz.tbi", "Clinical_Phenotype.docx", f"{stem}_L001_R1_001.fastq.gz", "orphan_L009_R1_001.fastq.gz.download-part"):
        _appledouble(root / f"._{name}")


def fastq_complete_docx_hpo(root: Path) -> None:
    write_vcf(root / "case.vcf.gz", samples=[PROBAND], contigs=_contigs(GenomeBuild.GRCH38, prefix=""))
    write_fastq_gz(root / "SYNTHLIB_S1_L001_R1_001.fastq.gz", lane=1, read=1)
    write_fastq_gz(root / "SYNTHLIB_S1_L001_R2_001.fastq.gz", lane=1, read=2)
    write_docx(root / "phenotype.docx", ["Phenotype", "Seizures (HP:0001250)", "Global developmental delay HP:0001263", "Typo HP:12345"])


def no_genomic_input(root: Path) -> None:
    write_hpo(root / "hpo.txt", VALID_HPO)


CASES: dict[str, Callable] = {
    "A_healthy": healthy,
    "B_unknown_build": unknown_build,
    "C_missing_index": missing_index,
    "D_reference_conflict": reference_conflict,
    "E_malformed_hpo": malformed_hpo,
    "F_unknown_auxiliary": unknown_auxiliary,
    "G_truncated_bam": truncated_bam,
    "H_cram_without_reference": cram_without_reference,
    "I_cram_with_reference": cram_with_reference,
    "J_trio_with_pedigree": trio_with_pedigree,
    "K_sample_mismatch": sample_mismatch,
    "L_extension_mismatch": extension_mismatch,
    "M_md5_sidecar": md5_sidecar,
    "N_no_genomic_input": no_genomic_input,
    "O_fastq_exfat_partial": fastq_exfat_partial,
    "P_fastq_complete_docx_hpo": fastq_complete_docx_hpo,
}


def build(name: str, root: Path, scratch: Path) -> Path:
    fn = CASES[name]
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("variants", "reads", "phenotype", "ref"):
        (root / sub).mkdir(exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    if fn.__code__.co_argcount == 2:
        fn(root, scratch)
    else:
        fn(root)
    for sub in ("variants", "reads", "phenotype", "ref"):
        d = root / sub
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
    return root
