# Stage 02 — Case Input Normalization

> Stage 01 asked "what were we given?". Stage 02 asks "can we turn it into one coherent,
> explicit, analysis-ready representation — without diagnosing anything?"

`rarepipe normalize` consumes a **CaseManifest** (never the case directory) and produces a
**NormalizedCase**: canonical identities, measured VCF characteristics, and readiness stated
per capability rather than as one yes/no.

## Usage

```bash
uv run rarepipe normalize \
  --manifest /secure/work/MVA_001/intake/RUN_.../case_manifest.private.json \
  --resources /resources/rarepipe \
  --output /secure/work/MVA_001/normalization
```

| option | purpose |
|---|---|
| `--resources DIR` | Pinned resources (HPO release, NCBI assembly report) with `resources.lock.json`. Absent or unverifiable resources degrade specific capabilities; they never silently change results. |
| `--assertions FILE` | A `CaseAssertions` artifact (below). |
| `--case-root DIR` | Case mounted somewhere other than at intake time. Assets are still SHA-256 verified against the manifest. |
| `--quiet` | No progress output. |

Exit codes: `0` complete (with or without warnings) · `3` `NORMALIZATION_BLOCKED` · `2` usage error.

Outputs, in a new immutable run directory: `normalized_case.private.json`,
`normalized_case.sanitized.json`, `normalization_report.md`, `normalization.log`, `SHA256SUMS`.

## The pipeline contract, enforced

- The **manifest is the only description of the case**. Stage 02 never walks the case directory,
  so a file Stage 01 did not record cannot be consumed — re-run Stage 01 instead.
- Every asset it opens is **SHA-256 verified** against the manifest first (`SOURCE_ASSET_CHANGED`
  blocks otherwise), and the manifest itself is checked against the Stage 01 run seal.
- It opens exactly: the primary VCF, its index, and the phenotype asset(s). **FASTQs are never
  opened** (a test makes them unreadable and the stage still succeeds).
- **No transformation.** No rewriting, decomposition, left-alignment, filtering, sorting, liftover,
  alignment, calling, phasing, annotation or prioritization. Every operation is recorded in
  `provenance.operations` with `transforms_source_data: false`.

## What it measures

**VCF (complete stream, twice):** a strict text parser validates every record and accumulates
aggregates only, then htslib reads the file independently; the two record counts must agree.
Recorded: FILTER distribution (PASS / non-PASS / `.`, per label, multi-filter, undeclared, and
declared-but-unused), record and allele classes (SNV, MNV, insertion, deletion, complex, symbolic,
breakend, spanning deletion, multiallelic), coordinate ordering, duplicates, allele syntax,
per-FORMAT-field declaration and population fractions, GT state counts, phase availability
(`|` separators, `PS`, `PGT`/`PID`), and upstream tool provenance from the header.

**Non-PASS records are never dropped.** FILTER is evidence, not an exclusion rule. Note also that
seeing non-PASS records does not prove upstream processing kept everything it called — the file
can only describe itself.

**Phenotype:** every supplied identifier is resolved against a pinned HPO release — active,
secondary (`alt_id`), obsolete with an unambiguous `replaced_by` (followed, original preserved),
obsolete with only `consider` (left unresolved, candidates surfaced), or unknown. The HPO branch of
each supplied term is named (e.g. a mode-of-inheritance term listed as a phenotype is flagged).
No ancestors, descendants, similarity or gene/disease associations are added.

**Polarity** defaults to `unspecified` and is never inferred from a term being listed. It changes
only via a `CaseAssertions` record, and never overrides polarity stated by the source document.

**Contigs:** each declared contig is bound by **name and length** to a pinned NCBI assembly report,
giving a canonical identity (`GRCh38:NC_000001.11`), a label, aliases (UCSC/GenBank/RefSeq) and a
class (primary, mitochondrial, alt, unlocalized, unplaced, patch, decoy/other, unknown). Contigs the
report does not cover fall back to a *labelled* name heuristic or stay `unbound`. `1` and `chr1`
reach the same canonical identity without either file being rewritten. Per-contig record counts are
private-only (e.g. chrY counts are biologically revealing); the report shows counts per class.

**Reference:** knowing the assembly is not the same as possessing the exact FASTA. Stage 02 records
`analysis_reference.status: not_yet_bound` and never downloads a reference: different GRCh38
distributions differ in ALT/decoy content and naming, so any future binding must be checksum-pinned
and checked against the VCF's contig dictionary.

## Readiness by capability

A case is not globally "ready". Each capability reports `yes` / `partial` / `no` with reasons:
`phenotype_based_prioritization`, `vcf_based_prioritization`, `trio_analysis`,
`phase_aware_analysis`, `variant_decomposition_left_alignment`, `read_level_analysis`.

## CaseAssertions — human facts as data

Facts a computation cannot establish enter only through a versioned artifact, never through code:

```json
{"schema": {"name": "CaseAssertions", "version": "1.0.0"},
 "case_id": "MVA_001",
 "assertions": [
   {"assertion_id": "ASSERT_001",
    "subject": {"type": "sample", "id": "SAMPLE_001"},
    "predicate": "role", "value": "proband",
    "evidence": {"type": "organizer_documentation", "reference": "challenge README §2"},
    "asserted_by": "operator", "asserted_at": "2026-09-17T00:00:00+00:00"}]}
```

Predicates: `role` (sample), `phenotype_polarity` (phenotype_set / hpo_term), `sample_linkage`
(raw_read_set → sample). An applied assertion is recorded with its evidence, marks the Stage 01
issue it addresses as `addressed_by_assertion`, and is hashed into provenance. An assertion that
does not fit the case is rejected, not partially applied. **No assertions are required; `unknown`
is a legitimate state.**

## Resources (pinned, never fetched during a case run)

```bash
uv run rarepipe resources fetch-hpo --resources /resources/rarepipe --release latest   # network
uv run rarepipe resources fetch-assembly-report --resources /resources/rarepipe        # network
uv run rarepipe resources register --resources /resources/rarepipe --kind hpo_ontology \
    --file /resources/rarepipe/hpo/v2025-05-06/hp.obo --version 2025-05-06 --name "hp.obo"  # offline
uv run rarepipe resources verify --resources /resources/rarepipe
```

`resources.lock.json` records kind, version, origin, retrieval time, size and SHA-256. A case run
verifies every entry and **refuses** a file whose bytes differ (`RESOURCE_CHECKSUM_MISMATCH`), so a
silently updated ontology cannot change a result. The ontology release is recorded in the
NormalizedCase, and re-running against a newer release yields a different `semantic_digest`.
`rarepipe.resources.fetch` is the only module that touches the network and no stage imports it
(enforced by a test).

## Issues and uncertainty across stages

Stage 01 issues are carried forward with `origin_stage: case_intake` and a `resolution`
(`unresolved`, `addressed_by_assertion`, `informational`), alongside Stage 02's own issues. Nothing
is lost between stages.

## Privacy and retention

The private artifact carries source sample labels, HPO identifiers and labels, local paths, header
command lines and per-contig record counts. The sanitized artifact and the report carry none of
these — redaction is schema-driven, and a test asserts no leakage. All outputs inherit the case's
deletion policy (`retention.classification: inherits_case_policy`, `review_required: true`).

## Limitations

- Multi-sample VCFs are characterized, but FORMAT/GT aggregates are summed across samples and no per-sample breakdown is produced.
- Duplicate detection is exact-match within a position; equivalent representations (e.g. an indel written differently) are not detected without left-alignment, which needs a bound reference.
- Genotype "populated" means "not a missing value", not that a value is meaningful.
- Contig heuristics recognise common decoy/HLA/EBV naming; anything else stays `unknown` rather than being guessed.
- `sorted` means coordinate-ordered within contiguous contig blocks; contig order differing from the header is reported separately.
- The stage validates HPO *identity* only. Whether the supplied terms describe the patient well is a clinical question it does not touch.
