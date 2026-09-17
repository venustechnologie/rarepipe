# Stage 01 — Case Intake

> "We understand what we were given."

`rarepipe intake` turns an arbitrary case directory into a versioned, machine-readable
`CaseManifest` plus a human report. It performs **no** scientific interpretation, no
transformation, and no network access.

## Usage

```bash
uv sync
uv run rarepipe intake \
  --case-root /secure/mva_case \
  --case-id MVA_001 \
  --output /secure/work/MVA_001/intake
```

| option | purpose |
|---|---|
| `--reference PATH` (repeatable) | Reference FASTA living outside the case root (needed to verify a CRAM's reference). Recorded as `external_reference`. |
| `--primary-variant REL` | Case-relative path of the VCF downstream stages should use, when more than one exists. |
| `--exclude GLOB` (repeatable) | Ignore paths (matched against relative path and filename). |
| `--config FILE` | JSON with `exclude_globs`, `primary_variant_asset`, `references`, `checksum_cache`. CLI flags win. |
| `--no-checksum-cache` | Hash every file from scratch (default resumes unchanged files from `<output>/.cache`). |
| `--quiet` | No progress output. |

Exit codes: `0` INTAKE_COMPLETE / INTAKE_COMPLETE_WITH_WARNINGS · `3` INTAKE_BLOCKED · `2` usage error.
The run directory path is printed on stdout; progress goes to stderr.

Other commands: `rarepipe schema` (JSON Schema), `rarepipe verify-run RUN_DIR` (check the
`SHA256SUMS` seal), `rarepipe fixtures --output DIR` (materialize synthetic cases).

## Outputs

Each execution creates a new immutable directory `<output>/RUN_<UTC>_<random>/`:

| file | audience | content |
|---|---|---|
| `case_manifest.private.json` | the pipeline, inside the controlled environment | Full `CaseManifest`: relative paths, source sample labels, HPO term lists, configuration paths. **Restricted.** |
| `case_manifest.sanitized.json` | project owner / reviewers | Same schema with every `restricted` field cleared. Not anonymous — it still describes one real person's case structure. |
| `intake_report.md` | humans | Rendered **only** from the sanitized manifest. |
| `intake.log` | operators | Operations only (asset aliases, counts, statuses). |
| `SHA256SUMS` | integrity | Seal over the files above; `rarepipe verify-run` checks it. |

Files are staged under `.incomplete-<run_id>/`, made read-only, and atomically renamed
when complete. Nothing is ever edited in place; re-running produces a sibling run.

### Consuming the manifest (PRD 002 and later)

Downstream stages read `case_manifest.private.json` via `CaseManifest.model_validate_json`
and must not walk the case directory. Everything they need is addressable:

- `primary_inputs` — which asset IDs are the variant file(s) (and which one is primary, or
  that the choice is `ambiguous`), alignments, references, phenotype, pedigree.
- `assets[].relative_path` + `provenance.configuration.case_root` — where each file is.
- `assets[].checksum_sha256` — verify you are reading the exact bytes intake saw.
- `relationships` — `INDEX_OF`, `SEQUENCE_DICTIONARY_OF`, `CHECKSUM_OF`, `VERIFIED_REFERENCE_FOR`, `CANDIDATE_REFERENCE_FOR`.
- `reference.genome_build` (case level) and per-asset `metadata.genome_build`, each with `value`, `confidence`, `evidence`.
- `samples` — internal `SAMPLE_nnn` aliases with where each was observed; `pedigree.relationships` holds only explicitly asserted edges.
- `readiness.normalization_ready` — false iff any BLOCKER exists; `readiness.actions_required` lists decisions a human still owes.
- `provenance.fingerprints.input_fingerprint` — changes iff any file's content changes ("have the inputs changed since the last analysis?").
- `semantic_digest` — identical across reruns on unchanged inputs; excludes only `execution`.

### Schema

`schemas/case_manifest.schema.json` (CaseManifest 1.0.0) is generated from the Pydantic
models and drift-tested. Properties tagged `"restricted": true` are private-only; the
sanitizer clears them generically, so adding a sensitive field means tagging it — there is
no second list to maintain.

## What intake inspects

| asset | inspected | explicitly not done |
|---|---|---|
| all files | streamed SHA-256, content sniffing (magic bytes / first decompressed block), extension-vs-content comparison | copying, renaming, recompressing |
| VCF/BCF | header (version, samples, contigs+lengths, `##reference`, FILTER/INFO/FORMAT IDs, tool lines), BGZF EOF, index loadability, whether the first record parses (discarded) | iterating, filtering, annotating, ranking variants |
| BAM/CRAM | header (`@HD SO`, `@SQ` incl. M5/UR/AS, `@RG` SM/PL, `@PG`), `samtools quickcheck`, EOF, index loadability | reading alignments, coverage, locus inspection, decoding CRAM |
| FASTQ | structure of the first 1,000 records (4-line shape, seq/qual lengths, Phred+33 range), Illumina header lane/read number vs filename, R1↔R2 mate pairing by naming convention, BGZF EOF when applicable | storing reads, counting all reads, decompressing whole files |
| DOCX | text of `word/document.xml` scanned for HPO identifiers | interpreting prose |
| partial downloads | `.download-part`, `.crdownload`, `.part`, … → BLOCKER `INCOMPLETE_DOWNLOAD` | — |
| macOS `._` files | recognised as AppleDouble system files (exFAT drives); no format checks | — |
| FASTA | contig names/lengths (from `.fai`, or a streamed scan); per-sequence MD5 **only when a CRAM is present** | creating `.fai`/`.dict` |
| HPO | identifier syntax (`HP:` + 7 digits), explicit polarity (phenopacket `excluded`, polarity column, `NOT`/`!` prefix) | ontology validation, parent expansion, similarity |
| pedigree | PED/FAM rows, VCF `##PEDIGREE` Father/Mother | any relationship not explicitly written |
| checksum sidecars | `.md5`/`.sha256` compared with computed digests | — |

### Genome build

Contig **lengths** decide the build (GRCh37, GRCh37+decoy, GRCh38, T2T-CHM13, custom, unknown).
The length tables were cross-checked against UCSC `hg19`/`hg38`/`hs1` chrom.sizes.

| evidence | result |
|---|---|
| ≥3 canonical nuclear contig lengths match exactly one assembly, no contradicting claim | that build, `high` |
| 1–2 matching contigs, or lengths match but header text claims another build | that build, `medium` (+ issue) |
| non-canonical names (e.g. RefSeq accessions) whose lengths fingerprint one assembly | that build, `medium` |
| no lengths, a single header claim (`##reference`, `@SQ AS/UR`) | claimed build, `low`, ACTION_REQUIRED |
| canonical lengths match no single assembly | `custom`, ACTION_REQUIRED |
| names only / nothing | `unknown`, `insufficient`, ACTION_REQUIRED |

Chromosome naming (`chr1` vs `1`) is recorded as evidence, never as a conclusion.

## Issue taxonomy

Severities: **BLOCKER** (case cannot proceed) · **ACTION_REQUIRED** (proceed only after a human
decision) · **WARNING** (carry forward) · **INFO** (a fact). Status is `INTAKE_BLOCKED` if any
BLOCKER, `INTAKE_COMPLETE_WITH_WARNINGS` if any ACTION_REQUIRED or WARNING, else
`INTAKE_COMPLETE`. Absent optional material (pedigree, alignments) is INFO, not failure.

Codes are defined in `src/rarepipe/core/issues.py`. Key blockers: `VCF_PARSE_FAILED`,
`BGZF_EOF_MISSING`, `ALIGNMENT_PARSE_FAILED`, `ALIGNMENT_QUICKCHECK_FAILED`,
`REFERENCE_BUILD_CONFLICT`, `REFERENCE_CONTIG_LENGTH_MISMATCH`,
`PRIMARY_GENOMIC_INPUT_MISSING`, `FORMAT_EXTENSION_MISMATCH` (file named as a genomic format
but not readable as one), `CHECKSUM_SIDECAR_MISMATCH` (on a primary genomic file).

## Security assumptions

- The case root is controlled data. Intake opens inputs read-only and writes only under `--output`, which must be outside the case root (enforced). A test hashes the input tree before and after every fixture run.
- **Network:** none required. htslib's default CRAM behaviour downloads references from EBI when `REF_PATH` is unset; intake pins `REF_PATH`/`REF_CACHE` to a nonexistent local path for its duration. Tests run intake with Python sockets disabled *and* under an OS sandbox (`sandbox-exec deny network*` on macOS, `unshare -n` on Linux).
- **No telemetry, no LLM calls, no external logging.** Dependencies: pysam, pydantic, typer.
- **Logs and report** contain asset/sample aliases, counts, codes, and format facts only. Error messages from htslib/samtools (which embed absolute paths) are not propagated. A test asserts that no fixture's report, sanitized manifest, or log contains source sample labels, absolute paths, case filenames, ≥20-base sequences, or variant-row patterns.
- **Governance:** every asset gets a `retention_class`. VCF/BAM/CRAM/indexes and unidentified binaries are `controlled_genomic_delete_required`; other case material is `controlled_case_material_review_required`. The private manifest and `.cache/checksums.json` hold no genomic content, but the private manifest does hold source identifiers and HPO terms — keep it in the controlled environment and include `--output` in the deletion plan.
- **AI-agent development:** all development and tests use `rarepipe.testing.fixtures` (random sequence, invented labels). Do not paste real manifests' private content into agent conversations.

## Limitations (known, deliberate)

- Sample identity across files is metadata-only (exact label equality). Near-identical labels are flagged, never merged. No genotype concordance.
- A CRAM reference is `available_verified_md5` only when every `@SQ M5` matches an MD5 computed from a supplied FASTA. Reference-less or embedded-reference CRAMs are not detected from the header.
- Computing FASTA MD5s streams the whole reference (measured ~240 MB/s on an M-series laptop → ~15 s for GRCh38, plus disk time); it only happens when a CRAM is present. SHA-256 of all inputs is bounded by disk throughput (CPU does ~2 GB/s).
- A `.gzi` for a BGZF FASTA is linked but not validated. Plain-gzip FASTA cannot be indexed and is scanned instead.
- Pedigree: PED/FAM and VCF `##PEDIGREE` only. Phenopacket `subject`/family blocks and free-text clinical metadata are recorded as assets, not parsed for relationships.
- HPO detection in free text needs ≥50% of non-comment lines to carry an HPO-like token; a README that mentions a term is not treated as a phenotype file.
- FASTQ: plain-gzip files cannot be checked for truncation without full decompression (reported as `FASTQ_INTEGRITY_UNVERIFIED`); FASTQs carry no sample metadata, so their link to the VCF sample is never asserted. Instrument/flowcell IDs are private-only.
- DOCX: only explicit `HP:nnnnnnn` identifiers are extracted; clinical prose is left for a later stage.
- Index staleness (index older than data) is not checked — mtimes are unreliable after data transfers. Index *loadability* is checked.
- The first VCF record is parsed to prove the body is readable; a corrupt record deeper in the file will not be detected by intake.
- `asset_id` derives from the relative path, so a rename changes the ID (content identity is `checksum_sha256`).

## Running against the real hackathon dataset (deliverable 10)

This must happen **inside** the environment approved for the controlled data, never on a
developer laptop and never with outputs pasted into an AI tool.

```bash
git clone <this repo> && cd rarepipe && uv sync --frozen
uv run pytest -q                                   # prove the build on synthetic data first
uv run rarepipe intake --case-root <case dir> --case-id MVA_001 --output <work dir>/MVA_001/intake
uv run rarepipe verify-run <printed run dir>
```

If a CRAM is present, supply its reference with `--reference` (from the organizers' stated
reference, not a guessed one). Then review `intake_report.md` and share only the report
and/or the sanitized manifest with the project owner. Do not commit either for the real case.
