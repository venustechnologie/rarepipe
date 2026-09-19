# AlphaGenome Atlas adapter (PRD 006A)

A new evidence capability for the mechanism stage, added without rebuilding anything. The Atlas
precomputes molecular-effect predictions for all ~9 billion possible human SNVs and exposes an
AlphaGenome Variant Impact (AVI) score with a feature attribution — which is exactly the kind of
source Stage 06 was built to absorb.

## Why the privacy pattern works

The Atlas client exposes `query_interval`, which returns predictions for **every** variant in a
genomic window. So we never ask about the child's variant:

```
public question          query a public gene region (Ensembl-derived coordinates)
        ↓
local cache              ~180,000 hypothetical variants, hashed, with provenance
        ↓
local match              the child's alleles are matched against the cache, on this machine
        ↓
AlphaGenomeEvidence      a prediction, with the allele's rank among all substitutions in the region
```

Google learns that someone is studying BUB1B. It does not learn what this child carries.

Two commands, split exactly like the literature corpus:

```
rarepipe alphagenome fetch-region --gene BUB1B --scorer AVI_SCORE --scorer AVI_SCORE_FEATURE_IMPORTANCE --output <cache>
rarepipe alphagenome match --cache <cache file> --adjudication-run <stage 04 private> --output <dir>
rarepipe mechanism resolve --alphagenome <dir> ...
```

`fetch-region` never opens a case artifact. `match` never touches the network. A window narrower
than 2,000 bp is refused outright: a region that tight would disclose the variant it was drawn
around, which is the whole thing we are avoiding.

## Weight of the evidence

Atlas records enter as `EvidenceLevel.COMPUTATIONAL` with `EpistemicClass.EXTERNAL_EVIDENCE` — an
identifiable external source stating a value, but a model output rather than a measurement. Under
the Stage 06 rules that means it can **accompany** a functional claim and never **establish** one.
It will show up in the dossier as indirect evidence beside `MC_0006`, not as its resolution.

Recorded limitations travel with every record: not experimental evidence; not validated or approved
for clinical use; **not diploid-aware**, so each allele is scored independently and the predictions
say nothing about the compound-heterozygous state; and the tissue coverage is the model's, not this
child's.

## The key

`ALPHAGENOME_API_KEY` is read from the environment only. It is never written into the repo, and
`*.key` is git-ignored. Keep it in a file outside the working tree:

```bash
export ALPHAGENOME_API_KEY=$(cat ~/.config/rarepipe/alphagenome.key)
```

## Replaceability

`VariantMechanismProvider` is a Protocol. The Atlas client is one implementation; a Google Cloud
commercial endpoint, a different predictor or a future model can be another without changing the
pipeline contract. Free non-commercial access is right for a hackathon, and rarepipe should not
become structurally dependent on it.

## Practical notes discovered by using it

* Responses are capped at 4 MB. Dense track scorers (`RNA_SEQ`, 371 tracks even filtered to one
  gene) blow that limit when combined; request them separately or not at all.
* `AVI_SCORE` is one value per variant. `AVI_SCORE_FEATURE_IMPORTANCE` returns 18 named features —
  `MERGED_SPLICING`, `ALPHAMISSENSE`, `MAX_ABS_RNA_SEQ`, `PROTEIN_TERMINATION`, `CACTUS_241_WAY`
  and others — which is what distinguishes a splicing effect from a protein effect. The adapter
  keeps named vectors per feature and only summarises wide track matrices.
* The client chunks an interval into 32 bp requests, so every call is a region call.
