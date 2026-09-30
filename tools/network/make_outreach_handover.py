#!/usr/bin/env python3
"""Generate the outreach handover: who to contact, what to ask, and why.

This is the document handed to the people responsible for the child — the treating clinician and
the family — so *they* can decide whether to contact anyone. Rarepipe does not send anything:
external send is disabled in policy, and every request this project composes is a prepared, unsent
draft.

Generated from the seed registry and the live composer so it cannot drift from the system. Nothing
here is transcribed by hand.

Usage: uv run python tools/network/make_outreach_handover.py [--out docs/network/OUTREACH_HANDOVER.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rarepipe.stages.network.compose import ScientificRequestComposer  # noqa: E402
from rarepipe.stages.network.model import CampaignScope  # noqa: E402
from rarepipe.stages.network.registry import load_seed  # noqa: E402
from rarepipe.stages.prospective.model import Actor, ActorType, Role  # noqa: E402

PLACEHOLDER_SENDER = "<the accountable sender's address>"


def build(out: Path) -> Path:
    registry = load_seed()
    campaign = registry.get_campaign("cmp-mva-001")
    questions = {q.id: q for q in campaign.questions}
    nodes = registry.all_nodes()
    leads = {n.id: registry.get_lead(n.id) for n in nodes}
    sender = Actor(identity=PLACEHOLDER_SENDER, actor_type=ActorType.HUMAN,
                   roles=(Role.RESEARCH_OPERATIONS,))

    L: list[str] = []
    w = L.append
    w("# Who to contact, and what to ask")
    w("")
    w("Generated from the capability registry and the live message composer by")
    w("`tools/network/make_outreach_handover.py`. Regenerate it rather than editing it.")
    w("")
    w("## What this is")
    w("")
    w("A list of research groups and services that, from their **public** work, look able to answer")
    w("one of the open questions about this child's biology — and, for each, the exact question we")
    w("would put to them and the smallest useful thing they could send back.")
    w("")
    w("**Nothing here has been sent.** External sending is switched off in this software. Every")
    w("message below is a prepared draft. Whether to contact anyone, and who signs the message, is")
    w("a decision for the treating clinician and the family, not for this project.")
    w("")
    w("Each entry says plainly what is **public fact** about that group and what remains")
    w("**unconfirmed**. A group appearing here has not agreed to anything, has not been asked, and")
    w("may hold nothing relevant. Their listed capability is what their own publications and pages")
    w("say, not a commitment.")
    w("")
    w("## The questions we would be asking")
    w("")
    w("| ID | Question we would ask | What an answer could change |")
    w("|---|---|---|")
    for qid in sorted(questions):
        q = questions[qid]
        w(f"| {qid} | {q.text or '*not recorded*'} | {q.decision} |")
    w("")
    w("## The groups")
    w("")
    by_tier: dict[int, list] = {}
    for node in nodes:
        by_tier.setdefault(leads[node.id].ranking_tier, []).append(node)
    for tier in sorted(by_tier):
        w(f"### Priority {tier}")
        w("")
        for node in sorted(by_tier[tier], key=lambda n: n.institution):
            lead = leads[node.id]
            title = node.institution + (f" — {node.group}" if node.group else "")
            w(f"#### {title}")
            w("")
            w(f"- **Questions they could speak to:** {', '.join(lead.questions)}")
            w(f"- **Why them:** {lead.candidate_rationale}")
            w(f"- **Public source:** {node.source.reference}")
            if lead.sourced_evidence:
                w("- **Established from public sources:**")
                for item in lead.sourced_evidence:
                    w(f"  - {item}")
            if lead.inferred:
                w("- **Our inference, not established:**")
                for item in lead.inferred:
                    w(f"  - {item}")
            if lead.confirmation_remains:
                w("- **Still to confirm with them:**")
                for item in lead.confirmation_remains:
                    w(f"  - {item}")
            route = node.contact_route.recipient if node.contact_route else None
            w(f"- **Contact route:** {route or 'not recorded'} — "
              f"**{'unverified' if not (node.contact_route and node.contact_route.verification) else 'verified'}**; "
              "a person must confirm the right recipient before anything is sent.")
            w(f"- **Do they hold a suitable resource?** {node.resource_available} "
              "(unknown until they say so)")
            w(f"- **Permission to analyse?** {node.analysis_permission} (unknown until they say so)")
            w("")
    w("## What one of these messages actually says")
    w("")
    w("Produced by the composer for the first group and first question below, unedited:")
    w("")
    first = sorted(nodes, key=lambda n: (leads[n.id].ranking_tier, n.institution))[0]
    first_q = questions[leads[first.id].questions[0]]
    drafted = ScientificRequestComposer().compose(campaign, first_q, first, sender=sender)
    w("```")
    w(drafted.content)
    w("```")
    w("")
    w("Every message is built the same way: it names the sender and their role, states one bounded")
    w("question, says why this group specifically, offers five ways to reply including a plain")
    w("referral or a short explanation, states what we will not disclose, and gives a one-line way")
    w("to decline and stop all further contact.")
    w("")
    w("## What is deliberately not in the message")
    w("")
    w("- The child's exact genetic variants, their position, or anything identifying them.")
    w("- Any request for a sample, a dataset, or patient records.")
    w("- Any claim that a clinical lead has been appointed when none has.")
    w("- Any suggestion of treatment. These are laboratory questions about cells.")
    w("")
    w("## Before any of this is sent, a person must")
    w("")
    w("1. Confirm the right recipient at each group. Every route above is unverified.")
    w("2. Decide who signs it. The software leaves the sender blank on purpose.")
    w("3. Appoint a clinical lead, or leave that line saying none is appointed — it must not be")
    w("   implied.")
    w("4. Approve the content. Nothing sends itself.")
    w("")
    scopes = {leads[n.id].campaign_scope for n in nodes}
    assert scopes == {CampaignScope.MVA_SCIENTIFIC}, scopes
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[2] / "docs/network/OUTREACH_HANDOVER.md")
    args = ap.parse_args()
    written = build(args.out)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
