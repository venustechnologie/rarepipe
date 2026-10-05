# EXP01 — execution-ready protocol

**Deliverable status:** handover document. Decision authority stays with
`MVA_EXP01_DECISION_PACKET.md`; this specifies the bench work that feeds it. No new decision vocabulary
is introduced here, and the precommitted interpretation matrix is the one already in the packet.

**Question.** When this case's altered BubR1 is expressed at abundance matched to the wild-type
replacement arm, are chromosome alignment, checkpoint silencing and chromosome segregation normal?

**Not the question.** Checkpoint activation. It is class-supported for this child's domain (I909T and
L1012P restored it at matched abundance) and therefore cannot discriminate H01 from H02. It is measured
as a replication control — and if the exact allele unexpectedly fails it while the I909T/L1012P
reference arm succeeds, that is informative and is reported, not discarded.

---

## 1. Materials

**Cells.** A human line with established BubR1 depletion-and-replacement: U2OS or HeLa. Both are used in
PMID:20516114 Fig. 4–5. One line is sufficient for the primary question; the second is the independent
context if the result is to be replicated.

For live imaging of segregation, a line stably expressing a chromatin marker (H2B-EYFP as in the source)
is required.

**Depletion.** shRNA or siRNA against endogenous *BUB1B*, as in the source. Where abundance needs to be
set deliberately rather than merely depleted, the doxycycline-inducible shRNA line used for the titration
in the source is the appropriate tool.

**Constructs.** RNAi-insensitive BubR1 cDNA, N-terminally LAP-tagged (the source confirms the tag does
not affect function or localisation), in the following arms:

| arm | construct | role |
|---|---|---|
| A | wild-type | assay validity; the abundance reference all matching is against |
| B | **this case's exact substitution** | the test arm |
| C | I909T *or* L1012P | restored-abundance reference — replication of the published rescue |
| D | L844F | an allele that cannot reach matched abundance |
| E | vector only | the deficient state |
| F | mock (no depletion) | the undepleted baseline |

Construct identity — transcript, isoform, and the exact substitution — is verified locally and held in
the private layer (`private:exp01-construct`). It does not appear in any external order, report or
query. Arm B is specified to the synthesis provider as a sequence, through the same private channel.

Arm D is a negative control for *expressibility*, not for function. It must not be read as a
matched-abundance loss-of-function control; the packet states this and the interpretation depends on it.

---

## 2. Matched abundance — the gate the whole experiment passes through

Nothing about function is interpretable unless `E01_EXPR` reads `matched`. If it does not, the result is
`MATCHED_ABUNDANCE_NOT_ACHIEVED` (`B02`) and no function claim is admissible.

**Procedure.** Quantitative immunoblot from the same lysates that produced the functional readout, all
arms on one membrane, loading control (tubulin, as in the source). Introduced protein must be
distinguishable from residual endogenous protein — the LAP tag provides this; depletion efficiency is
reported alongside.

**Criterion.** Arm B's level comparable to arm A on the same blot. Comparable is defined by the
laboratory's own measured reproducibility across replicate blots of arm A against itself, declared before
the test arms are read. **No numerical threshold is specified here, because none is grounded.** Two facts
constrain the judgement without supplying a cutoff:

- Segregation fidelity is steeply non-linear in BubR1 level: ~6% of wild-type mis-segregates in most
  cells, ~13% is almost normal (source, Fig. 4D lower). This was *normal* protein, so it does not
  transfer as a threshold for an altered protein — it is the reason "roughly comparable" is not
  sufficient and the comparison must be quantitative.
- Patient-line full-length BubR1 runs 2–6 fold below wild-type alleles. Matching is to arm A, never to a
  patient level.

**Per experiment, not once.** The protein being matched has elevated turnover by hypothesis, so the match
is re-established in every biological replicate rather than assumed from a pilot.

**Expect to need titration.** If arm B does not reach arm A's level at the same construct dose, the dose
is adjusted and the blot repeated. If no dose reaches it, that is itself the finding — route to
`MATCHED_ABUNDANCE_NOT_ACHIEVED`, and the question becomes STAB01's.

---

## 3. Primary readouts

Run all three on every arm, in the same experiments that produced the matching blot.

**`E01_ALN` — chromosome alignment.** MG132 (proteasome inhibition) to prevent mitotic exit, then fix and
score the fraction of mitotic cells with misaligned chromosomes. The source used 90 minutes. Criterion:
comparable to arm A. Cold-stable microtubule staining is the mechanistic adjunct where attachment status
needs resolving.

**`E01_SIL` — checkpoint silencing.** Time-lapse imaging of unperturbed mitosis; time from chromosome
alignment to anaphase onset. Criterion: timely exit comparable to arm A. This endpoint has never been
measured at restored abundance for any MVA allele, so there is no directional expectation and the
forecast declares none (`F02`). A *prolonged* mitosis with normal alignment is the signature to watch:
that is what 483X produced, and it is a silencing phenotype rather than an activation one.

**`E01_MIS` — chromosome segregation.** Live imaging of H2B-marked cells through division; missegregation
events per assessable division. The denominator is required and reported — per assessable division, not
per field, so that a change in how many cells divide cannot masquerade as a change in fidelity.

## 4. Replication control

**`E01_ACT` — checkpoint activation.** Nocodazole 16 h, MPM-2 positivity of the 4N population by flow
cytometry, as in the source. Criterion: within arm A's justified reference range. A prolonged arrest is
not automatically better.

Arm C is the load-bearing comparison. If arm C fails to restore activation, the published result has not
replicated in this lab, `qc.controls_valid` is false, `B01` fires, and `B03`/`B04` are inadmissible by
construction. No conclusion about the case allele can be reached from a run in which the reference arm
failed.

## 5. Mechanistic readouts, where they explain a result

**`E01_KT` — kinetochore localisation.** BubR1 and ACA (centromere) immunostaining after brief nocodazole
with MG132 (30 min in the source), quantified as BubR1/ACA per kinetochore.

**`E01_PP2A` — PP2A-B56 recruitment.** Where a validated assay exists.

Both are optional and neither decides anything. Localisation dissociates from function in this protein:
Y155C localises normally and is checkpoint-dead, and residual mutant protein in patient cells reaches
kinetochores. A normal `E01_KT` is therefore not evidence of function — it is evidence that a functional
failure is *not* explained by mislocalisation.

## 6. Safety and confounder readouts — required

**`E01_VIA` viability**, **`E01_DEATH` cell death**, **`E01_DIV` division rate**, each with its
denominator, in the same experiments.

These are not optional and are not trimmed to make the experiment smaller. Nothing in the retrieved
literature covers them: the `cell_death -> division_rate` relation is `ASSERTED_ONLY` because the full
source article contains zero occurrences of death, apoptosis, viability, proliferation, division rate or
clonogenic survival. An unmeasured step is observed, not assumed. Fewer missegregation events in a
population that is dying faster or dividing more slowly is selective loss, not rescue — and reading
`E01_MIS` without these three would reintroduce exactly the confounder the rules exist to catch.

## 7. Replication and blinding

Three biological replicates minimum for each readout, consistent with the source's own design (3–5
experiments per panel). Scoring of alignment and missegregation is done blind to arm identity; the
unblinding key is held outside the scoring record. Outcome assignment is mechanical from the matrix in
the decision packet once the readouts are categorised — the matrix is precommitted, so no interpretation
happens after the result is seen.

## 8. Outcome

Categorise each endpoint as `normal`, `impaired`, `partial` or `not measured`, set `E01_EXPR` to
`matched` or not, then read the outcome off the precommitted matrix in
`MVA_EXP01_DECISION_PACKET.md` §5. The six outcomes and their rules (`B02`, `B03`, `B04`, `B04`+`B14`,
`B09`/`B16`, `B00`/`B01`/`B15`) are defined there and are not restated here, so that one matrix stays the
single authority.

## 9. What this experiment cannot conclude

Patient benefit. Treatment readiness. The child's endogenous protein behaviour. Additionally: normal
protein rescuing the assay validates the assay and says nothing about the altered protein; construct
results in a cancer line are not a statement about the child's cells; and a stabilised protein is not a
functional protein — that is this experiment's question, while physical controllability is STAB01's.
