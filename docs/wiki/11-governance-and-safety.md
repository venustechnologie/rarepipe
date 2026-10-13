# Governance and safety

This is the page a reviewer or an ethics board would read. It consolidates every rule the project
holds itself to, says where each one is enforced, and — in the final section — separates the ones
that are **tested in code** from the ones that are **policy backed by nothing but intent.**

That separation is the point of the page. A governance document that presents aspirations and
mechanisms in the same voice is worse than none, because it teaches the reader to trust the wrong
things.

---

## 1. The privacy boundary

**The rule.** Case-specific genomic identity never leaves local compute. No genomic rows, sequences,
sample identifiers or case-specific raw data go to any LLM API, annotation API, analytics endpoint,
telemetry service, error reporter or external log. Exact patient variants, variant pairs and HPO
combinations are never transmitted externally by default.

**Where it is enforced.**
[`src/rarepipe/stages/adjudicate/disclosure.py`](../../src/rarepipe/stages/adjudicate/disclosure.py) —
one module, imported by every stage and tool that can send anything. `check_query()` refuses nine
pattern classes: genomic coordinate, HGVS coding/genomic, HGVS protein, protein-change shorthand,
bare residue position, dbSNP identifier, ClinVar variation id, HPO identifier, bare allele change.

**It fails closed, and the ordering matters.** The private-residue cross-check runs **first**, on
every residue-shaped token, *before* any pattern is applied — so a token that trips no pattern at all
is still compared against the case's own residue. That ordering was wrong once (the pattern scan ran
first), and fixing it exposed a second defect: bare residue positions were not gated at all, because
a bare position matched no pattern and the cross-check therefore had nothing to compare. Both fixes
are recorded in comments in the module.

**The guard is deliberately over-broad.** The bare-residue pattern also matches ordinary strings such
as a `C57` mouse strain, so legitimate gene-level queries are sometimes refused. That was a conscious
choice. A false refusal is cheaper than a false release.

**Residue release, when it is legitimate.** Published residues sometimes have to appear in a
literature query. This is **not** solved with a syntax whitelist, because a whitelist that permits
"things shaped like a residue" permits the private one. A residue token leaves only under a
`PublicResidueProvenance`, and all of the following must hold:

- the token is **named explicitly** — per token, not per query;
- it is **found verbatim in the stored text** of the attesting document — per source;
- the attesting document lies **inside the committed snapshot tree** under `data/literature`;
- **nothing the caller supplies as metadata is consulted** — only the stored text is read;
- identity-grade patterns (coordinate, rsID, ClinVar id, HPO code) **can never be unlocked this
  way.**

And the rule that makes it coherent: **a residue derived from the private case is refused however
well attested it is elsewhere.** The private boundary is not a question of whether a string is public
somewhere.

**Redaction.** [`src/rarepipe/core/redaction.py`](../../src/rarepipe/core/redaction.py) — a field
declared `restricted()` lives only in the private artifact; `clear_restricted()` walks the model
recursively and clears every tagged field. Schema-driven rather than list-driven, so adding a
sensitive field means tagging it and there is no second list to forget. Every report renderer asserts
`visibility == "sanitized"` before writing a line; the assertion is present in all seven.

**Why gradings are restricted even though they contain no identifier.** The published documents state
that the child's missense allele is in the protein kinase domain, because a domain name is public
biology. They never state the position. The directness grades comparing a published residue to the
child's are computed locally and held only in restricted fields, because **a nearby published variant
plus a proximity grade would localise the child's residue.** The grade is identifying without
containing an identifier, so it is treated as identifying — and it is withheld entirely unless the
allele is numbered on the canonical transcript.

---

## 2. Search governance and therapeutic-output governance are different things

This is the project's sharpest governance distinction, and it was arrived at by finding the original
version self-defeating.

**The problem.** An early policy blocked therapy-related vocabulary from outbound searches. But
mechanisms in cell biology are *established by perturbing systems* — with inhibitors, knockdowns,
CRISPR, compound screens. The paper this case rests on identifies its own mechanism using an HSP90
inhibitor, cycloheximide and a proteasome inhibitor. So the policy blocked search from looking for
exactly the experiments that establish the mechanism.

The inconsistency was visible inside a single module: `knockdown` and `sirna` scored **positively**
in the relevance triage while search refused to look for them.

**The resolution — two independent governance layers:**

| Layer | What it governs | Rule |
|---|---|---|
| **SEARCH governance** | What may be asked of the outside world | Perturbation **vocabulary** is searchable. Therapeutic **intent** is refused. |
| **THERAPEUTIC-OUTPUT governance** | What the system may say | No therapy, dose, regimen or recommendation may be produced, in any document. |

The line, stated the way the code comment states it:

> An agent may search for an experiment that inhibited, depleted or degraded something. What it may
> not do is turn **"inhibiting X raised Y in a cell"** into **"administer an inhibitor of X."**

**Searchable** (named explicitly so the split is testable rather than accidental): `inhibitor`,
`inhibition`, `knockdown`, `knockout`, `depletion`, `degrader`, `degradation`, `proteasome
inhibition`, `kinase inhibition`, `sirna`, `shrna`, `degron`, `overexpression`, `rescue`, `crispr`,
`small molecule`, `compound screen`, `modifier screen`, `proteostasis`, `genetic screen`.

The last six were opened deliberately after a search round missed genetic-modifier and proteostasis
screens entirely — a screen is how the unbiased version of *"what changes this protein's abundance"*
gets asked, and all of those words name a laboratory method rather than an intention to treat anyone.

**Refused:** `drug`, `treatment`, `treat`, `therapy`, `therapeutic`, `repurpos*`, `gene therapy`,
`mRNA therapy`, `dosing`, `dose`, `clinical trial`, `patients should/receive/benefit`, `efficacy`,
`indication`. Note that `gene therapy` is blocked **twice over**, since `therapy` alone matches
inside it.

**One controlled lift.** `check_intervention_query` in
[`stages/discovery/lanes.py`](../../src/rarepipe/stages/discovery/lanes.py) is the single place the
therapy filter is lifted — because that stage's entire job is to search the approved-medicine record
— and it lifts **only** that filter. The case-identity guard still applies in full.

### The recommendation and dose guards, and why they are negation-aware

Therapeutic-output governance is enforced over the **generated documents**, in
[`tools/control/check_skills.py`](../../tools/control/check_skills.py):

```
DOSE      = \b\d+(\.\d+)?\s?(mg|µg|ug|mcg|mmol|IU)(/kg)?\b
RECOMMEND = \bwe recommend\b | \bshould be (given|administered)\b | \bshould take\b
```

Every `MVA_*.md` document under `docs/control/` is scanned. And the scan is **negation-aware**, which
sounds like a nicety and is not:

**These documents state the prohibition explicitly.** A sentence of the form
*"it does not say that this compound should be given to this child"*
**contains the forbidden phrase while asserting its opposite.** A naive pattern fires on the
project's own disclaimer — and a guard that fires on its own
disclaimer gets worked around, which is strictly worse than no guard, because now the discipline is
gone *and* everyone believes it is present.

So the check walks back to the start of the sentence and skips the match if a negation precedes it.

**The guard publishes its own limitation**, in its test docstring: it will not catch a recommendation
in a sentence that happens to carry an unrelated negation beforehand. The window is one sentence, so
an evasion has to be deliberate. In its own words — **"the guard is a floor, not a proof."**

One further limit, found by running this guard over this wiki: the sentence window is bounded by
newlines as well as by sentence punctuation, so **a line wrap falling between a negation and the
phrase it negates splits the window** and the guard fires on a correctly-negated sentence. The
example above is reflowed for exactly that reason. The fix is to move the text, never to widen the
guard.

A paired test exists specifically to make sure negation-awareness did not quietly turn the guard off:
`test_the_recommendation_guard_still_catches_an_actual_recommendation`. That pairing is the pattern to
copy when adding any guard with an exemption.

### Representational impossibility, where it was achievable

In several places the prohibition is not a filter but a type:

| Mechanism | Where |
|---|---|
| `treatment_recommendation: Literal[False]` | Stage 09 — a recommendation **cannot be represented** |
| `clinical_actionability: Literal["NOT_ASSESSED"]` | Stage 09 — no other value exists |
| The no-treatment-recommendation statement is **byte-fixed** | Realization and synthesis reports — a model validator forbids rewording it |
| An advisory-phrase scan over all free text | Synthesis compiler — raises if the report *advises* rather than reports |
| Selected actions containing `ADMINIST`, `PRESCRIB` or `TREAT` are rejected | Stage 10 decision review |
| Patient-directed actions raise `PatientActionForbiddenError` | Network adapter |
| Patient and laboratory-execution actions are **unrepresentable** in the action space | Network policy — raises `UnrepresentableActionError` |
| `"a cellular result does not establish patient benefit or treatment readiness"` | Appended **unconditionally** to every decision record |

The advisory scan has negative-control tests proving it does **not** fire on ordinary scientific
language such as *"dose-dependent"* or *"the authors recommend caution"* — because a guard that fires
on legitimate prose gets disabled.

---

## 3. Safety in experiment design

Safety here is a **filter, not a weight.** It is never traded against benefit.

**Ranking is lexicographic with safety as the first key.** The objective module explicitly refuses
the weighted form `J(u) = aD + bR + cC + dU`, because none of those four weights is grounded. A
weighted objective would let a large enough benefit outvote a safety violation, and the honest
response to ungrounded weights is to not have them.

**An unsafe path returns its verdict first and is never chosen.** In the realization layer the status
ordering puts unsafe last, so it cannot be selected among candidates. In the reachability engine, a
hard-safety violation is an **early abort** that returns the offending path, so the refusal is
visible rather than silent.

**Unsafe compositions are kept in the report, not filtered out**, so you can see what was rejected
and why.

**Safety variables must be measured, not modelled.** This is the most consequential rule in the
section. In the live encoding the three safety variables — cell death, viability, division rate — are
declared **exogenous**: nothing in the biological model moves them. That is deliberate, because
intervention-induced population effects belong to a different layer. The consequence is that the
compiler **insists those variables be measured** and records the point as a known omission rather
than claiming safety.

> **"Safe under the model" says almost nothing.** A model's prediction that a safety variable will
> not move cannot certify safety. The observability layer enforces this.

**Fewer errors in a dying population is selective loss, not rescue.** If an intervention
preferentially kills aneuploid cells, every fidelity readout improves while nothing has been
corrected in any cell. So:

- Viability, cell death and division rate are **required** readouts with their denominators. A result
  missing one is not weaker — it is inadmissible.
- A reading counts as a clean discriminator only if **no uncontrolled process could fake it.** The
  code names the confounders and credits only an experiment that measures them too.
- A population-scale improvement must state, in the same breath, that it **corrected no cell.**
- A mechanism that moves a population must declare what makes the movement selective. **"Selection"
  is not an answer** — the field has a minimum length for exactly that reason.
- A confounding process must name at least one observable that would exclude it.
- The cell-level target is a **conjunction of four** conditions, so "fewer errors" alone cannot
  satisfy it.
- No benefit verdict overrides harm. In the bench matrix, a `population_harmed` outcome closes the
  component on safety grounds and licenses nothing about efficacy.

**Scale is never conflated.** Organism-level risk is not a cellular phenotype, and the two live in
separate branches with separate gates. A result in an immortalised or cancer line is not a result in
the lineages that carry this child's burden — that transfer is a separately named question with its
own unknowns.

**Experiment selection uses deterministic elimination, not expected information gain.** The criterion
is literally `deterministic_elimination`. Expected information gain is deliberately not computed,
because it would require inventing a probability.

---

## 4. Human-in-the-loop, and the gate that stops

**Nothing irreversible or outward-facing happens without a named human.**

| Decision | Requirement |
|---|---|
| Approving a target or safety definition | A **human** holding `SCIENTIFIC_LEAD` or `TREATING_CLINICIAN`. `ActorType.HUMAN` is checked explicitly |
| Freezing a plan | `APPROVE_FOR_FREEZE` from scientific lead, assay scientist **and** statistician — each a human, each naming the current review digest |
| A scientific review decision | A human confirmation from the reviewer, referencing that assessment, in the role the question declares as required |
| Authorizing outreach | A named human issuer's own confirmation, with a validity window and revocation |
| Asserting independence between evidence families | A named human. **Two replies from two institutions are not independent by default** |
| Submitting anything externally | A person. **No stage uploads anything**, and the artifacts say so deliberately |

**Agents get read and draft permissions only.** They can never sign a review or perform a freeze. Six
permissions are mapped over nine roles, and `external_send` is **disabled for everyone** in this
deployment.

**External sending does not exist rather than being switched off.** The dispatch path checks
authorization and then returns a **stored unsent draft**. The transport layer's test implementation
records what would be sent and delivers nothing. The prospective layer's send function is a policy
check followed by `NotImplementedError` — there is no transport to disable.

### The approval gate stops rather than proceeding

`approval_gate()` in the disclosure module **has no success path.** It always raises.

There is no configuration flag, no environment variable and no administrative override that enables
exact-variant external querying, because the function that would authorise it has no branch that
returns. If the project ever needs that capability, someone has to write the gate — deliberately,
visibly, in a reviewable diff.

**A refusal is a bug to fix or a decision to escalate, never something to work around.** If
`check_query` refuses a query believed legitimate, the question is whether the guard is wrong (fix
it, with a test) or whether the query really does carry case identity (change the query). Loosening a
pattern to get past it is the one move not available.

---

## 5. Governance in the case data itself

Governance is not only in the code. The route map carries it as data:

- A terminal state `GOVERNANCE_BLOCKED` exists in the closed vocabulary, so "not permitted" is a
  distinct, first-class outcome rather than a missing branch. One branch in the live map is blocked
  this way — **no patient material is available and none may be acquired.** It is not a biology
  problem and no experiment resolves it.
- A `requires` value of `GOVERNANCE_ABSENT` sorts unknowns that are blocked by permission rather than
  by physics.
- The ultimate organism-level target is recorded as reachable by no route today, **bounded by
  governance as well as biology**: no intervention in this child is authorised, there is no
  recontact, and much of the phenotype is developmental and already established.
- The bench-handoff record states the private boundary explicitly — which campaign's substitution
  stays local, and that the published residue cited in one question and the child's allele are in
  different protein regions, so neither document discloses the other.

---

## 6. Obligations with dates attached

For the one live case:

| Obligation | Status |
|---|---|
| No redistribution of supplied genomic material | In force |
| Delete genomic material within 30 days of the hackathon close, notifying `MVAHackathon2026@synapse.org` | Submission period runs to 24 October 2026 |
| **No recontact** of the child, the family, or the patient-organisation contacts | In force, absolute |
| Repository becomes public after the hackathon | Which is why `.gitignore` is a safety control |
| An API key pasted into a transcript must be rotated | Outstanding; a test fails the build if key-shaped material reaches a tracked file |

`.gitignore` excludes `*.private.json`, every genomic file extension, prediction CSVs, `/secure/`,
`/work/`, `/out/` and the whole `research/` directory. The accepted consequence is that **two stages
are not reproducible from a public clone.**

---

## 7. What is tested, and what is only policy

The section that determines whether the rest of this page is credible.

### Enforced in code and covered by tests

| Rule | How |
|---|---|
| Inputs are never modified | Whole input tree hashed before and after every fixture run |
| No network in case stages | Sockets disabled, OS sandbox, htslib reference paths pinned, and a test asserting no stage imports the fetching module |
| Compilation never touches the network | `test_compilation_never_touches_the_network` |
| Case identity cannot leave | `check_query`, fails closed, private cross-check first; tested with deliberately fabricated identifiers |
| No committed query was case-specific | `test_no_query_in_the_snapshot_was_case_specific` |
| No committed query was a gene-name lookup | `test_gate1_queries_are_functional_not_gene_name_lookups` |
| Exact-variant external querying | **Structurally impossible** — no success path exists |
| Residue release requires public attestation | Per token, per source, against committed text, with roots validated |
| Redaction is complete | Schema-driven and recursive, with report-side assertions in all seven renderers |
| No case-level genomic content in generated reports | Two dedicated tests, over realization and gap reports |
| Descriptive stages produce no interpretation | A test greps the report for *pathogenic*, *benign*, *causal*, *candidate gene*, *diagnosis*, *compound het*, *drug* |
| No recommendation or dose in generated documents | The negation-aware guard, plus a paired test proving it still catches a real one |
| No advisory phrasing in synthesis reports | Scan with negative controls |
| A recommendation cannot be represented | `Literal[False]` / `Literal["NOT_ASSESSED"]` typing |
| Patient and lab-execution actions cannot be represented | Raise at construction |
| Agents cannot review, freeze or approve | Role policy, with `ActorType.HUMAN` checks |
| No disease name, gene panel or seed gene reaches solver job files | A test greps the generated job files |
| Synthetic material cannot be mistaken for authentic | Origin inheritance, with synthetic dominating any mix |
| Operational refusals cannot become evidence | Validator-enforced |
| Generated documents cannot be hand-edited | Six CI staleness checks |
| Determinism across processes | Re-run under different hash seeds; digests must match |
| No hand-written digests, no `hash()` seeds, no piped pytest | Static source scan |

### Policy, backed by intent rather than by a mechanism

Stated plainly because a reader will find out anyway, and finding out independently is worse.

| Rule | Why it is not enforced |
|---|---|
| **Deletion of controlled material** | Retention classes are *recorded in the artifact*; **nothing in the code deletes anything.** A human or an operational step must act |
| **Retention classes on derived artifacts** | Asserted, inherited from case policy |
| **Non-recontact** | No code path exists to contact anyone, but this is a commitment, not a mechanism |
| **No redistribution** | A commitment |
| **API key rotation** | Outstanding action; only the *leak into tracked files* is tested |
| **Running controlled data under the offline sandbox** | An operator discipline. The command is documented and the stages are network-free, but nothing forces the sandbox |
| **"Sanitized" is not "anonymous"** | Stated by the sanitizer itself. Internal aliases remain and the artifact still describes one real individual's case structure |

### The limits the guards publish about themselves

The project's scanners state their own blind spots, which is itself a governance property:

- The static invariant scanner prints a `not_checked` list including *"whether the science is right"*
  and *"anything requiring the code to run"*. It also defaults to one package, so other stage
  packages are **not covered** by it.
- The recommendation guard is **"a floor, not a proof."**
- The citation audit **can disqualify an attribution and cannot confirm one**, and reports three of
  its nine checks as `not_machine_checkable`.
- The branch-reachability check runs advisory in CI (`|| true`) and cannot see whether a branch is
  computed at all.
- The endpoint-discrimination tool warns that a minimal endpoint subset is a costing question and
  **never a recommendation to measure less.**

---

## Where to go next

- **The guard itself** —
  [`stages/adjudicate/disclosure.py`](../../src/rarepipe/stages/adjudicate/disclosure.py), with
  [`tests/test_disclosure.py`](../../tests/test_disclosure.py).
- **The data-holder view of the same rules** —
  [`09-for-data-collaborators.md`](./09-for-data-collaborators.md), including the
  enforced-versus-asserted table from a collaborator's angle.
- **The epistemic rules these sit on top of** —
  [`05-evidence-discipline.md`](./05-evidence-discipline.md).
- **Safety as it appears in the three live experiments** —
  [`docs/control/MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md), whose
  closing section states what none of the three licenses.
- **What must never be claimed externally** —
  [`10-for-commercial-and-strategy.md`](./10-for-commercial-and-strategy.md) §6.
- **Outstanding obligations** — [`docs/POTENTIAL_IMPROVEMENTS.md`](../POTENTIAL_IMPROVEMENTS.md) §10.

---

> A refusal is a bug to fix or a decision to escalate, never something to work around. "Safe under
> the model" says almost nothing. A guard that fires on its own disclaimer gets worked around.
