# MVA_001 — EXP01 decision packet

**The question.** When this case's altered BubR1 is expressed at wild-type-comparable abundance, are
chromosome alignment, checkpoint silencing and chromosome segregation functionally normal?

Checkpoint activation is deliberately *not* the question. It is class-supported for this child's
domain — `assess()` returns class level `function_persists` on I909T and L1012P, the only two alleles
with a matched-abundance measurement — so it can no longer separate H01 from H02. It appears below as a
replication control.

This packet adds no new branch vocabulary. The six required outcomes are a view over the deterministic
rules already in `rarepipe.stages.prospective.rules`, and the endpoint ids are the ones EXP01 already
declares. Nothing here invents a numerical threshold: every criterion is relative to the wild-type
replacement arm, which is how the existing endpoints are specified.

## 1. Experimental model

`EXACT_ALLELE_ENGINEERED`. An engineered model of the exact missense allele, endogenous and introduced
protein distinguishable, with transcript, isoform and construct identity held in the private layer
(`private:exp01-construct`). This is an allele-function experiment, not a reconstruction of the child's
genotype — the second allele is not part of the question.

Design, following PMID:20516114 Fig. 4: deplete endogenous BubR1 by shRNA in a human line where the
replacement assay is established (U2OS or HeLa), and express an RNAi-insensitive construct. The
depletion-and-replacement format is what makes the readout attributable to the introduced protein.

## 2. Matched-abundance requirement

The whole experiment is conditional on it. `E01_EXPR` (`expression_comparability`) must read `matched`
against the wild-type replacement arm. If it does not, no statement about function at matched
abundance is admissible — the rules fire `B02` and the residual-function dependency stays exactly where
it is today.

**How matched abundance is verified.** Quantitative immunoblot from the same lysates as the functional
readout, run beside: the wild-type replacement arm; the restored-abundance reference (I909T or L1012P);
and the poorly expressed reference (L844F). Introduced protein must be distinguishable from any
residual endogenous protein. Verification is per experiment, not once at setup, because the thing being
matched is a steady-state level of a protein whose defect *is* elevated turnover.

Two grounded facts constrain the reading, and neither is a threshold to be applied numerically:
- Segregation fidelity is steeply sensitive to BubR1 level in HeLa — ~6% of wild-type mis-segregates in
  most cells while ~13% is almost normal. That was established with *normal* protein, so it does not
  transfer to an altered protein as a cutoff. It is the reason "roughly comparable" is not good enough.
- Patient-line full-length BubR1 runs 2–6 fold below wild-type alleles. Matching is to the wild-type
  replacement arm, not to a patient level.

## 3. Necessary controls

| control | what it establishes | what it cannot establish |
|---|---|---|
| wild-type replacement | the assay can be rescued; `qc.controls_valid` | nothing about the altered protein — recorded explicitly as an assay-validity statement only |
| deficient / vector | the defect is present to be rescued | — |
| restored-abundance reference (I909T or L1012P) | **replication** of the published matched-abundance rescue in these hands | that this child's allele behaves likewise |
| poorly expressed reference (L844F) | an allele that cannot reach matched abundance | it is *not* a matched-abundance loss-of-function control, and must not be read as one |

The restored-abundance reference is the load-bearing addition. If it fails here, `qc.controls_valid` is
false, `B01` fires, and `B03`/`B04` are inadmissible by construction — so a failure of the published
result in this lab cannot be mistaken for a finding about this child's allele.

## 4. Endpoints

Primary discriminators — the three functions never measured at restored abundance for any MVA
kinase-domain substitution:

| id | endpoint | criterion |
|---|---|---|
| `E01_ALN` | chromosome alignment | comparable to the wild-type replacement arm (MG132-arrested, as Fig. 4C) |
| `E01_SIL` | checkpoint silencing | timely exit once chromosomes are attached, comparable to the wild-type arm |
| `E01_MIS` | missegregation | comparable to the wild-type arm, per assessable division |

Replication control, not a discriminator:

| `E01_ACT` | checkpoint activation (nocodazole response, MPM-2) | within the justified reference range of the wild-type arm; a prolonged arrest is not automatically better |

Mechanistic, where useful — these explain a defect, they do not decide one:

| `E01_KT` | kinetochore localisation | comparable to wild type (optional) |
| `E01_PP2A` | PP2A-B56 recruitment | comparable to wild type (optional) |

Localisation is worth measuring precisely because it dissociates from function: Y155C localises
normally and is still checkpoint-dead, and residual mutant protein in patient cells reaches
kinetochores. A normal `E01_KT` is therefore not evidence of function.

Safety and confounder endpoints — required, not optional:

| `E01_VIA` | viability | no loss relative to comparators |
| `E01_DEATH` | cell death | no increase |
| `E01_DIV` | division rate | no reduction relative to comparators |

These stay in because nothing in the retrieved literature covers them. The `cell_death -> division_rate`
edge is `ASSERTED_ONLY`: the full article was read and the terms for death, apoptosis, viability,
proliferation, division rate and clonogenic survival appear zero times in it. An unmeasured step must be
observed, not assumed. Fewer errors in a population that is dying or dividing more slowly is what
selective loss looks like, not rescue.

## 5. Precommitted interpretation matrix

Precommitted means decided before the result exists. The condition column is the existing predicate;
`FUNCTION_KEYS` is `checkpoint_activation, checkpoint_silencing, chromosome_alignment, missegregation`.

| outcome | condition | rule | hypothesis effect |
|---|---|---|---|
| `MATCHED_ABUNDANCE_NOT_ACHIEVED` | `E01_EXPR` is not `matched` | `B02` | none — function at matched abundance stays unresolved |
| `ABUNDANCE_SUFFICIENT_FOR_TESTED_FUNCTIONS` | matched **and** every `FUNCTION_KEYS` endpoint normal | `B03` | H01 `STRENGTHENED`, for the measured endpoints only |
| `RESIDUAL_FUNCTION_DEFECT` | matched **and** any `FUNCTION_KEYS` endpoint impaired or partial | `B04` | H01 `WEAKENED`, H02 `UNDER_INVESTIGATION` |
| `MIXED_FUNCTIONAL_RESCUE` | matched, some endpoints normal and others impaired | `B04`, with `B14` where endpoints conflict in direction | same as `RESIDUAL_FUNCTION_DEFECT` — see below |
| `SAFETY_OR_CONFOUNDER_HOLD` | increased death, reduced division or reduced viability; or a critical adverse flag | `B16`, `B09` | conclusions held; these fire whether or not the result is otherwise admissible |
| `INDETERMINATE` | identity or provenance unverified (`B00`); precision inadequate, controls invalid or a required readout missing (`B01`); or a valid result matching no branch (`B15`) | `B00`, `B01`, `B15` | none; `B15` additionally requires model revision |

**`MIXED_FUNCTIONAL_RESCUE` is not a seventh verdict, and that is deliberate.** The rule engine fires
`B04` on *any* persisting defect, because a partial functional response is not full rescue: an
abundance-only strategy is weakened by the endpoint that failed regardless of which others were
rescued. The mixed pattern is recorded per endpoint and reported, not promoted into a separate
conclusion. Inventing a seventh branch here would let a partial result read as a qualified success.

**Precedence, as the code implements it.** `B00` quarantines. `B01` makes `B03`/`B04` inadmissible.
`B02` fires even when the result is otherwise inadmissible. `B09` and `B16` always fire. So a failed
control cannot become a finding, and an unmatched abundance cannot become a function claim.

## 6. What this experiment cannot conclude

Carried on every forecast and export, verbatim from the plan: patient benefit; treatment readiness; the
child's endogenous protein behaviour. Plus, specific to this design: normal-protein rescue validates
the assay and does not establish mutant-protein function; construct results are not the child's
endogenous protein; and a result at matched abundance in a cancer line is not a statement about the
child's own cells.

## 7. Where the result lands

| outcome | consequence for the case |
|---|---|
| `ABUNDANCE_SUFFICIENT_FOR_TESTED_FUNCTIONS` | the abundance premise is established for this allele across all four functions; the open problem becomes entirely physical — an actuator that raises abundance, which is `MVA_BUBR1_STABILITY_REALIZATION.md` |
| `RESIDUAL_FUNCTION_DEFECT` / `MIXED_FUNCTIONAL_RESCUE` | H02 for this child; an abundance-only route is weakened even where the checkpoint looks rescued, and the stabilisation search stops being the critical path |
| `MATCHED_ABUNDANCE_NOT_ACHIEVED` | the prior question becomes whether this allele is expressible at wild-type-comparable level at all — itself a statement about turnover, and directly relevant to the stabilisation search |
| `SAFETY_OR_CONFOUNDER_HOLD` | no functional conclusion; the population must be characterised before any endpoint is credited |
| `INDETERMINATE` | nothing moves; the specific failed gate is named and repeated |
