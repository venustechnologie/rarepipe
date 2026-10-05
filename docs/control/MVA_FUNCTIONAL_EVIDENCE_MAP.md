# MVA functional evidence map — what PMID:20516114 actually measured

Case MVA_001. This is a case evidence artifact, not a new ontology. It records the experiments one
paper performed, what each one can carry, and what it cannot.

The experiments are stored as case data in `research/experiments/pmid_20516114.yaml` (the research
directory that travels with the controlled case work, not this repo — the repo's literature snapshot
is titles and abstracts only). Seventeen records, every readout a verbatim quote that
`rarepipe.stages.mechanism.experiments.load_experiments()` re-finds in the stored document before the
file is accepted. The verdicts below are computed by the existing `assess()`; none of them is typed
in by hand.

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

| probe region | class level | restored-abundance alleles in that region | endpoints measured there | endpoints **not** measured there | exact allele | decision |
|---|---|---|---|---|---|---|
| TPR (62–226) | `mixed` | Y155C (partial) | checkpoint activation, alignment | silencing, segregation | `insufficient` | `INSUFFICIENT` |
| central (227–765) | `function_persists` | R550Q | checkpoint activation, alignment | silencing, segregation | `insufficient` | `INSUFFICIENT` |
| kinase (766–1050) | `function_persists` | I909T, L1012P, Q921H | checkpoint activation, segregation | silencing, **alignment** | `insufficient` | `INSUFFICIENT` |
| no annotation available | `insufficient` | — | — | — | `insufficient` | `INSUFFICIENT` |

The region moves the class-level reading a long way. It moves the decision not at all, because no
experiment in the corpus expressed any one child's exact substitution at matched abundance. Sharing a
domain is suggestive; it is not a measurement.
