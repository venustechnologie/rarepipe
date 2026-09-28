# Rarepipe Prospective Experiment and Decision Plan

Product requirements document | Version 1.0 | 28 September 2026

Audience: Rarepipe engineering, research operations, scientific reviewers and the clinician responsible for the case.

## 1 Product decision

Build Stage 10 as a versioned prospective planning layer on top of Rarepipe's existing evidence artifacts. It must turn an unresolved hypothesis into explicit conditional forecasts, proposed experiments, interpretable outcome branches and accountable next actions. Each new observation must update a reviewable case state without rewriting what was predicted beforehand.

The first case is MVA_001 and the first drug hypothesis is RH_001, nicotinic acid. The product must distinguish whether the altered protein can function, whether an intervention improves cellular function, and whether any improvement could eventually translate into patient benefit. These are separate questions with separate evidence requirements.

The MVP delivers a scientific planning and decision-support workflow. It does not establish a treatment, execute a laboratory experiment, prescribe a drug or claim a validated simulation of this child. It must nevertheless be useful immediately: the team should know which result would change the next decision, what evidence would distinguish the alternatives, who owns that work and what can be prepared before results arrive.

### 1.1 Definition of the first release

An operator can import a verified Stage 09 baseline, create and review a plan, explore every defined branch, freeze a scientifically complete prospective version, ingest an observation, see a reproducible interpretation, and propose the next version. A doctor can inspect the case without managing the research workflow. Research operations owns follow-through.

Software release readiness and scientific plan readiness are different. The software can ship with the supplied planning example and synthetic fixtures. The real MVA plan must remain DRAFT or REVIEW_REQUIRED while assay thresholds, model availability or scientific reviews are incomplete.

### 1.2 The question every screen must answer

What do we expect, under which assumptions, what observation would change our view, and what happens next?

## 2 Current baseline and immediate handoff

Use the supplied candidate as the development input. Do not label it the final frozen baseline.

| Field | Supplied value |
| --- | --- |
| Candidate | v0.1.3-r2, untagged |
| Source commit for runs | 110f4f2fb75acf7c3409d82cbc7ce0c8faf2141f |
| Package assembly and captured test commit | 15af6e1886d3f55096d2e0164808697a77a67994 |
| Stage 06 run | RUN_20260928T135830Z_94f5ec |
| Stage 07 run | RUN_20260928T135832Z_94ee35 |
| Stage 08 discovery run | RUN_20260928T135832Z_e3b0ab |
| Stage 09 run | RUN_20260928T135833Z_a1d00a |
| Stage 09 semantic digest | sha256:50ca1185e06653cb7409176b5aa542996f88222ce54eaab914f0abfaed289040 |
| Submitted ZIP SHA256 | c265a6aff960f96ea33bccd8e75e0fc808e5b40ca58557ab0fe57444a04c2d43 |
| Manifest inspection | All 23 listed payload files match their hashes |
| Captured tests | 350 passed, 8 skipped, at package assembly commit; not independently rerun for this PRD |
| Exact allele residual function | INSUFFICIENT and unresolved |
| RH_001 evidence grade | MECHANISTIC_INDIRECT |
| Direction on required cellular state | Observed direction unknown |

The knowledge baseline includes a corpus-scoped negative rapamycin experience, class-level restored-abundance checkpoint-activation observations, an abstract-level 2020 domain-function finding, and unresolved links from nicotinic acid to the required cellular state. Existing facts retain their source and scope. A later paper repeating a finding must not count as independent corroboration.

### 2.1 Decisions resolving the developers' questions

Proceed with retrieving the publisher's supplement directly and verifying the bytes before import. No additional permission is needed to perform that public, read-only retrieval within the already requested work. The companion source archive preserves the original publisher bytes retained in this workspace; extraction must be followed by checksum verification in the receiving environment. A visually equivalent or delivery-modified PDF is a different byte artifact and must not inherit the original file's byte-verification status.

For pitch sentence 15, use the minimal revision: **It is an approved medicine.** Adding an indication is optional future evidence enrichment; it is not needed for this pitch or this PRD. Do not infer an indication, formulation or pediatric suitability from an ingredient-level approval record.

Retain the intent and wording of pitch sentence 22 by extending the proposed validation plan. Add a requirement to verify model genotype locally, distinguish an exact genotype model from a generic BUB1B-deficient model, and measure viability, cell death and division rate alongside chromosome-sorting outcomes. This authorizes a more specific research plan; it does not establish that patient cells exist, authorize sample acquisition, contact anyone or authorize treatment. A newly versioned RH_001 record must carry these requirements before the pitch can pass its artifact check.

Rebuild the affected evidence and hypothesis artifacts after those changes, rerun the pitch check, and record the actual build and test commits. Stage 10 must then rebase explicitly onto the corrected baseline. Existing frozen runs and the superseded hypothesis record remain immutable.

### 2.2 Provenance correction

The earlier provenance described a 1,619,161-byte publisher PDF with MD5 d0f8765d46ab319b1c4c31b82f8143f6 and SHA256 dd2464e93bbda5459a216c7804e2dfd6d3b38ac64d5ab2e1596ee03323ce94b7. The developers received different bytes. The point of transformation has not been established. Do not label that discrepancy corruption, tampering or a particular delivery-system behavior without evidence. Record the original, received and derived artifacts separately.

## 3 Users and responsibility

| Role | Responsibility | Principal interface |
| --- | --- | --- |
| Treating clinician | Defines clinical questions and meaningful patient goals; reviews clinical implications | Case overview and decision review |
| Scientific lead | Owns biological interpretations, model relevance and proposed experiments | Plan editor and evidence comparison |
| Research operations | Obtains permitted evidence, coordinates tasks and tracks blockers | Task queue and capability requests |
| Assay scientist | Specifies controls, measurement validity and laboratory feasibility | Experiment specification |
| Statistician or modelling scientist | Specifies analysis, uncertainty and forecasting validity | Forecast and simulation review |
| Engineer | Implements schemas, deterministic evaluation, security and reproducibility | CLI, tests and artifact inspection |
| Patient or caregiver | States priorities and sees approved progress summaries when sharing is enabled | Patient summary, later release |

One person may hold several roles. Review records must identify the capacity in which a decision was made. An agent cannot sign as a human reviewer. The team operating the service owns task completion; the clinician is not assigned routine literature retrieval or institutional coordination by default.

## 4 Scope and release boundaries

### 4.1 P0 required for the first release

- Import existing evidence and preserve dependency lineage.
- Maintain competing hypotheses, assumptions and gaps.
- Specify experiments and conditional forecasts with explicit unknowns.
- Evaluate structured outcomes using deterministic rules and three-valued logic.
- Explore hypothetical branches without creating real observations.
- Freeze, amend and compare plan versions; retain forecast history.
- Produce tasks, unsent node-query specifications and laboratory handoff drafts.
- Provide an operator editor and a doctor-facing progress view.
- Export private and sanitized artifacts with checksums and policy enforcement.
- Replay the supplied synthetic acceptance scenarios offline.

### 4.2 P1 after P0

Add numerical sensitivity analysis through validated model adapters, approved local node execution, structured evidence-envelope import, workload ranking and prospective forecast scoring. Start with a small number of permissioned nodes and defined scientific models. Agent counts and node counts are configuration limits, not success criteria.

### 4.3 P2 later product development

Add additional diseases, validated quantitative forecasts, patient sharing, operational service tiers and prospective evaluation of decision quality. A consumer service may expose continuity, options and progress before personalized numerical forecasts are validated. Patient-facing risk claims require their own evidence and review.

### 4.4 Outside this release

No drug administration, autonomous clinical action, automated external messaging, external transfer of controlled variants, automatic purchase of laboratory work, whole-person digital twin, combinatorial drug recommendation engine or claim that a simulated outcome is patient evidence. Combination hypotheses may be represented later but cannot inherit single-drug approval, safety or efficacy conclusions.

For the current MVA challenge, preserve the existing prohibition on contacting the MVA Society, child or family. Generate unsent research tasks only. Any separate SPRIND deployment must have its own permitted data access; access granted for one challenge is not automatically permission for another use.

## 5 Product principles and scientific distinctions

**FR-001 Evidence and forecasts stay distinct.** Every statement is typed as observation, literature claim, hypothesis, assumption, conditional forecast, simulation output or proposed action. A simulation cannot be promoted to an observation by changing a display label.

**FR-002 Scope follows the experimental system.** Store species, tissue or cell type, genotype relationship, intervention identity, exposure, timeframe, endpoint and comparator. Gene-level, variant-class and exact-genotype evidence are distinct. Exact matching remains local and private.

**FR-003 Uncertainty is explicit.** Unknown, not measured, not reported, unavailable, inconclusive, evidence against and not applicable are distinct states. Missing numeric values are null with a reason, never zero. No retrieved test is not proof that no test exists.

**FR-004 Positive results remain endpoint-specific.** More protein, checkpoint activation, checkpoint silencing, chromosome alignment, missegregation and patient benefit must not collapse into a single works flag. A prolonged arrest is not automatically a better checkpoint; desired behavior is a justified normal range or reference response.

**FR-005 Negative findings have conditions.** Failure to reach statistical significance does not establish no effect. Evidence against a specified meaningful effect requires a prespecified analysis capable of excluding that effect with adequate precision. Invalid or under-informative experiments produce INCONCLUSIVE.

**FR-006 Independence is recorded.** Repeated citations, overlapping cohorts, shared cell lines, duplicate datasets and agents analysing the same source do not create independent replications. Preserve independence-group identifiers and overlap notes.

**FR-007 Patient benefit has its own evidence.** Laboratory improvement may motivate further investigation. It cannot unlock a treatment-ready state. The MVP has no transition that prescribes or automatically recommends administration to a patient.

## 6 End to end workflow

1. **Import the baseline.** Verify the package manifest, schema versions, referenced run IDs and visibility. Display candidate/frozen status and unresolved provenance limitations.
2. **Define the decision.** The scientific lead records the question, intended scope, useful outcomes, patient-relevant goal if known, constraints and the current alternatives.
3. **Build the model.** Connect hypotheses to evidence, assumptions, experiments and expected observations. Include competing explanations and an unmodelled-result branch.
4. **Specify the experiment.** Separate biological model requirements from specimen availability. Complete endpoint definitions, controls, analysis and interpretation criteria with the laboratory team.
5. **Explore possible results.** Users select synthetic outcomes and inspect resulting actions. The interface remains visibly in scenario mode.
6. **Review and freeze.** Pin the evidence, protocol, forecast, rules, reviewers and software version before the applicable experimental results are available.
7. **Receive evidence.** Preserve the original result object, verify identity and provenance, run quality checks and classify the observation vector.
8. **Review the interpretation.** Show matched rules, missing inputs, conflicting findings, affected hypotheses and proposed next tasks. A reviewer accepts or amends the interpretation with a reason.
9. **Prepare the next version.** Create new tasks and a successor plan. Never overwrite the frozen forecast or silently move its success criteria.

Repeated research is represented by new experiment IDs and plan versions. Avoid unbounded graph loops that keep launching the same task.

## 7 The MVA hypothesis set

Seed the following hypotheses from the current evidence. Their outcomes are unknown for this child's exact genotype. These alternatives are not assumed to be mutually exclusive, and some apply at different levels.

| ID | Hypothesis or competing explanation | What would distinguish it |
| --- | --- | --- |
| H01 | Adequate abundance of the altered protein permits useful function | Matched-abundance exact-allele function study |
| H02 | A functional defect remains despite restored abundance | Persistent defects under validated matched-expression conditions |
| H03 | Nicotinic acid does not produce the required intracellular upstream effect in this model | Relevant intracellular readouts with assay and exposure validity |
| H04 | An upstream change occurs but does not improve the SIRT2 to BubR1 connection | Mechanistic measurements alongside abundance |
| H05 | Cellular improvement involves a mechanism outside the proposed chain | Reproducible functional benefit without the predicted mechanistic signature |
| H06 | Apparent benefit is explained by selective death, reduced division or measurement bias | Viability, death, division and independent outcome assessments |
| H07 | Cellular benefit is real but not practically translatable | Exposure, model relevance or safety limits identified in later review |

Do not automatically discard H05 because it contradicts the favoured explanation. A hypothesis about a mechanism and a hypothesis about functional benefit can receive different updates from the same observation.

## 8 Experiment specifications for the first case

These are research-design requirements, not executable wet-laboratory protocols. The assay scientist chooses and documents methods, concentrations, timing, replication and thresholds before a plan becomes scientifically ready. The software must display unresolved fields and the responsible owner.

### 8.1 EXP01 Exact allele residual function

**Decision:** Is an abundance-only strategy biologically coherent for the altered protein in a defined system?

**Model:** A locally verified engineered model of the exact missense allele, with endogenous and introduced protein contributions distinguishable. This is an allele-function experiment, not automatically a recreation of the child's complete genotype or tissues. Store transcript, isoform and construct identity in the private layer.

**Comparators:** Wild-type replacement, appropriate deficient or vector control, restored-abundance reference such as I909T or L1012P, and a poorly expressed reference such as L844F where scientifically suitable. L844F is not a known matched-abundance loss-of-function control. Normal-protein rescue validates the assay; it does not establish mutant-protein function.

**Required measurements:** Expression comparability, checkpoint activation, checkpoint silencing or timely exit, chromosome alignment, chromosome-missegregation rate per assessable division, viability and division rate. Kinetochore localization or PP2A-B56 recruitment can be additional mechanistic measurements when feasible.

**Interpretation:** If matched abundance is not achieved or cannot be established, residual function at matched abundance remains unresolved. A partial functional response is not full rescue. Preserve the distinction between construct results and the child's endogenous protein.

### 8.2 EXP02 Nicotinic acid mechanism and cellular function

**Decision:** Does nicotinic acid improve the required cellular functions in a defined BUB1B-deficient model, and does the proposed chain explain that improvement?

**Model hierarchy:** Prefer a validated model carrying the relevant genotype when available and permitted. A patient-derived model is conditional on legitimate availability; none is asserted here. An engineered exact-allele model, a complete-genotype model and a generic deficient model must have separate applicability labels. If only a generic model is feasible, retain that limitation throughout every forecast and export.

**Intervention identity:** Nicotinic acid must remain distinct from nicotinamide and NMN. Record ingredient, formulation or reagent identity and experimental exposure. Approval of an ingredient for another use does not establish suitability for this child.

**Comparators:** Appropriate vehicle or untreated deficient cells and suitable isogenic or healthy reference cells; mechanistic and assay controls selected by the scientific lead. Reference compounds used to interrogate a pathway are not automatically eligible treatment candidates.

**Measurements:** Intracellular NAD+, SIRT2 activity where measured by a validated approach, BubR1 abundance, K668 acetylation where feasible, checkpoint activation, checkpoint silencing, chromosome alignment, missegregation per viable assessable division, cell viability, cell death and division rate. Capture total aneuploidy separately from newly observed missegregation. Optional or unavailable mechanistic assays must not be silently treated as passed.

**Success definition:** Prespecified functional improvement with interpretable controls and adequate precision, assessed with viability and division behavior. An abundance increase alone supports only an intermediate step. Viability alone does not exclude selection bias; record death and division measurements and the relevant denominators.

**Failure interpretation:** Lack of a measured upstream effect challenges that link in the tested context. Upstream improvement without functional improvement challenges the downstream bridge. A valid unexpected functional benefit opens an alternative-mechanism investigation. Worsening creates a scientific hold and review task. These outcomes do not prove universal efficacy or universal failure.

### 8.3 EXP03 Replication and relevance

**Trigger:** A reviewable functional signal from EXP02, or an unexpected result needing confirmation.

Use an independent execution or laboratory where possible; record what is independent. Test whether the effect persists in another relevant model or context, and compare exposures with a justified translational assessment. Quantitative pediatric exposure and safety conclusions require appropriate clinical pharmacology expertise and evidence; no values are supplied by this PRD.

A positive result may unlock a translational-review task. A reviewer then determines whether further preclinical work or clinician-led study planning is warranted. No patient intervention is unlocked automatically.

### 8.4 Required analysis fields

Every experiment must specify the independent experimental unit; biological and technical replication; allocation and blinding where applicable; primary and secondary endpoints; effect scale; analysis population; denominators; time windows; missing-data and exclusion rules; multiplicity approach where relevant; meaningful-effect criterion; uncertainty method; and conditions for repeat or termination. A cell count must not be misrepresented as the number of independent biological replicates.

Numerical thresholds must be justified by assay performance, scientific goals and review. The fixture labels improved, unchanged and worsened are software test inputs, not preapproved biological thresholds.

## 9 Forecast contract

**FR-010** Every forecast names a hypothesis, experiment, intervention or comparator, endpoint, expected direction or range, observation window, assumptions, evidence snapshot, disconfirming pattern and branch actions. It also records model applicability and what cannot be concluded.

**FR-011** Forecast modes are QUALITATIVE_CONDITIONAL, QUANTITATIVE_EXPLORATORY and QUANTITATIVE_VALIDATED_FOR_CONTEXT. Validation is specific to an endpoint, population, context and use; it is never a universal badge. Default to the qualitative mode for the MVA case.

**FR-012** Probability may be null with a reason. A numerical probability requires a defined event, horizon, population or system, method, calibration evidence and uncertainty. Model votes, verbal confidence and the proportion of arbitrary simulations that succeed are not patient-response probabilities.

**FR-013** Model uncertainty, parameter uncertainty, measurement uncertainty and biological variability must be represented separately when known. Mark unquantified uncertainty explicitly. Avoid translating an ordinal evidence grade into a percentage.

**FR-014** Every frozen forecast has an outcome-availability declaration. Record planned experiment start, actual start when known, earliest result generation, first result access and available timestamp evidence. If timing cannot be established, use TEMPORAL_STATUS_UNVERIFIED. A hash proves byte identity, not that the author had never seen a result.

**FR-015** Use distinct evaluation modes: PROSPECTIVE_NEW_RESULT, BLINDED_EXISTING_RESULT, RETROSPECTIVE_REPLAY and SYNTHETIC_DEMO. Existing hidden results do not become prospective merely because the operator has not viewed them.

## 10 Outcome branches and decision rules

The rules engine evaluates an observation vector rather than one success flag. Each predicate evaluates to TRUE, FALSE or UNKNOWN. Missing required data yields UNKNOWN. Rules list required inputs and may emit additional information requests. Preserve all matched findings even when one operational action takes priority.

| Branch | Qualifying pattern after relevant checks | Decision consequence |
| --- | --- | --- |
| B00 | Source or sample identity unverified, or quality criteria failed | Quarantine scientific interpretation and resolve provenance or assay issues |
| B01 | Precision inadequate, controls inconclusive or required readout missing | Keep affected hypotheses unresolved; improve the experiment or evidence |
| B02 | Valid EXP01; matched abundance not established | Keep matched-abundance residual function unresolved |
| B03 | Valid EXP01; matched abundance and specified functional improvement | Strengthen H01 for measured endpoints; permit drug-mechanism planning |
| B04 | Valid EXP01; matched abundance and meaningful defect persists | Weaken abundance-only H01 in this context; examine H02 |
| B05 | Valid EXP02; required upstream effect is absent with adequate precision | Investigate H03; no inference of a general protein-function failure |
| B06 | Upstream effect present; expected abundance or mechanistic response absent | Investigate H04; separate mechanism from functional outcome |
| B07 | Abundance rises; required functional endpoint does not improve | Record partial mechanistic response; examine residual functional limitations |
| B08 | Apparent improvement accompanied by problematic death, division or selection | Hold a rescue conclusion; investigate H06 |
| B09 | Adverse cellular direction or predefined harm criterion | Hold progression and create scientific review; retain any simultaneous benefits |
| B10 | Interpretable functional benefit with required viability and division checks | Candidate functional signal; propose independent replication |
| B11 | B10 pattern with absent or discordant predicted mechanistic signature | Preserve the signal and investigate H05; do not claim the original mechanism proved |
| B12 | Replicated signal but exposure feasibility or relevance unresolved or adverse | Hold translational progression; investigate H07 |
| B13 | Replication and relevance review justify further assessment | Create translational-review task; clinical action remains outside the engine |
| B14 | Valid results conflict across endpoints, models or explanations | Show disagreement and require an explicit interpretation |
| B15 | Valid result fits no existing branch | Record unmodelled observation and create a model-revision task |

### 10.1 Precedence and conflicts

A critical adverse flag always creates a visible hold-and-review task, including when the underlying result is still unverified; the uncertainty accompanies the alert. Integrity and quality gates separately determine whether a scientific conclusion is admissible. A favourable endpoint cannot cancel a harm flag or make failed controls acceptable.

Rules may match simultaneously. B10 plus B11 can produce replicate signal and investigate alternative mechanism. B08 plus an apparently favourable endpoint cannot produce confirmed rescue. Contradictory next actions yield DECISION_REVIEW_REQUIRED, not an arbitrary winning branch. The reviewer must explain a deviation from a suggested action.

### 10.2 Decision records

Store all rule matches, predicate values, missing inputs, proposed actions, selected actions, reviewer, rationale and resulting case-state delta. Deterministic replay must reproduce the rule evaluation from the pinned inputs. Human judgement remains visible as a separate event.

## 11 Simulation and scenario exploration

### 11.1 P0 scenario explorer

**FR-020** Provide a preview in which users choose an experiment and enter hypothetical readout categories. The engine shows branch matches, unknowns, next actions and which assumptions matter. Display Hypothetical scenario throughout. Preview inputs must never enter the real evidence store or update the scientific case state.

Allow positive, negative, partial, adverse, inconclusive and unexpected inputs. A view showing only the desired trajectory does not meet acceptance.

### 11.2 P1 numerical model adapters

Each adapter declares purpose, mathematical model version, permitted inputs and outputs, units, parameter provenance, ranges or distributions, assumptions, solver/version, random seed where relevant, execution environment, verification checks and validation scope. Save results with the input hash and model hash. Missing calibration yields an exploratory label, not an invented probability.

Initial adapter candidates are exposure models, protein production/degradation models, cell-division outcome models and experiment-noise models. Their feasibility is an engineering and scientific assessment, not an assertion that adequate models or parameters already exist for this child. Simulating several plausible mechanisms is permitted; averaging incompatible mechanisms without an explicit model is not.

Separate software verification, numerical validation, biological validation and clinical validation. Numerical solver convergence is not evidence that the biological model is correct. A model fitted to the same outcomes it later reports as predictions is not an independent validation.

### 11.3 Information value and task ranking

**FR-021** In P0 use an explained ordinal ranking based on potential to change a decision, relevance, uncertainty resolved, feasibility, burden, cost and time when known. Show missing estimates. Do not display numeric expected information gain or an optimal-next-step claim without the necessary probability and utility model.

**FR-022** Quantitative value-of-information support is P1. It requires explicit alternatives, outcome likelihoods, utilities or losses, costs, constraints and sensitivity analysis. Keep information gained distinct from patient benefit. The ranking must account for the value and burden of waiting and allow preserving an option as a useful action.

## 12 Decentralized evidence and capability requests

**FR-030** Extend the existing NodeQuerySpecification rather than inventing a disconnected messaging system. Each request names the decision it could change, required capability, permitted scope, useful positive and negative outputs, minimum metadata, local-compute restrictions, authorization requirements, responsible owner and an expiry or recheck date.

MVP request types are FIND_EXISTING_RESULT, ASSESS_MODEL_AVAILABILITY, ASSESS_ASSAY_CAPABILITY and REQUEST_FEASIBILITY_ESTIMATE. These produce drafts only. A laboratory protocol or an order to perform work requires its own review and authorization outside P0.

**FR-031** Responses distinguish NO_RELEVANT_DATA, NOT_SEARCHED, ACCESS_DENIED, NO_RESPONSE, INCONCLUSIVE_RESULT, MEASURED_NO_EFFECT and MEASURED_EFFECT. A hospital reporting no cases must never become a drug-failure observation. A refusal is operational knowledge, not negative biology.

**FR-032** A returned EvidenceEnvelope includes question and task IDs; node identity; authorization and purpose reference; evidence and result type; methodology; relevant model and endpoint metadata; uncertainty; independence/overlap; provenance and hashes; disclosure conditions; and omissions or suppressed fields. Summaries and aggregates remain potentially identifying in tiny populations and need explicit output policy.

A node may answer a bounded question locally or supply an approved summary. Public capabilities inferred from a paper remain inferred until verified. Do not assume a published capability is available to this case or a dataset permits the proposed computation.

## 13 Data model

The following objects are normative contracts. Existing Rarepipe identifiers and artifact conventions should be reused where equivalent. These names and proposed commands are requirements for implementation, not claims that the interfaces already exist.

| Object | Required content |
| --- | --- |
| ProspectivePlan | ID, schema version, case reference, version, lifecycle state, baseline reference, owner, policy, hypotheses, experiments, forecasts, rules, reviewers, temporal status, unresolved requirements, content digest |
| BaselineRef | Stage/run IDs, exact artifact paths and raw-byte hashes, semantic digests with their algorithms, code commit, corpus snapshot, candidate/frozen status and known limitations |
| Hypothesis | ID, statement, level, dependencies, alternatives, evidence references, scope, current assessment and falsification conditions |
| ExperimentSpec | ID, decision question, model requirements and availability separately, intervention/comparator, endpoints, controls, analysis plan, thresholds, feasibility, owners and readiness |
| EndpointSpec | ID, biological meaning, measurement method, unit, denominator, reference/comparator, desired direction or interval, window, requiredness, validity and effect criteria |
| Forecast | ID, hypothesis/experiment/endpoint references, conditional prediction, assumptions, mode, probability or null reason, model reference, disconfirming result and temporal metadata |
| Observation | ID, experiment and execution references, raw-result hash, measured values and units, uncertainty, denominators, QC, sample/model identity, timing, origin and disclosure policy |
| DecisionRule | ID/version, applicability, predicates, required inputs, outputs, constraints, compatible/conflicting actions and rationale |
| DecisionRecord | Pinned inputs/rules, evaluated predicates, matches, unknowns, proposed and selected actions, human interpretation, case-state delta and audit event |
| SimulationRun | Model/input/environment hashes, parameters and provenance, seed, execution outcome, outputs, limits, validation scope and synthetic/exploratory status |
| ResearchTask | ID, branch/decision origin, type, owner, dependencies, status, estimated cost/time or unknown, external-action authorization and completion evidence |
| ReviewRecord | Actor type and identity, role, object/version reviewed, decision, rationale, timestamp and permitted authority |

### 13.1 Identity and serialization

Use immutable object IDs plus explicit version IDs. A new revision has a parent version and a machine-readable change reason. Raw-file hashes and semantic digests are different fields. Document the canonicalization algorithm and version before comparing semantic digests. Include the full numeric representation, units and relevant metadata in scientific content hashing.

Stage 10 may consume a sanitized baseline for public planning. Exact model validation uses private local references. Do not publish a raw variant, a reversible encoding, a low-entropy genotype hash or a nearest-known-variant clue. A public opaque reference may resolve only inside the authorized environment. Output checks must cover free text as well as structured fields.

### 13.2 Result representation

Store original numerical values with units and uncertainty when available. Derived categories require an AnalysisSpec reference, threshold version and derivation record. Accepting a manually adjudicated category must identify its human author and basis. The engine must reject incompatible units, missing denominators and model identity mismatches instead of silently coercing them.

## 14 Lifecycle and provenance

Plan states are DRAFT, REVIEW_REQUIRED, READY_TO_FREEZE, FROZEN, SUPERSEDED and WITHDRAWN. Frozen payloads are immutable. Execution state is separate: NOT_STARTED, RUNNING, RESULTS_PENDING, RESULT_RECEIVED, RESULT_REVIEW_REQUIRED and CLOSED. Availability or policy blockers are structured lists, not substitutions for every lifecycle state.

**FR-040** A scientific freeze requires a verified intended baseline; resolved blocking dependencies; completed required experiment and analysis fields; reviewed rules and forecasts; a recorded result-availability declaration; and appropriate scientific reviews. The system refuses a scientific freeze when numeric thresholds required for interpretation remain null.

**FR-041** A plan with missing scientific inputs can still be exported for review. It must remain marked incomplete. Freezing a software fixture does not preregister an actual experiment.

**FR-042** A change after freeze creates a successor. If outcomes were already available, that version is labelled retrospective or post-result amendment for the affected forecasts. Preserve original scoring against the original criteria, even when the amended analysis is more useful.

**FR-043** When baseline evidence changes, show an impact report identifying affected hypotheses, forecasts, experiments, decisions and tasks. Invalidate applicable reviews for the successor version. Keep unaffected historical records intact. Source corrections can require reevaluation without pretending that the original forecast had the corrected knowledge.

**FR-044** Preserve original bytes, transport bytes if different, extraction outputs and transforms. Link each extraction to the bytes actually parsed. An expected checksum mismatch produces INTEGRITY_MISMATCH, not VERIFIED because the text looks correct. An accepted transformed copy needs documented provenance and a separate acceptance decision.

## 15 Agent behavior and human review

Agents may propose hypotheses, extract evidence, identify contradictions, draft plans, run authorized model adapters and prepare tasks. Each operation must record model/provider/version, prompt or workflow version, input references, tools invoked, execution boundary, output and uncertainty. Treat documents and node responses as untrusted content; their text cannot alter system policy or authorize actions.

Agents must not silently set unknown scientific thresholds, invent specimen availability, convert an indirect finding to exact-allele evidence, assign approval status or send messages. They may suggest a value with a cited basis and request review inside the workflow.

Review is required when accepting a scientific interpretation, freezing a real experiment plan or progressing toward clinical assessment. Routine drafting, retrieval permitted by policy, scenario previews and formatting do not require repeated permission prompts. Separate biological agreement from operational authorization.

Multiple agents should cover distinct hypotheses, model checks or retrieval tasks. Deduplicate outputs and track shared evidence. Ten thousand correlated answers do not constitute ten thousand replications. P0 must work with no model API access and replay stored structured artifacts deterministically.

## 16 Interface requirements

### 16.1 Doctor view

Show the current question, present evidence level, unresolved decision, next proposed step, owner and blocker. Provide a concise account of what changed since the last review. Allow opening the underlying evidence, assumptions and competing interpretations. Do not expose run IDs or technical implementation details in the default view.

### 16.2 Operator plan editor

Show experiment completeness, forecasts, endpoint definitions, rule coverage, tasks and review status. A graph is useful for dependencies, with a table alternative for accessibility. Missing fields must be actionable: name the field, reason it matters and owner. Preserve edits as drafts until an explicit version action.

### 16.3 Scenario explorer

Provide experiment selection, hypothetical outcomes, matched branches, unknown inputs and resulting next steps. Include adverse and unexpected-result examples. A prominent hypothetical label must remain visible when printing or exporting. Previewing a branch must not send a request, alter an observation or create a clinical recommendation.

### 16.4 Result review

Compare what was frozen with what was observed, endpoint by endpoint. Show quality gates and any protocol deviations before the aggregate interpretation. Offer accept interpretation, amend with reason, request clarification and defer decision. Conflicting evidence remains visible after a decision is made.

### 16.5 Change and audit view

Compare baseline and plan versions; highlight altered assumptions, thresholds, sources, forecasts and actions. Distinguish editorial changes from scientific changes. A changed sentence that changes scope is a scientific change. Downloads use the same underlying records as the UI.

## 17 Architecture and interfaces

Implement Stage 10 in the existing Rarepipe repository and artifact pipeline. Start with a local domain layer and adapters, not a new distributed platform. The domain layer owns schemas, validation, rule evaluation, lineage and export. Persistence, UI, optional model calls and future node transports call that layer.

| Proposed command | Behavior |
| --- | --- |
| rarepipe prospective init --baseline PATH | Verify and pin input; create DRAFT plan |
| rarepipe prospective validate PLAN | Report structural, scientific-readiness, provenance and policy errors separately |
| rarepipe prospective preview PLAN --scenario PATH | Evaluate hypothetical branch inputs without mutating the case |
| rarepipe prospective freeze PLAN | Enforce real-plan gates and produce immutable version |
| rarepipe prospective ingest PLAN --observation PATH | Store immutable result, validate provenance and produce review proposal |
| rarepipe prospective review DECISION | Record authorized human interpretation and task proposals |
| rarepipe prospective diff OLD NEW | Explain scientific and operational changes |
| rarepipe prospective export PLAN --visibility public | Apply output policy and write a complete manifest |

The same operations must be callable through an internal service interface for the frontend. Exact HTTP paths can follow the existing application conventions. Mutations require idempotency keys and version preconditions. Re-ingesting identical evidence must not duplicate it or count another replication. Competing edits return a conflict with a diff; never use last-write-wins for a frozen plan.

Imports and exports must be atomic. A failed build or partial write does not advance the active plan pointer. Retrying a build with the same canonical inputs must reproduce scientific content; timestamps and execution logs may differ in separately hashed execution metadata.

## 18 Security and data boundaries

**FR-050** Controlled patient data and exact-allele matching stay inside the existing authorized local environment. Public research retrieval receives only approved sanitized inputs. No network-enabled model is given private values or data-derived clues by default.

**FR-051** Enforce permissions in the domain/service layer as well as the UI. Separate read, draft, scientific review, freeze, private export and external-send permissions. Record policy decisions in the audit log without copying sensitive payloads into operational logs.

**FR-052** In this challenge deployment, external sending and remote execution are disabled. Node queries remain drafts even when a capability is known. Future institutional deployments must check authorization, permitted purpose, allowed computation and output disclosure for each request.

**FR-053** Public exports use an allowlist plus a leakage review. Raw samples, variants, contact details, credentials, private paths and inference-revealing free text must not leave. Small aggregate counts and summaries are not automatically safe. Test controls with synthetic secrets, never actual variants in test fixtures.

**FR-054** Consent, retention and access revocation can constrain future use. Preserve an audit record of the event without assuming that prohibited underlying data may remain retrievable. Legal and institutional requirements are configuration inputs to a reviewed deployment, not claims settled by this PRD.

## 19 Acceptance tests

The following are release gates. The supplied JSON fixtures specify synthetic scenarios; they are not biological evidence. Implementation tests must exercise the actual importer, evaluator and export path rather than simply comparing hard-coded labels.

| ID | Given and when | Required result |
| --- | --- | --- |
| AT01 | Valid current package is imported | All manifest entries verify (23 for the supplied r2); candidate status and unresolved limitations remain visible |
| AT02 | A source byte or expected digest is changed | Integrity failure blocks verified import or scientific freeze |
| AT03 | A draft lacks effect thresholds or required review | Draft export allowed; scientific freeze rejected with named gaps |
| AT04 | EXP01 expression comparability is unknown | No conclusion about function at matched abundance |
| AT05 | Normal-protein replacement rescues an assay | Assay validity may improve; mutant residual function stays unresolved |
| AT06 | Protein abundance rises with no functional rescue | Intermediate finding retained; no cellular-rescue conclusion |
| AT07 | Activation improves but silencing worsens | Partial/conflicting finding and hold; never full rescue |
| AT08 | Error count falls while death rises or division falls | Confounding branch and review; no automatic rescue |
| AT09 | NAD+ rises but the predicted downstream response is absent | Scoped bridge challenge; no universal drug-failure claim |
| AT10 | Function improves with a different mechanistic signature | Preserve signal, open alternative mechanism, propose replication |
| AT11 | Function improves only at exposure with unresolved feasibility | No translational-ready conclusion |
| AT12 | Valid replicated cellular benefit is recorded | Translational-review task only; no patient administration action |
| AT13 | A node reports no relevant cases or denies access | Operational result only; never MEASURED_NO_EFFECT |
| AT14 | Required result fields are missing or incompatible | UNKNOWN or validation error; no zero imputation |
| AT15 | Identical evidence is imported twice | One observation identity; no extra independence count |
| AT16 | A frozen threshold is edited after outcome availability | Original immutable; successor marked post-result for affected forecasts |
| AT17 | Source correction affects an upstream assumption | Dependency impact report and review invalidation for successor |
| AT18 | A scenario preview is executed | Hypothetical outputs only; no case mutation or external action |
| AT19 | A synthetic fixture is offered as real result evidence | Rejected from real evidence promotion |
| AT20 | 731X is encountered during matching | Preserve source-backed frameshift identity; no generic Ter731 equivalence |
| AT21 | A public export contains a synthetic private marker in free text | Export rejected or field removed under policy with logged reason |
| AT22 | An agent or node document requests emailing private data | No policy change or send; untrusted instruction ignored |
| AT23 | Two result reviewers edit the same version | Version conflict and explicit reconciliation |
| AT24 | A forecast has no calibrated probability model | Probability remains null; no invented numeric confidence |
| AT25 | A plan is hashed but result timing is unknown | Temporal status unverified; no preregistration claim |
| AT26 | Multiple compatible branches or contradictory actions match | Preserve all findings; flag contradictory actions for review |
| AT27 | An observation falls outside all modelled branches | Unmodelled-result path creates a revision task |
| AT28 | A hypothesis plan is superseded for viability requirements | Pitch check traces the proposed measurement to the new artifact |

### 19.1 Completion demonstration

Demonstrate the following without live network access: import the current candidate; explain why the real plan cannot yet freeze; preview the supplied branches; freeze a separately labelled complete synthetic fixture; ingest a synthetic outcome in that demo environment; show a reviewer decision and successor; export a sanitized artifact; and replay the interpretation with the same result. The demonstration must not mark the actual MVA plan as experimentally validated.

## 20 Evaluation and success metrics

### 20.1 Software and operational measures

For the MVP, require complete traceability for all rendered scientific claims and branch decisions; zero unlabelled synthetic outcomes in real evidence; zero permitted transitions from an unresolved cellular hypothesis to treatment-ready; and deterministic rule replay on all acceptance fixtures. Report missing data and review latency rather than hiding them behind a completion percentage.

Track time from result receipt to a reviewed next step, proportion of tasks with an owner and blocker, proportion of branches with interpretable actions, duplicate evidence avoided and scientist/clinician corrections to generated drafts. Establish pilot baselines before choosing commercial performance targets.

### 20.2 Scientific forecast evaluation

Compare frozen forecasts to later eligible observations. For quantitative event forecasts, prespecify calibration and proper scoring measures such as Brier or log score, with uncertainty and coverage reporting. Do not average probabilities over unrelated events or hide abstentions. Qualitative forecasts receive prespecified outcome adjudication; a confidence score must not be invented retrospectively to score them.

Report by model, endpoint, tissue or system and evidence applicability. Evaluate decisions and burdens as well as forecast accuracy. One rare-disease case can demonstrate workflow, not validate general clinical predictive performance.

### 20.3 SPRIND demonstration

Build a permissioned dataset of hypotheses, frozen predictions, intervention conditions, endpoints, quality information and positive, negative and inconclusive results. Preserve the context needed for valid comparison; do not pool incompatible assays into one unqualified label.

Compare a public-evidence baseline against a version using permitted institutional evidence under matched evaluation conditions. Separate the benefit of additional data from extra compute or manual curation where feasible. Use held-out institutions or time periods, audit outcome leakage and shared cohorts, and distinguish retrospective demonstrations from prospective results. A substantial public contribution could be the protocol, schema, synthetic fixtures and a permitted benchmark layer; the specific contribution must meet the challenge terms.

The challenge currently asks teams to curate a valuable dataset and demonstrate an AI application, with demonstrable access to a suitable dataset. A registry or forecast interface alone is not sufficient. Do not assume the MVA challenge's controlled-data permission covers a SPRIND dataset. [S3]

## 21 Implementation sequence and delivery gates

| Milestone | Deliverables | Exit criterion |
| --- | --- | --- |
| M0 Baseline closure | Correct source import, updated RH_001 plan, revised pitch, build/test lineage | Corrected baseline passes its existing gates |
| M1 Domain model | Objects, import validation, immutable version store and policy adapter | AT01-05, AT14-17, AT20, AT23, AT25 pass |
| M2 Decision engine | Three-valued predicates, branch evaluator, scenario fixtures and task proposals | Scientific branch tests AT06-13, AT24, AT26-27 pass |
| M3 Prospective workflow | Readiness checks, freeze, observation intake, review and amendments | Temporal and synthetic-separation tests pass end to end |
| M4 Frontend and export | Doctor view, editor, scenario explorer, result comparison and sanitized export | Role/policy tests and operational user walkthrough pass |
| M5 Pilot readiness | Scientific review of the real plan, lab feasibility and predeclared evaluation | Real plan complete enough to freeze or explicit unresolved blockers accepted as pending work |
| M6 Numerical and node extensions | Reviewed simulation adapter and one permissioned evidence-node pilot | Validation scoped to actual use and dataset rights verified |

M1-M4 can proceed using the candidate and synthetic fixtures while M0 and scientific feasibility work proceed. M0 is required before rebasing and freezing the real plan. Engineering must estimate calendar and staffing needs after checking the repository; this PRD does not promise a research or clinical timeline.

## 22 Questions requiring scientific input

| Open item | Owner | Blocks |
| --- | --- | --- |
| Exact model availability and permitted use | Research operations and scientific lead | Real experiment readiness |
| Which model adequately represents the relevant genotype and tissue question | Scientific lead | Applicability and interpretation |
| Assay methods, comparators and validity thresholds | Assay scientist | Scientific freeze |
| Meaningful effects, replication and uncertainty analysis | Statistician and assay scientist | Scientific freeze |
| Model parameters and biological calibration | Modelling scientist | Quantitative forecast claims |
| Exposure plausibility and pediatric relevance | Clinical pharmacologist and treating clinician | Clinical translation assessment |
| Patient-relevant goal and observation horizon | Treating clinician and patient or caregiver | Clinical outcome planning |
| Access rights for a separate decentralized-data pilot | Data holder and research operations | External node use |

The system should allow useful planning while these are unresolved. It must not manufacture answers to make a dashboard green.

## 23 Deliverables expected from engineering

Provide the Stage 10 domain implementation, migration or adapter for existing artifacts, proposed CLI operations, frontend views, structured plan/forecast/observation/decision exports, synthetic fixtures, end-to-end tests, provenance and privacy checks, and an operator guide. Include a concise architecture decision record explaining reused infrastructure and any interface changes.

The MVA seed plan must retain unresolved biology, distinguish experimental models, contain the complete branch set including unexpected results, and generate unsent requests. Its first scientific freeze is a separate reviewed event after required inputs are complete.

## 24 Sources and companion materials

**S1 Supplied project evidence.** MVA_001_stage06F_revised_candidate_v0.1.3r2.zip and pitch_claim_check.md, supplied 28 September 2026. Specific references are the baseline snapshot, sanitized hypothesis set, residual-function assessment, experiment records and per-claim corrections. These establish the project's current assessment, not independent replication of the science.

**S2 Publisher supplement.** Suijkerbuijk and colleagues, supplement to PMID:20516114. Article DOI https://doi.org/10.1158/0008-5472.CAN-09-4319. Supplement DOI https://doi.org/10.1158/0008-5472.22382025.v1. Public metadata https://api.figshare.com/v2/articles/22382025. Publisher file https://ndownloader.figshare.com/files/39827442. The archive metadata lists CC BY 4.0. The companion source archive contains provenance and byte checks.

**S3 SPRIND Recoding Medicine.** https://www.sprind.org/en/actions/challenges/recoding-medicine, consulted 28 September 2026. Used for the dataset, AI application, demonstrable access and public-contribution requirements.

**S4 FDA Model Informed Drug Development program.** https://www.fda.gov/drugs/development-resources/model-informed-drug-development-paired-meeting-program, consulted 28 September 2026. Supports the existence of model-based study design, outcome forecasting and context-of-use assessment. It does not validate this plan or a model for this child.

**S5 Domain-function study.** PMID:33207204, DOI https://doi.org/10.1016/j.celrep.2020.108397. The supplied baseline adjudicates the abstract and records its limits. This PRD carries that assessment forward and requires activation, silencing and alignment to remain distinct.

Companions: illustrative JSON plan, synthetic acceptance cases, baseline handoff note, revised plain-language pitch and publisher-source archive. The examples are implementation aids, not completed laboratory protocols or clinical recommendations.
