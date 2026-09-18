# Stage 06 — molecular mechanism resolution

Track 1 answered *which* variants are causal. This stage asks what they do, and is built so that
a fluent story cannot pass for evidence.

Two commands, split along the network boundary:

```
rarepipe mechanism fetch-corpus --output <work>/mechanism_corpus       # networked, never opens a case artifact
rarepipe mechanism resolve --corpus-run <corpus run> \                 # offline, opens the case, no network
  --adjudication-run <stage 04>/adjudicated_hypothesis.private.json \
  --validation <stage 05>/external_validation_result.json \
  --output <work>/mechanism
```

## The rules the schema enforces

* **Four epistemic classes, and no fifth.** `observation`, `external_evidence`, `derived_inference`,
  `unknown`. There is no "model knowledge": anything an agent produces is a derived inference that
  must cite evidence, or it is recorded as an `InvalidInference` and discarded.
* **Scope is never widened.** Evidence at `variant_class` scope — other kinase-domain variants —
  cannot establish a claim at `exact_variant` scope about this child's allele. The claim stays
  `UNRESOLVED` and says why.
* **Only a measurement can establish a functional claim.** A domain annotation or a predictor score
  is recorded as *indirect* evidence: visible in the claim, unable to change its status.
* **A claim must be about its own subject.** Topic guards stop a sentence mentioning "transcript
  levels" from counting as evidence of nonsense-mediated decay.
* **Every quote is re-found in its stored source** before the record is accepted. A fabricated
  quote or a citation to a document outside the corpus fails closed.
* **Unknown links stay in the graph** as unknown edges, and contradictions get their own section
  rather than a softening clause. Where sources disagree, both mechanistic classes are kept — the
  disagreement is the finding.

## Retrieval

Queries are gene-, protein- and disease-level, and pass two gates before they are sent: the Stage 04
disclosure guard (no coordinates, HGVS, residue, rsID or HPO terms) and a therapy filter that refuses
anything that looks like intervention search. The child's residue is never a query — the corpus is
downloaded first, and exact-allele matching runs locally against it. Full text is stored only where
it is openly available; a paywalled paper is recorded as metadata and abstract with an access note,
never scraped around.

Every query is logged with what generated it, how many records it returned and how many were kept,
so the research process itself becomes pipeline data.

## Output

`mechanism_dossier.private.json`, its sanitized sibling, `mechanism_graph.json`, and a human-readable
`mechanism_dossier.md`. The run ends in exactly one of two states:

* `MECHANISM_READY_FOR_INTERVENTION_SEARCH` — the disease-level mechanism is established well enough
  that an intervention search would have something to act on. It does **not** mean every allele
  detail is known.
* `MECHANISM_BLOCKED` — a link is unresolved or contradicted, and the dossier names which.

No drug, treatment or repurposing reasoning happens here, and rescue experiments are recorded as
mechanistic evidence, not as proposed treatments.
