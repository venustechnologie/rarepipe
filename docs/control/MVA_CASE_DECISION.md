# MVA_001 — case decision after reading the primary functional evidence

Companion to `MVA_FUNCTIONAL_EVIDENCE_MAP.md`, which holds the experiments this rests on.

Computed by `rarepipe mechanism resolve` against the controlled case artifacts, offline under
`sandbox-exec -p '(version 1)(allow default)(deny network*)'`. Run `RUN_20261005T142213Z_dd4b1e`:
16 variant experiments, every quote re-found in the stored corpus; 49 claims, 1410 evidence records.
Nothing below is typed in by hand.

Disclosure posture: this names published variants, domain boundaries, and the domain the child's
missense allele falls in — the domain name is public biology and the code treats it as such. It names
no residue, no coordinate and no HGVS. The directness grading that compares a published residue to
the child's is computed locally and held in restricted fields, which the sanitized dossier strips; a
nearby published variant plus its position would localise the child's residue. No case variant was
sent to any external provider.

## What we now know

**The child's missense allele sits in the protein kinase domain**, from the case's own protein-feature
evidence. That places it in the regime this paper characterises best, and it is the regime where
abundance, not catalysis, is the problem.

**For that region, function at restored abundance is demonstrated — for one endpoint.** Two
kinase-domain substitutions, I909T and L1012P, forced to wild-type-comparable levels, fully restored
the nocodazole response. `assess()` returns class level `function_persists` on exactly those two.

**The mechanism of the low abundance is protein turnover, not transcription.** mRNA is normal;
turnover roughly doubles under cycloheximide; levels collapse under HSP90 inhibition while wild-type
barely moves. The authors read this as misfolding.

**The kinase domain is dispensable for both mitotic functions.** 731X has no kinase domain and
restores checkpoint, segregation and alignment. A kinase-domain substitution therefore matters because
it destabilises the protein, not because it removes catalysis.

**Abundance alone is not a general explanation for MVA *BUB1B* alleles.** The paper demonstrates the
opposite regime in the same assays: Y155C, in the N-terminal TPR domain, is expressed normally,
localises normally, restores chromosome alignment and fails to restore checkpoint activity. 483X is
its mirror image — checkpoint-competent, alignment-incompetent, with a significantly extended mitosis.
Function is separable by domain, and a protein at full abundance can still be half broken.

## What we still do not know

**Only one of four functional endpoints was measured at restored abundance.** The assessment computes
`class_level_endpoints = ['checkpoint activation (nocodazole response)']` and
`readouts_not_reported_at_restored_abundance = ['checkpoint_silencing', 'chromosome_segregation',
'chromosome_alignment']`. Alignment was tested for these alleles only at the low ectopic level, where
failure is uninterpretable because the abundance was insufficient. The paper's generalisation that
these mutations constrain nothing but abundance rests on the nocodazole response alone.

**No experiment anywhere expressed this child's exact substitution at matched abundance.** `MC_0006`,
the exact-variant claim, is `UNRESOLVED` on **zero** establishing records and 7 indirect. `MC_0005`,
the variant-class claim, is `PARTIALLY_SUPPORTED` on 103. The gap between those two numbers is the
case.

## Abundance-limited, residual-function defect, or unresolved

**`ABUNDANCE_LIMITED_MECHANISM_SUPPORTED` at class level. `CASE_REMAINS_UNRESOLVED` for this allele.**
Both at once, and the two must not be merged:

| level | verdict | basis |
|---|---|---|
| variant class (kinase domain) | `function_persists` | I909T and L1012P restored the measured function at wild-type-comparable level |
| this child's allele (exact-allele evidence) | `insufficient` | no experiment expressed this exact substitution; sharing a domain does not settle residual function |
| **decision** | **`INSUFFICIENT`** | the residual-function dependency stays open |

The region assignment moved the class-level reading a long way and moved the decision not at all. That
was checked before the annotation was available, by running `assess()` with a probe residue in each of
the three domains: class level came back `function_persists` in the kinase domain and the central
region and `mixed` in the TPR domain, while the decision stayed `INSUFFICIENT` in every one. The real
annotation then landed in the kinase domain and returned the same decision. The invariance is the
result, not a coincidence.

No probability is attached to any of this, and none should be.

## H01 versus H02, re-evaluated

The experiments discriminate, but not by making one hypothesis win. They make the two **asymmetric in
endpoint**, which is sharper than returning both as possible.

- **H01** ("adequate abundance permits useful function") now rests on a direct matched-abundance
  experiment in the child's own domain rather than on inference — for checkpoint activation only. Its
  scope note in the plan, "checkpoint activation only", is confirmed by the primary experiment and is
  a hard limit, not a caveat.
- **H02** ("a functional defect remains despite restored abundance") was carried on a single
  abstract-level citation at gene scope. It is now an experimentally demonstrated phenotype for a
  *BUB1B* missense allele at normal abundance and normal localisation: Y155C. H02 stopped being a bare
  alternative.
- The two are **not mutually exclusive**. The paper's own model is two patient groups, one explained by
  abundance and one combining reduced abundance with direct functional impairment. `MIXED` is a live
  outcome, not a hedge.

**For this child's allele the discrimination collapses to three observables: chromosome alignment,
checkpoint silencing and chromosome segregation at matched abundance.** Checkpoint activation can no
longer separate H01 from H02, because the class-level evidence says it returns. That is the smallest
remaining biological uncertainty.

## The experiment that would change it

Specified in full, with its precommitted interpretation matrix, in
`MVA_EXP01_DECISION_PACKET.md`. In outline:

Deplete endogenous BubR1 (shRNA in U2OS or HeLa, as in PMID:20516114 Fig. 4) and express an
RNAi-insensitive construct carrying this child's exact substitution at wild-type-comparable level,
confirmed by immunoblot beside wild-type, a known restored-abundance control (I909T or L1012P) and a
poorly expressed control (L844F). Measure checkpoint activation (MPM-2 after nocodazole), checkpoint
silencing (timely exit once chromosomes align), chromosome segregation by live imaging, and chromosome
alignment; where feasible, kinetochore PP2A-B56 recruitment.

- All four persist → strengthens stabilisation.
- Alignment, silencing or segregation impaired at matched abundance → H02 for this child; an
  abundance-only strategy is weakened even though the checkpoint looks rescued.
- Not expressible at matched level → the premise that stabilising the protein is achievable needs its
  own test before anything downstream matters.

### Consequence for EXP01

| | |
|---|---|
| **Already supported by external experiment** | checkpoint activation at restored abundance for kinase-domain substitutions (I909T, L1012P), the child's own domain; patient cells are rescuable by normal protein; the turnover/HSP90 mechanism of low abundance; residual mutant protein still reaches kinetochores |
| **Partially transferable** | the ~6% / ~13% abundance threshold (normal protein in HeLa — direction transfers, magnitude does not); the domain map (class level, not allele level); the shRNA-replacement design itself, which transfers as protocol |
| **Must still be measured in this case** | chromosome alignment, checkpoint silencing and chromosome segregation at matched abundance for this exact substitution; whether this substitution is expressible at wild-type-comparable level at all; whether any medication raises BubR1 abundance in this child's cells |
| **Not relevant to H01/H02 discrimination** | kinase catalytic activity and the presence of the kinase domain (731X shows both are dispensable); the truncation domain mapping beyond interpreting endpoints; NMD biology of the truncating allele |

Endpoints are not being trimmed. Cell death and division rate stay in EXP01 as safety endpoints, and
the recent repair is an argument for keeping them: the `cell_death -> division_rate` edge is now
`ASSERTED_ONLY` because PMID:20516114 does not measure cell loss — the full article was read and the
terms for death, apoptosis, viability, proliferation, division rate and clonogenic survival appear
zero times in it. Nothing in the literature covers that step, so it must be observed rather than
assumed. A checkpoint that looks rescued while cells are dying is not a rescue.

## Which physical control route becomes more or less plausible

**More plausible, and redirected.** An abundance-raising route keeps its premise and gains a
mechanism: the defect is protein turnover and chaperone-dependent misfolding, not transcription, and
the child's allele sits in the domain where that is true. A route should target stability — turnover
and folding — rather than expression. This narrows the realization search; it does not add a layer.

**Eliminated.** Any route premised on restoring BubR1 *kinase activity* is unsupported: the whole
kinase domain is dispensable for both functions in these assays.

**Unchanged, and still the weakest link.** This paper says nothing about any actuator. It supports the
premise that abundance matters; it offers no evidence that nicotinic acid, NAD or SIRT2 moves BubR1
abundance in this child's cells. That chain's direct edge remains `ASSERTED_ONLY` after REPAIR_R1, the
realization verdicts stand, and the two robust synthesis routes that never touch BubR1 are untouched
by anything here.

## Gate

`MECHANISM_READY_FOR_INTERVENTION_SEARCH`. The disease-level mechanism is supported by human
experimental and curated evidence. This child's missense allele remains functionally unmeasured, and
that is a question about how severe the genotype is, not about which mechanism is in play.
