# Rarepipe Research-Network MVP: End-to-End Operator Runbook and Verification

## 1. Pinned Baseline & Native Interface Contracts

This deployment builds directly upon the pinned prospective experiment-and-decision baseline defined in `docs/network/T01-native-interfaces.md` (inspected at commit `b4de48e`):

| Property | Pinned Value |
|---|---|
| Native Plan ID | `PP_MVA_001_RH_001@0002-455419f1` |
| Rules Version | `stage10-rules-1.1.0` (17 branch descriptors, B00–B16) |
| Plan Lifecycle / Status | `DRAFT`; baseline status `CANDIDATE` |
| Native Validator | `freezable=False`, **112** scientific-readiness gaps, 0 structural errors |
| Primary Controlled Store | `/Volumes/Lexar/rarepipe_work/MVA_001/prospective` |

A registry entry, an institutional reply, a simulated exploration, or a learned policy update **cannot close a scientific gap**. Only an authorized human clinician or adjudicator accepting an edit through the native versioned workflow can close gaps.

---

## 2. Installation & Prerequisites

This runbook assumes a clean checkout of the repository at `/Users/venus/Desktop/rarepipe`.

### Prerequisites
- Python >= 3.12 (tested on Python 3.12.13)
- `uv` package manager (>= 0.5.0)
- Optional hardware: Controlled external drive at `/Volumes/Lexar/rarepipe_work/MVA_001/prospective`

### Checking the Controlled Drive
The prospective baseline plan lives on the controlled volume. Check its mount state with:
```bash
test -d /Volumes/Lexar/rarepipe_work/MVA_001/prospective && echo "mounted" || echo "not mounted"
```
Actual output:
```
mounted
```

Verify that the pinned HEAD baseline exists on the drive:
```bash
cat /Volumes/Lexar/rarepipe_work/MVA_001/prospective/PP_MVA_001_RH_001/HEAD
```
Actual output:
```
PP_MVA_001_RH_001@0002-455419f1
```

> **Note**: If the controlled drive is not mounted, native plan store modifications will be blocked. However, research-network simulation, request drafting, candidate querying, policy evaluation, reporting, and public exporting can proceed independently in any local workspace.

### Environment Synchronization
Install dependencies into the virtual environment using `uv`:
```bash
uv sync
```

---

## 3. Configuration (No Secrets, Never Read or Write `.env`)

All configuration parameters in Rarepipe research-network are passed explicitly through strongly typed domain objects or CLI options.
**Never read or write `.env` files.** The system does not use or store credentials in environment files. External sending is permanently disabled in this release (`Permission.EXTERNAL_SEND` raises `PolicyError`), so no SMTP or API tokens are required or permitted.

Example configuration of an operator actor and campaign limits:
```python
from datetime import datetime, timezone
from rarepipe.stages.network.model import BudgetCadence, Campaign, CampaignMode, CampaignScope
from rarepipe.stages.prospective.model import Actor, ActorType, Role, Quantity

operator = Actor(
    actor_type=ActorType.HUMAN,
    identity="operator@example.org",
    roles=[Role.RESEARCH_OPERATIONS],
)

limits = BudgetCadence(
    max_requests=5,
    minimum_interval=Quantity(value=60, unit="seconds"),
    spend_limit=Quantity(value=10, unit="EUR"),
)
```

---

## 4. Seed Capability Registry

The capability registry imports public scientific evidence for candidate institutions without fabricating response probabilities, confirmed resources, or pre-arranged collaboration agreements.

### Querying Candidates by Question
Run the following Python snippet to query seeded candidate institutions for questions Q01 through Q06:
```bash
uv run python -c "
from rarepipe.stages.network.registry import load_seed
reg = load_seed()
for q_id in ['Q01', 'Q02', 'Q03', 'Q04', 'Q05', 'Q06']:
    nodes = reg.query_nodes_by_question(q_id)
    print(f'{q_id}: {[n.id for n in nodes]}')
"
```
Actual output:
```
Q01: ['node-chu-quebec-elowe', 'node-hubrecht-kops', 'node-mpi-musacchio']
Q02: ['node-helsinki-aswlab', 'node-oulu-pirinen']
Q03: ['node-harvard-sinclair', 'node-mpi-musacchio']
Q04: ['node-chu-quebec-elowe', 'node-harvard-sinclair', 'node-hubrecht-kops', 'node-euro-bioimaging']
Q05: ['node-bbmri-eric', 'node-icr-london']
Q06: ['node-chu-quebec-elowe', 'node-hubrecht-kops', 'node-mpi-musacchio', 'node-helsinki-aswlab', 'node-oulu-pirinen', 'node-euro-bioimaging']
```

### Inspecting Scenario Fixtures
Inspect a synthetic scenario assumption trace using the operator CLI:
```bash
uv run python -m rarepipe.stages.network.cli views scenarios --scenario-id S01
```
Actual output:
```
view: scenarios
  scenario_id: S01
  origin: synthetic
  synthetic_label: synthetic
  campaign_id: sim-S01
  scope: MVA_SCIENTIFIC
  selected_assumptions: [{'name': 'residual_function', 'value': "<withheld: reveals the synthetic world's hidden truth>", 'label': 'ASSUME', 'note': ''}]
  withheld_assumption_names: ['residual_function']
  reveals_world_truth: False
  action_trace: [{'step': 'contribution', 'detail': 'syn-afd479e4830019a0:scientific'}]
  resulting_decisions: ['expected:retain_abundance_premise_without_claiming_drug_rescue', 'invariant_holds:True']
  expected_invariant: retain_abundance_premise_without_claiming_drug_rescue
  invariant_holds: True
  content_digest: sha256:67202727f42eaf8b0bbec484a9f2cdb49f6ab8f7e27a1f0928b3608327506b43
  available_actions:
    - sim.scenarios.rebuild [enabled] via rarepipe.stages.network.sim.scenarios
```

---

## 5. Run Campaign in Synthetic Mode

A campaign in `SYNTHETIC` mode creates an immutable, append-only journal in the target workspace directory. Derived synthetic records cannot cross into live campaign stores.

### Initializing the Campaign
Initialize a synthetic campaign journal:
```bash
uv run python -c "
from datetime import datetime, timezone
from pathlib import Path
from rarepipe.stages.network.model import Campaign, CampaignMode, CampaignScope, BudgetCadence, Question
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.prospective.model import Actor, ActorType, Role, Knowledge, Quantity

now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
operator = Actor(actor_type=ActorType.HUMAN, identity='operator@example.org', roles=[Role.RESEARCH_OPERATIONS])
limits = BudgetCadence(max_requests=5, minimum_interval=Quantity(value=60, unit='seconds'), spend_limit=Quantity(value=10, unit='EUR'))
campaign = Campaign(
    id='CAMP_SYNTH_001',
    purpose='Preclinical investigation of NAD/BubR1 mechanism',
    scope=CampaignScope.MVA_SCIENTIFIC,
    mode=CampaignMode.SYNTHETIC,
    status='ACTIVE',
    owner=operator,
    limits=limits,
    questions=(
        Question(id='Q01', campaign_id='CAMP_SYNTH_001', scope=CampaignScope.MVA_SCIENTIFIC, decision='What function remains when abundance is normalized?', state=Knowledge.UNKNOWN),
        Question(id='Q02', campaign_id='CAMP_SYNTH_001', scope=CampaignScope.MVA_SCIENTIFIC, decision='Does nicotinic acid increase intracellular NAD?', state=Knowledge.UNKNOWN),
    ),
)
workspace = Path('out/campaign_work')
box = Outbox(workspace, campaign)
print('Initialized campaign:', box.campaign().id)
print('Campaign status:', box.campaign().status, '| Mode:', box.campaign().mode.value)
"
```
Actual output:
```
Initialized campaign: CAMP_SYNTH_001
Campaign status: ACTIVE | Mode: synthetic
```

### Inspecting the Case View
View the current campaign status and open research questions:
```bash
uv run python -m rarepipe.stages.network.cli views case --workspace out/campaign_work --campaign-id CAMP_SYNTH_001
```
Actual output:
```
view: case
  campaign_id: CAMP_SYNTH_001
  campaign_status: ACTIVE
  current_question_id: Q01
  current_question_decision: What function remains when abundance is normalized?
  known_premises: []
  unknown_premises: [{'name': 'intervention', 'status': 'unknown', 'recorded_value': 'UNKNOWN', 'source': 'question.evidence_criteria'}, {'name': 'compartment', 'status': 'unknown', 'recorded_value': 'UNKNOWN', 'source': 'question.evidence_criteria'}, {'name': 'species', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'model', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'tissue_or_cell', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'endpoint', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'comparator', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'method', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'experimental_unit', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'denominator', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'timeframe', 'status': 'unknown', 'recorded_value': 'not recorded', 'source': 'question.evidence_criteria'}, {'name': 'exposure', 'status': 'unknown', 'recorded_value': 'UNKNOWN', 'source': 'question.evidence_criteria'}, {'name': 'effect_criterion', 'status': 'unknown', 'recorded_value': 'UNKNOWN', 'source': 'question.evidence_criteria'}, {'name': 'question_state', 'status': 'unknown', 'recorded_value': 'UNKNOWN', 'source': 'question.state'}]
  latest_change: event ...
  next_task_id: ...
  owner_identity: not recorded
  next_trigger: not recorded
  clinical_lead: not recorded
  content_digest: sha256:...
  available_actions:
    - intake.import_reply [blocked] via rarepipe.stages.network.intake
    - policy_q.select [enabled] via rarepipe.stages.network.policy_q
```

---

## 6. Compose and Inspect Requests without Sending

Requests are composed with bounded scientific inquiries, strict disclosure limitations, and an explicit decline route. If no clinical lead is appointed, the message explicitly states that clinical leadership is unassigned.

### Composing and Preparing a Request
```bash
uv run python -c "
from datetime import datetime, timezone
from pathlib import Path
from rarepipe.stages.network.model import Campaign, CampaignMode, CampaignScope, BudgetCadence
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.network.compose import compose_request
from rarepipe.stages.network.registry import load_seed
from rarepipe.stages.prospective.model import Actor, ActorType, Role

now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
operator = Actor(actor_type=ActorType.HUMAN, identity='operator@example.org', roles=[Role.RESEARCH_OPERATIONS])
workspace = Path('out/campaign_work')
box = Outbox(workspace, Campaign(id='CAMP_SYNTH_001', purpose='x', scope=CampaignScope.MVA_SCIENTIFIC, mode=CampaignMode.SYNTHETIC, status='ACTIVE', owner=operator, limits=BudgetCadence()))
campaign = box.campaign()
reg = load_seed()
node_hubrecht = reg.get_node('node-hubrecht-kops')
q01 = campaign.questions[0]
req = compose_request(campaign=campaign, question=q01, node=node_hubrecht, sender=operator, clinical_lead=None)
claim = box.prepare(req, idempotency_key='req-q01-hubrecht-01', actor=operator, now=now)
print('Prepared request ID:', req.id)
print('Task state in outbox:', box.load(req.id).state.value)
"
```
Actual output:
```
Prepared request ID: 4b7eba53-14d9-4255-bd95-de81a426bc37
Task state in outbox: DRAFT
```

### Inspecting Prepared Content via Operator CLI
```bash
uv run python -m rarepipe.stages.network.cli views requests --workspace out/campaign_work --campaign-id CAMP_SYNTH_001
```
Actual output:
```
view: requests
  campaign_id: CAMP_SYNTH_001
  campaign_status: ACTIVE
  tasks: [{'task_id': '4b7eba53-14d9-4255-bd95-de81a426bc37', 'state': 'DRAFT', 'question_id': 'Q01', 'node_id': 'node-hubrecht-kops', 'content': "From: operator@example.org (Role: research_operations)\nTo: inquiry@node-hubrecht-kops.org\nSubject: Research Inquiry: Bounded Question on Q01\n\nDear Research Team at Hubrecht Institute,\n\nClinical Leadership: Unassigned (no clinical lead is currently appointed). This is an exploratory preclinical research inquiry; no clinical leadership or patient-care decision is asserted or implied.\n\n1. Bounded Research Question:\nWe are investigating a specific preclinical question (Q01):\nDecision Question: What function remains when abundance is normalized?\n\n2. Relevance and Public Source:\nYour institution was identified based on public scientific publications and institutional profiles:\nInstitution: Hubrecht Institute (Kops group)\nPublic Reference: https://www.hubrecht.eu/research-groups/kops-group/\nRelevant Public Capabilities: Chromosome segregation fidelity, SAC signaling, and aneuploidy mechanisms research; Cellular and organoid model systems for kinetochore and spindle checkpoint dynamics; Live-cell microscopy for mitotic timing and chromosome alignment\n\n3. Smallest Useful Contribution:\nWe seek the smallest useful contribution that can inform this question. A complete study, private data transfer, or biological specimen shipment is NOT required. We welcome any of the following alternatives:\n  (a) An existing result or historical finding relevant to the mechanism.\n  (b) A brief methods explanation, interpretation, or advice on assay limitations.\n  (c) A referral to another group, sample custodian, or research infrastructure.\n  (d) A feasibility reply on whether your laboratory could evaluate this endpoint.\n  (e) A formal quote or service agreement proposal.\n\n4. Disclosure Limits:\nPreclinical research scope only. Under institutional policy, no identifying patient combinations, exact variant coordinates, private repository paths, or clinical case records are disclosed.\n\n5. Declining Further Contact:\nIf your group does not wish to participate, does not have relevant resources, or prefers not to receive further contact, please reply with 'DECLINE' or 'OPT OUT'. We will immediately respect your preference and close this outreach route without further follow-up.\n\nSincerely,\noperator@example.org", 'authorization_ref': 'not recorded', 'authorization_status': 'no authorization_ref recorded', 'owner_identity': 'not recorded', 'next_trigger': 'not recorded', 'unscheduled_reason': 'not recorded', 'schedule_state': 'UNSCHEDULED', 'next_followup': 'follow-up bound not recorded', 'origin': 'public_evidence', 'available_actions': [{'action_id': 'outbox.transition_ready', 'label': 'Mark ready', 'owning_module': 'rarepipe.stages.network.outbox', 'preconditions': ['task state is DRAFT or AUTHORIZATION_REQUIRED or CONTACT_UNVERIFIED', 'campaign is ACTIVE'], 'enabled': True, 'blocked_reason': None}, {'action_id': 'outbox.begin_attempt', 'label': 'Begin dispatch attempt', 'owning_module': 'rarepipe.stages.network.outbox', 'preconditions': ['task state is READY', 'fresh authorization check returns True', 'campaign is ACTIVE'], 'enabled': False, 'blocked_reason': 'not ready or campaign stopped'}, {'action_id': 'scheduler.claim', 'label': 'Claim due timer', 'owning_module': 'rarepipe.stages.network.scheduler', 'preconditions': ['task is WAITING and SCHEDULED', 'next_trigger <= now', 'campaign is ACTIVE'], 'enabled': False, 'blocked_reason': 'timer not scheduled'}]}]
  waiting_surfaces: []
  stop_pause_controls: {'can_pause': True, 'can_cancel': True, 'can_resume': False, 'can_handoff': False, 'campaign_status': 'ACTIVE', 'owning_module': 'rarepipe.stages.network.outbox', 'pause_precondition': 'campaign status is ACTIVE', 'cancel_precondition': 'campaign is not already CANCELLED', 'resume_precondition': 'campaign status is PAUSED', 'handoff_precondition': 'campaign status is PAUSED or CANCELLED'}
  content_digest: sha256:46dbe8b22a1eb589d053b597c765e7e2663fcca3e7f2011298ce2310b3c26b5a
  available_actions:
    - outbox.stop_pause [enabled] via rarepipe.stages.network.outbox
    - outbox.stop_cancel [enabled] via rarepipe.stages.network.outbox
    - outbox.resume [blocked] via rarepipe.stages.network.outbox
    - outbox.handoff [blocked] via rarepipe.stages.network.outbox
```

---

## 7. Run Network Evaluation

Train tabular Q-learning policy parameters in simulation and evaluate against fixed expert and simple heuristic baselines on held-out world splits:
```bash
uv run python -m rarepipe.stages.network.cli evaluate run --out out/eval_run.json --seed 20260930 --train-episodes 1 --held-out-episodes 1
```
Actual output:
```
wrote out/eval_run.json
```

---

## 8. Generate Report and Export

Generate the human-readable Markdown evaluation report and public sanitized export.

### Generating the Report
```bash
uv run python -m rarepipe.stages.network.cli evaluate report out/eval_run.json --out out/eval_report.md
```
Actual output:
```
wrote out/eval_report.md
```

### Generating the Public Export
The public export automatically strips restricted internal fields, validates that no case-private terms or paths leak, and outputs an audit-sealed JSON bundle:
```bash
uv run python -m rarepipe.stages.network.cli evaluate export --out out/public_export.json --results out/eval_run.json
```
Actual output:
```
wrote out/public_export.json
```

---

## 9. Pause and Cancel with Handoff

The campaign state machine allows pausing or cancelling at any time without losing recorded journal history. Both generate an operational `Handoff` record.

### Pausing the Campaign
```bash
uv run python -c "
from datetime import datetime, timezone
from pathlib import Path
from rarepipe.stages.network.model import Campaign, CampaignMode, CampaignScope, BudgetCadence
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.prospective.model import Actor, ActorType, Role

now = datetime(2026, 9, 30, 12, 5, 0, tzinfo=timezone.utc)
operator = Actor(actor_type=ActorType.HUMAN, identity='operator@example.org', roles=[Role.RESEARCH_OPERATIONS])
workspace = Path('out/campaign_work')
box = Outbox(workspace, Campaign(id='CAMP_SYNTH_001', purpose='x', scope=CampaignScope.MVA_SCIENTIFIC, mode=CampaignMode.SYNTHETIC, status='ACTIVE', owner=operator, limits=BudgetCadence()))
handoff = box.stop(cancel=False, actor=operator, now=now)
print('Campaign status:', box.campaign().status)
print('Handoff next_action:', handoff.next_action)
print('Handoff task refs count:', len(handoff.task_refs))
"
```
Actual output:
```
Campaign status: PAUSED
Handoff next_action: OPERATOR_REVIEW
Handoff task refs count: 1
```

### Inspecting the Audit & Handoff View
```bash
uv run python -m rarepipe.stages.network.cli views audit --workspace out/campaign_work --campaign-id CAMP_SYNTH_001
```
Actual output:
```
view: audit_export
  campaign_id_opaque: cd6053e39a1a525eb5c80466458d6299b482e192987e0159f429cc932c18520c
  campaign_status: PAUSED
  provenance: [['campaign_id_opaque', 'cd6053e39a1a525eb5c80466458d6299b482e192987e0159f429cc932c18520c'], ['campaign_mode', 'synthetic'], ['campaign_scope', 'MVA_SCIENTIFIC'], ['campaign_status', 'PAUSED'], ['event_count', '4']]
  supersessions: [['not recorded', 'no supersession recorded']]
  scoped_sharing: ['no scoped sharing grants recorded']
  plain_language_account: ['Campaign purpose recorded as: Preclinical investigation of NAD/BubR1 mechanism', 'Status is PAUSED with 4 journal events retained', 'Pause/cancel recorded through outbox.stop; journal events remain readable', 'Handoff next_action=OPERATOR_REVIEW; task_refs=1; reconciliation_required=0']
  event_ids: ['dcb7e597-113d-47d9-9979-7aef390c8233', 'baf49964-ffb2-4705-a549-8fbdd13c99fe', '74edd9a0-0f51-4a3a-8de8-e964a750098c', '9c37bcc8-ef50-4aaf-b6c1-115b527a6763']
  event_count: 4
  handoff: {'campaign_ref': 'cd6053e39a1a525eb5c80466458d6299b482e192987e0159f429cc932c18520c', 'status': 'PAUSED', 'task_refs': ['395405f41d8e0b47686473903d416a0918066624b6d9e407615767862318c025'], 'event_ids': ['dcb7e597-113d-47d9-9979-7aef390c8233', 'baf49964-ffb2-4705-a549-8fbdd13c99fe', '74edd9a0-0f51-4a3a-8de8-e964a750098c', '9c37bcc8-ef50-4aaf-b6c1-115b527a6763'], 'reconciliation_required': [], 'next_action': 'OPERATOR_REVIEW'}
  history_survived_stop: True
  content_digest: sha256:a7b03e340758eaec5ab73ed34b4bbeee89741626c5828ce7011762bf51aa5dfe
  available_actions:
    - outbox.handoff [enabled] via rarepipe.stages.network.outbox
```

---

## 10. Verification at Known Revision

### Recorded Revision and Environment
Verification was performed on macOS (darwin, arm64) under Python 3.12.13 at git revision:
- **Git HEAD**: `ee890c5f60fef623126e5837b31023481db408ab`
- **Dirty State**: `True` (T13 implementation files in working directory: `src/rarepipe/stages/network/cli.py`, `docs/network/RUNBOOK.md`, `tests/test_network_t13.py`)

### Is this record still current?

A runbook records the revision its verification actually ran at. Work continuing past that point
does not make the record wrong — it makes it **stale**, and a reader has to be able to tell which.
Check before citing any number below as describing the current code:

```bash
uv run python -m rarepipe.stages.network.cli verify runbook-revision
```

It reports `CURRENT` or `STALE` with the number of commits since, and exits 0 either way: a
historical record is not a defect. If it reports `STALE`, re-run the verification in this section
and regenerate section 11 before quoting the results.

Verify the environment with the verification CLI:
```bash
uv run python -m rarepipe.stages.network.cli verify environment
```
Actual output:
```
Network Runtime & Baseline Verification Environment:
  python_version              : 3.12.13
  git_head                    : ee890c5f60fef623126e5837b31023481db408ab
  git_dirty                   : True
  controlled_drive_path       : /Volumes/Lexar/rarepipe_work/MVA_001/prospective
  controlled_drive_mounted    : True
  baseline_plan_id            : PP_MVA_001_RH_001@0002-455419f1
  baseline_plan_head_matches  : True
  rules_version               : stage10-rules-1.1.0
  scientific_readiness_gaps   : 112
```

### Static Invariant Scanner
Verify all static invariants (no randomized seeds, no literal digests, latent truth containment, model immutability):
```bash
uv run python tools/network/check_invariants.py
```
Actual output:
```json
{
  "status": "NETWORK_INVARIANTS_HOLD",
  "files_scanned": {
    "source": 24,
    "tests": 13
  },
  "checked": {
    "process_random_hash": "no seed derives from Python's process-randomised hash()",
    "literal_digest": "no sha256 digest is written by hand",
    "latent_reachable": "hidden world truth is named only where it is defined or scored",
    "piped_pytest": "no pytest invocation reports a pipe's exit status",
    "snapshot_mutation": "no immutable record is edited through model_copy(update=)"
  },
  "not_checked": [
    "whether the science is right",
    "whether a delegated module's behaviour matches its own tests",
    "anything requiring the code to run — this scan is static by design"
  ],
  "findings": []
}
```

### Non-Integration Test Suite Run
The suite is run with:
```bash
uv run pytest -q -m "not integration"
```
Real process exit status: 0

Execution summary:
```
606 passed, 8 skipped in 68.42s
```

#### Detailed Record of Skipped Tests (8 Total)
Pytest skipped exactly 8 tests across 2 files due to deliberately unprovisioned external components:
1. `tests/test_baseline_solver.py:97` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
2. `tests/test_baseline_solver.py:105` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
3. `tests/test_baseline_solver.py:119` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
4. `tests/test_baseline_solver.py:134` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
5. `tests/test_baseline_solver.py:148` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
6. `tests/test_baseline_solver.py:175` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
7. `tests/test_baseline_solver.py:188` — `no provisioned Exomiser (set RAREPIPE_EXOMISER_HOME / RAREPIPE_EXOMISER_DATA)`
8. `tests/test_track1.py:187` — `official evaluation.py not provisioned (set RAREPIPE_TRACK1_SCORER)`

#### Integration-Marked Tests
- **Integration tests excluded**: `0` (no test currently carries the `integration` mark).
- Future integration tests that exercise authentic institutional email exchanges will require live SMTP credentials, verified human recipient contact routes, and an active human clinical lead appointment.

---

## 11. Acceptance Map

Generated from the test suite by `collect_acceptance_map()` (AST inspection of every
`tests/test_*.py`), not transcribed from the PRD. Regenerate with:

```bash
uv run python -m rarepipe.stages.network.cli verify acceptance-map
```

**What this table is, and is not.** It indexes each acceptance ID to the tests whose name or
docstring mentions it, so a reviewer can run any row directly. It does **not** measure whether
the criterion is exercised: a test that names `A08` and asserts nothing would appear here
exactly the same. Treat `NAMED_BY_TEST` as "here is where to look", and read the cited tests
to decide whether the criterion actually holds. Every defect found in review of T05, T06, T07,
T09, T11 and T12 was in a task whose own tests passed, which is the reason for this caution.

This table is an **index built from test names and docstrings**, so a reviewer can run any row with `uv run pytest -q <node_id>`. `NAMED_BY_TEST` means a test names the ID; it is not evidence that the criterion is exercised, and only reading the cited tests establishes that. `NOT_NAMED_BY_ANY_TEST` is a definite gap.

| ID | Status | PRD Requirement | Test Node ID(s) naming this ID |
|---|---|---|---|
| A01 | **NAMED_BY_TEST** | Each seeded node has a source, node type and explicit unknown availability/permission fields. | `tests/test_network_t02.py::test_a01_node_unknown_defaults_and_native_types`<br>`tests/test_network_t03.py::test_a01_every_seeded_node_has_source_url_type_and_unknown_fields` |
| A02 | **NAMED_BY_TEST** | A public profile match cannot become a confirmed resource or collaboration without a new evidence event. | `tests/test_network_t02.py::test_a02_public_match_needs_new_institutional_event`<br>`tests/test_network_t03.py::test_a02_match_carries_no_confirmed_resource_and_requires_new_evidence_event`<br>`tests/test_network_t06.py::test_a07_an_unparsed_reply_claims_nothing_about_the_node` |
| A03 | **NAMED_BY_TEST** | Exact intervention mismatches survive ingestion; NMN findings cannot become nicotinic-acid observations. | `tests/test_network_t02.py::test_a03_intervention_mismatch_survives`<br>`tests/test_network_t03.py::test_a03_question_routes_preserve_intervention_identity`<br>`tests/test_network_t06.py::test_a03_exact_intervention_mismatch_survives_ingestion` |
| A04 | **NAMED_BY_TEST** | Blood-only NAD evidence cannot close the relevant-cell or functional question. | `tests/test_network_t02.py::test_a04_blood_cannot_satisfy_intracellular_question`<br>`tests/test_network_t06.py::test_a04_blood_compartment_cannot_close_intracellular_question` |
| A05 | **NAMED_BY_TEST** | Unknown endpoints and missing interpretive fields stay unknown. | `tests/test_network_t02.py::test_a05_missing_interpretation_stays_unknown_after_roundtrip`<br>`tests/test_network_t06.py::test_a05_missing_fields_stay_unknown_without_defaults` |
| A06 | **NAMED_BY_TEST** | Two replies about one original study do not become independent replication or duplicate reward. | `tests/test_network_t02.py::test_a06_shared_family_is_not_replication_and_independence_needs_reason`<br>`tests/test_network_t06.py::test_a06_shared_study_deduplicates_family_not_independent_replication`<br>`tests/test_network_t09.py::test_a06_invalidating_the_credited_family_clears_the_question_value`<br>`tests/test_network_t09.py::test_a06_relabelling_one_study_under_a_new_family_earns_nothing`<br>`tests/test_network_t09.py::test_a06_two_reports_one_study_scored_once` |
| A07 | **NAMED_BY_TEST** | Refusal, no response, no resource, QC failure and informative negative remain distinct. | `tests/test_network_t02.py::test_a07_response_distinctions_and_separate_event_types`<br>`tests/test_network_t06.py::test_a07_an_unclassified_reply_routes_to_a_human_and_infers_nothing`<br>`tests/test_network_t06.py::test_a07_an_unparsed_reply_claims_nothing_about_the_node`<br>`tests/test_network_t06.py::test_a07_five_distinct_outcomes_preserved_through_whole_pipeline`<br>`tests/test_network_t06.py::test_a07_the_five_reply_kinds_stay_distinct_in_ordinary_wording` |
| A08 | **NAMED_BY_TEST** | Native B16 behavior is preserved on the current reduced-division/unknown-benefit fixture; native death and other review routes regress unchanged. | `tests/test_network_t07.py::test_a08_adverse_flag_holds_even_when_unverified`<br>`tests/test_network_t07.py::test_a08_b08_keeps_its_meaning_when_benefit_is_present`<br>`tests/test_network_t07.py::test_a08_b16_and_candidate_signal_require_review`<br>`tests/test_network_t07.py::test_a08_b16_is_not_a_toxicity_or_selection_finding`<br>`tests/test_network_t07.py::test_a08_native_b16_carries_reduced_division_when_benefit_is_unknown`<br>`tests/test_network_t07.py::test_a08_native_death_hold_b09_preserves_hold_with_b16`<br>`tests/test_network_t07.py::test_a08_native_hold_is_preserved_over_policy_routing` |
| A09 | **NAMED_BY_TEST** | Conflicting scientific findings create context comparison/review, not a majority-vote conclusion. | `tests/test_network_t06.py::test_a09_conflicting_findings_produce_context_comparison_not_averaging`<br>`tests/test_network_t07.py::test_a09_conflicting_findings_route_to_context_comparison`<br>`tests/test_network_t07.py::test_a09_contradictory_native_actions_require_human_review` |
| A10 | **NAMED_BY_TEST** | Frozen native plans cannot be mutated; stale edits fail with a conflict. | `tests/test_network_t07.py::test_a10_a_stale_pin_whose_version_is_gone_still_raises_a_conflict`<br>`tests/test_network_t07.py::test_a10_amend_frozen_plan_creates_draft_successor_leaving_frozen_parent_intact`<br>`tests/test_network_t07.py::test_a10_frozen_plan_cannot_be_mutated`<br>`tests/test_network_t07.py::test_a10_stale_edit_fails_with_version_conflict` |
| A11 | **NAMED_BY_TEST** | No persona/agent can sign a required human review or release a scientific freeze. | `tests/test_network_t07.py::test_a11_agent_actor_cannot_freeze_plan`<br>`tests/test_network_t07.py::test_a11_agent_actor_cannot_sign_human_review`<br>`tests/test_network_t07.py::test_a11_candidate_baseline_gaps_block_human_freeze`<br>`tests/test_network_t07.py::test_a11_human_without_required_role_cannot_review` |
| A12 | **NAMED_BY_TEST** | Every live waiting task has an owner and next trigger or a visible unscheduled reason. | `tests/test_network_t04.py::test_a12_waiting_is_a_validated_union_and_timers_are_utc`<br>`tests/test_network_t11.py::test_a12_unowned_waiting_task_is_surfaced_not_dropped` |
| A13 | **NAMED_BY_TEST** | Send/reply retries deduplicate correctly; an ambiguous send enters reconciliation before another transmission. | `tests/test_network_t04.py::test_a13_deduplication_and_unknown_requires_reconciliation`<br>`tests/test_network_t05.py::test_a13_ambiguous_send_reconciles_before_retransmission`<br>`tests/test_network_t05.py::test_a13_deduplication_by_idempotency_key` |
| A14 | **NAMED_BY_TEST** | Revocation, opt-out, exclusion or unset required authorization blocks dispatch, including pending retries. | `tests/test_network_t04.py::test_a14_unset_limits_allow_preparation_but_block_dispatch`<br>`tests/test_network_t05.py::test_a14_a_referenced_authorization_belonging_to_another_sender_is_refused`<br>`tests/test_network_t05.py::test_a14_direct_campaign_exclusions_block_dispatch`<br>`tests/test_network_t05.py::test_a14_intermediary_exclusion_blocks_dispatch`<br>`tests/test_network_t05.py::test_a14_naming_an_authorization_does_not_widen_its_envelope`<br>`tests/test_network_t05.py::test_a14_opt_out_blocks_dispatch`<br>`tests/test_network_t05.py::test_a14_revocation_blocks_pending_retry_after_reconciliation`<br>`tests/test_network_t05.py::test_a14_revocation_invalidates_pending_queued_sends_and_retries`<br>`tests/test_network_t05.py::test_a14_unset_authorization_blocks_dispatch` |
| A15 | **NAMED_BY_TEST** | Synthetic contributions and synthetic learning feedback cannot cross into real campaign stores. | `tests/test_network_t02.py::test_a15_live_campaign_rejects_synthetic_contribution_and_feedback`<br>`tests/test_network_t08.py::test_a15_synthetic_contribution_cannot_enter_live_campaign`<br>`tests/test_network_t11.py::test_a15_synthetic_scenario_label_survives_summary_projection` |
| A16 | **NAMED_BY_TEST** | Hidden world truth is absent from policy inputs, prompts and UI payloads supplied during decisions. | `tests/test_network_t08.py::test_a16_policy_observation_has_no_latent_keys_by_introspection`<br>`tests/test_network_t09.py::test_a16_scorer_sees_hidden_truth_without_policy_leak`<br>`tests/test_network_t11.py::test_a16_a_scenario_view_cannot_be_hand_built_around_the_redaction`<br>`tests/test_network_t11.py::test_a16_latent_truth_absent_from_every_view_payload`<br>`tests/test_network_t11.py::test_a16_post_hoc_review_can_reveal_but_says_so`<br>`tests/test_network_t11.py::test_a16_the_real_catalogue_cannot_publish_its_own_hidden_truth` |
| A17 | **NAMED_BY_TEST** | The learner updates persisted parameters from the declared reward; static routing alone fails this test. | `tests/test_network_t10.py::test_a17_persisted_parameters_change_from_declared_reward` |
| A18 | **NAMED_BY_TEST** | Eligible-action constraints apply to exploration as well as exploitation. | `tests/test_network_t10.py::test_a18_eligibility_masks_constrain_exploration` |
| A19 | **NAMED_BY_TEST** | Fixed and heuristic baselines receive equivalent observations and budgets; held-out splits are checked for leakage. | `tests/test_network_t09.py::test_a19_baselines_share_observations_budgets_and_splits_leakage`<br>`tests/test_network_t10.py::test_a19_learner_and_baselines_share_observations_and_budget`<br>`tests/test_network_t12.py::test_a19_learner_and_baselines_share_observation_and_budget_held_out_never_fit` |
| A20 | **NAMED_BY_TEST** | Repeated fresh-process runs reproduce scoped semantic results with generated digests and honest provenance differences. | `tests/test_network_t08.py::test_a20_fresh_process_runs_reproduce_generated_digest`<br>`tests/test_network_t12.py::test_a20_science_digest_byte_identical_across_fresh_processes` |
| A21 | **NAMED_BY_TEST** | Metrics and narrative are generated from records; each reported rate has its actual count/denominator. | `tests/test_network_t09.py::test_a21_every_reported_rate_has_numerator_and_denominator`<br>`tests/test_network_t12.py::test_a21_report_renders_rates_from_record_not_hand_typed` |
| A22 | **NAMED_BY_TEST** | A later correction or permission change invalidates affected derivatives and pending dependent actions. | `tests/test_network_t07.py::test_a22_source_correction_invalidates_derivatives_suspends_dispatch`<br>`tests/test_network_t12.py::test_a22_correction_invalidates_report_claims` |
| A23 | **NAMED_BY_TEST** | A malicious instruction in an external reply cannot change permissions, execute code or export records. | `tests/test_network_t05.py::test_a23_malicious_instruction_in_reply_is_inert_and_cannot_modify_policy`<br>`tests/test_network_t06.py::test_a23_hostile_instruction_changes_no_permissions_executes_nothing` |
| A24 | **NAMED_BY_TEST** | A contribution's restrictions survive exports, other-case routing, and training selection. | `tests/test_network_t02.py::test_a24_restrictions_roundtrip_and_inherited_use_query`<br>`tests/test_network_t06.py::test_a24_restrictions_survive_intake_and_enforced_downstream`<br>`tests/test_network_t12.py::test_a24_restrictions_survive_export`<br>`tests/test_network_t12.py::test_a24_restrictions_survive_other_case_routing`<br>`tests/test_network_t12.py::test_a24_restrictions_survive_training_selection` |
| A25 | **EXTERNAL_MILESTONE** | An authentic institutional reply is imported with provenance and produces an assessed next action; synthetic inputs cannot pass this milestone. | *None (external milestone: cannot be satisfied by synthetic fixtures)* |
| A26 | **NAMED_BY_TEST** | A partnership reply cannot satisfy an MVA scientific question or imply dataset access. | `tests/test_network_t02.py::test_a26_partnership_cannot_attach_to_mva_question`<br>`tests/test_network_t06.py::test_a26_partnership_reply_cannot_satisfy_mva_scientific_question` |
| A27 | **NAMED_BY_TEST** | A coherent positive scientific branch ends at confirmation/review tasks, with no patient action. | `tests/test_network_t07.py::test_a27_a_patient_directive_is_refused_however_it_is_phrased`<br>`tests/test_network_t07.py::test_a27_actions_are_checked_against_the_engines_closed_vocabulary`<br>`tests/test_network_t07.py::test_a27_coherent_positive_branch_terminates_at_review_no_patient_action`<br>`tests/test_network_t07.py::test_a27_ordinary_preclinical_work_is_not_blocked` |
| A28 | **NAMED_BY_TEST** | Public exports omit private identifiers, case-local paths, recipient details and restricted text unless expressly permitted. | `tests/test_network_t12.py::test_a28_a_private_value_in_an_ordinary_field_is_refused`<br>`tests/test_network_t12.py::test_a28_an_ordinary_simulated_summary_still_exports`<br>`tests/test_network_t12.py::test_a28_export_scan_fails_on_private_terms`<br>`tests/test_network_t12.py::test_a28_patterns_match_notation_not_a_word_list`<br>`tests/test_network_t12.py::test_a28_the_rejection_names_which_rule_fired` |
| A29 | **NAMED_BY_TEST** | The submission index distinguishes implemented, observed, simulated, proposed and unresolved claims. | `tests/test_network_t12.py::test_a29_claim_index_classifications_and_pending_t14` |
| A30 | **NAMED_BY_TEST** | The user can pause/cancel a campaign and obtain a permitted handoff without losing its recorded history. | `tests/test_network_t04.py::test_a30_stop_preserves_history_and_produces_private_reference_handoff`<br>`tests/test_network_t11.py::test_a30_pause_cancel_preserves_recorded_history`<br>`tests/test_network_t11.py::test_a30_the_audit_account_distinguishes_no_handoff_from_one_not_fetched` |

## 12. External Milestone (Task T14 / Acceptance A25)

### Real Status of T14
T14's real status:
- **No verified recipient route**: Candidate institutional addresses in the registry are derived strictly from public directory listings and have not been confirmed by a verified recipient route.
- **No appointed clinical lead**: No human clinician has been appointed to the `treating_clinician` / `clinical_lead` role.
- **No authentic institutional reply**: No authentic reply has been received or imported.
- **Nothing sent**: External sending is disabled by system policy.
- **A25 milestone status**: **PENDING**.

Synthetic fixtures (such as scenario fixtures S01–S16 or simulated intake responses) thoroughly test the intake parsing, deduplication, and adapter machinery, but **cannot satisfy milestone A25**. Only a genuine institutional interaction can satisfy it.

### Next Authorized Action and Who Must Take It
The next authorized action and accountable parties are:
1. **Appointment of Clinical Lead**: An accountable clinical institution or governing body must formally designate a human clinician to the clinical lead role.
2. **Recipient Verification**: A human research operator must verify recipient identity and standing communication routes before outreach.
3. **Standing Authorization**: Execution of outreach must be explicitly authorized with defined cadence and spend limits.
4. **Intake Processing**: An authentic institutional response must be received and imported via the authenticated manual-import interface.
