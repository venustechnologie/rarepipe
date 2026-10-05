# MVA_001 — case decision after reading the primary functional evidence

Companion to `MVA_FUNCTIONAL_EVIDENCE_MAP.md`, which holds the experiments this rests on.

Disclosure posture: this document names published variants and domain boundaries, which are public
biology. It names nothing about this child's alleles. The directness grading that compares a
published residue to the child's is computed locally and held in restricted fields, because a nearby
published variant plus its position would localise the child's residue. No case variant was sent to
any external provider in producing this.

## What we now know

**Raising BubR1 abundance restores the mitotic checkpoint for kinase-domain substitutions — as a
class, for one endpoint.** Two MVA substitutions that are destabilising at native level (I909T,
L1012P), forced to wild-type-comparable abundance, fully restored the nocodazole response. A third
(Q921H) is normal in level and function. The abundance premise behind an abundance-raising strategy
is therefore more plausible than the frozen result stated.

**The mechanism of the low abundance is protein turnover, not transcription.** mRNA is normal;
turnover roughly doubles; levels collapse under HSP90 inhibition while wild-type barely moves. The
authors read this as misfolding.

**Abundance alone is not a general explanation for MVA *BUB1B* alleles.** The paper demonstrates the
opposite regime in the same assays: Y155C, in the N-terminal TPR domain, is expressed normally,
localises normally, restores chromosome alignment and *fails* to restore checkpoint activity. 483X is
its mirror image — checkpoint-competent, alignment-incompetent, with a significantly extended
mitosis. Function is separable by domain, and a protein at full abundance can still be half broken.

**The kinase domain is dispensable for both functions.** 731X has no kinase domain and restores
checkpoint, segregation and alignment. Kinase-domain substitutions matter because they destabilise
the protein, not because they remove catalysis.

## What we still do not know

**Chromosome alignment at restored abundance has never been measured for any MVA kinase-domain
substitution.** Alignment was tested for those alleles only at the low ectopic level, where failure
is uninterpretable. The paper's generalisation that these mutations constrain nothing but abundance
rests on the nocodazole response alone.

**Checkpoint silencing at restored abundance has never been measured for any allele.** 483X's
extended mitosis is a consequence of failed alignment holding the checkpoint on, not a silencing
assay.

**No experiment anywhere expressed this child's exact substitution at matched abundance.** This is
the binding constraint, and it has not moved.

## Abundance-limited, residual-function defect, or unresolved

**`CASE_REMAINS_UNRESOLVED`** — for two separable reasons, only one of which is about missing data.

1. The child's domain assignment is derived from the controlled adjudication, which is not mounted in
   this session, so the local mapping could not be run. This is recoverable: run
   `rarepipe mechanism resolve` with the research directory and the assessment computes the state.
2. More fundamentally, it would still be `CASE_REMAINS_UNRESOLVED`. `assess()` was run with a probe
   residue in each of the three domains. The class-level reading moves a long way — `function_persists`
   in the kinase domain and the central region, `mixed` in the TPR domain — and the decision does not
   move at all. It is `INSUFFICIENT` in every region, because the exact-allele function at matched
   abundance is unmeasured everywhere. Sharing a domain with I909T is suggestive; it is not a
   measurement.

No probability is attached to any of this, and none should be.

## H01 versus H02, re-evaluated

The experiments do discriminate, but not by making one hypothesis win. They make the two hypotheses
**asymmetric in endpoint**, which is sharper than returning both as possible.

- **H01** ("adequate abundance permits useful function") is now supported by a direct
  matched-abundance experiment rather than by inference — but only for checkpoint activation, plus
  segregation via Q921H. Its scope note in the plan, "checkpoint activation only", is confirmed by
  the primary experiment and is a real limit, not a caveat.
- **H02** ("a functional defect remains despite restored abundance") was carried in the plan on a
  single abstract-level citation at gene scope. It is now an experimentally demonstrated phenotype
  for a *BUB1B* missense allele at normal abundance and normal localisation: Y155C. H02 stopped being
  a bare alternative.
- The two are **not mutually exclusive**. The paper's own model is two patient groups, one explained
  by abundance and one combining reduced abundance with direct functional impairment. `MIXED` is a
  live outcome, not a hedge.

For a kinase-domain allele the discrimination collapses to a single observable: **H01 and H02 differ
only on the endpoints that were never measured at matched abundance — chromosome alignment and
checkpoint silencing.** Checkpoint activation can no longer separate them, because the class-level
evidence says it returns. That is the smallest remaining biological uncertainty.

## The experiment that would change it

Deplete endogenous BubR1 (shRNA in U2OS or HeLa, as in PMID:20516114 Fig. 4) and express an
RNAi-insensitive construct carrying this child's exact substitution at wild-type-comparable level,
confirmed by immunoblot beside wild-type, a known restored-abundance control (I909T or L1012P) and a
poorly expressed control (L844F). Measure checkpoint activation (MPM-2 after nocodazole), checkpoint
silencing (timely exit once chromosomes align), chromosome segregation by live imaging, and
chromosome alignment; where feasible, kinetochore PP2A-B56 recruitment.

- Function persists across all four → strengthens stabilisation.
- Alignment or silencing impaired at matched abundance → H02 for this child; an abundance-only
  strategy is weakened even though the checkpoint looks rescued.
- Not expressible at matched level → the premise that stabilising the protein is achievable needs its
  own test before anything downstream matters.

### Consequence for EXP01

| | |
|---|---|
| **Already supported by external experiment** | checkpoint activation at restored abundance for kinase-domain substitutions; segregation for Q921H; patient cells are rescuable by normal protein; the turnover/HSP90 mechanism of low abundance; residual mutant protein still reaches kinetochores |
| **Partially transferable** | the ~6% / ~13% abundance threshold (normal protein in HeLa — direction transfers, magnitude does not); the domain map (class level, not allele level); the shRNA-replacement design itself, which transfers as protocol |
| **Must still be measured in this case** | chromosome alignment at matched abundance for this exact substitution; checkpoint silencing at matched abundance; whether this substitution is expressible at wild-type-comparable level at all; whether any medication raises BubR1 abundance in this child's cells |
| **Not relevant to H01/H02 discrimination** | kinase catalytic activity and the presence of the kinase domain (731X shows both are dispensable); the truncation domain mapping beyond interpreting endpoints; NMD biology of the truncating allele |

Endpoints are not being trimmed. Cell death and division rate stay in EXP01 as safety endpoints, and
the recent repair is an argument for keeping them: the `cell_death -> division_rate` edge is now
`ASSERTED_ONLY` because PMID:20516114 does not measure cell loss — the full article was read and the
terms for death, apoptosis, viability, proliferation, division rate and clonogenic survival appear
zero times in it. Nothing in the literature covers that step, so it must be observed rather than
assumed. A checkpoint that looks rescued while cells are dying is not a rescue.

## Which physical control route becomes more or less plausible

**More plausible, and redirected.** An abundance-raising route keeps its premise and gains a
mechanism: the defect is protein turnover and chaperone-dependent misfolding, not transcription. A
route should therefore target stability — turnover and folding — rather than expression. This is a
narrowing of the realization search, not a new layer.

**Eliminated.** Any route premised on restoring BubR1 *kinase activity* is unsupported: the whole
kinase domain is dispensable for both functions in these assays.

**Unchanged, and still the weakest link.** This paper says nothing about any actuator. It supports
the premise that abundance matters; it offers no evidence that nicotinic acid, NAD or SIRT2 moves
BubR1 abundance in this child's cells. That chain's direct edge remains `ASSERTED_ONLY` after
REPAIR_R1, the realization verdicts stand, and the two robust synthesis routes that never touch
BubR1 are untouched by anything here.
