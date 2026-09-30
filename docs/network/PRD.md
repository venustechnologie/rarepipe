# Rarepipe research-network MVP — implementation PRD

Version: 0.1, 30 September 2026. Product owner: Xavier Ramos. Status: proposed implementation specification for developer review. This document defines work to build; it does not certify that the new features exist or approve the scientific plan.

## 1. Decisions incorporated

- Build an actual MVP that obtains and uses institutional contributions, extending the existing prospective experiment-and-decision system.
- The first live-pilot milestone requires an authentic institutional reply. Synthetic replies exercise the software but cannot satisfy that milestone.
- The Hugging Face deliverables are a detailed report, a GitHub link, and a three-minute spoken pitch. A recorded software demonstration is not required. Internal executable acceptance tests are still required.
- The proposal remains an investigation of nicotinic acid for the BUB1B-associated MVA mechanism. Institutional coordination and simulation are tools for advancing that investigation.
- The separate decentralized-data application may pursue other institutional datasets and disease areas. Its partnership workflow and claims must remain separate from the MVA scientific campaign.
- No new delivery date was supplied. Use milestone dependencies, not an invented deadline.
- No live correspondence, purchase, experiment, or patient intervention is authorized by this PRD. Implement standing-authorized automation so a future deployment does not require repeated approval of every covered action.

## 2. Product statement

Rarepipe turns a clinician's unanswered research question into a managed sequence of evidence-acquisition tasks. It identifies relevant institutions, prepares bounded requests, handles permitted replies, tracks what changed, and chooses the next useful research action. The institution may return an existing finding, a methods interpretation, a local-analysis result, a feasibility assessment, or a referral. It need not adopt Rarepipe or transfer patient records to participate.

The simulator represents both scientific possibilities and institutional events. A trainable policy learns action selection in that bounded environment. The product distinguishes a changed scientific assessment, a changed capability record, a learned policy update, and an engineering correction.

The family-facing value is continuity and relief from coordination. Every open consequential task has an owner and a next trigger. A rejected route or negative result leads to an explicit reassessment or pause, not an unrecorded disappearance.

## 3. Current state and integration prerequisites

The supplied developer reports identify the current plan as `PP_MVA_001_RH_001@0002-455419f1`, rules 1.1.0, DRAFT, with 112 gaps and a candidate baseline. Preserve that status unless the existing native workflow changes it legitimately. A new registry entry, institutional reply, or policy-training result cannot silently close scientific gaps.

The existing Stage 10 implementation reportedly supplies plans, versioning, a decision engine, synthetic scenarios, ingestion/review/replay, and static views. Its source checkout was not available to the author of this PRD. Task T01 must inspect the actual interfaces before implementing adapters. Proposed names in this document are logical contracts, not asserted native fields or CLI commands.

B16's reduced-division review behavior is part of the baseline to preserve. Do not reimplement or infer the meaning of B08/B09/B16 from their names; call the existing rules through an adapter and test against repository fixtures.

The scientific status remains: this child's residual BubR1 function is unresolved. Nicotinic acid, NAM, NR, and NMN are distinct interventions. Public literature and institutional expertise do not establish genotype-specific efficacy.

## 4. Scope

### P0 — required MVP

1. One MVA research campaign with a compound-specific question graph.
2. A sourced capability registry seeded with the nine leads in section 7.
3. A request/task workflow with durable scheduling, bounded follow-up, and a test transport.
4. A configured live email path or an authenticated manual-import path supporting one actual institutional exchange.
5. Structured contribution intake with provenance, applicability, permissions, missing fields, and human interpretation review.
6. A simulator of scientific responses and institutional processes.
7. A real trainable action policy selecting question, node, and action; reproducible training and evaluation against fixed baselines.
8. A doctor/research-operator view driven by actual stored state.
9. An adapter into the current Stage 10 proposal/review workflow.
10. A report/export explaining what was built, what was simulated, what was received, and what remains proposed.

### P1 — after the first pilot

Continuous public-source discovery, broader institutional connectors, case-to-case permitted evidence reuse, calibration from sufficient real operational history, and policy promotion into bounded live coordination.

### Outside this MVP

Patient dosing or treatment selection; autonomous clinical interventions; claiming a biological digital twin; arbitrary execution of code inside hospitals; a global EHR; federated model training over private records; automated commissioning of laboratory work without authorization; replacing existing scientific review; claiming broad patient applicability from one case.

The API must allow future contribution methods without requiring those future methods now. Ordinary email is a valid first transport.

## 5. Users and accountable roles

| Role | Responsibilities | Work the software carries |
|---|---|---|
| Clinician / clinical lead | Clinical priorities and any patient-care decisions; identity remains unset until actually appointed | Research status, concise interpretation packets, tracking |
| Scientific adjudicator | Accept/reject scientific interpretations and proposed next experiments | Source context, alternatives, missing inputs and conflicts |
| Research operator | Campaign scope, recipient verification, authorized outreach, partner follow-up | Drafting, scheduling, deduplication, response structuring |
| Institution contributor | Choose a permitted contribution and its reuse scope | Small questions, flexible response methods, attribution |
| Developer / service operator | Runtime, adapters, monitoring, policy evaluation and rollback | Observable failures, reproducibility and configuration |
| Family / patient | Actual preferences and participation choices through the applicable process | Plain-language continuity; no requirement to coordinate labs |

Persona files influence preparation and product behavior. They cannot occupy a human review role or assert a real family preference. Role appointments must identify a real responsible party or remain unassigned. An unassigned owner blocks live execution of the action that needs that owner; it does not block unrelated preparation.

## 6. Question graph

Create these campaign-local question IDs. T01 maps them to existing hypotheses, experiments and validator gaps where justified; never guess native IDs or create apparent closure through a broad many-to-one mapping.

| ID | Question | What an answer could change |
|---|---|---|
| Q01 | In an appropriately characterized model, what function remains when altered BubR1 abundance is normalized? | Whether an abundance-restoration premise remains plausible; which functional endpoints remain necessary |
| Q02 | Does nicotinic acid increase intracellular NAD in a relevant cell compartment under interpretable conditions? | Whether the first drug-to-cell connection is supported for that model |
| Q03 | Does the proposed NAD/SIRT2 connection change BubR1 stability or a relevant activity? | Which mechanistic connection is supported or challenged |
| Q04 | Do required functional outcomes improve, accounting for division, cell loss, and measurement limitations? | Whether independent confirmation or translational review is justified |
| Q05 | Who currently has a suitable, permitted model, existing finding, assay, or analysis capability? | Where and how to obtain the next contribution |
| Q06 | Which methods and analysis choices can make a proposed measurement interpretable? | Which scientific design decisions can be prepared for review |

Each question must store its decision consequence, prerequisites, acceptable evidence categories, known limits, proposed owner, and required review. Unknown fields stay explicit. Do not populate scientific effect thresholds, equivalence margins, sample sizes, or exposure specifications from generic defaults.

The graph must support parallel tasks when independent. Several positive replies cannot substitute for a missing decisive endpoint. If more compounds are later introduced, each gets its own intervention identity and dependency graph. A compound combination is a separate hypothesis.

## 7. Seed capability registry

Import the longer discovery brief as the human-readable source of proposed questions. Enter the following leads with public evidence only. Default `resource_available`, `analysis_permission`, `capacity`, `cost`, and `turnaround` to unknown.

| Node | Public relevance | Initial question route | Official source |
|---|---|---|---|
| Hubrecht Institute, Kops group, Netherlands | Current MVA and chromosome-segregation research | Q01/Q04/Q06: existing restored-abundance findings, endpoint limits, model/method referral | https://www.hubrecht.eu/research-groups/kops-group/ |
| University of Helsinki, ASWLab, Finland | Tissue/systemic metabolism; human nicotinic-acid research | Q02/Q06: blood-versus-cell measurement interpretation and existing methods | https://www.helsinki.fi/en/researchgroups/mitochondrial-medicine/research |
| University of Oulu, Pirinen Lab, Finland | NAD metabolism and the same human niacin study | Q02/Q06: nicotinic-acid-specific response conditions and feasible analyses | https://www.oulu.fi/en/research-groups/mitochondria-and-nutrient-signaling |
| Harvard Medical School, Sinclair Lab, US | Original SIRT2/BubR1 work; current NAD/sirtuin expertise | Q03/Q04: existing mechanistic findings and distinction between abundance and function | https://agingresearch.hms.harvard.edu/faculty/sinclair/ |
| BBMRI-ERIC, Europe | Collection discovery and negotiation infrastructure | Q05: identify a holder and a permitted feasibility/local-analysis route | https://www.bbmri-eric.eu/bbmri-sample-and-data-portal/ |
| Euro-BioImaging, Europe | Image analysis, tracking and workflow services | Q04/Q06: endpoint feasibility, image QC and execution arrangement | https://www.eurobioimaging.eu/image-data-services/image-analysis-services/ |
| MPI Molecular Physiology, Musacchio group, Germany | Biochemical reconstitution and cell-division methods | Q01/Q03/Q06: orthogonal assay interpretation when cellular results are ambiguous | https://www.mpi-dortmund.mpg.de/research-groups/musacchio |
| CHU de Québec–Université Laval, Elowe lab, Canada | Mitotic signaling and domain/silencing research | Q01/Q04/Q06: activation versus silencing/alignment limitations | https://www.projets-recherche.ulaval.ca/projet?id=479868 |
| Institute of Cancer Research, London, UK | Historical BUB1B/MVA research involvement | Q05: current custodial or scientific referral, not an assumed resource | https://www.icr.ac.uk/about-us/icr-news/detail/children-with-rare-disorder-lead-scientists-to-cancer-related-gene |

These are candidate matches, not active partners. The registry must distinguish an evidence-producing lab, an analysis service, a discovery network, and a historical custodial lead. Helsinki and Oulu reports based on the same study share an evidence-family ID.

Each match explains: which question the node could answer, supporting source, what is inferred, and what confirmation remains. Do not rank by a fabricated response probability. A source date is not an availability confirmation date.

### Separate partnership lead: Centre Léon Bérard

The user-supplied screenshot lists an oncology data holder seeking a partner for Recoding Medicine. The listed material is multidisciplinary virtual tumour board meeting notes, 2017–2026. It is marked raw, not longitudinal, with no annotation or linkage listed; consent basis is unclear, access model undecided, departure from the institution unsure, and ethics approval not started. Preserve these as listing-reported states, not independently verified institutional facts or established access rights.

Create a separate `PARTNERSHIP_ONCOLOGY` campaign. Its initial task asks whether they are still considering an AI partner. A subsequent scope discussion may concern extracting research questions, reasoning and evidence needs from permitted meeting-note material. The listing alone does not establish clinical outcomes, treatment-effect labels, a longitudinal cohort, or a ready RL environment.

The screenshot gives `info@schmitt-t.com` as its contact. Store it as the directory-listed contact; do not label it a verified institutional-domain address or invent the contact's name/role. Verify the responsible party before sharing nonpublic material. A partnership-availability reply can advance this campaign but supplies no MVA scientific evidence.

## 8. Records and invariants

Use repository conventions for identifiers and serialization. Generate identifiers and content digests through code. Never write a plausible digest manually. Store the digest coverage definition with each digest; exclude the digest's own value from its input.

| Record | Required conceptual fields |
|---|---|
| Campaign | ID, purpose, case-local reference if any, scope, mode, owner, exclusions, status, budget/cadence configuration |
| Question | ID, exact decision, dependencies, evidence criteria, required reviewer, state, links to native artifacts |
| Node | ID, institution/group, node type, public source/date, capabilities with evidence status, verified contact route, distinct resource/permission/capacity states |
| Match | Question/node IDs, reasons, sources, gaps, eligibility result, ranking basis and version |
| Request | ID, question/node, exact approved content, sender, recipient, disclosure scope, permissions reference, parent request, state, next trigger |
| Contribution | ID, request, responder/source, origin, received timestamp, type, evidence status, permitted content, interpretation fields, restrictions, evidence family |
| Assessment | Contribution/question IDs, claim-level relation, applicability, missing fields, reviewer identity/type, decision and source references |
| Action event | ID, previous state, eligible options, selected action, selection probability if randomized, policy/config versions, actual timing/cost, outcome |
| Learning feedback | Action ID, component values, assessor/method, synthetic/observed/pending status, units, feedback version and restrictions |
| Policy artifact | Algorithm, feature contract, training config/seed, dataset/world split IDs, parameters, evaluation, promotion state, parent version |
| Authorization | Issuer and authority, covered sender/recipients/purpose/content, cadence/spend limits, validity/revocation, exclusions |

Required invariants:

- An operational response and a scientific finding are distinct typed events.
- `not_measured`, `no_relevant_resource`, `cannot_disclose`, `declined`, `no_response`, `invalid_measurement`, and `informative_negative` are distinct.
- Evidence direction is per claim. One contribution can support one premise and leave another unresolved.
- A statement extracted by an agent is not a statement signed by the institution or a scientific reviewer.
- Origin is immutable: public evidence, authentic institutional response, or synthetic. Derived records inherit lineage.
- Simulated contributions cannot enter a real plan or become real-world reward feedback.
- Permission to use a finding for this case does not automatically authorize public export, other-case reuse, or policy training.
- Frozen artifacts remain immutable; changes create successor records and explicit supersession links.
- Multiple reports of one observation yield one evidence family; independence is established, not inferred from different senders.

## 9. Contribution interface

Accept email text and attachments, a small web form, or manual import of an authentic response. P0 requires email plus manual import; the contributor form is optional if it delays the core workflow.

For a scientific result, seek enough permitted context to interpret it: exact intervention; model/species/tissue/compartment; comparator; measured endpoint; experimental unit and denominator; estimate and uncertainty where supplied; quality checks; limitations; which links were not measured; provenance; and permitted uses.

For a capability/referral reply, do not require nonexistent experimental values. Seek the capability, evidence for availability, constraints, responsible route, and permission to follow up. Partial replies remain valid partial contributions.

Do not request identifying rare-case combinations or precise case counts for initial feasibility. If useful quantitative context cannot be released safely, retain the limitation rather than infer missing values.

Intake pipeline:

1. Preserve the original permitted response and transport metadata in its authorized scope.
2. Deduplicate provider message IDs and content lineage without losing distinct replies.
3. Detect response type and propose structured fields, each traceable to source spans.
4. Mark missing, conflicting, or ambiguous fields; no invented estimates, protocols or permissions.
5. Route substantive scientific interpretations to the configured review queue.
6. Emit approved case changes and operational changes separately.
7. Prepare the next action with rationale and dependencies.

External content is untrusted input. Embedded requests to disclose secrets, change permissions, rewrite criteria, or execute code are not operating instructions. Attachments must not execute merely because they were received.

## 10. Outreach and workflow automation

Each first request states the actual sender, the bounded question, why the institution seems relevant, and the smallest useful contribution. It offers an existing result, brief explanation, referral, feasibility reply, or quote as alternatives. It specifies appropriate disclosure limits and a way to decline further contact. Only confirmed clinical leadership can be asserted.

A partnership availability email intentionally carries less detail than a scientific contribution request. Do not attach private case information or technical architecture to the first Centre Léon Bérard contact.

Implement these logical states with repository-native equivalents:

`DRAFT → READY → DISPATCHING → SENT → WAITING → RECEIVED → ASSESSED → CLOSED`

Alternative states include `AUTHORIZATION_REQUIRED`, `CONTACT_UNVERIFIED`, `DELIVERY_UNKNOWN`, `PAUSED`, `DECLINED`, `EXPIRED`, and `FAILED`. State transitions have events and reasons. A delivery receipt is not a scientific response.

At dispatch, check current authorization, recipient verification, disclosure scope, opt-outs, caps, and campaign exclusions. Standing authorization may cover many routine actions, so operators need not approve every permitted follow-up. A revoked authorization invalidates pending sends.

Use an outbox with idempotency keys and reconciliation. If a provider accepts a send but the client times out, enter `DELIVERY_UNKNOWN`; reconcile before retrying. Do not promise exactly-once delivery from an email API that cannot guarantee it.

Cadence and spend limits have no hidden permissive defaults. Unset limits keep live dispatch blocked while allowing preparation. Timers use UTC internally and display local time. Respect configured recipient quiet hours. Waiting tasks have an owner and next trigger, or an explicit unscheduled state. No repeated polling or follow-ups merely to show activity.

MVA Society, the child, and the family are excluded from outreach in the MVA challenge campaign. This exclusion includes contact intended to circumvent the direct-contact restriction through intermediaries.

The service can prepare experiment specifications and obtain feasibility/quotes. It cannot start physical work, order samples, spend money, or recommend patient administration solely because a simulation branch reaches that action.

## 11. Simulator contract

Represent a bounded research world with latent scientific conditions, resource availability, institutional reply behavior, assay quality, evidence overlap, costs, and delays. Policies observe only what their actions have revealed, plus authorized public profiles. Hidden truth must not appear in prompts, UI data, feature tensors, filenames visible to the policy, or reward explanations supplied during action selection.

Use fictional node identities for generated availability, refusals, delays and findings. Real names can appear in the public capability catalogue, but synthetic responses must never look like correspondence actually received from those institutions.

Separate simulation components:

- Scientific response generator: compartment-specific changes, residual function, downstream outcomes, selection and uncertainty.
- Institutional process generator: existing findings, no measurement, referrals, permission conditions, workload, latency, refusal and nonresponse.
- Observation adapter: transforms generated findings into the same intake contract as authentic replies.
- Decision adapter: sends eligible reviewed observations to existing Stage 10 logic.
- Scheduler: processes parallel requests and virtual-time events deterministically.
- Scorer: evaluates the decision trace against hidden scenario truth, outside the policy boundary.

Simulation parameters are explicit assumptions. Do not label fictional response rates, clinical effect probabilities, costs or timings as estimates of actual institutions. Include parameter changes and unfavorable worlds, not just worlds favorable to the chosen policy.

Changing a result source or institutional response can change the next action without rewriting history. A correct answer may be to seek a clarification, stop one hypothesis, or pause pending a prerequisite. Exhaustion of this candidate network is not exhaustion of global knowledge.

## 12. Scenario fixture catalogue

The following JSON is a conceptual test catalogue, not native plan input. Developers must materialize validated fixtures through actual constructors after T01. Every item is synthetic and has a specific expected invariant.

```json
{
  "schema": "rarepipe.research-network.scenario-catalogue.v0.1",
  "origin": "synthetic",
  "scenarios": [
    {"id":"S01","event":"residual_function_retained","expected":"retain_abundance_premise_without_claiming_drug_rescue"},
    {"id":"S02","event":"functional_defect_at_adequate_abundance","expected":"weaken_model_scoped_premise_and_prepare_review"},
    {"id":"S03","event":"blood_nad_only","expected":"leave_relevant_cell_nad_and_function_unknown"},
    {"id":"S04","event":"intracellular_nad_up_function_unresolved","expected":"retain_upstream_finding_and_identify_missing_link"},
    {"id":"S05","event":"division_decreased_benefit_unknown","expected":"preserve_native_b16_review_route"},
    {"id":"S06","event":"cell_death_increased","expected":"preserve_native_adverse_review_route"},
    {"id":"S07","event":"coherent_functional_benefit","expected":"propose_confirmation_or_translational_review_without_patient_action"},
    {"id":"S08","event":"two_replies_one_original_study","expected":"one_evidence_family_without_replication_credit"},
    {"id":"S09","event":"conflicting_findings","expected":"compare_context_and_prepare_discriminating_question"},
    {"id":"S10","event":"resource_exists_permission_unresolved","expected":"create_access_task_without_analysis_or_biology_update"},
    {"id":"S11","event":"no_reply","expected":"managed_wait_or_reroute_without_biological_negative"},
    {"id":"S12","event":"no_relevant_findings_with_referral","expected":"verify_referral_and_preserve_scientific_uncertainty"},
    {"id":"S13","event":"measurement_qc_failure","expected":"prepare_method_repair_without_drug_failure_claim"},
    {"id":"S14","event":"nmn_result_returned_to_nicotinic_acid_question","expected":"preserve_intervention_mismatch"},
    {"id":"S15","event":"later_source_correction","expected":"invalidate_affected_derivations_with_history_preserved"},
    {"id":"S16","event":"partner_availability_reply_in_oncology_campaign","expected":"update_partnership_state_without_mva_evidence"}
  ]
}
```

Add transport and permissions fixtures separately: duplicate delivery, delayed response after a timeout, send uncertainty, unauthorized attachment, changed reuse permission, opt-out, missing reviewer, and a malicious instruction embedded in a reply.

## 13. Reinforcement-learning implementation

### 13.1 First learner

Implement a small tabular Q-learning agent over a finite, versioned observation-state representation and eligible joint actions. This is an engineering choice for an inspectable MVP. It is not a validated clinical decision model. Because the world is partially observed, report this as a bounded observation-state policy without convergence or global-optimality claims.

The joint action encodes a micro choice (question/clarification/analysis-feasibility task) and a macro choice (node/route/follow-up/wait). This lets one learner optimize both decisions initially. Do not create two independently learning policies before an evaluation shows why that complexity is needed.

Possible actions: request an existing finding, ask a clarification, verify a capability, verify a referral, request method feasibility, request a local-analysis proposal, follow up, wait, prepare scientific review, stop a particular route, or pause. Lab execution and patient actions are not in the action space.

The observation-state encoder includes question status, missing prerequisites, evidence overlap, node capability-confirmation states, permissions, requests in flight, elapsed-time bucket, budget remaining, and relevant context compatibility. Version all bins and features. Do not include hidden result labels. Retain full event history for audit even if the learner uses compressed features.

### 13.2 Update rule and explicit toy defaults

Use the conventional update `Q(s,a) ← Q(s,a) + α[r + γ max Q(s',a') − Q(s,a)]`, with zero future value at terminal states and maximization restricted to eligible actions. Apply permission and scientific-gate masks before exploration and exploitation.

Initial algorithm defaults: alpha 0.1; gamma 0.95; epsilon linearly decreasing from 0.2 to 0.05 over training, and epsilon zero for held-out evaluation. These are adjustable simulator settings, not scientific quantities. Log actual tie-breaking/randomized selection probabilities at decision time. Do not reconstruct propensities afterward.

Q values estimate simulator utility under the configured reward. They must not be rendered as drug efficacy probabilities, confidence in a biological claim, or the chance that an institution will help.

### 13.3 Reward and feedback

Define `V(s)` from independently scored decision-relevant knowledge in the synthetic world: each correctly resolved question has a declared value; a subsequently invalidated resolution loses it. Unresolved questions and duplicate reports add no resolution value. Accurate support and accurate rejection are equally eligible. Operational knowledge can have separate declared value when it changes feasible routing; mere delivery and generic replies have none by default.

For the first toy benchmark, use:

`reward = delta_V - 0.01 * elapsed_ticks - 0.05 * cost_units - 0.05 * contact_units - 1.0 * unsupported_decisions`

Set each correctly resolved question to one value unit in this toy configuration. World files define operational values, time/cost units, caps and penalties before training. All weights and units are synthetic benchmark conventions. Include sensitivity runs; do not treat these weights as patient preferences, monetary valuations or validated research utility.

Score correctness outside the learner and outside the narrative-generating agent. A learner cannot create reward by rewriting the definition of resolved, accepting its own evidence, splitting duplicate findings, or changing scientific thresholds. Hard exclusions and permissions are constraints, not costs it may trade away.

Live feedback is separate. An authentic response may provide observed delivery, time, availability or referral feedback. Biological usefulness requires the configured scientific assessment. Missing feedback stays pending, even after a campaign closes. A delayed response is not a negative biological finding. Permission for case use does not necessarily permit policy training.

The P0 policy trains in simulation and runs in shadow mode for authentic campaigns, storing recommendations alongside actual authorized actions. A real policy-parameter update requires actual eligible feedback and an explicit training event. Data ingestion alone is not an RL update.

### 13.4 Evaluation

Compare the learned policy against both a fixed expert-designed sequence and a simple eligible-node routing heuristic. Supply all policies the same observable information, constraints, and resource budget. Define baselines before evaluating; do not deliberately weaken them to make learning look useful.

Use disjoint train/development/held-out world families or parameter regions as well as distinct seeds. Holding out random seeds alone is insufficient. Include informative null results, attractive irrelevant replies, correlated reports, costly high-value answers, and changed response patterns. Report policy dependence on assumptions and state compression.

Use keyed exogenous randomness indexed by world, node, question and event when comparing policies, so different action order does not accidentally generate a different underlying institution. A later action may still encounter time-dependent capacity if that is an explicit part of the world.

Initial engineering run budget: 2,000 training episodes and 200 held-out worlds, with configurable bounded episode length and request budget recorded in the manifest. These counts exercise software; they are not biological replication requirements or proof of statistical sufficiency. Increase runs only to answer a concrete evaluation question.

Report correctly resolved questions, unsupported conclusions, time/cost/contact burden, refusals honored, missing-feedback rates, and policy updates. For replicate-level binary rates, include numerator, denominator and an appropriate interval; for paired policy differences, retain the paired world IDs and use an appropriate paired uncertainty method. State when no interval is supplied. Never infer empirical superiority from one favorable trace.

No performance-improvement threshold is fabricated here. Engineering acceptance requires actual learning updates and a valid comparison. If the learner does not improve over baselines, report that result and keep the better baseline as the operating recommendation.

### 13.5 Reproducibility

Derive streams from an explicit master seed using a stable cryptographic derivation or equivalent documented stable method, not Python's process-randomized `hash()`. Check stream collisions. Record code revision and dirty state, runtime/dependency versions, canonical configuration, world split, policy version and seeds.

Produce a reproducible semantic-results digest over simulation content and a separate whole-record digest over provenance plus content, each with documented coverage. Timestamps and changed revisions can change the latter. Generate reports from result records; never transcribe rates or digests by hand.

Repeat a bounded run in fresh processes at the same revision/configuration. Report precisely which content is identical. Do not claim a whole document is byte-identical when only scientific values match.

## 14. Stage 10 integration and evidence updates

The adapter reads a pinned plan and proposes successor content. It must check that the pin is still current before applying a reviewed change. New evidence can create a pending proposal without authorizing an amendment or a freeze.

Use native review identities and role checks. Agents cannot sign required human reviews. Missing methods, thresholds, model availability and interpretation inputs remain missing until their actual dependencies are resolved. A proposal with alternatives is conditional, not apply-ready.

Existing native rule outputs and institutional-routing outputs are distinct. Preserve native holds and review routes even when the learned policy prefers a different task. If multiple rules or actions conflict, use the existing review mechanism.

When a source is corrected or restricted, traverse dependencies and mark affected proposals/assessments stale, create a review task, and suspend any downstream dispatch that depends on the invalidated premise. Preserve prior observations and decisions as historical records.

## 15. Interface

Build a small local application or equivalent existing Rarepipe interface sufficient for an operator to run the workflow. Do not require a polished hosted web product or a screen-recorded demo. Reuse existing views where possible; a static snapshot alone cannot perform intake, action selection or queue management.

Required views:

- **Case:** current question, known/unknown premises, latest change, next task, owner and trigger.
- **Network:** explained candidates; public evidence versus confirmed availability and permissions.
- **Requests:** exact draft/sent content, authorization status, task state, next follow-up, stop/pause controls.
- **Contribution review:** original permitted content, structured proposal, missing fields, applicability, evidence family and reviewer action.
- **Scenarios:** selected world assumptions, action trace and resulting decisions, with persistent synthetic labeling.
- **Learning:** baseline comparisons, reward components, policy version, updates and limitations.
- **Audit/export:** provenance, supersessions, scoped sharing, and a plain-language account of actual work.

The family-facing summary uses the same event store: what changed, what it means, what remains unresolved, who owns the next step. Do not display invented continuous activity, partnership status, or efficacy confidence. Clinical leadership and family preferences must not be fabricated to populate a screen.

## 16. Real institutional pilot

Software completion and external participation have separate milestones. A simulator can satisfy the former. The live-pilot milestone requires all of the following:

1. An approved campaign, verified recipient route, actual accountable sender and authorized content.
2. A genuine response retained with provenance and disclosure scope.
3. A structured contribution linked to the question actually asked.
4. An appropriate assessment and a visible next action or explicit pause.

A useful methods, feasibility, referral, or no-relevant-findings response can satisfy the authentic-response requirement. Positive biology is not required. An automated acknowledgement or delivery receipt cannot satisfy it.

For the MVA campaign, the response must concern a relevant MVA research question. For the oncology partnership campaign, a reply about availability advances partner qualification only. Report both accurately; do not use the latter to claim the former has private scientific evidence.

If authentic participation is delayed, mark that milestone pending and name the next authorized action. Do not fabricate a partner or silently replace the criterion with synthetic correspondence.

## 17. Track 2 submission alignment

The rubric below is taken from the user's supplied challenge text. No score or eligibility outcome is promised.

| Criterion | Weight | Deliverable contribution | Claim limit |
|---|---:|---|---|
| Scientific rigor | 35% | Mechanism, exact candidate identity, primary evidence, contradictions, residual-function uncertainty, interpretable experiment/decision plan | Software complexity does not substitute for pharmacological or mechanistic support |
| Potential impact | 25% | Decisions the work could change if independently validated; which uncertainties or unproductive routes it could resolve | A research workflow and simulated improvement are not a clinical benefit |
| Innovation | 25% | Executable institution-response loop, scientific/institutional scenario simulation, actual evaluated policy learning | Claim only implemented methods and observed evaluation results |
| Scalability | 15% | Case/compound adapters, typed contributions, reusable capabilities and bounded operations | One case does not establish cross-disease performance |

Generate a submission evidence index mapping important report/pitch claims to sources or software artifacts. Classify claims as observed, implemented, simulated, proposed, or unresolved. The three-minute video is a spoken explanation of the hypothesis and approach, not a mandatory UI walkthrough. Keep the name of the separate challenge out of that video, as previously requested.

For the separate decentralized-data application, a public capability map and prepared emails do not prove dataset access. A returned insight, a collaboration discussion, and permission to access/curate a suitable dataset are different milestones. Confirm the actual dataset/application plan and applicable call conditions with a willing partner.

## 18. Acceptance tests

| ID | Required behavior |
|---|---|
| A01 | Each seeded node has a source, node type and explicit unknown availability/permission fields. |
| A02 | A public profile match cannot become a confirmed resource or collaboration without a new evidence event. |
| A03 | Exact intervention mismatches survive ingestion; NMN findings cannot become nicotinic-acid observations. |
| A04 | Blood-only NAD evidence cannot close the relevant-cell or functional question. |
| A05 | Unknown endpoints and missing interpretive fields stay unknown. |
| A06 | Two replies about one original study do not become independent replication or duplicate reward. |
| A07 | Refusal, no response, no resource, QC failure and informative negative remain distinct. |
| A08 | Native B16 behavior is preserved on the current reduced-division/unknown-benefit fixture; native death and other review routes regress unchanged. |
| A09 | Conflicting scientific findings create context comparison/review, not a majority-vote conclusion. |
| A10 | Frozen native plans cannot be mutated; stale edits fail with a conflict. |
| A11 | No persona/agent can sign a required human review or release a scientific freeze. |
| A12 | Every live waiting task has an owner and next trigger or a visible unscheduled reason. |
| A13 | Send/reply retries deduplicate correctly; an ambiguous send enters reconciliation before another transmission. |
| A14 | Revocation, opt-out, exclusion or unset required authorization blocks dispatch, including pending retries. |
| A15 | Synthetic contributions and synthetic learning feedback cannot cross into real campaign stores. |
| A16 | Hidden world truth is absent from policy inputs, prompts and UI payloads supplied during decisions. |
| A17 | The learner updates persisted parameters from the declared reward; static routing alone fails this test. |
| A18 | Eligible-action constraints apply to exploration as well as exploitation. |
| A19 | Fixed and heuristic baselines receive equivalent observations and budgets; held-out splits are checked for leakage. |
| A20 | Repeated fresh-process runs reproduce scoped semantic results with generated digests and honest provenance differences. |
| A21 | Metrics and narrative are generated from records; each reported rate has its actual count/denominator. |
| A22 | A later correction or permission change invalidates affected derivatives and pending dependent actions. |
| A23 | A malicious instruction in an external reply cannot change permissions, execute code or export records. |
| A24 | A contribution's restrictions survive exports, other-case routing, and training selection. |
| A25 | An authentic institutional reply is imported with provenance and produces an assessed next action; synthetic inputs cannot pass this milestone. |
| A26 | A partnership reply cannot satisfy an MVA scientific question or imply dataset access. |
| A27 | A coherent positive scientific branch ends at confirmation/review tasks, with no patient action. |
| A28 | Public exports omit private identifiers, case-local paths, recipient details and restricted text unless expressly permitted. |
| A29 | The submission index distinguishes implemented, observed, simulated, proposed and unresolved claims. |
| A30 | The user can pause/cancel a campaign and obtain a permitted handoff without losing its recorded history. |

Acceptance A25 is a real operational milestone; test its processing code with synthetic fixtures, but only a genuine event can mark the milestone complete. Tests cannot create consent, access rights, biological evidence or human review.

## 19. Implementation tasks

Each task should become an issue with the dependencies and acceptance IDs below. Existing working components should be reused. If an interface differs from this PRD, record the decision and update the contract before coding around it.

| Task | Deliverable | Dependencies | Acceptance |
|---|---|---|---|
| T01 | Inspect repository, identify native interfaces, pin baseline, document adapter and ownership decisions | None | A08, A10, A11 |
| T02 | Campaign/question/node/contribution schemas, origin and permission invariants | T01 | A01–A07, A15, A24, A26 |
| T03 | Seed registry and bounded request specifications from sourced discovery brief | T02 | A01, A02, A03 |
| T04 | Durable event log, task scheduler, outbox, reconciliation and pause controls | T02 | A12–A14, A30 |
| T05 | Request composer, authorization enforcement, test transport and live/manual-import interfaces | T03, T04 | A13, A14, A23 |
| T06 | Intake, source-grounded extraction, deduplication and contribution review | T02, T05 | A03–A07, A09, A23, A24, A26 |
| T07 | Native plan adapter, supersession and dependency invalidation | T01, T06 | A08–A11, A22, A27 |
| T08 | Scenario environment and fixture catalogue with hidden-truth boundary | T02, T04 | A15, A16, A20 |
| T09 | Reward scorer, fixed/expert and heuristic baselines, world splits | T08 | A06, A16, A19, A21 |
| T10 | Q-learning policy, parameter persistence, masking, shadow recommendations | T09 | A17–A19 |
| T11 | Case, network, request, contribution, scenario and learning views | T03–T10 | A12, A15, A16, A30 |
| T12 | Evaluation runner, generated reports, digests, exports and submission claim index | T07, T10, T11 | A19–A24, A28, A29 |
| T13 | End-to-end operator runbook and verification at a known revision | T12 | All engineering acceptance IDs |
| T14 | Authorized authentic institutional pilot and documented next state | T05–T07, actual owners and authorization | A25, A26 |

T14 has external dependencies and must not be marked complete by an engineer-generated fixture. T01–T13 can progress without an institution agreeing to participate. T14 must identify its actual operator, authorized target and next follow-up event when activated.

## 20. Definition of done and review packet

Deliver committed code, runnable local instructions, configuration examples without secrets, generated seed registry, scenario catalogue, policy artifacts and baseline comparison, exact verification commands/results, and the current authentic-pilot state.

Tests must propagate the real process exit status; do not hide failures through output pipelines. Record skipped tests and integration limits. Verification run provenance must identify the code that actually produced it. Never fabricate hashes or infer all tests passed from a tail excerpt.

The review packet must show independently:

- Engineering features completed and their verification evidence.
- Scientific plan status and unresolved native gaps.
- Synthetic learning outcomes and assumptions.
- Authentic institutional events, including operational-only replies.
- Remaining owners, permissions, access dependencies and next actions.

Completion does not require niacin to work, a favorable RL benchmark, or a partner to disclose restricted information. It requires an honest working process whose successes, failures and boundaries are inspectable. An unresolved external milestone remains visible.

## 21. Source and authoring notes

This PRD incorporates the user's 30 September clarification, supplied Track 2 rubric, developer reports, the attached Centre Léon Bérard listing screenshot, and the previously prepared `rarepipe-insight-network-mvp-discovery.md`. The screenshot was visually inspected; its contact and dataset status were not independently confirmed with the institution. No message was sent.

Platform inspiration: https://www.moleculeo.com/ for explained capability/evidence-gap matching; https://newgenia.com/multiomics-ai-platform/ and the supplied diagram for distinguishing DNA/RNA/protein/metabolite layers. These descriptions do not validate performance or an RL implementation. Rarepipe adds functional-cell evidence as an explicit design layer.

Scientific anchor references: the human nicotinic-acid study, PMID32386566, and the SIRT2/BubR1 study, PMID24825348, inform different links and contexts. Their findings cannot be fused into observed rescue for this child. The discovery brief contains source links and access limits.

The separate challenge's public page is https://www.sprind.org/en/actions/challenges/recoding-medicine. Dataset access and project suitability remain to be established through the applicable process. Centre Léon Bérard is an oncology partnership lead, not a publicly verified holder of relevant MVA results.

The System Steward and Family Advocate personas informed ownership, low-burden participation, faithful updates and permission boundaries. They did not perform human scientific review or express this family's actual preferences.
