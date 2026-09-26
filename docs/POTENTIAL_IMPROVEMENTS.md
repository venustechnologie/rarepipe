# Potential improvements

A backlog, not a plan. Nothing here is urgent, and nothing here changes a scientific conclusion
already reached. Each entry says what is true today, what would be better, and what it would cost —
so a future reader can decide rather than rediscover.

Measurements are from mechanism run `RUN_20260919T105438Z_09a60f` and intervention run
`RUN_20260926T150901Z_b7fd2b`, taken 2026-09-26.

---

## 1. Attach sources to the interpretation layer

**The observation that started this.** The artifacts contain two layers with very different rigour,
and nothing in the schema distinguishes them.

Evidence and claims are fully sourced:

```
1,194 evidence records   1,194 with source_id   1,194 with a quote verified in the stored text
   48 claims             48 citing at least one evidence id
```

Interpretation is not:

```
43 prose statements · 5,021 characters
  with a machine-readable basis:  4
  with none:                     39
     InterventionPoint.limitations[]  11    MindChanger.would_weaken       4
     MechanisticAxis.limitations[]     5    MindChanger.would_falsify      4
     MindChanger.would_strengthen      4    expected_downstream_effect     4
     ActionOutcome.actual_result       3    ActionOutcome.lesson           3
```

Concretely: `MC_0012` ("restoring BUBR1 rescues the cellular phenotype") carries 43 evidence ids,
each resolving to a PMID and a verbatim quote. The limitation sitting beside it — "a molecular
rescue is not a clinical rescue" — is true, load-bearing, and points at nothing. A reader cannot
tell whether it came from a paper, from the claim statuses, or from an agent reasoning at 2am.

The shape of the schema is deliberate and should stay: 19 enum-constrained fields against 102
free-text ones in the dossier. The enums carry *status* and are what a machine gates on; everything
explanatory is prose, and should be.

**Proposal — a `Sourced` wrapper.** Not fewer words; the same words with a basis.

```
Sourced:
  text:       "a molecular rescue is not a clinical rescue"
  basis:      [MC_0012, EV_0047]          ids that must resolve inside this artifact
  derived_by: rarepipe.intervention_v1 | LLMRS_0008 | operator
  kind:       inference | definitional | editorial
```

Applied to `limitations`, `what_would_change_our_mind`, `expected_downstream_effect`,
`status_basis`, axis limitations and `ActionOutcome`. Validated by the same deterministic gate the
research import already uses: every id in `basis` must resolve, or the build fails. `kind:
definitional` is the escape hatch for genuinely editorial sentences ("prevention and reversal are
different goals") — allowed without a basis, but it has to declare itself, so unsourced statements
are visible rather than blended in.

The point is to make insight *cheaper*, not scarcer. Today a bare assertion feels unsafe to write,
so conclusions get under-written. With a basis field the incentive flips: write the conclusion, name
what it rests on, and let the validator surface the ones resting on nothing — which are exactly the
ones worth arguing about.

**Cost.** Schema change to both artifacts. Stage 06 (`v0.2.0`) and Stage 07 (`v0.1.0`) would need a
re-run and re-freeze at new schema versions. The claims, evidence and statuses come out identical;
the digests change. Decide whether to apply retroactively or from Stage 08 forward.

---

## 2. Full text for the 10 abstract-only documents

10 of 64 corpus documents are metadata and abstract only, including the priority-seed study
(PMID 20516114), which is not open access. This is the most likely reason the local residue search
found nothing: a residue appears in figures, tables and methods, rarely in an abstract.

Legitimate access only — publisher, institutional, author manuscript or organizer-provided. Ingest,
re-run the local residue search, and reopen `MC_0006` if anything matches. No paywall circumvention;
"potentially relevant evidence exists but is presently inaccessible" is a valid recorded state.

---

## 3. Three public knowledge tasks remain unread

`KT_0003` (truncating alleles), `KT_0006` (assay outputs distinguishing mutation classes),
`KT_0007` (downstream defect most linked to MVA) are `DETERMINISTICALLY_EXTRACTED` — retrieved and
pattern-extracted, never read by a reasoning process. The task-state model makes this visible; the
remedy is three research sessions, roughly an hour of reading each.

---

## 4. Bundle quality is only as good as the query wording

A bundle is carved by matching a task's own queries, so a narrowly-worded task gets a narrow bundle:
`KT_0001` received 5 documents while the corpus held 64. That is honest but blunt. Worth considering:
a second pass that offers documents from sibling tasks, or a relevance-based carve with the reason
recorded per document.

---

## 5. Retrieval is reproducible from the corpus, not from the query

Content hashes and the full query log are sealed, but Europe PMC will return different results next
month. The corpus *is* the record. If reproducibility from queries ever matters, it needs a pinned
snapshot service, which is a much larger commitment.

---

## 6. The deterministic extractor is noisy by construction

1,194 evidence records from 67 sources, sentence-pattern matched. Claim statuses use distinct
*sources*, not sentence counts, so the noise does not inflate confidence — but it does inflate the
artifact and makes per-claim evidence lists hard to read. Options: deduplicate near-identical
sentences, or cap per-claim lists with a "and N more from the same source" summary.

---

## 7. The rescue classifier is gene-specific

`classify_rescue` in `stages/intervention/stage.py` hardcodes `BUB1B|BubR1|BUBR1` to decide whether
a rescue record establishes a point or merely sits near it. Correct for this case, useless for the
next one. Generalise to take the case's gene symbols from the dossier.

---

## 8. AlphaGenome: only two scorers cached

`AVI_SCORE` and `AVI_SCORE_FEATURE_IMPORTANCE` over the BUB1B locus (180,459 variants). Dense track
scorers (`RNA_SEQ` at 371 tracks, `SPLICE_SITES`, `SPLICE_SITE_USAGE`) were not fetched because
combined responses exceed the API's 4 MB cap at 32 bp granularity. They would need separate
per-scorer runs. Worth it only if a specific question needs them — the questions that earned the
adapter are answered.

---

## 9. Outstanding external requests

* **Organizer phase question** — posted as discussion #24 on the challenge Space, asking for a
  private channel for the two loci. Part 2 (the exact loci) stays on the drive until they name one.
  No reply as of freezing Stage 07.
* **ClinVar submitter-level records** for the truncating allele — outstanding since Stage 04, where
  the solver's bundled snapshot and the current release disagreed about which condition its
  pathogenic assertion was made for.
* **Cytogenetic data for this child**, which would connect the case directly to the disease-level
  aneuploidy bridge by observation rather than by inference.

---

## 10. Obligations with dates attached

* The GitHub repository is private and **must be made public after the hackathon closes** (organizer
  rule; submissions are judged from it).
* Genomic material must be **deleted within 30 days of the hackathon close**, with notification to
  `MVAHackathon2026@synapse.org`. The hackathon submission period runs to 24 October 2026.
* The AlphaGenome API key was pasted into a chat transcript on 2026-09-19 and should be **rotated**
  once the hackathon work is done. It lives in `~/.config/rarepipe/alphagenome.key` (mode 600,
  outside the repo); a test fails the build if key-shaped material ever reaches a tracked file.
