# MVA_001 — physical stabilisation of BubR1: what is experimentally demonstrated

`raise BubR1 abundance` is no longer treated as a single control. The primary experiment factored it:

```
altered kinase-domain protein  ->  misfolding / elevated turnover  ->  low steady-state abundance
```

Transcript level is normal, so expression is not the lever. The lever is **turnover**. This document
asks what physical mechanism is experimentally demonstrated to raise BubR1 protein abundance or slow its
degradation, and refuses anything that is only an association.

**Grounding bar.** Every entry must resolve to `physical component -> perturbation -> measured BubR1
abundance/stability -> biological context -> source`. A mention, a pathway membership or a plausible
mechanism does not qualify. No drug is recommended and none was searched for.

**Retrieval.** 36 queries in three rounds against Europe PMC, phrased by physical function only; 460
unique records. Snapshot frozen at `data/literature/mva-stability-v1/` (19 documents, titles and
abstracts only) so every rejection below is checkable against the text that produced it.

**Round 3 exists because the search policy was corrected.** The earlier filter refused any query
containing `inhibition`, which made most of experimental cell biology unsearchable — a mechanism is
established by perturbing a system and measuring what moves, and the paper this case rests on
identifies its own mechanism with geldanamycin, cycloheximide and MG132. Search governance and
therapeutic-output governance are now separate: perturbation vocabulary is searchable, therapeutic
framing is still refused, and the prohibition on turning "inhibiting X raised Y" into "administer an
inhibitor of X" is enforced over these documents instead. Round 3 returned 8 BubR1-plus-stability
records the old filter could not reach, and one of them changed a verdict below.

## 1–6. Mechanisms that cleared the bar

### M1 — SIRT2 deacetylation of BubR1 K668 (NAD+-dependent)

| field | value |
|---|---|
| physical components | SIRT2 (NAD+-dependent deacetylase); CBP (acetyltransferase, opposing); BubR1 lysine-668; NAD+ |
| perturbation | SIRT2 overexpression; NMN (an NAD+ precursor) administered to mice |
| measured effect | **"increases BubR1 abundance in vivo"** — a measured rise in BubR1 protein, not a pathway inference |
| supporting mechanism | the age-related loss of BubR1 is attributed to declining NAD+ and to SIRT2's ability to "maintain lysine-668 of BubR1 in a deacetylated state", "counteracted by the acetyltransferase CBP" |
| biological context | mouse tissues in vivo; aged wild-type mice and BubR1 hypomorphic (H/H) mice |
| source | PMID:24825348 (*EMBO J* 2014) |

K668 acetylation is a destabilising mark; deacetylation preserves the protein. This is a turnover
mechanism with a named residue, a named writer, a named eraser, and a measured abundance increase.

**The same relation, in human cells, in the opposite direction.** Selective Sirt2 inhibition by the
ligand SirReal2 "induces destabilization of the checkpoint protein BubR1" in HeLa cells
(PMID:25672491). Taken with M1 this brackets the relation: raising SIRT2 activity raises BubR1
abundance in mouse tissue, lowering it lowers BubR1 abundance in human cells. That supplies the human
context M1 by itself lacked, and it is a record the previous search policy made unreachable.

**Applicability gap to this case.** The protein whose abundance moved was *wild-type* BubR1 — declining
with age in M1, destabilised by Sirt2 inhibition in PMID:25672491 — not a misfolding missense mutant.
The gain-of-function direction, the one a rescue needs, is still only demonstrated in mouse tissue in
vivo. And the agent there was NMN, not the agent in this case's chain, a distinction the repository
already records on this citation.

### M2 — SCF-FBXW7 ubiquitination via the BubR1 Thr620 phosphodegron

| field | value |
|---|---|
| physical components | SCF-FBXW7 E3 ubiquitin ligase; BubR1 Thr620 phosphodegron; Cdk1 (upstream kinase); CENP-E (co-regulated) |
| perturbation | FBXW7 depletion; phospho-resistant T620 mutation; Cdk1 inhibition |
| measured effect | "Depletion of FBXW7 results in prolonged metaphase arrest with **increased stabilization of BubR1 at kinetochores**"; FBXW7 induced BubR1 ubiquitination, and the T620 phospho-resistant mutation impaired both the BubR1–FBXW7 interaction and FBXW7-mediated ubiquitination |
| biological context | human cells, mitosis |
| source | PMID:38008853 (2023) |

**Applicability gap to this case.** The stabilisation was measured **at kinetochores**, which is a
localised pool, not the steady-state cellular abundance this case needs raised. The substrate is
normally folded BubR1 being turned over on schedule during mitosis; nothing shows this route clears the
misfolded protein that defines this allele class. And FBXW7 is a tumour suppressor, so depleting it is a
direction with its own consequences in a chromosomal-instability disorder.

### M3 — HSP90-dependent folding and proteasomal clearance of the mutant protein

| field | value |
|---|---|
| physical components | HSP90; the proteasome; the mutant protein itself |
| perturbation | HSP90 inhibition (geldanamycin); cycloheximide; MG132; and combinations |
| measured effect | mutant BubR1 levels fell severely under HSP90 inhibition while wild-type barely moved; MG132 prevented the enhanced turnover that HSP90 inhibition caused; turnover of I909T and R727C was ~2-fold higher than wild-type |
| biological context | U2OS stably expressing LAP-tagged wild-type, I909T or L1012P; MVA patient lymphoblastoid lines |
| source | PMID:20516114 |

This is the only entry measured **on this allele class**, and it is the reason the problem is
well-posed: the machinery that sets this protein's abundance is identified as chaperone-dependent
folding plus proteasomal degradation.

**Applicability gap.** It runs in the destabilising direction only. It establishes that the mutant
protein depends on HSP90 and is cleared by the proteasome; no experiment here or elsewhere in the
snapshot raises its abundance by acting on either.

### M4 — EZH2 as a stabilising binding partner, independent of its catalysis

| field | value |
|---|---|
| physical components | EZH2, in a methyltransferase-activity-independent role; direct EZH2–BubR1 interaction |
| perturbation | EZH2 depletion by morpholino; ectopic EZH2 expression; methyltransferase inhibition (DZNep, GSK343) as the specificity control |
| measured effect | "EZH2 directly interacted with and stabilized BubR1"; depletion produced chromosome misalignment and abnormal spindle assembly, while inhibiting EZH2's catalytic activity did not affect maturation — so the stabilisation is a binding function, not a methylation function |
| biological context | mouse oocyte meiosis |
| source | PMID:27226494 (2016) |

This is the only candidate in the **stabilising-interaction** class the brief asked about, and the
catalysis-independence is what makes it interesting: a binding partner that holds the protein up is a
different kind of lever from an enzyme that marks it.

**Applicability gap.** Mouse oocytes and meiosis, not human somatic cells; the abstract reports
stabilisation without a quantitative abundance figure; and nothing tests it on a misfolding substrate.

### M5 — APC/C-Cdh1 and the BubR1 KEN degrons: a route that defeats itself

| field | value |
|---|---|
| physical components | Mad3/BubR1 KEN boxes (KEN30, KEN296, "conserved from yeast Mad3p to human BubR1"); APC/C; Cdh1 |
| perturbation | KEN30 mutation; APC/C subunit mutation; Cdh1 mutation |
| measured effect | "mutation of Mad3-KEN30, APC/C subunits, or Cdh1p, stabilised Mad3p in G1" — a real stabilisation, with a named degron |
| biological context | budding yeast |
| source | PMID:17406666 (2007) |

Recorded because it is a genuine turnover mechanism, and rejected as a route for this case for a reason
worth stating: **the degron is also function-essential.** Both KEN boxes are required for spindle
checkpoint function, and PMID:20516114 notes both are intact in the checkpoint-competent 483X
truncation. Stabilising BubR1 by disabling its KEN box would preserve the protein and destroy the
function the protein is wanted for. A stabilisation route has to be checked against function before it
is called a route at all — which is precisely why STAB01 does not conclude anything about function.

## 7. Candidates that survived grounding

**M1 (SIRT2 / K668), M2 (FBXW7 / T620), M4 (EZH2 binding)** — a measured effect on BubR1 protein
abundance or stability. **M3** survives as mechanism identification on the correct allele class, in the
destabilising direction only. **M5** is a real mechanism rejected as a route, on function grounds.

Ranked by what each still needs:

| | right measurement (steady-state abundance) | right system (human somatic cells) | tested on a misfolding substrate |
|---|---|---|---|
| M1 SIRT2 / K668 | yes, raised (mouse); lowered (human) | partly — human only in the lowering direction | no |
| M2 FBXW7 / T620 | no — a kinetochore pool | yes | no |
| M3 HSP90 / proteasome | yes, but lowered only | yes | **yes** — this allele class |
| M4 EZH2 binding | stabilisation asserted, not quantified | no — mouse oocyte meiosis | no |

No row has all three. M3 is the only one measured on the right substrate, and it only knows how to
make things worse. That is the shape of the gap.

## 8. Candidates rejected, and why

| candidate | source | why it fails the bar |
|---|---|---|
| Aurora B → BubR1 K250 acetylation | PMID:41533580 | measures MCC stability and fibrous-corona maintenance, not BubR1 abundance. A different lysine from K668 and a function mechanism, not a turnover one |
| Sirt2 → BubR1 K243 acetylation | PMID:29067790 | readouts are meiotic spindle anomalies and aneuploid-egg incidence, not BubR1 protein level; mouse oocyte meiosis; a third lysine again |
| UBR5 ubiquitin ligase | PMID:35217622 | ubiquitylation here drives Bub3·BubR1 **complex dissociation**, not degradation. Ubiquitin is not always a turnover signal, and this is the case where it is not |
| codon usage bias | PMID:35811551 | transcript-level and translational tuning, in fission yeast. This case's transcript is already normal, so it addresses a step that is not broken |
| CWC22 splicing factor | PMID:41534835 | knockdown **lowers** BubR1 — wrong direction — and acts on expression, not stability |
| HSP90/HSF1 perturbation with arsenic trioxide | PMID:19371599 | wrong direction (further destabilising) and an intervention-shaped study, not a stabilisation mechanism |
| Sirt2 structural inhibitor development | PMID:25672491 | the *mechanism* is used above as M1's human-cell bracket; as a route it is the wrong direction (it destabilises BubR1) and the paper's own framing is inhibitor development |
| Mad3 KEN box / Cdc20-APC interaction | PMID:18556659 | checkpoint function of the KEN boxes, not BubR1 abundance; yeast |
| BubR1 repression in acute myeloid leukaemia | PMID:23812934 | expression-level repression and re-expression in cancer cells; not a stability mechanism |
| BubR1 post-translational modification review | PMID:33892776 | a review. Useful as a pointer to primary work; it is not itself a measurement |
| mono-allelic BubR1 MVA mouse; MVA progeria allelic effects; BubR1 insufficiency in cardiac aging | PMID:23300461, PMID:31738183, PMID:40607964 | phenotype consequences of low BubR1. They motivate raising abundance; they do not demonstrate a mechanism that raises it |

## 9. The exact missing physical capability

> **No source demonstrates that any perturbation raises the steady-state abundance of a misfolding,
> kinase-domain-destabilised BubR1 missense protein in a human cell.**

Stated as the single missing molecular relation:

```
perturbation of [chaperone-dependent folding or degradative clearance]
  -> increased steady-state abundance of a misfolding BubR1 missense protein
     in a human cell, measured by quantitative immunoblot
```

Every element of that relation exists separately in the literature. What is missing is the edge:

- the substrate class is characterised (M3: HSP90-dependent, proteasome-cleared, ~2-fold faster turnover)
- a demonstrated way to raise BubR1 abundance exists (M1), but on wild-type protein in mouse tissue
- that same relation is now demonstrated in human cells — but only in the lowering direction
  (PMID:25672491), which is evidence the axis is live in human cells and not yet evidence it can rescue
- a demonstrated BubR1 degradation route exists in human cells (M2), but it is a mitotic phosphodegron
  acting on a kinetochore pool, and misfolded-protein clearance is a different pathway
- a stabilising binding partner exists (M4), in mouse oocyte meiosis, unquantified
- and one route that would work is ruled out on function grounds rather than evidence grounds (M5): the
  KEN degron is also required for the checkpoint

The nearest experiment that would close it is narrow and does not need a new capability: express this
allele class — I909T or L1012P, already in hand as the restored-abundance reference — in human cells and
ask whether any perturbation of chaperone or degradative machinery raises its steady-state level toward
wild-type, by quantitative immunoblot. That is a stability experiment, not a function experiment, and it
is independent of EXP01.

## What this changes upstream

The abundance route is no longer a black box, and its weak link has moved. Previously the chain was
`nicotinic acid -> NAD -> SIRT2 -> BubR1` with an `ASSERTED_ONLY` final edge. The mechanism half of that
chain — SIRT2 maintaining K668 deacetylated, with a measured abundance increase — is the best-grounded
stabilisation mechanism found here. The actuator half is still the problem: nothing connects nicotinic
acid specifically, in human cells, to this effect.

So the correct next physical question is not "does niacin work". It is whether **this allele's**
turnover is reducible at all, and by what component. The two surviving mechanisms say where to look:
the K668 acetylation switch, and the degradative machinery that clears the misfolded protein.
