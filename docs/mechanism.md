# Stage 06 — molecular mechanism resolution

Track 1 answered *which* variants are causal. This stage asks what they do, and is built so that
a fluent story cannot pass for evidence.

## How the research actually happens

The pipeline owns the questions and the evidence; an assistant is a replaceable worker. Nothing in
the stage calls a model, and the whole stage runs without one — a test asserts the stage code
contains no API endpoint, no key lookup, and no client.

```
rarepipe research create-task      → KnowledgeTask, with its queries checked before they are sent
rarepipe research retrieve         → EvidenceBundle: the documents, and only those, that answer it
rarepipe research brief            → the paste-ready brief: rules, documents, required return shape
   [ a person works with Claude Code, ChatGPT, a local model or a researcher ]
rarepipe research import-analysis  → deterministic validation, then MechanismClaims
rarepipe mechanism resolve --research <workspace>
```

An imported proposal is rejected unless every one of these holds: the cited source was actually
retrieved into that bundle; the quoted passage is found verbatim in the stored document; the scope
is a legal value; and — for a claim at `exact_variant` scope — one of the cited documents actually
mentions this case's residue, checked locally against the private artifact. The assistant proposes;
the evidence store proves.

Each import writes an `LLMResearchSession`: provider, interface, model, which task, which documents
it was permitted to see, which claims it produced, which were accepted, which were rejected, and
whether a human reviewed it. Enough to answer "which model helped with which reasoning step",
without capturing a conversation.

`automation_status` is stated in every dossier: orchestration `deferred`, mode
`human_operated_llm_assistance` or `deterministic_only`, and `pipeline_depends_on_an_llm: false`.
We are discovering the research workflow before automating it.

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
* **Every quote is re-found in its stored source** before the record is accepted, whether it came
  from the deterministic extractor or from an assistant. A fabricated quote or a citation to a
  document outside the bundle fails closed.
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

## Stage 06F — reopening a frozen run

A frozen corpus and dossier are never edited. Reopening builds new runs beside them and a
computed comparison.

1. **Refresh the corpus.** `rarepipe mechanism refresh-corpus --corpus-run <frozen> --output <dir>`
   copies the frozen corpus into a new sealed run, then retries licensed full text for every
   abstract-only document and tries each listed supplement. Every document gets a record: what it
   was before, what it is now, why, and when it was retrieved. If the repository answers with a
   bot-detection challenge, the supplement is recorded as `inaccessible_bot_challenge` and left
   alone. Nothing solves or bypasses the challenge. A person can download it and pass it back with
   `--supplement SOURCE_ID=file.pdf`.
2. **Extract experiments, not sentences.** `research/experiments/*.yaml` holds `VariantExperiment`
   records: the construct, what protein was tested, the abundance condition and each readout
   (abundance, mRNA, turnover, chaperone dependence, checkpoint, segregation, alignment). Each
   readout's quote, and any `authors_interpretation`, must be re-found verbatim in the stored
   source. Notation is matched across forms (I909T / Ile909Thr / p.(Ile909Thr) / LAP-I909T; 731X /
   \*731). Normal-protein replacement is kept separate from the altered protein, and it can never
   answer the residual-function question.
3. **Grade directness locally.** Each experiment is graded exact / same position / nearby (≤10
   residues) / same region / different region against the child's missense allele. Positions use
   the canonical isoform (UniProt O60566-1 = ENST00000287598), and the transcript is checked first.
   If the transcript is not canonical, grades are withheld. Grades live only in restricted fields,
   because a nearby published variant would localise the child's residue.
4. **Decide at two levels.** `ResidualFunctionAssessment` answers one question: when abundance is
   restored, does the altered protein work? It answers once at class level and once for this
   child's allele, and keeps the two separate. The decision follows the exact-allele level:
   `STRENGTHENS_STABILIZATION`, `WEAKENS_ABUNDANCE_ONLY` or `INSUFFICIENT`. When the decision is
   insufficient, the assessment names the distinguishing experiment.
5. **Correct extractor directions on review.** The extractor reads cue words, and new full text
   brings new false contradictions. Examples are "comparable to wild-type" in a rescue legend and
   "not required" about the kinase domain. `research/corrections/*.yaml` records a reviewed
   direction for a passage, keyed by source and passage text rather than evidence id. The dossier
   lists each correction and how many records it matched. A correction that matches nothing is
   reported as stale.
6. **Compare.** `mechanism resolve ... --compare-mechanism-run <frozen> --compare-track2-run <frozen>`
   writes `comparison_with_baseline.md`, a table computed from the two sanitized artifacts. It
   also lists the dependent stages that must be regenerated. Stage 07 then cites the assessment
   in IP_001 and IP_004 without changing their gates. Stage 09 (`track2 adjudicate --mechanism-run`)
   re-derives every hypothesis's residual-function efficacy dependency and SC_004 from it.
