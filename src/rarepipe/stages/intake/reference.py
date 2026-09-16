"""Genome-build determination from contig evidence.

Deliberate deviation from the PRD's preference order (explicit metadata first):
free-text claims such as ``##reference=`` are frequently uninformative (a local
path) or stale (a header copied across tools), whereas nuclear contig lengths
*are* the coordinate system. So lengths decide the value; claims corroborate,
and a claim that contradicts the lengths is surfaced as an issue. A claim with
no length evidence yields at most ``low`` confidence.

Length tables: primary-assembly nuclear contigs, cross-checked against the UCSC
chrom.sizes files for hg19, hg38 and hs1 (T2T-CHM13v2.0).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rarepipe.stages.intake.manifest import Confidence, Contig, ContigNaming, GenomeBuild, GenomeBuildCall

_CANONICAL = [str(i) for i in range(1, 23)] + ["X", "Y"]

BUILD_LENGTHS: dict[GenomeBuild, dict[str, int]] = {
    GenomeBuild.GRCH37: dict(zip(_CANONICAL, [
        249250621, 243199373, 198022430, 191154276, 180915260, 171115067, 159138663, 146364022,
        141213431, 135534747, 135006516, 133851895, 115169878, 107349540, 102531392, 90354753,
        81195210, 78077248, 59128983, 63025520, 48129895, 51304566, 155270560, 59373566,
    ])),
    GenomeBuild.GRCH38: dict(zip(_CANONICAL, [
        248956422, 242193529, 198295559, 190214555, 181538259, 170805979, 159345973, 145138636,
        138394717, 133797422, 135086622, 133275309, 114364328, 107043718, 101991189, 90338345,
        83257441, 80373285, 58617616, 64444167, 46709983, 50818468, 156040895, 57227415,
    ])),
    GenomeBuild.T2T_CHM13: dict(zip(_CANONICAL, [
        248387328, 242696752, 201105948, 193574945, 182045439, 172126628, 160567428, 146259331,
        150617247, 134758134, 135127769, 133324548, 113566686, 101161492, 99753195, 96330374,
        84276897, 80542538, 61707364, 66210255, 45090682, 51324926, 154259566, 62460029,
    ])),
}

# GRCh37+decoy shares GRCh37 coordinates; conflicts are judged per family.
FAMILY = {GenomeBuild.GRCH37: "GRCh37", GenomeBuild.GRCH37_DECOY: "GRCh37", GenomeBuild.GRCH38: "GRCh38", GenomeBuild.T2T_CHM13: "T2T-CHM13"}

HIGH_CONFIDENCE_MIN_CONTIGS = 3

CLAIM_PATTERNS: list[tuple[GenomeBuild, re.Pattern]] = [
    (GenomeBuild.GRCH38, re.compile(r"GRCh38|hg38|GCA_000001405\.15|GCF_000001405\.(26|39|40)|assembly38|\bb38\b", re.I)),
    (GenomeBuild.GRCH37, re.compile(r"GRCh37|hg19|\bb37\b|hs37d5|human_g1k_v37|GCF_000001405\.(13|25)|assembly19", re.I)),
    (GenomeBuild.T2T_CHM13, re.compile(r"CHM13|T2T|\bhs1\b|GCA_009914755|GCF_009914755", re.I)),
]

_CHR_RE = re.compile(r"^(chr)?([0-9]{1,2}|X|Y|M|MT)$", re.I)


def canonical_key(name: str) -> tuple[str | None, bool]:
    """('1', True) for 'chr1'; ('MT', False) for 'MT'; (None, _) for non-canonical names."""
    m = _CHR_RE.match(name)
    if not m:
        return None, False
    key = m.group(2).upper()
    if key == "M":
        key = "MT"
    if key.isdigit() and not 1 <= int(key) <= 22:
        return None, False
    return key, bool(m.group(1))


def naming_convention(contigs: Iterable[Contig]) -> ContigNaming:
    prefixed = unprefixed = 0
    total = 0
    for c in contigs:
        total += 1
        key, has_chr = canonical_key(c.name)
        if key is None:
            continue
        if has_chr:
            prefixed += 1
        else:
            unprefixed += 1
    if total == 0:
        return ContigNaming.UNKNOWN
    if prefixed and unprefixed:
        return ContigNaming.MIXED
    if prefixed:
        return ContigNaming.UCSC_CHR_PREFIXED
    if unprefixed:
        return ContigNaming.NUMERIC
    return ContigNaming.NONSTANDARD


def _markers(contigs: list[Contig]) -> list[str]:
    names = [c.name for c in contigs]
    found = set()
    for n in names:
        if n == "hs37d5":
            found.add("hs37d5_decoy_contig")
        elif n.endswith("_decoy"):
            found.add("decoy_contigs")
        elif n.endswith("_alt"):
            found.add("alt_contigs")
        elif n.startswith("HLA-"):
            found.add("hla_contigs")
        elif n.upper() in ("CHREBV", "EBV", "NC_007605"):
            found.add("ebv_contig")
    for c in contigs:
        key, has_chr = canonical_key(c.name)
        if key == "MT" and c.length == 16571:
            found.add("hg19_style_chrM_16571")
    return sorted(found)


def match_claims(claims: Iterable[tuple[str, str]]) -> dict[GenomeBuild, list[str]]:
    """claims: (field label, raw value). Evidence strings never echo the raw value (it may be a path)."""
    hits: dict[GenomeBuild, list[str]] = {}
    for label, raw in claims:
        for build, pattern in CLAIM_PATTERNS:
            m = pattern.search(raw or "")
            if m:
                hits.setdefault(build, []).append(f"{label} contains a {build.value} identifier (matched '{m.group(0)}')")
    return hits


def determine_build(contigs: list[Contig], claims: Iterable[tuple[str, str]] = ()) -> GenomeBuildCall:
    naming = naming_convention(contigs)
    markers = _markers(contigs)
    evidence: list[str] = []
    claim_hits = match_claims(claims)
    claimed = set(claim_hits)

    # 1. name-keyed length comparison over canonical nuclear contigs
    compared: dict[str, int] = {}
    for c in contigs:
        key, _ = canonical_key(c.name)
        if key and key != "MT" and c.length is not None:
            compared[key] = c.length
    by_build = {b: sum(1 for k, v in compared.items() if lengths.get(k) == v) for b, lengths in BUILD_LENGTHS.items()}
    exact = [b for b, n in by_build.items() if compared and n == len(compared)]

    length_build: GenomeBuild | None = None
    length_strength = 0
    if exact:
        length_build = exact[0]
        length_strength = len(compared)
        evidence.append(f"{len(compared)} canonical nuclear contig length(s) match {length_build.value} exactly")
    elif compared:
        partial = ", ".join(f"{b.value}: {n}/{len(compared)}" for b, n in by_build.items())
        evidence.append(f"canonical contig lengths match no single recognized assembly ({partial})")
    else:
        # 2. name-independent length fingerprint (e.g. RefSeq accession names)
        all_lengths = {c.length for c in contigs if c.length is not None}
        fp = {b: len(all_lengths & set(lengths.values())) for b, lengths in BUILD_LENGTHS.items()}
        best = max(fp, key=fp.get) if fp else None
        if best and fp[best] >= HIGH_CONFIDENCE_MIN_CONTIGS and sorted(fp.values())[-2] == 0:
            length_build = best
            length_strength = 1  # name-independent → never 'high'
            evidence.append(f"{fp[best]} contig length(s) match {best.value} nuclear contigs (names not canonical)")
        elif contigs and not all_lengths:
            evidence.append("contig names present but no contig lengths declared")
        elif not contigs:
            evidence.append("no contig/sequence dictionary declared")
        else:
            evidence.append("contig lengths present but do not fingerprint a recognized assembly")

    if naming in (ContigNaming.UCSC_CHR_PREFIXED, ContigNaming.NUMERIC):
        compat = "GRCh38, hg19 or T2T-CHM13" if naming == ContigNaming.UCSC_CHR_PREFIXED else "GRCh37 (b37) or Ensembl/NCBI-style GRCh38"
        evidence.append(f"contig naming ({naming.value}) is compatible with {compat}; naming alone does not identify a build")
    for build in sorted(claim_hits, key=lambda b: b.value):
        evidence.extend(claim_hits[build])
    if markers:
        evidence.append("auxiliary contig markers: " + ", ".join(markers))

    actions: list[str] = []
    if length_build:
        value = length_build
        if value == GenomeBuild.GRCH37 and "hs37d5_decoy_contig" in markers:
            value = GenomeBuild.GRCH37_DECOY
        conflicting = {b for b in claimed if FAMILY.get(b) != FAMILY[value]}
        if conflicting:
            confidence = Confidence.MEDIUM
            actions.append("header metadata claims a different build than contig lengths — confirm which reference produced this file")
        elif length_strength >= HIGH_CONFIDENCE_MIN_CONTIGS:
            confidence = Confidence.HIGH
        else:
            confidence = Confidence.MEDIUM
            actions.append("few contigs available for length fingerprint — corroborate build")
        return GenomeBuildCall(value=value, confidence=confidence, evidence=evidence, naming_convention=naming, markers=markers,
                               claim_conflict=bool(conflicting), action_required=actions)

    if compared:
        return GenomeBuildCall(
            value=GenomeBuild.CUSTOM, confidence=Confidence.MEDIUM, evidence=evidence, naming_convention=naming, markers=markers,
            action_required=["identify the reference this file was produced against; contig lengths are not a recognized human assembly"],
        )

    if len(claimed) == 1:
        (claim,) = claimed
        if claim == GenomeBuild.GRCH37 and "hs37d5_decoy_contig" in markers:
            claim = GenomeBuild.GRCH37_DECOY
        return GenomeBuildCall(
            value=claim, confidence=Confidence.LOW, evidence=evidence, naming_convention=naming, markers=markers,
            action_required=["build is asserted by header text only — confirm with contig lengths or a sequence dictionary"],
        )

    if len(claimed) > 1:
        evidence.append("header metadata claims more than one build")
    return GenomeBuildCall(
        value=GenomeBuild.UNKNOWN, confidence=Confidence.INSUFFICIENT, evidence=evidence, naming_convention=naming, markers=markers,
        action_required=["determine build from reference metadata, a sequence dictionary, or contig lengths"],
    )


def shared_contig_length_mismatches(a: list[Contig], b: list[Contig]) -> list[str]:
    la = {c.name: c.length for c in a if c.length is not None}
    return sorted(c.name for c in b if c.length is not None and c.name in la and la[c.name] != c.length)


def canonical_name_sets(contigs: list[Contig]) -> tuple[set[str], set[str]]:
    """(canonical keys, raw names of canonical contigs)."""
    keys, names = set(), set()
    for c in contigs:
        key, _ = canonical_key(c.name)
        if key:
            keys.add(key)
            names.add(c.name)
    return keys, names
