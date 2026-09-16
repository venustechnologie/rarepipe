"""Cross-asset validation: samples, reference consistency, CRAM references, readiness.

Identity is established only by exact metadata label equality. Near-identical
labels are flagged, never merged. Genotype-based identity checks are out of
scope for intake.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from rarepipe.core.issues import Issue, IssueCode, Severity
from rarepipe.stages.intake.manifest import (
    AlignmentMetadata,
    AssetBuild,
    AssetRelationship,
    Confidence,
    Contig,
    ContigNaming,
    CramReference,
    CramReferenceStatus,
    FastaMetadata,
    Format,
    GenomeBuild,
    GenomeBuildCall,
    PedigreeIndividual,
    PedigreeMetadata,
    PedigreeSection,
    Relationship,
    RelationshipType,
    Sample,
    SampleObservation,
    AssertedValue,
    SequenceDictionaryMetadata,
    VcfMetadata,
)
from rarepipe.stages.intake.pedigree import ParsedPedigree
from rarepipe.stages.intake.reference import FAMILY, shared_contig_length_mismatches

_CONF_RANK = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.INSUFFICIENT: 0}


# ── samples ──────────────────────────────────────────────────────────────────


@dataclass
class SampleRegistry:
    by_label: dict[str, Sample] = field(default_factory=dict)

    def observe(self, label: str, asset_id: str, via: str) -> str:
        sample = self.by_label.get(label)
        if sample is None:
            sample = Sample(sample_id=f"SAMPLE_{len(self.by_label) + 1:03d}", observed_in=[], source_labels=[label])
            self.by_label[label] = sample
        obs = SampleObservation(asset_id=asset_id, via=via)
        if obs not in sample.observed_in:
            sample.observed_in.append(obs)
        return sample.sample_id

    def id_of(self, label: str) -> str:
        return self.by_label[label].sample_id

    @property
    def samples(self) -> list[Sample]:
        return sorted(self.by_label.values(), key=lambda s: s.sample_id)


def _norm(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.lower())


def sample_consistency(registry: SampleRegistry, vcf_labels: dict[str, list[str]], aln_labels: dict[str, list[str]],
                       ped_labels: dict[str, list[str]]) -> list[Issue]:
    issues: list[Issue] = []
    all_vcf = {l for labels in vcf_labels.values() for l in labels}
    genomic = all_vcf | {l for labels in aln_labels.values() for l in labels}

    if all_vcf:
        for asset_id, labels in aln_labels.items():
            for label in labels:
                if label not in all_vcf:
                    issues.append(Issue(
                        code=IssueCode.SAMPLE_UNMATCHED_ACROSS_ASSETS, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                        sample_ids=[registry.id_of(label)],
                        message="Alignment read-group sample label does not exactly match any variant-file sample label; correspondence cannot be established from metadata.",
                        evidence=[f"variant-file samples: {', '.join(sorted(registry.id_of(l) for l in all_vcf))}"],
                        suggested_action="Confirm identity with the data provider. Genotype-concordance checks are out of scope for intake.",
                    ))

    groups: dict[str, set[str]] = defaultdict(set)
    for label in registry.by_label:
        groups[_norm(label)].add(label)
    for labels in groups.values():
        if len(labels) > 1:
            issues.append(Issue(
                code=IssueCode.SAMPLE_ID_NEAR_MATCH, severity=Severity.WARNING, sample_ids=sorted(registry.id_of(l) for l in labels),
                message="Sample labels differ only by case or punctuation; they are kept as distinct samples.",
                suggested_action="Confirm whether these refer to the same biological sample.",
            ))

    if len(genomic) > 1:
        issues.append(Issue(code=IssueCode.MULTIPLE_SAMPLES_PRESENT, severity=Severity.INFO,
                            sample_ids=sorted(registry.id_of(l) for l in genomic),
                            message=f"{len(genomic)} distinct sample labels appear in genomic assets. No roles are asserted unless pedigree metadata states them."))

    for asset_id, labels in ped_labels.items():
        missing = [l for l in labels if l not in genomic]
        if missing and genomic:
            issues.append(Issue(code=IssueCode.PEDIGREE_SAMPLE_WITHOUT_DATA, severity=Severity.INFO, asset_ids=[asset_id],
                                sample_ids=sorted(registry.id_of(l) for l in missing),
                                message=f"{len(missing)} pedigree individual(s) have no matching sample label in any genomic asset."))
    return issues


def pedigree_section(registry: SampleRegistry, parsed: dict[str, ParsedPedigree], vcf_pairs: dict[str, list[tuple[str, str]]]
                     ) -> tuple[PedigreeSection, dict[str, PedigreeMetadata]]:
    rels: list[Relationship] = []
    metas: dict[str, PedigreeMetadata] = {}
    for asset_id, ped in parsed.items():
        individuals = []
        for row in ped.rows:
            sid = registry.observe(row.individual, asset_id, "pedigree_individual")
            sample = registry.by_label[row.individual]
            if row.sex != "unknown":
                sample.asserted_sex.append(AssertedValue(value=row.sex, source_asset_id=asset_id))
            if row.affected != "unknown":
                sample.asserted_affected_status.append(AssertedValue(value=row.affected, source_asset_id=asset_id))
            individuals.append(PedigreeIndividual(sample_id=sid, asserted_sex=row.sex, asserted_affected_status=row.affected, source_family_label=row.family))
        for row in ped.rows:
            for parent in (row.father, row.mother):
                if parent:
                    pid = registry.observe(parent, asset_id, "pedigree_individual")
                    rels.append(Relationship(subject=registry.id_of(row.individual), relation="child_of", object=pid, source_asset_id=asset_id))
        metas[asset_id] = PedigreeMetadata(individual_count=len(ped.rows), family_count=len({r.family for r in ped.rows}), individuals=individuals)
    for asset_id, pairs in vcf_pairs.items():
        for child, parent in pairs:
            c = registry.observe(child, asset_id, "vcf_pedigree_header")
            p = registry.observe(parent, asset_id, "vcf_pedigree_header")
            rels.append(Relationship(subject=c, relation="child_of", object=p, source_asset_id=asset_id))
    rels = sorted({r.model_dump_json(): r for r in rels}.values(), key=lambda r: (r.subject, r.object, r.source_asset_id))
    asset_ids = sorted(set(parsed) | {a for a, p in vcf_pairs.items() if p})
    return PedigreeSection(status="available" if (parsed or rels) else "unavailable", asset_ids=asset_ids, relationships=rels), metas


# ── reference ────────────────────────────────────────────────────────────────


def _label(fmt: Format) -> str:
    return fmt.value


def per_asset_build_issues(asset_id: str, fmt: Format, call: GenomeBuildCall) -> list[Issue]:
    issues = []
    if call.value == GenomeBuild.UNKNOWN:
        issues.append(Issue(code=IssueCode.GENOME_BUILD_UNKNOWN, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message=f"Genome build of this {_label(fmt)} could not be determined.", evidence=call.evidence,
                            suggested_action="Determine the build from reference metadata, a sequence dictionary, or the data provider."))
    elif call.value == GenomeBuild.CUSTOM:
        issues.append(Issue(code=IssueCode.GENOME_BUILD_UNKNOWN, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message=f"Contig lengths of this {_label(fmt)} do not match a recognized human assembly (recorded as 'custom').", evidence=call.evidence,
                            suggested_action="Identify the exact reference used to produce this file."))
    elif call.claim_conflict:
        issues.append(Issue(code=IssueCode.GENOME_BUILD_CLAIM_CONFLICT, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message=f"Header text of this {_label(fmt)} names a different build than its contig lengths establish.", evidence=call.evidence,
                            suggested_action="Confirm which reference produced this file."))
    elif call.confidence == Confidence.LOW:
        issues.append(Issue(code=IssueCode.GENOME_BUILD_UNCONFIRMED, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message=f"Genome build of this {_label(fmt)} ({call.value.value}) is asserted by header text only.", evidence=call.evidence,
                            suggested_action="Confirm with contig lengths or a sequence dictionary."))
    elif call.confidence == Confidence.MEDIUM:
        issues.append(Issue(code=IssueCode.GENOME_BUILD_UNCONFIRMED, severity=Severity.WARNING, asset_ids=[asset_id],
                            message=f"Genome build of this {_label(fmt)} ({call.value.value}) rests on limited contig evidence.", evidence=call.evidence))
    if call.naming_convention == ContigNaming.NONSTANDARD:
        issues.append(Issue(code=IssueCode.NONSTANDARD_CONTIG_NAMING, severity=Severity.WARNING, asset_ids=[asset_id],
                            message="No contigs use standard human chromosome names (chr1/1 … chrX/X)."))
    elif call.naming_convention == ContigNaming.MIXED:
        issues.append(Issue(code=IssueCode.NONSTANDARD_CONTIG_NAMING, severity=Severity.WARNING, asset_ids=[asset_id],
                            message="Contig names mix 'chr'-prefixed and unprefixed chromosome names within one file."))
    return issues


@dataclass
class RefEntry:
    asset_id: str
    fmt: Format
    contigs: list[Contig]
    call: GenomeBuildCall


def reference_consistency(entries: list[RefEntry]) -> tuple[GenomeBuildCall, list[AssetBuild], list[Issue]]:
    issues: list[Issue] = []
    per_asset = [AssetBuild(asset_id=e.asset_id, value=e.call.value, confidence=e.call.confidence) for e in entries]

    firm = [e for e in entries if e.call.value in FAMILY and e.call.confidence in (Confidence.HIGH, Confidence.MEDIUM)]
    soft = [e for e in entries if e.call.value in FAMILY and e.call.confidence == Confidence.LOW]
    firm_families = {FAMILY[e.call.value] for e in firm}
    evidence = [f"{e.asset_id} ({e.fmt.value}): {e.call.value.value}, confidence {e.call.confidence.value}" for e in entries]

    conflict = False
    if len(firm_families) > 1:
        conflict = True
        issues.append(Issue(code=IssueCode.REFERENCE_BUILD_CONFLICT, severity=Severity.BLOCKER, asset_ids=[e.asset_id for e in firm],
                            message="Genomic assets are consistent with different genome builds.", evidence=[x for x in evidence if any(e.asset_id in x for e in firm)],
                            suggested_action="Obtain files on a single reference. Intake does not lift over coordinates."))
    elif firm_families and any(FAMILY[e.call.value] not in firm_families for e in soft):
        issues.append(Issue(code=IssueCode.REFERENCE_BUILD_CONFLICT, severity=Severity.ACTION_REQUIRED,
                            asset_ids=[e.asset_id for e in firm + soft], evidence=evidence,
                            message="A header-text build claim disagrees with the build established by contig lengths in another asset."))

    if not conflict:
        mismatches = []
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                names = shared_contig_length_mismatches(a.contigs, b.contigs)
                if names:
                    mismatches.append((a, b, names))
        for a, b, names in mismatches:
            shown = ", ".join(names[:5]) + (f" (+{len(names) - 5} more)" if len(names) > 5 else "")
            issues.append(Issue(code=IssueCode.REFERENCE_CONTIG_LENGTH_MISMATCH, severity=Severity.BLOCKER, asset_ids=[a.asset_id, b.asset_id],
                                message=f"{len(names)} identically named contig(s) have different lengths between two assets.",
                                evidence=[f"contigs: {shown}"], suggested_action="The assets were produced against different references; do not combine them."))
            conflict = True

    namings = {e.call.naming_convention for e in entries if e.call.naming_convention in (ContigNaming.UCSC_CHR_PREFIXED, ContigNaming.NUMERIC)}
    if len(namings) > 1:
        issues.append(Issue(code=IssueCode.CONTIG_NAMING_INCONSISTENT, severity=Severity.WARNING,
                            asset_ids=[e.asset_id for e in entries if e.call.naming_convention in namings],
                            message="Assets use different chromosome naming conventions ('chr1' vs '1').",
                            evidence=[f"{e.asset_id}: {e.call.naming_convention.value}" for e in entries if e.call.naming_convention in namings],
                            suggested_action="Harmonize naming in a normalization stage; intake does not rename contigs."))

    if conflict:
        case_call = GenomeBuildCall(value=GenomeBuild.UNKNOWN, confidence=Confidence.INSUFFICIENT, evidence=evidence,
                                    action_required=["resolve the reference conflict between assets before any analysis"])
    elif firm or soft:
        best = max(firm + soft, key=lambda e: _CONF_RANK[e.call.confidence])
        values = {e.call.value for e in firm + soft}
        value = best.call.value if len(values) == 1 else next(b for b in (GenomeBuild.GRCH37, GenomeBuild.GRCH38, GenomeBuild.T2T_CHM13) if FAMILY[b] == FAMILY[best.call.value])
        actions = []
        undetermined = [e for e in entries if e.call.value not in FAMILY]
        if undetermined:
            actions.append(f"{len(undetermined)} genomic asset(s) could not be independently fingerprinted; their build is not proven by the others")
        if best.call.confidence != Confidence.HIGH:
            actions.extend(best.call.action_required)
        case_call = GenomeBuildCall(value=value, confidence=best.call.confidence, evidence=evidence, naming_convention=best.call.naming_convention,
                                    markers=sorted({m for e in firm + soft for m in e.call.markers}), action_required=actions)
    elif any(e.call.value == GenomeBuild.CUSTOM for e in entries):
        case_call = GenomeBuildCall(value=GenomeBuild.CUSTOM, confidence=Confidence.MEDIUM, evidence=evidence,
                                    action_required=["identify the custom reference used"])
    else:
        case_call = GenomeBuildCall(value=GenomeBuild.UNKNOWN, confidence=Confidence.INSUFFICIENT,
                                    evidence=evidence or ["no genomic asset declares contigs"],
                                    action_required=["determine build from VCF reference metadata or contig fingerprint"])
    return case_call, per_asset, issues


def resolve_cram_reference(asset_id: str, meta: AlignmentMetadata, declared_uris: list[str],
                           fastas: dict[str, FastaMetadata]) -> tuple[CramReference, list[AssetRelationship], list[Issue]]:
    issues: list[Issue] = []
    rels: list[AssetRelationship] = []
    sq = meta.contigs
    all_md5 = bool(sq) and all(c.md5 for c in sq)
    evidence: list[str] = []
    verified, candidates = [], []
    for fasta_id, fm in sorted(fastas.items()):
        by_name = {c.name: c for c in fm.contigs}
        if not all(c.name in by_name and by_name[c.name].length == c.length for c in sq):
            evidence.append(f"{fasta_id}: contig names/lengths do not cover this CRAM's sequence dictionary")
            continue
        if all_md5 and fm.md5_computed:
            if all(by_name[c.name].md5 == c.md5 for c in sq):
                verified.append(fasta_id)
                evidence.append(f"{fasta_id}: all {len(sq)} @SQ M5 checksums match sequence MD5s computed from the FASTA")
            else:
                bad = sum(1 for c in sq if by_name[c.name].md5 != c.md5)
                evidence.append(f"{fasta_id}: names/lengths match but {bad} sequence MD5(s) differ — not the reference used")
        else:
            candidates.append(fasta_id)
            evidence.append(f"{fasta_id}: contig names/lengths match; sequence MD5 not verifiable")

    if verified:
        status = CramReferenceStatus.AVAILABLE_VERIFIED_MD5
        rels += [AssetRelationship(type=RelationshipType.VERIFIED_REFERENCE_FOR, source=f, target=asset_id, evidence=["@SQ M5 == FASTA sequence MD5 for every contig"]) for f in verified]
    elif candidates:
        status = CramReferenceStatus.AVAILABLE_UNVERIFIED
        rels += [AssetRelationship(type=RelationshipType.CANDIDATE_REFERENCE_FOR, source=f, target=asset_id, evidence=["contig names and lengths match"]) for f in candidates]
        issues.append(Issue(code=IssueCode.CRAM_REFERENCE_UNVERIFIED, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id, *candidates],
                            message="A reference FASTA matching this CRAM's contig names/lengths is present, but sequence identity could not be verified by MD5.",
                            evidence=evidence, suggested_action="Confirm the exact reference; decoding CRAM against the wrong sequence silently corrupts reads."))
    else:
        status = CramReferenceStatus.UNAVAILABLE
        issues.append(Issue(code=IssueCode.CRAM_REFERENCE_UNAVAILABLE, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message="The reference sequence required to decode this CRAM is not available to intake.",
                            evidence=evidence or ["no reference FASTA supplied in the case root or via --reference"],
                            suggested_action="Supply the exact reference (e.g. rarepipe intake --reference /path/ref.fa). Intake never substitutes a reference or fetches one over the network."))
    if sq and not all_md5:
        issues.append(Issue(code=IssueCode.CRAM_REFERENCE_MD5_ABSENT, severity=Severity.WARNING, asset_ids=[asset_id],
                            message="Some @SQ lines lack M5 checksums; reference identity cannot be verified by sequence digest."))
    return CramReference(all_sequences_have_md5=all_md5, status=status, reference_asset_ids=verified or candidates,
                         declared_uris=declared_uris, evidence=evidence), rels, issues


def reference_entries(metas: dict[str, object]) -> list[RefEntry]:
    entries = []
    for asset_id, m in sorted(metas.items()):
        if isinstance(m, VcfMetadata) and m.header_valid:
            entries.append(RefEntry(asset_id, m.format, m.contigs, m.genome_build))
        elif isinstance(m, AlignmentMetadata) and m.header_valid:
            entries.append(RefEntry(asset_id, m.format, m.contigs, m.genome_build))
        elif isinstance(m, FastaMetadata) and m.contigs:
            entries.append(RefEntry(asset_id, Format.FASTA, m.contigs, m.genome_build))
        elif isinstance(m, SequenceDictionaryMetadata):
            entries.append(RefEntry(asset_id, Format.SEQUENCE_DICTIONARY, m.contigs, m.genome_build))
    return entries
