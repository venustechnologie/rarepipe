"""Generated reports, public exports and the submission claim index (A21–A24, A28, A29).

Every figure and every sentence is derived from a stored run record or repository artifact.
Never transcribe a rate, count or digest into prose — that failed here once and reached a reviewer.
A simulated improvement is not a clinical benefit and must not read as though it were.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

from rarepipe.stages.network.adapter import InvalidationReport, NativePlanAdapter
from rarepipe.stages.network.model import Contribution, ImmutableModel, UsePurpose
from rarepipe.stages.network.sim.reward import ReportedRate, RewardScorer
from rarepipe.stages.prospective.store import content_digest

REPO_ROOT = Path(__file__).resolve().parents[4]

# Field names that must never leave a public export (A28).
RESTRICTED_FIELD_NAMES: frozenset[str] = frozenset({
    "recipient", "case_ref", "exact_variant", "variant", "position",
    "genomic_position", "private_path", "responder", "private_recipient",
    "nearest_variant", "variant_clue",
})

ALWAYS_PRIVATE = re.compile(
    r"private:[\w\-./]+|/Users/|/Volumes/|/private/tmp|\.private\.json",
    re.I,
)

# Dropping restricted FIELD NAMES does not protect a case identifier or an exact variant written
# into an ordinary field's value — `{"caveat": "derived from the MVA_001 baseline"}` and
# `{"note": "chr15:40,000,000 BUB1B c.2211-1G>A"}` both exported cleanly. The caller can pass
# `private_terms`, but an export that is only safe when the caller remembers is not safe.
#
# These match notation rather than vocabulary: HGVS and genomic coordinates have a defined syntax,
# so this generalises to variants nobody listed. It is a floor, not a guarantee — free text can
# always describe a case without using its notation, which is why export is a human decision.
VARIANT_NOTATION = re.compile(
    r"\b[cgmnrp]\.\d+[+-]?\d*\s*(?:[ACGTU]+\s*>\s*[ACGTU]+|del|dup|ins|fs|_)"
    r"|\bp\.(?:[A-Z][a-z]{2}|[A-Z])\d+(?:[A-Z][a-z]{2}|[A-Z*]|fs|Ter)",
)
GENOMIC_COORDINATE = re.compile(
    r"\bchr(?:[1-9]|1\d|2[0-2]|[XYM]|MT)\s*[:\-]\s*[\d,._]{3,}",
    re.I,
)
CASE_IDENTIFIER = re.compile(r"\b[A-Z]{2,12}_\d{3,4}\b")
# Simulated ids are lower-case and hyphenated ("network-sim-split-v1", "family-favourable"),
# so this shape belongs to case references and does not fire on anything the runner emits.

STRUCTURAL_PRIVATE: tuple[tuple[re.Pattern[str], str], ...] = (
    (ALWAYS_PRIVATE, "private reference or local path"),
    (VARIANT_NOTATION, "exact variant notation"),
    (GENOMIC_COORDINATE, "genomic coordinate"),
    (CASE_IDENTIFIER, "case identifier"),
)

RATE_INTERVAL_NOTE = (
    "Replicate-level episode rates are binomial in the episode, so they carry the event "
    "count and a Wilson interval. Catalogue coverage checks and design digests are not "
    "sampling rates of that kind — when no interval applies, the record states why."
)


class ClaimClassification(StrEnum):
    OBSERVED = "observed"
    IMPLEMENTED = "implemented"
    SIMULATED = "simulated"
    PROPOSED = "proposed"
    UNRESOLVED = "unresolved"


class ExportRejected(ValueError):
    """Public export refused after a private-term scan hit (fail, do not warn)."""

    def __init__(self, findings: list[str]):
        super().__init__("public export rejected: " + "; ".join(findings))
        self.findings = findings


class ClaimIndexEntry(ImmutableModel):
    claim_id: str
    statement: str
    classification: ClaimClassification
    artifact: str | None = None
    source_refs: tuple[str, ...] = ()
    pending_external_milestone: str | None = None
    next_authorized_action: str | None = None
    invalid: bool = False
    invalidation_reason: str | None = None
    content_digest: str | None = None

    def with_digest(self) -> ClaimIndexEntry:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return ClaimIndexEntry(**data)


class SubmissionClaimIndex(ImmutableModel):
    generated_from: str
    entries: tuple[ClaimIndexEntry, ...]
    content_digest: str | None = None

    def with_digest(self) -> SubmissionClaimIndex:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return SubmissionClaimIndex(**data)


class GeneratedReport(ImmutableModel):
    """A report whose claims can be invalidated when a later correction arrives (A22)."""

    run_science_digest: str
    markdown: str
    claim_index: SubmissionClaimIndex
    invalid: bool = False
    invalidation_reasons: tuple[str, ...] = ()
    generated_at_label: str = "derived_from_run_record"


def format_reported_rate(rate: ReportedRate | dict[str, Any]) -> str:
    """Render a rate from its stored numerator/denominator — never a hand-typed percentage."""
    if isinstance(rate, dict):
        rate = ReportedRate(**{
            k: rate[k] for k in (
                "name", "numerator", "denominator", "point", "interval_lo", "interval_hi",
                "interval_method", "interval_applies", "no_interval_reason",
            ) if k in rate
        })
    n, d = rate.numerator, rate.denominator
    if d == 0:
        reason = rate.no_interval_reason or "denominator is zero"
        return f"{rate.name}: undefined ({n}/{d}; {reason})"
    point = rate.point if rate.point is not None else (n / d)
    if rate.interval_applies and rate.interval_lo is not None and rate.interval_hi is not None:
        method = rate.interval_method or "interval"
        return (
            f"{rate.name}: {point:.1%} ({n}/{d}, {method} "
            f"{rate.interval_lo:.1%}–{rate.interval_hi:.1%})"
        )
    reason = rate.no_interval_reason or "no interval applies for this sampling unit"
    return f"{rate.name}: {point:.1%} ({n}/{d}; {reason})"


def _rate_from_run(rates: dict[str, Any], key: str) -> str:
    raw = rates.get(key)
    if raw is None:
        return f"{key}: not recorded in run"
    return format_reported_rate(raw)


def generate_report_markdown(run: dict[str, Any]) -> str:
    """Generate the full narrative from the run record. No figure is typed by hand."""
    out: list[str] = []
    w = out.append
    rates = run.get("rates") or {}
    science = run.get("science_digest") or {}
    results = run.get("results_digest") or {}
    split = run.get("world_split") or {}
    policy = run.get("policy_version") or {}
    a19 = run.get("a19_equivalence") or {}
    leakage = run.get("leakage_report") or {}

    w("# Research-network evaluation report\n")
    w(
        "Generated from a stored evaluation run record by "
        "`rarepipe.stages.network.report.generate_report_markdown`. "
        "Every figure below is read from that record; none is transcribed by hand.\n"
    )
    w(f"**What carries an interval.** {RATE_INTERVAL_NOTE}\n")
    w(f"> {run.get('caveat', 'No caveat recorded on the run.')}\n")

    w("## What is implemented\n")
    w(
        f"- Evaluation runner: `{run.get('generated_by', 'unknown')}` over split "
        f"`{split.get('split_id', 'unknown')}` (digest `{split.get('content_digest', 'unknown')}`)."
    )
    w(
        f"- Learner: `{policy.get('policy_id', 'unknown')}` / `{policy.get('algorithm', 'unknown')}` "
        f"with parameter digest `{policy.get('parameter_digest', 'unknown')}` "
        f"(updates={policy.get('update_count', 'unknown')}, "
        f"training_events={policy.get('training_events', 'unknown')})."
    )
    w(
        "- Baselines compared on the held-out families: fixed expert sequence and eligible-node "
        "heuristic, sharing the observation contract and resource budget with the learner."
    )
    w(
        f"- Rules engine version recorded on the run: `{run.get('rules_version', 'unknown')}`.\n"
    )

    w("## What was observed\n")
    w(f"- {_rate_from_run(rates, 'learner_held_out')}")
    w(f"- {_rate_from_run(rates, 'expert_held_out')}")
    w(f"- {_rate_from_run(rates, 'heuristic_held_out')}")
    leak_rate = rates.get("leakage")
    if isinstance(leak_rate, dict) and "numerator" in leak_rate and "denominator" in leak_rate:
        w(f"- {format_reported_rate({
            'name': str(leak_rate.get('name', 'held_out_family_leakage')),
            'numerator': int(leak_rate['numerator']),
            'denominator': int(leak_rate['denominator']),
            'interval_applies': bool(leak_rate.get('interval_applies', True)),
            'no_interval_reason': leak_rate.get('no_interval_reason'),
        })}")
    w(
        f"- Split leakage check passed={leakage.get('passed', 'unknown')}; "
        f"held-out families fit during training={a19.get('held_out_families_fit', 'unknown')}."
    )
    w(
        f"- A19 shared observation contract={a19.get('same_observation_contract', 'unknown')}; "
        f"shared budget={a19.get('same_budget', 'unknown')}; "
        f"held-out learner epsilon={a19.get('learner_epsilon_held_out', 'unknown')}.\n"
    )

    w("## What is simulated\n")
    w(
        "- World families, institutional replies, and the toy benchmark reward are synthetic. "
        "They exercise the software loop; they are not authentic institutional measurements."
    )
    w(
        "- Any apparent learner improvement over a baseline is a simulated engineering outcome "
        "under the declared synthetic reward. It is **not** a clinical benefit and must not be "
        "read as evidence about a patient, a drug effect, or a real laboratory's willingness to help.\n"
    )

    w("## What remains proposed\n")
    w(
        "- Live email transport provider selection remains an operator decision "
        "(standing authorization still cannot bypass EXTERNAL_SEND)."
    )
    w(
        "- Role appointments (clinical lead, scientific adjudicator, research operator) have no "
        "real people assigned in this deployment.\n"
    )

    w("## What is unresolved\n")
    w(
        "- The authentic institutional pilot (external milestone T14) is not complete. "
        "A synthetic fixture cannot mark it complete."
    )
    w(
        "- Scientific thresholds, effect sizes, sample sizes, exposures and permissions that the "
        "native plan still lists as unknown remain unknown; this evaluation does not populate them.\n"
    )

    w("## Limitations\n")
    w(
        f"- Master seed `{run.get('master_seed', 'unknown')}`; seed derivation: "
        f"{run.get('seed_derivation', 'not recorded')}."
    )
    w(
        f"- Code revision `{run.get('code_revision', 'unknown')}`, dirty={run.get('dirty', 'unknown')}, "
        f"python `{run.get('python', 'unknown')}`."
    )
    w(
        f"- Science digest `{science.get('sha256', 'unknown')}` — {science.get('covers', '')}"
    )
    w(
        f"- Results digest `{results.get('sha256', 'unknown')}` — {results.get('covers', '')}"
    )
    w(
        "- Produced by the same engineering process that wrote the learner it evaluates; "
        "agreement with baselines is a self-test, not independent biological replication.\n"
    )
    return "\n".join(out) + "\n"


def restricted(name: str) -> bool:
    """True when a field name is on the public-export drop list (A28)."""
    token = name.strip().casefold().replace("-", "_")
    if token in RESTRICTED_FIELD_NAMES:
        return True
    if token.endswith("_recipient") or token.startswith("private_"):
        return True
    if "variant" in token and token not in {"variant_count_public"}:
        return True
    return False


def _drop_restricted(obj: Any, *, path: str = "$") -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if restricted(str(k)):
                continue
            out[k] = _drop_restricted(v, path=f"{path}.{k}")
        return out
    if isinstance(obj, list):
        return [_drop_restricted(v, path=f"{path}[{i}]") for i, v in enumerate(obj)]
    return obj


def _scan_private_terms(obj: Any, patterns: list[re.Pattern[str]], *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(_scan_private_terms(v, patterns, path=f"{path}.{k}"))
        return hits
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_scan_private_terms(v, patterns, path=f"{path}[{i}]"))
        return hits
    if isinstance(obj, str):
        structural = len(STRUCTURAL_PRIVATE)
        for n, pattern in enumerate(patterns):
            if pattern.search(obj):
                rule = (STRUCTURAL_PRIVATE[n][1] if n < structural
                        else f"caller-supplied private term #{n - structural + 1}")
                hits.append(f"{path}: matched output-policy rule '{rule}'")
    return hits


def contribution_may_export(contribution: Contribution) -> bool:
    return contribution.may_use(UsePurpose.PUBLIC_EXPORT)


def contribution_may_route_other_case(contribution: Contribution, *, other_case_ref: str) -> bool:
    """A24: case-scoped grants do not authorize another case."""
    del other_case_ref  # other_case is a separate boolean grant, not implied by case_ref match
    return contribution.may_use(UsePurpose.OTHER_CASE)


def contribution_may_select_for_training(contribution: Contribution) -> bool:
    """A24: restrictions survive training selection — no policy_training grant ⇒ refused."""
    return contribution.may_use(UsePurpose.POLICY_TRAINING)


def build_public_export_payload(
    *,
    run: dict[str, Any] | None = None,
    contributions: Iterable[Contribution] = (),
    private_terms: Iterable[str] = (),
    permit_restricted_text: bool = False,
) -> dict[str, Any]:
    """Build a public export. Refuses restricted text unless a recorded permission allows it.

    Scans the produced payload for case-private terms and raises ``ExportRejected`` on a hit
    rather than warning (A28).
    """
    contributions = tuple(contributions)
    exported_contributions: list[dict[str, Any]] = []
    for contrib in contributions:
        if not contribution_may_export(contrib):
            if permit_restricted_text:
                raise ExportRejected([
                    f"contribution {contrib.id}: permit_restricted_text requires an express "
                    "public_export grant on the contribution; none was recorded"
                ])
            exported_contributions.append({
                "id_opaque": content_digest({"id": contrib.id})[:24],
                "origin": contrib.origin.value,
                "export_status": "omitted_no_public_export_permission",
                "restrictions_survived": contrib.restrictions.model_dump(mode="json"),
            })
            continue
        body = contrib.model_dump(mode="json")
        body = _drop_restricted(body)
        body.pop("campaign_id", None)
        body["restrictions_survived"] = contrib.restrictions.model_dump(mode="json")
        exported_contributions.append(body)

    payload: dict[str, Any] = {
        "export_kind": "network_public",
        "contributions": exported_contributions,
        "restrictions_note": (
            "A contribution's restrictions survive this export, other-case routing checks, "
            "and training selection; they are not widened by export."
        ),
    }
    if run is not None:
        payload["run_summary"] = _drop_restricted({
            "science_digest": (run.get("science_digest") or {}).get("sha256"),
            "results_digest": (run.get("results_digest") or {}).get("sha256"),
            "rates": run.get("rates"),
            "world_split_id": (run.get("world_split") or {}).get("split_id"),
            "caveat": run.get("caveat"),
            "simulated_not_clinical": True,
        })

    patterns = [p for p, _ in STRUCTURAL_PRIVATE] + [
        re.compile(re.escape(t), re.I) for t in private_terms if t
    ]
    hits = _scan_private_terms(payload, patterns)
    if hits:
        raise ExportRejected(hits)
    return payload


def write_public_export(
    path: Path,
    *,
    run: dict[str, Any] | None = None,
    contributions: Iterable[Contribution] = (),
    private_terms: Iterable[str] = (),
) -> Path:
    """Write a public export or raise ``ExportRejected`` before creating the file."""
    payload = build_public_export_payload(
        run=run, contributions=contributions, private_terms=private_terms,
    )
    path = Path(path)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    patterns = [p for p, _ in STRUCTURAL_PRIVATE] + [
        re.compile(re.escape(t), re.I) for t in private_terms if t
    ]
    hits = _scan_private_terms(text, patterns, path="$text")
    if hits:
        raise ExportRejected(hits)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _artifact_exists(rel: str) -> bool:
    return (REPO_ROOT / rel).is_file()


def build_submission_claim_index(run: dict[str, Any]) -> SubmissionClaimIndex:
    """Map important report claims to artifacts. No artifact ⇒ unresolved, not implemented (A29)."""
    entries: list[ClaimIndexEntry] = []

    def add(
        claim_id: str,
        statement: str,
        classification: ClaimClassification,
        artifact: str | None,
        *,
        source_refs: tuple[str, ...] = (),
        pending: str | None = None,
        next_action: str | None = None,
    ) -> None:
        if classification is ClaimClassification.IMPLEMENTED and not (
            artifact and _artifact_exists(artifact)
        ):
            classification = ClaimClassification.UNRESOLVED
            pending = pending or "missing_software_artifact"
            next_action = next_action or f"add or locate artifact for {claim_id}"
        entries.append(ClaimIndexEntry(
            claim_id=claim_id, statement=statement, classification=classification,
            artifact=artifact, source_refs=source_refs,
            pending_external_milestone=pending, next_authorized_action=next_action,
        ).with_digest())

    science_sha = (run.get("science_digest") or {}).get("sha256")
    add(
        "eval-runner-implemented",
        "An evaluation runner trains the tabular learner and compares both baselines on the world split.",
        ClaimClassification.IMPLEMENTED,
        "src/rarepipe/stages/network/evaluate.py",
        source_refs=("T12", "A19", "A20"),
    )
    add(
        "report-generated-from-record",
        "The evaluation narrative is generated from the stored run record, not hand-transcribed.",
        ClaimClassification.IMPLEMENTED,
        "src/rarepipe/stages/network/report.py",
        source_refs=("A21",),
    )
    add(
        "held-out-rates-observed",
        "Held-out episode reward rates were observed under the synthetic benchmark declaration.",
        ClaimClassification.OBSERVED,
        "src/rarepipe/stages/network/evaluate.py",
        source_refs=(f"science_digest:{science_sha}", "rates"),
    )
    add(
        "world-families-simulated",
        "World families and institutional replies used in evaluation are synthetic simulations.",
        ClaimClassification.SIMULATED,
        "src/rarepipe/stages/network/sim/splits.py",
        source_refs=("world_split",),
    )
    add(
        "live-transport-proposed",
        "A live authenticated email transport provider remains an operator proposal, not selected here.",
        ClaimClassification.PROPOSED,
        "src/rarepipe/stages/network/transport.py",
        source_refs=("T05", "T01 §6"),
    )
    add(
        "authentic-institutional-pilot",
        "Authentic institutional pilot exchange with a real evidence-producing laboratory.",
        ClaimClassification.UNRESOLVED,
        None,
        source_refs=("T14",),
        pending="T14 authentic institutional pilot",
        next_action=(
            "Obtain standing human authorization and an authentic institutional contact "
            "confirmation; do not treat any synthetic scenario fixture as completion."
        ),
    )
    add(
        "claim-without-artifact",
        "A placeholder claim that has no software artifact on purpose.",
        ClaimClassification.IMPLEMENTED,
        "src/rarepipe/stages/network/does_not_exist.py",
    )

    entries.append(ClaimIndexEntry(
        claim_id="science-digest-recorded",
        statement="A science digest over simulated content was recorded beside its coverage definition.",
        classification=(
            ClaimClassification.OBSERVED if science_sha else ClaimClassification.UNRESOLVED
        ),
        artifact="src/rarepipe/stages/network/evaluate.py",
        source_refs=(f"sha256:{science_sha}",) if science_sha else (),
        pending_external_milestone=None if science_sha else "run_record_missing_science_digest",
        next_authorized_action=None if science_sha else "re-run evaluation to produce digests",
    ).with_digest())

    return SubmissionClaimIndex(
        generated_from=(run.get("science_digest") or {}).get("sha256") or "run-without-digest",
        entries=tuple(entries),
    ).with_digest()


def build_report(run: dict[str, Any]) -> GeneratedReport:
    index = build_submission_claim_index(run)
    return GeneratedReport(
        run_science_digest=(run.get("science_digest") or {}).get("sha256") or "",
        markdown=generate_report_markdown(run),
        claim_index=index,
    )


def invalidate_report_after_correction(
    report: GeneratedReport,
    *,
    adapter: NativePlanAdapter | None = None,
    source_id: str | None = None,
    reason: str,
    actor,
    scorer: RewardScorer | None = None,
    evidence_family_id: str | None = None,
    permission_restricted: bool = False,
    now: datetime | None = None,
) -> tuple[GeneratedReport, InvalidationReport | None]:
    """A22: a later correction invalidates affected derivatives and pending dependent actions.

    Calls ``adapter.invalidate_source`` and ``RewardScorer.invalidate_family`` — does not
    reimplement invalidation. Affected claim-index entries are marked invalid rather than left standing.
    """
    inv: InvalidationReport | None = None
    if adapter is not None and source_id is not None:
        inv = adapter.invalidate_source(
            source_id, reason=reason, actor=actor,
            permission_restricted=permission_restricted,
            now=now or datetime.now(timezone.utc),
        )
    if scorer is not None and evidence_family_id is not None:
        scorer.invalidate_family(evidence_family_id)

    reasons = list(report.invalidation_reasons)
    reasons.append(reason)
    if inv is not None:
        reasons.append(
            f"adapter_invalidation:{inv.id}:proposals={list(inv.affected_proposals)}"
            f":assessments={list(inv.affected_assessments)}"
            f":suspended={list(inv.suspended_dispatch_tasks)}"
        )

    affected_ids = set()
    if inv is not None:
        affected_ids.update(inv.affected_proposals)
        affected_ids.update(inv.affected_assessments)
        if source_id:
            affected_ids.add(source_id)
    if evidence_family_id:
        affected_ids.add(evidence_family_id)

    rate_claim_ids = {
        "held-out-rates-observed", "world-families-simulated", "science-digest-recorded",
    }
    new_entries: list[ClaimIndexEntry] = []
    for entry in report.claim_index.entries:
        refs = set(entry.source_refs) | ({entry.artifact} if entry.artifact else set())
        cites_affected = bool(affected_ids & refs) or (
            evidence_family_id is not None
            and evidence_family_id in "".join(entry.source_refs)
        )
        rate_derivative = (
            evidence_family_id is not None and entry.claim_id in rate_claim_ids
        )
        if cites_affected or rate_derivative or (source_id and source_id in "".join(entry.source_refs)):
            new_entries.append(ClaimIndexEntry(
                claim_id=entry.claim_id,
                statement=entry.statement,
                classification=entry.classification,
                artifact=entry.artifact,
                source_refs=entry.source_refs,
                pending_external_milestone=entry.pending_external_milestone,
                next_authorized_action=(
                    entry.next_authorized_action
                    or "re-evaluate after human review of the corrected source"
                ),
                invalid=True,
                invalidation_reason=reason,
            ).with_digest())
        else:
            new_entries.append(entry)

    refreshed: list[ClaimIndexEntry] = []
    for entry in new_entries:
        if entry.pending_external_milestone and not entry.invalid:
            refreshed.append(ClaimIndexEntry(
                claim_id=entry.claim_id,
                statement=entry.statement,
                classification=entry.classification,
                artifact=entry.artifact,
                source_refs=entry.source_refs,
                pending_external_milestone=entry.pending_external_milestone,
                next_authorized_action=(
                    "Suspend dependent pilot outreach until the correction review completes; "
                    + (entry.next_authorized_action or "")
                ).strip(),
                invalid=False,
                invalidation_reason=None,
            ).with_digest())
        else:
            refreshed.append(entry)

    new_index = SubmissionClaimIndex(
        generated_from=report.claim_index.generated_from,
        entries=tuple(refreshed),
    ).with_digest()
    return GeneratedReport(
        run_science_digest=report.run_science_digest,
        markdown=report.markdown + (
            f"\n## Invalidation\n\nA later correction invalidated affected derivatives: {reason}\n"
        ),
        claim_index=new_index,
        invalid=True,
        invalidation_reasons=tuple(reasons),
    ), inv


def render_claim_index_markdown(index: SubmissionClaimIndex) -> str:
    """Render the claim index from the structured record — classifications are not retyped."""
    lines = [
        "# Submission claim index\n",
        f"Generated from run/artifact digest `{index.generated_from}`.\n",
        "| Claim | Classification | Artifact | Pending milestone | Next authorized action | Invalid |",
        "|---|---|---|---|---|---|",
    ]
    for e in index.entries:
        lines.append(
            f"| {e.claim_id}: {e.statement} | {e.classification.value} | "
            f"{e.artifact or 'none'} | {e.pending_external_milestone or '—'} | "
            f"{e.next_authorized_action or '—'} | {e.invalid} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"
