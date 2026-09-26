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
