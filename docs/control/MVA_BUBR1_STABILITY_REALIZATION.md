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

**Retrieval.** 24 queries in two rounds against Europe PMC, phrased by physical function only. Every
query passed the Stage 04 case-identity guard and the therapy filter — the filter refuses `inhibitor`,
`drug`, `treatment` and similar by design, so this could not drift into an intervention hunt. 354 unique
records seen; 19 passed a BubR1-plus-stability-plus-measurement screen; the snapshot
`data/literature/mva-stability-v1/` freezes the cited set plus every screen-passing candidate, titles
and abstracts only, so each rejection below is checkable against the text that produced it.

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

**Applicability gap to this case.** Three, and they are not small. The protein stabilised was
*wild-type* BubR1 declining with age, not a misfolding missense mutant. The context is mouse tissue
in vivo, not human cells carrying a kinase-domain substitution. And the agent was NMN, not the agent in
this case's chain — a distinction the repository already records on this citation.

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

## 7. Candidates that survived grounding

**M1 (SIRT2 / K668) and M2 (FBXW7 / T620)** — the only two with a measured effect on BubR1 protein
abundance or stability. M3 survives as mechanism identification on the correct allele class, in the
wrong direction.

Ranked by what they would still need: M1 has the right measurement (abundance, raised) in the wrong
system; M2 has the right system (human cells) and the wrong measurement (a kinetochore pool). Neither
has been tested on a misfolding substrate.

## 8. Candidates rejected, and why

| candidate | source | why it fails the bar |
|---|---|---|
| Aurora B → BubR1 K250 acetylation | PMID:41533580 | measures MCC stability and fibrous-corona maintenance, not BubR1 abundance. A different lysine from K668 and a function mechanism, not a turnover one |
| Sirt2 → BubR1 K243 acetylation | PMID:29067790 | readouts are meiotic spindle anomalies and aneuploid-egg incidence, not BubR1 protein level; mouse oocyte meiosis; a third lysine again |
| UBR5 ubiquitin ligase | PMID:35217622 | ubiquitylation here drives Bub3·BubR1 **complex dissociation**, not degradation. Ubiquitin is not always a turnover signal, and this is the case where it is not |
| codon usage bias | PMID:35811551 | transcript-level and translational tuning, in fission yeast. This case's transcript is already normal, so it addresses a step that is not broken |
| CWC22 splicing factor | PMID:41534835 | knockdown **lowers** BubR1 — wrong direction — and acts on expression, not stability |
| HSP90/HSF1 perturbation with arsenic trioxide | PMID:19371599 | wrong direction (further destabilising) and an intervention-shaped study, not a stabilisation mechanism |
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
- a demonstrated BubR1 degradation route exists in human cells (M2), but it is a mitotic phosphodegron
  acting on a kinetochore pool, and misfolded-protein clearance is a different pathway

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
