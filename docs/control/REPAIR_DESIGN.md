# Evidence seed repair and full recompile — design

The previous phase found that one of the citations this case rests on does not support the claim
built on it, and that a directly relevant human trial was in the repository attached to nothing.
This phase fixes the evidence layer and recomputes everything that depended on it:

```
evidence correction → epistemic correction → model correction → architecture correction
```

**Build authorization: repair and recompile only.** No new discovery features, no new providers, no
larger corpus, no new solvers, no new architectures.

Outputs: [`MVA_EVIDENCE_REPAIR_DELTA.md`](MVA_EVIDENCE_REPAIR_DELTA.md) and
[`MVA_FULL_RECOMPILE_DELTA.md`](MVA_FULL_RECOMPILE_DELTA.md). Every other generated map in
`docs/control/` was regenerated from the repaired evidence; none was edited.

## The test is not whether the old answer survives

The governing rule, and the reason several existing tests had to change. Two of them asserted the
historical conclusion directly — that the case's direct precursor route *is* contradicted — which
would have made the correct answer unreachable. They were rewritten to assert the property on
constructed chains, so the invariant survives while the conclusion is free to move:

> a contradicted verdict resting on exactly one citation cannot survive that citation being withdrawn

Three more asserted counts (six unmeasured parameters, six benchmark cases) that legitimately changed
when a new piece of evidence was connected. A count is not a property.

## Four repairs, versioned rather than overwritten

Each records the previous claim version, the previous source assignment, the previous verdict, the
reason for invalidation and the new version, so *why was this edge contradicted before and not now*
has an answer in the repository rather than in a commit message.

| Repair | Edge | Before | After |
|---|---|---|---|
| R1 | direct precursor → protein abundance | `contradicted`, PMID:42543917 | `asserted_only`, no citation |
| R2 | precursor → intracellular pool | not represented | `human_experimental`, PMID:32386566, human skeletal muscle |
| R3 | precursor → circulating pool | `human_experimental` capped by an unverified label | label lifted; retrieval confirmed the attribution verbatim |
| R4 | cell death → division rate | `model_experimental`, PMID:20516114 | `asserted_only`, no citation |

**R1 searched for the intended reference before withdrawing anything.** The project's own curated
artifact ids (`MC_0001`–`MC_0013`) hold nothing about this precursor, so no local artifact had been
mis-transcribed into a bare identifier. Five targeted queries returned work on oocytes, ovarian
ageing and reviews, and nothing reporting a null effect of this precursor on this protein. No
substitute was adopted. The new support level is what the chain's own validator permits once a
citation is withdrawn — an edge with no reference may only be `asserted_only` — and the edge was not
deleted, because deleting it would have hidden a hypothesis the case still holds.

**R4 was found by auditing everything, not just the citation that had already failed.** It is flagged
as needing a human decision: only abstracts are stored, so the remedy may be retrieving the full
article rather than leaving the edge as an assertion.

## The backward audit

Attributions are **derived from the chain**, one per cited edge, with the literature spellings of
each endpoint in a single table — so an edge added or re-cited is audited automatically and the audit
cannot fall behind its source. Six states, and the rule is asymmetric on purpose:

- an abstract mentioning **neither** endpoint is not about the relation → `DOES_NOT_SUPPORT_ATTRIBUTION`
- one endpoint absent → `PARTIALLY_SUPPORTS_ATTRIBUTION`, because full text is not stored and the
  absence may be scope
- a reference carrying three or more relations with an endpoint absent → `ATTRIBUTION_AMBIGUOUS`,
  since which one it supports cannot be isolated from what is stored
- both present → `SUPPORTS_ATTRIBUTION`, which is **necessary and not sufficient**

So the audit can disqualify an attribution; it cannot confirm one. Three of its nine checks are
reported as `not_machine_checkable`, including *does the claim follow from the source*, because
implying otherwise would overstate what a string match establishes.

Ordering mattered: the first version checked the unverified-citation label before the term checks,
so the decisive finding came back as "no retrieval record" and the fact that the document is about
something else was hidden behind the weaker one.

| | Before repair | After repair |
|---|---|---|
| `SUPPORTS_ATTRIBUTION` | 8 | 9 |
| `ATTRIBUTION_AMBIGUOUS` | 3 | 3 |
| `PARTIALLY_SUPPORTS_ATTRIBUTION` | 1 | 1 |
| `DOES_NOT_SUPPORT_ATTRIBUTION` | **2** | **0** |
| stale unverified labels | 2 | 0 |

## The counterintuitive result

**Withdrawing the refutation made the answer weaker, not stronger.** The direct precursor route used
to be *excluded* from propagation as falsified. It is now an assertion with no evidence either way,
so it contributes and the propagated verdict is capped by it: `propagate(precursor → abundance)` went
from a verdict set by the surviving routes to `ASSERTION_ONLY`, with the direct edge as the weakest
link. The system stopped knowing something it never had grounds for, and knows less as a result.

That is the opposite of what a phase aiming to improve an answer would produce, and it is the point.

## What the human trial changed, and what it did not

R2 records the trial at the context it supports and no wider: human skeletal muscle in myopathy
patients. The consequences:

- `precursor → intracellular pool` moved from `CONDITIONAL_ON_UNVERIFIED_SUBSTITUTION` to
  `SUPPORTED_IN_HUMANS`, and a test asserts that verdict can never appear without the tissue that
  bounds it — the limiting scope note says "not the cell type this case requires" and a caveat says
  nothing here recommends giving the compound to anyone.
- The capability gap for the intracellular pool keeps its headline, `CONTEXT_ONLY_CAPABILITY`, and
  changes its reason: the compartment objection is answered and a **transfer gap** replaces it,
  recorded as an object — *demonstrated in skeletal muscle (adult-onset mitochondrial myopathy),
  required patient-derived cells, missing evidence that the relation holds there too*.
- A benchmark had to be retargeted. It asserted the chain may claim *at most* compartment-substituted
  support for reaching the intracellular pool, which only held while one source monopolised that
  relation. The ceiling belonged to the transfer edge, and that is now what it checks.

Two downstream artifacts were removed rather than relaxed. A published-behaviour benchmark validated
the chain against a null result nobody published; it was retired, and the trial that was connected
to nothing took its place. And the negative-results store held a `MEASURED_NO_EFFECT` record for the
direct route — a store of negative results is exactly the wrong place to keep a null nobody measured,
so the record now says `NO_RELEVANT_DATA`.

## Propagation and staleness

Eleven layers, in dependency order, each observable read out of a **fresh compilation**. Ten moved;
one is reported unchanged with a reason, because "unchanged" without one is indistinguishable from
"not recomputed". Two moved only in their artifact digest, which the report states explicitly: the
contents changed and the conclusion did not.

The baseline is a recorded compilation, not a constant: a test checks the recorded control-model
digest against the committed map at the commit it was captured from.

## What did not change

The binding constraint on the case. The chain to missegregation is still capped by whether this
child's altered protein functions at restored abundance, and the control compiler is still
`CONTROL_INDETERMINATE` for exactly that reason. The repair corrected what the repository believed
about its own evidence; it did not move the question the case turns on, and it was not expected to.

## Mutation testing

Nine controls broken deliberately, all caught: re-associating the withdrawn citation, letting a
source with no relevant terms pass, widening skeletal muscle to the required cell system, removing
the context check, echoing the baseline back instead of recompiling, allowing a contradicted verdict
with no evidence behind it, letting a downstream artifact keep a constant digest, treating tissue
evidence as patient-derived-cell evidence, and dropping the transfer gap once the compartment
matches.

Two needed re-aiming, and one of those is worth recording: the chain has two identical
evidence-required guards, on `Parameter` and on `CausalEdge`, and the first attempt mutated the wrong
one. The control was never inert; the mutation was.
