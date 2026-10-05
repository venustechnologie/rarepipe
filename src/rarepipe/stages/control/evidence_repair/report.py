"""Render the evidence-repair delta and the full-recompile delta. Generated, never edited."""
from __future__ import annotations

import json

from rarepipe.stages.control.evidence_repair.recompile import LayerDelta
from rarepipe.stages.control.evidence_repair.records import RepairLedger

NO_RECOMMENDATION = (
    "Nothing in this document is a treatment recommendation. The human trial connected here "
    "reports that administered niacin raised muscle NAD in myopathy patients under that study's "
    "conditions. It does not say that niacin should be given to this child, that it would reach "
    "the relevant cells, or that it would do anything to the protein in question."
)


def render_evidence_delta(ledger: RepairLedger, deltas: tuple[LayerDelta, ...]) -> str:
    L: list[str] = []
    w = L.append
    w("# Evidence repair delta — MVA_001")
    w("")
    w("> The test is not whether the old answer survives. The test is whether the answer changes "
      "correctly when the evidence changes.")
    w("")
    w(f"Ledger `{ledger.ledger_version}` · baseline captured at commit "
      f"`{ledger.baseline.captured_at_commit}` · {len(ledger.repairs)} repairs, all at the evidence "
      "layer. No downstream verdict was edited by hand.")
    w("")

    w("## What prompted this")
    w("")
    w("A backward grounding audit over every load-bearing citation — the forward rule run over "
      "claims the system already believed. Of the citations the causal chain rests on:")
    w("")
    w("| Audit state | Count (before repair) |")
    w("|---|---|")
    for state, count in sorted(ledger.audit_summary.items()):
        w(f"| `{state}` | {count} |")
    w("")
    w("Two attributions were disqualified. One was already known. The other was found only because "
      "the audit was run over everything rather than over the one that had already failed.")
    w("")

    for repair in ledger.repairs:
        w(f"## {repair.repair_id} — `{repair.edge_id}`")
        w("")
        w(f"**Kind:** `{repair.kind.value}`")
        w("")
        w("**Before**")
        w("")
        w(f"- claim version: `{repair.previous_claim_version}`")
        w(f"- source assignment: {repair.previous_source_assignment or '*none*'}")
        w(f"- verdict: `{repair.previous_verdict}`")
        if repair.previous_scope_note:
            w(f"- scope: {repair.previous_scope_note}")
        w("")
        w("**Audit**")
        w("")
        w(f"- verdict: "
          f"`{repair.audit_verdict.value if repair.audit_verdict else 'not an audit failure'}`")
        w(f"- {repair.reason_for_invalidation}")
        w("")
        w("**Recovery of the intended reference**")
        w("")
        w(f"- outcome: `{repair.recovery.outcome.value}`")
        w("- searched inside the project:")
        for place in repair.recovery.searched_in_project:
            w(f"    - {place}")
        if repair.recovery.external_queries:
            w("- targeted external queries:")
            for query in repair.recovery.external_queries:
                w(f"    - `{query}`")
        w(f"- {repair.recovery.finding}")
        w("")
        w("**After**")
        w("")
        w(f"- claim version: `{repair.new_version}`")
        w(f"- source assignment: {repair.new_source_assignment or '*none*'}")
        w(f"- support level: `{repair.new_support_level}`")
        if repair.new_scope_note:
            w(f"- scope: {repair.new_scope_note}")
        w("")
        w(f"**Why this state and not another.** {repair.computed_not_chosen}")
        w("")
        if repair.needs_human_decision:
            w(f"**Needs a human decision.** {repair.needs_human_decision}")
            w("")
        affected = [d for d in deltas if repair.repair_id in d.attributed_to and d.changed]
        w("**Downstream effects**")
        w("")
        if affected:
            for delta in affected:
                moved = sorted(k for k in set(delta.before) | set(delta.after)
                               if delta.before.get(k) != delta.after.get(k))
                w(f"- `{delta.layer}`: {', '.join(moved)}")
        else:
            w("- none; no recomputed layer moved on account of this repair alone")
        w("")

    w("## The counterintuitive one")
    w("")
    w("Withdrawing the refutation made the result **weaker**, not stronger. The direct precursor "
      "route used to be excluded from propagation as falsified; it is now an assertion with no "
      "evidence either way, so it contributes and the propagated verdict is capped by it. The "
      "system stopped knowing something it never had grounds for, and the honest consequence is "
      "that it now knows less.")
    w("")
    w("## What this is not")
    w("")
    w(NO_RECOMMENDATION)
    w("")
    return "\n".join(L) + "\n"


def render_recompile_delta(ledger: RepairLedger, deltas: tuple[LayerDelta, ...]) -> str:
    L: list[str] = []
    w = L.append
    w("# Full recompile delta — MVA_001")
    w("")
    w("> Evidence correction → epistemic correction → model correction → architecture correction.")
    w("")
    w("Every layer below was recomputed from the repaired evidence in dependency order. No verdict "
      "was edited by hand. A layer that did not move still has a line, because \"unchanged\" "
      "without a reason is indistinguishable from \"not recomputed\".")
    w("")
    w(f"Baseline captured at commit `{ledger.baseline.captured_at_commit}`; "
      f"{sum(1 for d in deltas if d.changed)} of {len(deltas)} layers moved.")
    w("")
    w("| # | Layer | Moved | Following |")
    w("|---|---|---|---|")
    for delta in deltas:
        w(f"| {delta.position} | `{delta.layer}` | {'**yes**' if delta.changed else 'no'} | "
          f"{', '.join(delta.attributed_to) or '—'} |")
    w("")

    for delta in deltas:
        w(f"## {delta.position}. `{delta.layer}`")
        w("")
        w(f"**{'Changed' if delta.changed else 'Unchanged'}.** {delta.why}.")
        w("")
        keys = sorted(set(delta.before) | set(delta.after))
        moved = [k for k in keys if delta.before.get(k) != delta.after.get(k)]
        if moved:
            w("| Observable | Before | After |")
            w("|---|---|---|")
            for key in moved:
                before = json.dumps(delta.before.get(key), sort_keys=True)
                after = json.dumps(delta.after.get(key), sort_keys=True)
                w(f"| `{key}` | `{before[:160]}` | `{after[:160]}` |")
            w("")
        unchanged = [k for k in keys if k not in moved]
        if unchanged:
            w(f"Unchanged in this layer: {', '.join(f'`{k}`' for k in unchanged)}.")
            w("")

    w("## What did not change, and why that matters")
    w("")
    w("The binding constraint on the whole case is unchanged. The chain to missegregation is still "
      "capped by whether this child's altered protein functions at restored abundance, and the "
      "control compiler is still indeterminate for exactly that reason. The repair corrected what "
      "the repository believed about its own evidence; it did not move the question the case turns "
      "on, and it was not expected to.")
    w("")
    w("## What this is not")
    w("")
    w(NO_RECOMMENDATION)
    w("")
    return "\n".join(L) + "\n"
