# M5 packet tooling

Scripts used to build the M5 decision packet with the `rarepipe-prospective-research-team` skill.
They read `rarepipe prospective validate --json` and write into a packet directory outside the
immutable plan store; none of them touches a plan version, a review record or the case state.

| Script | What it does |
|---|---|
| `mk_gap_register.py` | Builds the gap register from the validator output: every real gap copied verbatim, grouped into work packages. Never invents a gap from a reported total. |
| `revise_proposals.py` | Applies the independent critique's accepted findings to `proposals.json`. |
| `fix_gap_ids.py` | Re-derives every proposal's `source_gap_ids` from the register, so a hand-typed field path can never stand in for a real one. |

Paths are currently pinned to the MVA_001 workspace on the controlled drive. Re-point them before
reuse. Validate the result with the skill's `scripts/check_proposal.py`, which checks the handoff
format only — not the science, the sources, or scientific readiness.
