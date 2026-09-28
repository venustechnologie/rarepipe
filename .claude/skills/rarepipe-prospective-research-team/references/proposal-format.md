# Proposal handoff format version 1.0

Use this format for agent proposals, not observations, accepted plan fields or native Rarepipe imports. Keep each proposed item linked to actual source gaps; if the gap list is unavailable, leave source IDs empty and mapping UNVERIFIED. Do not invent field paths or claim a validated import.

## Document fields

Set `schema_version` to `1.0`, `document_type` to `M5_AGENT_PROPOSAL`, `producer.actor_type` to `AGENT`, and record the role, model and workflow version when known. Pin baseline and plan references where available; null means uninspected or unknown and needs a reason in `baseline.limitations`.

Set the boundary to PUBLIC_ONLY or LOCAL_PRIVATE_APPROVED. The latter requires an actual authorization reference and permitted runner, not a persona label. Keep `automatic_external_action`, `clinical_action`, `real_plan_freeze` and `human_signoff_created` false. New agent proposals carry no new human reviews.

## Work items

Each item contains:

- `id`, real `source_gap_ids`, `source_gap_mapping`, proposed `field_path` or null, and `question`.
- `status`: DRAFT_PROPOSAL, READY_FOR_HUMAN_REVIEW, NEEDS_EXTERNAL_EVIDENCE or NEEDS_DESIGN_DECISION.
- `proposal`: recommended value/option or null, rationale, alternatives, explicit conditions and limitations.
- `basis`: kind, source references, calculation references and assumption labels.
- `required_reviewer_roles`, a precise `reviewer_question`, and `next_action`.

Basis kinds are EVIDENCE_DERIVED, DESIGN_CHOICE, MODELLING_ASSUMPTION, UNVERIFIED_PRIOR and UNRESOLVED. A design can combine sources and judgement; document that mixture rather than making it look measured. EVIDENCE_DERIVED requires references to retrieved evidence, not just identifiers mentioned elsewhere. UNVERIFIED_PRIOR cannot be READY_FOR_HUMAN_REVIEW.

READY_FOR_HUMAN_REVIEW requires a non-null recommendation, rationale, alternatives or an explained absence of alternatives, limitations, conditions and a precise reviewer question. It means a decision packet is prepared; it never implies approval or laboratory feasibility. If an essential empirical prerequisite remains unknown, use NEEDS_EXTERNAL_EVIDENCE or clearly make the decision under review conditional rather than asserting the prerequisite.

## Evidence references

Give each source an ID, locator, retrieval status, provenance note, scope and source location. Add a content hash when bytes are available. A URL is a locator, not proof of retrieval. Allowed retrieval states: STORED_FULL_TEXT, STORED_ABSTRACT, STORED_SUPPLEMENT, VERIFIED_PROJECT_ARTIFACT and NOT_RETRIEVED. Verify quotations against the actual stored text before using them.

## Checks

`scripts/check_proposal.py` checks shape, reference consistency, selected draft/review conditions and the four non-action flags. It cannot validate a citation's truth, authenticate a person, inspect runner permissions, assess science or replace the native plan validator. Passing it means HANDOFF_FORMAT_OK only.

Keep the review packet and critique beside the proposals. A real authenticated human decision should be recorded by the project's existing review workflow, linked to the exact resulting content. Do not add a new human signoff to this agent-authored document.
