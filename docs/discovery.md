# Stage 08 — approved intervention and experience discovery

Asks whether anything already approved has credible evidence of producing the change Stage 07
specified — and what happened when people tried. Ranks nothing, proposes no dose, recommends no
treatment.

```
rarepipe research create-task --intervention ...        # lane tasks; therapy terms permitted
rarepipe research retrieve --task KT_00NN --intervention
   [ a person reads the bundle with an assistant ]
rarepipe discovery import-experiences --analysis <yaml> --research <workspace>
rarepipe discovery build --intervention-map-run <stage 07 run> --research <workspace> --output <work>/discovery
```

## The rule everything else follows from

```
"we found no evidence it works"   ≠   "someone tried it and it did not work"
```

They live in different fields. A search that found nothing produces **no experience at all** — it
becomes an unresolved evidence need and a question for a future node. An `InterventionExperience`
exists only when a source says something was tried.

Three more distinctions the schema enforces:

* **Observed harm is not inferred harm.** An intervention a clinician *declined to give* has no
  measured outcome; it is recorded `unknown`, never `worsened`, and the mechanistic conflict is
  labelled as the inference it is.
* **An outcome needs an endpoint.** `improved` / `no_effect` / `worsened` are refused on import
  without at least one measured endpoint — "no effect" without saying what was measured is not
  reusable by anyone.
* **Approval is verified, not asserted.** RxNorm normalises the ingredient; the openFDA NDC
  directory establishes that finished human products are marketed. A class name is not an active
  ingredient and fails verification, which is correct. Jurisdiction is preserved: "not in the US
  directory" is not evidence of non-approval elsewhere, and the record says so.

## The four lanes

```
A  direct BUBR1 restoration          interventions reported to raise functional BUBR1
B  rescue in deficient biology       improvement of a relevant endpoint in BUB1B-deficient models
C  mechanistic leads                 DISCOVERY_ONLY until experiment bridges the gap
D  failure and harm                  observed failures, and anything pushing the forbidden direction
```

Lane D is a discovery lane, not a safety afterthought. On this case it produced the only substantive
results.

## The guard that changes here

Every earlier stage refused queries that looked like a search for a treatment. Stage 08 is where
that search is the point, so the therapy filter is lifted — and only that filter. No coordinate,
allele, HGVS, rsID or phenotype combination leaves the machine at any stage, and a test asserts it.

## Outcomes

`APPROVED_DRUG_CANDIDATES_FOUND` · `ONLY_LOW_CONFIDENCE_CANDIDATES` ·
`NO_DEFENSIBLE_APPROVED_DRUG_CANDIDATE_FOUND` — the third is a valid result, not a failure of the
stage. It makes the clinical-node questions more interesting, not less.
