# MVA functional evidence map — what PMID:20516114 actually measured

Case MVA_001. This is a case evidence artifact, not a new ontology. It records the experiments one
paper performed, what each one can carry, and what it cannot.

Downstream of this: `MVA_CASE_DECISION.md` (the case verdict), `MVA_EXP01_DECISION_PACKET.md` (the experiment that resolves it) and `MVA_BUBR1_STABILITY_REALIZATION.md` (the physical stabilisation search the turnover finding opened).

The canonical artifact is `research/experiments/PMID_20516114.yaml` in the research directory that
travels with the controlled case work — sixteen records, `VX_0001`–`VX_0016`, already present and
load-bearing: `VX_0007` and `VX_0008` are the evidence refs H01 cites in `prospective/seed.py`. A
prior session had already recovered this paper's full text into the corpus
(`corpus_refresh: abstract_only -> full_text_recovered`). The verdicts below are what the existing
`assess()` computes over that artifact in run `RUN_20261005T142213Z_dd4b1e`; none is typed in by hand.

This document was written from an independent re-extraction of the same paper (seventeen records),
which agrees with the canonical artifact on every decisive point and differs in two ways worth
recording. It **adds** `386X` and `483X`, which the canonical artifact does not carry — 483X is the
mirror image of Y155C and is the cleanest demonstration that alignment and checkpoint are separable.
It also **credits more alleles as restored-abundance tests**: the canonical encoding marks Q921H,
R550Q, Y155C and 731X as `ectopic_at_or_above_wild_type` with `function_at_restored_abundance` left at
`not_tested`, because the paper never titrated those stable proteins — it only expressed them. That
conservative reading is the authoritative one, and it yields the sharper result: under it just **one**
functional endpoint was measured at restored abundance, so three are missing rather than two. Where the
two readings differ, the canonical one is quoted here. The repo's own literature snapshot stays titles
and abstracts only, so neither file is committed.

Source: Suijkerbuijk, van Osch, Bos, Hanks, Rahman, Kops, *Cancer Research* 2010 (PMID:20516114,
PMC2887387). Full text retrieved from NCBI PMC under its stated text-mining licence and held with the
case work; it is not redistributed here.

## 1. The two regimes, as the paper demonstrates them

The paper splits MVA *BUB1B* alleles into two categories and then tests both.

**Regime 1 — abundance-limited.** Substitutions in or near the kinase domain are present at normal
mRNA level but 2–6 fold reduced as protein in patient cells, and 5–10 fold reduced as LAP constructs.
The cause is protein turnover, not transcription: turnover roughly doubles under cycloheximide, and
levels collapse under HSP90 inhibition while wild-type barely moves — the authors read this as
misfolding. At their native low level these mutants rescue nothing. Forced to wild-type-comparable
levels, I909T and L1012P **fully restored the nocodazole response**. The authors conclude these
mutations impose no significant constraint on function "other than affecting overall BUBR1 protein
abundance".

**Regime 2 — direct functional defect at normal abundance.** The two substitutions away from the
kinase domain are expressed normally, so their function can be read directly. R550Q (central region)
rescued both functions. **Y155C (N-terminal TPR domain) is a separation-of-function allele**: it
restored chromosome alignment, localised normally to unattached kinetochores, and *failed* to
reconstitute checkpoint activity. Its mirror image appears among the truncations: 483X restored
checkpoint activity but could not rescue misalignment, and the reconstituted cells therefore sat in a
significantly extended mitosis.

Both regimes are experimentally demonstrated. Neither is the default.

## 2. The domain map the paper establishes

| Region (UniProt O60566-1) | Required for | Evidence |
|---|---|---|
| TPR domain (62–226) | checkpoint signalling, **not** alignment | Y155C: alignment restored, checkpoint not |
| central region (227–765) | stable kinetochore–microtubule attachment | 483X fails alignment; 731X (ends at 715) succeeds |
| kinase domain (766–1050) | **neither function** | 731X has no kinase domain and restores both |

The kinase domain's role in these assays is to hold the protein up, not to act: it is dispensable for
both functions, yet substitutions inside it are the ones that destabilise the protein. That is why a
kinase-domain allele is a candidate for the abundance-limited regime in the first place.

Two cautions this table forces:
- Q921H sits in the kinase domain and is indistinguishable from wild-type in level *and* function.
  Kinase-domain location does not by itself predict instability.
- The paper groups R727C with "in or near the kinase domain" on phenotype, but residue 727 falls in
  the central region on canonical domain boundaries. A residue in the high 600s–700s is therefore
  classified differently by the paper's grouping than by the domain lattice. For such a residue the
  region assignment is not a safe proxy for regime.

## 3. The experiments

Columns: model → protein state → measured → observed → what it supports → what it does not support.

| id | model | protein state | measured | observed |
|---|---|---|---|---|
| `E_PT_I909T`, `E_PT_R727C`, `E_PT_R814H`, `E_PT_Y155C` | MVA patient lymphoblastoid + fibroblast lines, compound heterozygous | patient endogenous | abundance, kinetochore BUBR1, checkpoint, alignment, mRNA, turnover | abundance reduced 2–6×; residual protein still reaches kinetochores; checkpoint and alignment both impaired; mRNA normal; turnover ~2× for I909T and R727C |
| `E_STAB_HSP90` | U2OS stably expressing LAP wild-type / I909T / L1012P | not stated | chaperone dependence | HSP90 inhibition collapses mutant but not wild-type levels → misfolding |
| `E_LOWABUND_POOLED` | HeLa + U2OS, endogenous BUBR1 depleted | ectopic **below** wild-type | abundance, alignment | 5–10× below wild-type; alignment not restored |
| `E_RESCUE_I909T`, `E_RESCUE_L1012P` | U2OS, endogenous BUBR1 depleted | **restored to wild-type level** | checkpoint activation (MPM-2, 16 h nocodazole) | **restored** |
| `E_L844F` | U2OS/HeLa, depleted | ectopic below wild-type | abundance, checkpoint, alignment | poorly expressed; restored nothing |
| `E_Q921H` | U2OS/HeLa, depleted | at wild-type level | abundance, checkpoint, segregation | indistinguishable from wild-type |
| `E_STABLE_R550Q` | HeLa/U2OS, depleted | at wild-type level | abundance, checkpoint, alignment | both functions rescued |
| `E_STABLE_Y155C` | HeLa/U2OS, depleted | at wild-type level | abundance, alignment, checkpoint, localisation | alignment restored; **checkpoint not**; localisation normal |
| `E_TRUNC_386X` | HeLa/U2OS, depleted | not stated | checkpoint, alignment, localisation | none restored; cannot localise (no BUB3 domain) |
| `E_TRUNC_483X` | HeLa/U2OS, depleted | not stated | checkpoint, localisation, alignment | checkpoint restored; **alignment not**; extended mitosis |
| `E_TRUNC_731X` | HeLa/U2OS, depleted | not stated | checkpoint, segregation, alignment | all restored without a kinase domain |
| `E_WT_IN_PATIENT` | patient fibroblasts (731X/Y155C) vs parental (731X/WT) | ectopic at/above wild-type | checkpoint | almost fully restored to parental level |
| `E_TITRATION_WT` | HeLa, doxycycline-titrated BUBR1 shRNA | titrated down | segregation | ~6% of wild-type mis-segregates in most cells; ~13% is almost normal |

**What the restored-abundance experiments support.** For a kinase-domain substitution that can be
expressed at wild-type-comparable level, checkpoint activation and chromosome segregation come back.
Three alleles carry this: I909T, L1012P, Q921H.

**What they do not support.** Four things, each load-bearing:

1. **Chromosome alignment at restored abundance was never measured for any MVA kinase-domain
   substitution.** Alignment was tested for these alleles only at the low ectopic level, where
   failure is uninterpretable because the abundance was insufficient. The paper's own generalisation
   from the rescue rests on one endpoint, the nocodazole response.
2. **Checkpoint silencing was never measured at restored abundance for any allele.** 483X's extended
   mitosis is a consequence of failed alignment sustaining the checkpoint, not a silencing assay.
3. **The ~13% threshold does not transfer to an altered protein.** It was established with normal
   protein in HeLa. An altered protein may need more of itself to do the same work.
4. **A patient line measures a genotype, not an allele.** These lines are compound heterozygous and
   the second allele contributes almost no full-length protein, so the defect cannot be apportioned.

## 4. What the assessment computes, by region

`assess()` grades every experiment by how directly it applies to a given residue, then decides at
class level and exact-allele level separately. Run with a probe residue in each region — chosen more
than ten residues from every published variant, so each probe grades as same-region and never as an
exact or nearby match:

The real annotation puts this child's missense allele in the **protein kinase domain**, and the
computed result for the case is the first row:

| input | class level | restored-abundance alleles | measured there | **not** measured there | exact allele | decision |
|---|---|---|---|---|---|---|
| **the case, canonical artifact** | `function_persists` | I909T, L1012P | checkpoint activation | silencing, segregation, alignment | `insufficient` | `INSUFFICIENT` |
| probe: TPR (62–226) | `mixed` | Y155C (partial) | checkpoint activation, alignment | silencing, segregation | `insufficient` | `INSUFFICIENT` |
| probe: central (227–765) | `function_persists` | R550Q | checkpoint activation, alignment | silencing, segregation | `insufficient` | `INSUFFICIENT` |
| probe: kinase (766–1050) | `function_persists` | I909T, L1012P, Q921H | checkpoint activation, segregation | silencing, alignment | `insufficient` | `INSUFFICIENT` |
| no annotation available | `insufficient` | — | — | — | `insufficient` | `INSUFFICIENT` |

The probe rows are the re-extraction's bolder encoding, run before the annotation was available; they
are kept because of what they show. The region moves the class-level reading a long way and moves the
decision not at all — `INSUFFICIENT` in every region, under either encoding, because no experiment in
the corpus expressed any one child's exact substitution at matched abundance. Sharing a domain is
suggestive; it is not a measurement. At claim level the same gap reads `MC_0005` (variant class)
`PARTIALLY_SUPPORTED` on 103 establishing records against `MC_0006` (exact variant) `UNRESOLVED` on
zero.
