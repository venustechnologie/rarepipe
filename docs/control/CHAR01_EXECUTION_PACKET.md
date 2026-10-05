# CHAR01 — execution packet

**Core question.** Does this child's exact missense allele destabilise the BubR1 protein at all?

**Why this is first in F1.** Every route in the abundance family assumes it does, and nothing has tested
it. `MC_0006` — "this child's missense allele reduces BUBR1 abundance or function" — is `UNRESOLVED` on
**zero** establishing records; `MC_0005`, the variant-class claim, rests on 0 establishing and 11
indirect. And the class inference is not safe: **Q921H is a kinase-domain substitution that is normal in
both level and function**, so sitting in the kinase domain does not establish instability. If this
allele is not destabilised, EXP01's matched-abundance framing is miscast before it is run.

**What it resolves.** `CHAR01`, which is unavoidable for the abundance family and upstream of every other
F1 branch. No patient material is required.

**Decision authority.** `MVA_CONTINGENT_ROUTE_MAP.md`. No new decision machinery and no new vocabulary;
the four admissible results are the branch's declared outcomes in the map.

---

## 1. Constructs

| arm | construct | role |
|---|---|---|
| X | **this case's exact substitution**, LAP-tagged | the test arm |
| W | wild-type | the abundance reference everything is measured against |
| R1 | I909T | reference destabilised substrate: normal transcript, ~2-fold elevated turnover, HSP90-dependent |
| R2 | L1012P | second reference destabilised substrate |
| N | Y155C or R550Q | a substitution away from the kinase domain that does **not** affect protein level |
| Q | Q921H | the control that matters most here: a kinase-domain substitution that is normal in level and function |

Human cells, stable or inducible expression, as in PMID:20516114 Fig. 2D and 3C. Arm X's identity —
transcript, isoform, exact substitution — is verified locally and held in the private layer
(`private:exp01-construct`); it is supplied to a synthesis provider as a sequence through that channel
and appears in no external order, report or query.

Arms N and Q are what make a positive result mean something. Without them, "this allele is less abundant
than wild-type" cannot be separated from a tag, expression-system or clone artefact.

## 2. Readouts

| id | readout | method |
|---|---|---|
| C1 | steady-state abundance | quantitative immunoblot, all arms on one membrane, loading control, arm W as reference |
| C2 | protein turnover | cycloheximide chase (5 h in the source), decay quantified per arm |
| C3 | chaperone dependence | HSP90 inhibition (geldanamycin); the source's discriminator between mutant and wild-type |
| C4 | degradative route | MG132, and the MG132 + HSP90-inhibition combination the source used to show the turnover is proteasomal |
| C5 | transcript level | RT-qPCR for the construct and endogenous *BUB1B* |

**C5 is what makes this a protein-stability result.** The reference substrates have normal mRNA, so a
transcript-level difference would mean the construct or its expression is the variable, not the protein.

## 3. Admissible results

Precommitted, from the map.

| result | condition | what it means for F1 |
|---|---|---|
| `destabilised_like_reference` | C1 reduced versus W, C2 turnover elevated, C3 HSP90-dependent, C4 proteasomal, C5 transcript normal | the class premise holds for this allele; the abundance family is correctly framed and EXP01 is the next question |
| `not_destabilised` | C1 comparable to W with C5 normal | **simple abundance-limited instability is not demonstrated in this construct; exact functional characterisation remains required.** That is the whole entitlement. It does not establish a direct functional defect, and it does not assign the allele to the Y155C regime — a construct in a cell line is not the child's protein, and this assay measures abundance, not function |
| `destabilised_other_mechanism` | C1 reduced **with C5 normal**, but not HSP90-dependent or not proteasomal | abundance is reduced by a route where the P1/P2 grounding does not apply, so the stabilisation mechanisms in `MVA_STAB01_PROTOCOL.md` lose their basis for this allele |
| `not_expressible` | no construct dose reaches W's level | an expression-validity result before a biological one: it opens `EXPRVAL01` and stabilisation, and does **not** close the abundance family |

The last row is a deliberate correction. Failing to express a construct says something about the
construct, the promoter and the tag before it says anything about the protein.

## 4. Controls and validity

Three biological replicates minimum. Arm W against itself across replicates defines what "comparable"
means, declared before the test arms are read — **no numerical threshold is specified here, because none
is grounded.** Blinding of the blot quantification to arm identity, with the key held outside the
scoring record.

Validity fails, and **no result is assigned**, if: R1 and R2 do not reproduce their published reduction
relative to W; or Q921H does not come back normal; or C5 shows a transcript difference in the test arm.

**On C5 specifically**, because the two readings must not overlap. A transcript difference in the test
arm is a **validity failure, never a biological result**: protein stability cannot be read off an arm
whose transcript level differs, so the condition is uninterpretable for this question and routes to
expression-validity investigation rather than to any of the four results. Every result above therefore
requires C5 normal, and `destabilised_other_mechanism` means "reduced abundance at normal transcript by a
non-HSP90 or non-proteasomal route" — not "reduced transcript".

## 5. What this experiment cannot conclude

Whether the altered protein **works** — that is EXP01, and it is a different experiment at a different
abundance. Whether anything can raise this protein's abundance — that is STAB01. Anything about the
child's endogenous protein, since this is a construct in a cell line. And nothing about the second
allele, which is not part of this question.

## 6. Relationship to FLUX01

They do not replace each other and share no equipment-level dependency. `CHAR01` asks whether the
destabilised-protein premise is true for this allele. `FLUX01` asks whether that repair can be skipped
by correcting chromosome fidelity through other physics. A negative on either leaves the other
untouched, which is why the map reports them as separate priorities rather than as a ranking.
