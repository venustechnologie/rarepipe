"""The four baseline analysis profiles and the Exomiser job files they generate.

The matrix varies exactly two things — nothing else:

    profile          HPO set                      VCF FILTER treatment
    A standard       7 phenotypic-abnormality     failedVariantFilter (drop non-PASS)
    B filter-sens.   7 phenotypic-abnormality     no failedVariantFilter (non-PASS permitted)
    C pheno-sens.    all 8 supplied terms         failedVariantFilter
    D inclusive      all 8 supplied terms         no failedVariantFilter

``analysisMode: PASS_ONLY`` stays constant in all four. It is Exomiser's memory
strategy (retain only variants passing Exomiser's own filter chain) and has nothing
to do with the VCF's FILTER column; ``failedVariantFilter`` is the step that reads
that column. Conflating the two would silently change the experiment.

Step order follows Exomiser's shipped preset-genome-analysis (phenotype prioritiser
first, then priorityScoreFilter) because its own comments state this "dramatically
reduce[s] the time and memory required to analyse a genome". Two documented
deviations, recorded as assumptions rather than buried:
  * REMM is omitted from pathogenicitySources — the preset lists it, but it needs a
    separately downloaded tabix file we have not provisioned, and Exomiser refuses
    to start without it;
  * variantEffectFilter removes non-coding effects (as in Exomiser's own job
    template), keeping this baseline a coding-sequence analysis.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from rarepipe.stages.baseline.model import (
    AnalysisAssumption,
    AnalysisProfile,
    FilterPolicy,
    PhenotypeSelection,
)

GENOME_ASSEMBLY = "hg38"
FREQUENCY_MAX_PERCENT = 2.0
HIPHIVE_MIN_PRIORITY_SCORE = 0.501

INHERITANCE_MODES = {
    "AUTOSOMAL_DOMINANT": 0.1,
    "AUTOSOMAL_RECESSIVE_COMP_HET": 2.0,
    "AUTOSOMAL_RECESSIVE_HOM_ALT": 0.1,
    "X_DOMINANT": 0.1,
    "X_RECESSIVE_COMP_HET": 2.0,
    "X_RECESSIVE_HOM_ALT": 0.1,
    "MITOCHONDRIAL": 0.2,
}
FREQUENCY_SOURCES = [
    "UK10K", "GNOMAD_E_AFR", "GNOMAD_E_AMR", "GNOMAD_E_EAS", "GNOMAD_E_NFE", "GNOMAD_E_SAS",
    "GNOMAD_G_AFR", "GNOMAD_G_AMR", "GNOMAD_G_EAS", "GNOMAD_G_NFE", "GNOMAD_G_SAS",
]
PATHOGENICITY_SOURCES = ["REVEL", "MVP", "ALPHA_MISSENSE", "SPLICE_AI"]  # REMM deliberately omitted (see module docstring)
VARIANT_EFFECTS_REMOVED = [
    "FIVE_PRIME_UTR_EXON_VARIANT", "FIVE_PRIME_UTR_INTRON_VARIANT", "THREE_PRIME_UTR_EXON_VARIANT",
    "THREE_PRIME_UTR_INTRON_VARIANT", "NON_CODING_TRANSCRIPT_EXON_VARIANT", "NON_CODING_TRANSCRIPT_INTRON_VARIANT",
    "CODING_TRANSCRIPT_INTRON_VARIANT", "UPSTREAM_GENE_VARIANT", "DOWNSTREAM_GENE_VARIANT", "INTERGENIC_VARIANT",
    "REGULATORY_REGION_VARIANT",
]
OUTPUT_FORMATS = ["JSON", "TSV_GENE", "TSV_VARIANT"]  # no HTML: downstream stages must not parse human pages

PHENOTYPE_ASSUMPTION = AnalysisAssumption(
    id="ASSUME_HPO_DESCRIBE_PROBAND",
    statement="The supplied HPO terms are used as features describing this child for phenotype-driven prioritization.",
    basis=("The public challenge description states participants receive the child's genomic data plus a description of their "
           "symptoms/phenotypic presentations. The case record still states polarity: unspecified — this assumption belongs to "
           "the analysis, not to the case."),
)
ROLE_ASSUMPTION = AnalysisAssumption(
    id="ASSUME_ANALYSIS_ROLE_PROBAND",
    statement="The single sequenced sample is designated proband for this analysis.",
    basis="Single-subject case; a computational role the solver requires. NOT evidence about family structure.",
)
REMM_ASSUMPTION = AnalysisAssumption(
    id="ASSUME_NO_REMM_NONCODING_SCORING",
    statement="Non-coding pathogenicity scoring (REMM) is not used, and non-coding variant effects are filtered out.",
    basis=("Exomiser's genome preset lists REMM but requires a separately provisioned tabix file. This baseline is therefore a "
           "coding-sequence analysis; a non-coding profile would need REMM provisioned and would be a separate declared profile."),
)


@dataclass(frozen=True)
class ProfileSpec:
    profile_id: str
    label: str
    phenotype_rule: str  # phenotypic_abnormality_only | all_supplied_terms
    failed_variant_filter: bool


PROFILE_SPECS = [
    ProfileSpec("PROFILE_A", "Standard — phenotypic-abnormality terms, non-PASS dropped", "phenotypic_abnormality_only", True),
    ProfileSpec("PROFILE_B", "Filter-sensitive — phenotypic-abnormality terms, non-PASS permitted", "phenotypic_abnormality_only", False),
    ProfileSpec("PROFILE_C", "Phenotype-sensitive — all supplied terms, non-PASS dropped", "all_supplied_terms", True),
    ProfileSpec("PROFILE_D", "Inclusive — all supplied terms, non-PASS permitted", "all_supplied_terms", False),
]


def select_terms(terms: list[dict], rule: str) -> tuple[list[str], list[str]]:
    """(hpo ids, branches included). Uses each term's canonical id where the ontology resolved one."""
    chosen: list[str] = []
    branches: set[str] = set()
    for t in terms:
        tid = t.get("canonical_id") or t.get("source_id")
        if not tid:
            continue
        if rule == "phenotypic_abnormality_only" and "phenotypic_abnormality" not in (t.get("branches") or []):
            continue
        chosen.append(tid)
        branches.update(t.get("branches") or ["unclassified"])
    return sorted(dict.fromkeys(chosen)), sorted(branches)


def analysis_steps(failed_variant_filter: bool) -> list[dict]:
    steps: list[dict] = [
        {"hiPhivePrioritiser": {}},
        {"priorityScoreFilter": {"priorityType": "HIPHIVE_PRIORITY", "minPriorityScore": HIPHIVE_MIN_PRIORITY_SCORE}},
        {"geneBlacklistFilter": {}},
    ]
    if failed_variant_filter:
        # Drops variants whose VCF FILTER is neither PASS nor '.'. Their labels are never rewritten.
        steps.append({"failedVariantFilter": {}})
    steps += [
        {"variantEffectFilter": {"remove": list(VARIANT_EFFECTS_REMOVED)}},
        {"frequencyFilter": {"maxFrequency": FREQUENCY_MAX_PERCENT}},
        {"pathogenicityFilter": {"keepNonPathogenic": True}},
        {"inheritanceFilter": {}},
        {"omimPrioritiser": {}},
    ]
    return steps


def job_yaml(spec: ProfileSpec, *, proband_id: str, hpo_ids: list[str], vcf_path: Path, output_dir: Path, output_prefix: str) -> str:
    """One Exomiser job file: phenopacket + analysis + outputOptions (the shipped job-template shape)."""
    job = {
        "phenopacket": {
            "id": f"rarepipe-{spec.profile_id.lower()}",
            "subject": {"id": proband_id, "sex": "UNKNOWN_SEX"},
            "phenotypicFeatures": [{"type": {"id": t}} for t in hpo_ids],
            "htsFiles": [{"uri": str(vcf_path), "htsFormat": "VCF", "genomeAssembly": GENOME_ASSEMBLY}],
            "metaData": {"createdBy": "rarepipe", "phenopacketSchemaVersion": "1.0"},
        },
        "analysis": {
            "analysisMode": "PASS_ONLY",
            "inheritanceModes": dict(INHERITANCE_MODES),
            "frequencySources": list(FREQUENCY_SOURCES),
            "pathogenicitySources": list(PATHOGENICITY_SOURCES),
            "steps": analysis_steps(spec.failed_variant_filter),
        },
        "outputOptions": {
            "outputContributingVariantsOnly": False,
            "numGenes": 0,  # all ranked genes; truncation belongs in our report, not in the evidence
            "outputDirectory": str(output_dir),
            "outputFileName": output_prefix,
            "outputFormats": list(OUTPUT_FORMATS),
        },
    }
    return yaml.safe_dump(job, sort_keys=False, default_flow_style=False)


def application_properties(data_dir: Path, hg38_version: str, phenotype_version: str) -> str:
    return "\n".join([
        "# generated by rarepipe — pinned, offline",
        f"exomiser.data-directory={data_dir}",
        f"exomiser.hg38.data-version={hg38_version}",
        f"exomiser.phenotype.data-version={phenotype_version}",
        "logging.level.com.zaxxer.hikari=ERROR",
        "",
    ])


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def canonical_for_hashing(text: str) -> str:
    """Config digest must describe the *analysis*, not where this run happened to write files."""
    job = yaml.safe_load(text)
    job["outputOptions"]["outputDirectory"] = "<OUTPUT_DIR>"
    job["outputOptions"]["outputFileName"] = "<OUTPUT_PREFIX>"
    job["phenopacket"]["id"] = "<JOB_ID>"
    for hts in job["phenopacket"].get("htsFiles", []):
        hts["uri"] = "<VCF>"
    return yaml.safe_dump(job, sort_keys=False, default_flow_style=False)


def build_profile(spec: ProfileSpec, terms: list[dict], job_text: str, properties_text: str) -> AnalysisProfile:
    ids, branches = select_terms(terms, spec.phenotype_rule)
    return AnalysisProfile(
        profile_id=spec.profile_id,
        label=spec.label,
        phenotype=PhenotypeSelection(rule=spec.phenotype_rule, term_count=len(ids), branches_included=branches, term_ids=ids),
        filter_policy=FilterPolicy(analysis_mode="PASS_ONLY", failed_variant_filter=spec.failed_variant_filter,
                                   non_pass_records_permitted=not spec.failed_variant_filter),
        inheritance_modes=dict(INHERITANCE_MODES),
        frequency_max_percent=FREQUENCY_MAX_PERCENT,
        assumptions=[PHENOTYPE_ASSUMPTION, ROLE_ASSUMPTION, REMM_ASSUMPTION],
        analysis_yaml_sha256=sha256_text(canonical_for_hashing(job_text)),
        sample_yaml_sha256=sha256_text(canonical_for_hashing(job_text)),  # single job file carries both sections
        properties_sha256=sha256_text(properties_text),
    )
