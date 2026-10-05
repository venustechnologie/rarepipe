# FLUX01 — execution packet

**Core question.** Does a physical manipulation of microtubule poleward flux reduce chromosome
missegregation in a **BubR1-limiting** human-cell state, while preserving viability, division and cell
death?

**What it resolves.** Both branches on the shortest route to the cell-level functional state:
`DEP_FLUX` (is the effect independent of residual BubR1?) and `SAFE01` **for this component**. Population
safety is manipulation-specific, so this campaign settles it for flux and for nothing else.

**Decision authority.** `MVA_CONTINGENT_ROUTE_MAP.md`. This packet adds no decision machinery and no new
vocabulary; the five admissible results below are the campaign's declared outcomes in the map, and their
continuations are already computed there.

**Independence classifies the route; it does not grade the result.** The cell-level functional target is
low missegregation with viability, division and cell death preserved. It does not require that the route
avoid BubR1. So a benefit that depends on residual BubR1 is **not a failed bypass** — it is a
compensatory route, the third strategy between repairing the protein and routing around it: exploit the
residual function that is present, alter a different physical process. It closes only if the benefit
disappears in the limiting regime this case occupies, because then it needs more protein than the case
has.

**What this is not.** Not a treatment, not a candidate for anybody, and not a claim about MVA. Every
agent below is a tool for setting a state variable in a dish. Reaching the cell-level state would not
be disease resolution — the map keeps five further unknowns between it and the organism scale.

---

## 1. The state to be created: BubR1-limiting, not BubR1-null

This is the load-bearing requirement and the reason the question cannot be answered from the
literature. Every published experiment on every candidate ran at BubR1-present or BubR1-absent. This
case is **limiting**.

**System.** Human cells with established, titratable BubR1 depletion: a doxycycline-inducible BubR1
shRNA line, as used for the abundance titration in PMID:20516114 Fig. 4D. hTERT-RPE-1 is preferred for
the flux readouts because the flux work was done there and it is non-transformed; a HeLa inducible line
is the fallback where the RPE-1 titration is not available.

**Graded levels, not one condition.** Doxycycline is titrated to produce an **experimentally measured
BubR1-limiting gradient spanning the known reference regimes** — replete, partially reduced, and down
toward the range where published work reported segregation failure — with the gradient defined by what
the blot measures in this system, not by importing numbers from another.

**No abundance level here is claimed to reproduce this child.** The published percentages come from a
different cell line with normal protein, and this case's own BubR1 level has never been measured
(`MC_0006` is `UNRESOLVED` on zero establishing records). The gradient exists so the result is read as
a function of abundance rather than at one arbitrary point; it is not a model of the patient, and no
row of it should be described as such.

**Level is measured, not assumed.** Quantitative immunoblot from the same lysates as the functional
readout, every replicate, with the loading control and depletion efficiency reported. A condition whose
BubR1 level was not measured is not a condition.

## 2. The manipulation: three mechanistically independent flux perturbations

Using three is the source study's own control against a single-agent artefact, and it is retained.

| arm | perturbation | why |
|---|---|---|
| F-a | low-dose paclitaxel | the source used 2 nM, chosen to reduce missegregation while preserving spindle integrity |
| F-b | HAUS8 codepletion | shortens antiparallel overlaps, slowing k-fibre flux |
| F-c | NuMA codepletion | independent route to the same overlap/flux change |

**Engagement is validated per arm**, or a null result means nothing: k-fibre poleward flux rate
(photoactivation or speckle imaging) and PRC1-labelled antiparallel overlap length. The source reports
overlap length as a predictor of whether slowing flux rescues anything, so it is measured rather than
inferred.

## 3. The independence test — the part that is not a single condition

`DEP_FLUX` asks whether the benefit requires residual BubR1. A single BubR1-limiting condition cannot
answer that. It is answered by a **dose-response of the rescue against measured BubR1 level**, and the
answer is a classification rather than a pass or fail:

- Rescue comparable across the gradient, including at its most limiting end → **independent**, a bypass
  route.
- Rescue present but scaling with residual BubR1 → **compensatory**, and still a route to the functional
  target. This is a result, not a disappointment.
- Rescue present in replete cells and **absent at the limiting end of the gradient** → it needs more
  protein than this case has, and only this closes it.
- Absence of a BubR1 interaction in one condition is not independence. The claim is licensed by the
  gradient, not by a single well.

This is the design consequence of the map's finding that silence in the literature was never evidence
of independence.

## 4. Readouts

**Primary — the terminal endpoint.** Chromosome missegregation: lagging chromosomes in anaphase by live
imaging, and micronuclei in the following interphase. Reported **per assessable division**, so a change
in how many cells divide cannot masquerade as a change in fidelity. The source scored a chromosome as
lagging if it trailed the dividing mass by at least 2 µm; the threshold used here is declared before
scoring, whatever it is.

**Primary — population, required.** Viability, cell death and division rate, each with its denominator,
in the same experiments. These are not optional and they are not trimmed. Fewer errors in a population
that is dying or dividing more slowly is selective loss, not rescue.

**Mechanistic diagnostics — recorded, never success criteria.**

| diagnostic | readout |
|---|---|
| chromosome alignment | kinetochore-to-equator distance in metaphase |
| attachment state | cold-stable microtubule staining |
| checkpoint activation | MPM-2 positivity after nocodazole |
| checkpoint silencing | time from alignment to anaphase onset |

These explain a result; they do not grade it. **A route that lowers missegregation with the population
preserved is not failed for leaving the canonical BubR1 trajectory unreproduced.** That is the target
audit's conclusion and this packet is built on it: alignment, activation and silencing were judged
canonical mechanistic intermediates, not universal success criteria.

## 5. Controls

| control | establishes |
|---|---|
| BubR1-limiting + vehicle | the defect that is to be rescued, at each graded level |
| BubR1-replete + each flux arm | whether the perturbation harms a normal population by itself |
| KIF18A-depleted + each flux arm | **replication** of the published rescue in these hands; if this fails, the assay cannot detect the effect and no conclusion about BubR1-limiting is admissible |
| BubR1-saturating depletion | the regime boundary — where the published literature's "absent" condition sits on this gradient |

The KIF18A arm is the load-bearing one. It is the positive control for the entire campaign.

## 6. Admissible results

Precommitted, and taken from the map rather than invented here. Continuations are computed in
`MVA_CONTINGENT_ROUTE_MAP.md`; the condition column is what assigns each.

| result | condition |
|---|---|
| `lower_missegregation_population_preserved` | missegregation falls across the gradient with flux engagement validated, rescue not scaling with residual BubR1, and viability, death and division unchanged |
| `lower_missegregation_benefit_needs_residual_bubr1` | missegregation falls with the population preserved, and rescue magnitude scales with residual BubR1 while remaining present at the limiting end — **a compensatory route, not a failure** |
| `lower_missegregation_population_harmed` | missegregation falls but death rises, or viability or division fall |
| `no_reduction` | flux engagement validated and missegregation does not fall anywhere on the gradient |
| `benefit_absent_in_limiting_regime` | rescue present in replete cells and absent at the limiting end: it needs more BubR1 than this case has |
| `insufficient_or_invalid` | flux engagement not validated, the KIF18A control failed, BubR1 level unmeasured, or a required readout missing |

Harm is assigned whatever the missegregation result; no benefit verdict overrides it.

## 7. What this campaign cannot conclude

That flux manipulation is suitable for anyone. That an effect in a cell line transfers to this child's
cells. That the canonical checkpoint trajectory is dispensable in general — only that it was not
required for the measured endpoint in this system. And nothing about tumour predisposition: that is
`ACT_SAFETY01`, an organism-level gate with no validated cellular surrogate, and a favourable result
here does not touch it.
