# MVA_001 — bench execution matrix

Three questions, frozen. **`NO_CROSS_PREREQUISITE`**: each may be executed and interpreted without
knowing either of the others' outcomes. They can go to a bench in any order, or at once.

**That is a scheduling property, not biological independence.** They may well share mechanism —
`LV1_KINETOCHORE_PHOSPHATASE_CAPACITY` proposes that some of them do, and `BR1` exists precisely
because one connection between two of these districts is plausible. Nothing here claims they are
mechanistically unrelated. What is claimed is narrower: no result is a prerequisite for running or
reading another.

They are **not ranked** and none is conditional on another. This is a matrix for handoff, not a route.

Full specifications: `CHAR01_EXECUTION_PACKET.md`, `FLUX01_EXECUTION_PACKET.md`, and the frozen `BR1`
entry in `MVA_CONTINGENT_ROUTE_MAP.md`. Decision authority stays there; this page is the summary a lab
can work from, and the admissible outcomes below are the ones those sources declare.

---

## CHAR01 — is the destabilisation premise true for this allele?

| | |
|---|---|
| **Scientific question** | Does this child's exact missense allele destabilise the BubR1 protein at all? |
| **Required biological system** | Human cell line with established expression of LAP-tagged BubR1 constructs (U2OS or HeLa, as in PMID:20516114 Fig. 2D/3C). **No patient material required or used.** |
| **Experimental manipulation** | Express a construct panel: the exact case substitution; wild-type; I909T and L1012P (reference destabilised); Y155C or R550Q (stable, away from the kinase domain); Q921H (kinase-domain, normal in level and function). Then cycloheximide chase, HSP90 inhibition, MG132, and the MG132-plus-HSP90-inhibition combination. |
| **Validity gates** | I909T and L1012P reproduce their published reduction against wild-type; Q921H returns normal; transcript level normal in the test arm; construct identity (transcript, isoform, substitution) verified locally before use. |
| **Primary readout** | Steady-state abundance by quantitative immunoblot, all arms on one membrane, loading control, wild-type as reference. |
| **Supporting / safety readouts** | Protein turnover (cycloheximide chase); chaperone dependence (HSP90 inhibition); degradative route (MG132 and the combination); transcript level by RT-qPCR for construct and endogenous *BUB1B*. |

**Admissible outcomes, and what each licenses.**

| outcome | licenses | does **not** license |
|---|---|---|
| `destabilised_like_reference` | The class premise holds for this allele; the abundance family is correctly framed and function at matched abundance becomes the next question. | Any statement that the altered protein works, or that its abundance can be raised. |
| `not_destabilised` | Only this: **simple abundance-limited instability is not demonstrated in this construct, and exact functional characterisation remains required.** | A direct functional defect; assignment to the Y155C regime; anything about the child's endogenous protein. |
| `destabilised_other_mechanism` | Abundance is reduced by a route where the HSP90/proteasome grounding does not apply, so the stabilisation mechanisms lose their basis for this allele. | That no stabilisation is possible — only that the interrogated mechanism is not the one. |
| `not_expressible` | An expression-validity finding: the construct, promoter or tag is the suspect before the protein is. | Closure of the abundance family. It opens expression-validity and stabilisation instead. |

**Invalid / non-informative conditions.** A transcript difference in the test arm makes the condition
uninterpretable for this question — protein stability cannot be read off an arm whose transcript
differs — and routes to expression-validity investigation rather than to any of the four outcomes.
Reference arms failing, or Q921H not returning normal, voids the run.

**Private boundary.** The exact substitution stays local. It is supplied to a synthesis provider as a
sequence through the private channel and appears in no external order, report or query. It is not in
this document.

---

## FLUX01 — can chromosome fidelity be corrected by other physics?

| | |
|---|---|
| **Scientific question** | Does a physical manipulation of microtubule poleward flux reduce chromosome missegregation in a **BubR1-limiting** human-cell state, while preserving viability, division and cell death? |
| **Required biological system** | Human cells with titratable BubR1 depletion — a doxycycline-inducible shRNA line, hTERT-RPE-1 preferred because the flux work was done there and it is non-transformed; a HeLa inducible line as fallback. A chromatin marker (H2B-EYFP) for live imaging. |
| **Experimental manipulation** | An experimentally measured BubR1-limiting **gradient** spanning known reference regimes, crossed with three mechanistically independent flux perturbations: low-dose paclitaxel, HAUS8 codepletion, NuMA codepletion. |
| **Validity gates** | BubR1 level measured by quantitative immunoblot in **every** replicate, not assumed from a pilot; flux engagement validated per arm (k-fibre flux rate, PRC1-labelled overlap length); the KIF18A-depleted arm reproduces the published rescue in these hands. |
| **Primary readout** | Chromosome missegregation: lagging chromosomes in anaphase by live imaging and micronuclei in the following interphase, **per assessable division**. |
| **Supporting / safety readouts** | Viability, cell death and division rate, each with its denominator, required not optional. Mechanistic diagnostics recorded and never graded: alignment (kinetochore-to-equator distance), attachment state (cold-stable microtubules), checkpoint activation (MPM-2 after nocodazole), checkpoint silencing (time from alignment to anaphase). |

**Admissible outcomes, and what each licenses.**

| outcome | licenses | does **not** license |
|---|---|---|
| `lower_missegregation_population_preserved` | The cell-level functional state is reached by a non-canonical route, with dependency tested across the gradient. | Patient relevance; transfer to the child's cells; any claim about tumour-predisposition risk. |
| `lower_missegregation_benefit_needs_residual_bubr1` | A **compensatory** route — residual function exploited, another physical process altered. A result, not a failure. | Independence of BubR1; and it does not weaken the route, because the functional target never required avoiding the protein. |
| `lower_missegregation_population_harmed` | Closure on safety grounds for this component. | Nothing about the component's efficacy overriding that; no benefit verdict overrides harm. |
| `no_reduction` | Flux is not the controllable physics for this state. | Closure of the alignment control variable — other actuators remain. |
| `benefit_absent_in_limiting_regime` | The benefit needs more BubR1 than this case has. | Closure of a combination route pairing partial restoration with flux. |
| `insufficient_or_invalid` | Nothing. | Any conclusion in either direction. |

**Invalid / non-informative conditions.** Flux engagement not validated; the KIF18A control failing;
BubR1 level unmeasured in any arm; a required readout missing. A null without validated engagement is
not a null.

**No invented thresholds.** The published ~6% / ~13% abundance figures are cited as the reason a
quantitative match is needed, never as a cutoff, and no abundance level is claimed to reproduce this
child — whose own BubR1 level has never been measured.

---

## BR1 — does the abundance axis touch the phosphatase axis?

| | |
|---|---|
| **Scientific question** | At experimentally matched BubR1 abundance, does K668 state alter kinetochore PP2A-B56 recruitment? |
| **Required biological system** | Human cells expressing acetylation-mimetic and non-acetylatable K668 constructs, with abundance matched across the comparison conditions. K668 is a published residue in the central region; it is not this child's position. |
| **Experimental manipulation** | Compare the K668-state constructs at matched abundance in the same experiment. |
| **Validity gates** | **BubR1 abundance matched across comparison conditions, in the same experiment.** This is the whole design: the established K668 stability effect would otherwise confound the recruitment readout. |
| **Primary readout** | Kinetochore PP2A-B56 per kinetochore. |
| **Supporting / safety readouts** | Total BubR1 abundance; kinetochore BubR1; a K668-state or target-engagement measurement where one is experimentally available; standard viability, cell death and division safeguards. |

**Admissible outcomes, and what each licenses.**

| outcome | licenses | does **not** license |
|---|---|---|
| `recruitment_changes_at_matched_abundance` | Supports **BR1 only**, and opens the downstream four-neighbourhood co-movement experiment. | Anything about `LV1`; patient relevance; therapeutic suitability. |
| `recruitment_unchanged_at_matched_abundance` | Closes **BR1 only**. | Any conclusion about `LV1`, which rests on four neighbourhoods sharing a phosphatase substrate and on the four-allele retrodiction — neither involves K668. |
| `abundance_not_matched` | Nothing. `NON_INFORMATIVE_FOR_BR1`. | **Never negative evidence.** An unmatched comparison cannot close this bridge. |

**Invalid / non-informative conditions.** Abundance not matched. And a substitution that must be
refused: changes in **chromosome alignment, cohesion, checkpoint silencing or missegregation may not
stand in for the recruitment measurement.** Those four are exactly the readouts `LV1` predicts
co-move, so accepting one as evidence for BR1 would confirm the bridge from the observations that
motivated its parent. A change in any of them, with recruitment unmeasured, leaves BR1 unresolved.

**Note on prior.** The structural facts lean *against* this bridge: K668 sits at the B56 interface but
outside the three positions that carry binding. It is worth asking because a positive result would
create a cross-district mechanism, and because one experiment can kill it without touching anything
else.

---

## What none of the three licenses

Patient benefit. Treatment readiness. Any statement about this child's endogenous protein. Any
inference that a result in a cancer or immortalised line transfers to the lineages that carry this
child's burden — that is a separate context question with its own unknowns, and the map keeps them.
