# Stage 09 — Track 2 research-hypothesis adjudication

Stage 08 asked whether an approved medication has *already been shown* to produce the change the
mechanism needs. The answer was no. Stage 09 asks a strictly weaker question:

> is there an approved medication for which the evidence justifies **testing** the hypothesis?

That is not "the drug works". `MedicationCandidate` (Stage 08) means demonstrated match;
`ResearchRepurposingHypothesis` (here) means justified experiment. Nothing is promoted between them
silently, and the gate is what keeps them apart.

```
rarepipe track2 import-hypotheses --analysis <yaml> --research <workspace>
rarepipe track2 adjudicate --discovery-run <stage 08 run> --research <workspace> --output <work>/track2
```

## Arrow by arrow

A hypothesis is a chain. Each arrow is either **evidenced** — cited to a document that was actually
retrieved, quoting text verbatim in it — or explicitly an **inference**. There is no third option,
and an arrow claiming evidence it cannot produce fails the import rather than the reader's
attention.

## The promotion gate (all thirteen must pass)

specific active ingredient, not a class · approval verified in ≥1 jurisdiction · explicit mechanism
chain · direction matches the spec · ≥1 primary source for the medication's own molecular effect ·
every arrow evidenced or marked inference · contradictions explained · falsifiable validation
experiment defined · exact-allele dependency stated · limitations stated · untested status explicit ·
no dose or regimen · no efficacy claim and no treatment recommendation.

Evidence grades: `DIRECT` (tested in BUB1B-deficient or MVA biology) · `STRONG_INDIRECT` (drug →
required BUBR1 change shown, untested in MVA) · `MECHANISTIC_INDIRECT` (drug → target → evidenced
chain → required state). Never a probability of working.

## Two objects worth reusing

* **`SearchOutcome`** — what a search established *and*, in its own field, what it does not mean.
  `NO_EVIDENCE_FOUND` never renders as "shown not to work".
* **`SubmissionClaim`** — every substantive sentence the report may use, tied to its basis. The
  report generator consumes only validated claims, so the polished version cannot become more
  confident than the science underneath it.

## The sealed baseline

Written whichever branch the stage takes: run ids, semantic digests and the source commit, with
`created_before_network_search: true`. A later rerun that includes clinical-node evidence can be
compared against it to measure exactly what the network added — without spending a submission to
establish the "before" state.

## Outcomes

`TRACK2_RESEARCH_HYPOTHESIS_READY` or `TRACK2_SUBMISSION_BLOCKED_NO_DEFENSIBLE_HYPOTHESIS`. The
second is a real result: it marks where the public medical literature ends. The stage uploads
nothing either way.

## Packaging for a reviewer

`rarepipe export track2-package --track2-run <run> --submitter <name> --output-zip <zip>
[--mechanism-run <stage06 run>] [--extra verification/x.txt=file]` writes one folder with
`upload/`, `records/` and `verification/`, and a root `MANIFEST.sha256` over the paths as they
appear in the archive. Before returning, the command unpacks the package and runs the documented
`shasum -a 256 -c MANIFEST.sha256`; if that fails, no package is produced. The run's own
`SHA256SUMS` is shipped as `verification/run_SHA256SUMS.txt` for cross-checking only. It names
private files that are never exported, so `shasum -c` against it cannot pass inside a package.

## Edited pitch wording

A person may rewrite the generated pitch. `rarepipe track2 check-pitch --pitch <md> --claim-map
<yaml> --run <sealed run>... --output <report.md>` checks it against the sealed artifacts. The claim
map is written by a reviewer and says, for each sentence, which artifact ids support it. Every
sentence must be covered, every id must exist in the runs, and a sentence marked `not_in_artifact`
fails. Forbidden phrases (dosing, recommendations) fail; absolute wording is flagged. The check never
edits the pitch. `export track2-package --pitch --pitch-check` uploads an edited pitch only with a
passing report, and keeps the generated one under `records/`.

## Superseding a hypothesis record

Imported sessions are never edited. To change wording, import a new session whose `session:` block
has `supersedes: LLMRS_000N`. The earlier record stays on disk and is no longer loaded.
