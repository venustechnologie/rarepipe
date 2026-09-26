"""The four discovery lanes, and the guard that changes at this stage.

Every earlier stage refused any query that looked like a search for a treatment. Stage 08 is the
stage where that search becomes the point, so the therapy filter is lifted — and only that filter.
The case-identity guard is unchanged: no coordinate, allele, HGVS, rsID or phenotype combination
leaves the machine, at any stage, for any reason.
"""

from __future__ import annotations

from rarepipe.stages.adjudicate.disclosure import check_query
from rarepipe.stages.discovery.model import Lane

# question, reason, queries
LANE_TASKS: list[tuple[Lane, str, str, list[str]]] = [
    (Lane.A_DIRECT_RESTORATION,
     "KT_D01 — What pharmacological interventions have experimentally changed BUBR1 abundance, stability or "
     "relevant function?",
     "Lane A: direct restoration is what SPEC_001 route A asks for.",
     ["BUBR1 protein level increased compound treatment",
      "BUB1B BUBR1 expression restored pharmacological agent",
      "BUBR1 degradation inhibitor proteasome mitosis"]),
    (Lane.B_DEFICIENT_RESCUE,
     "KT_D02 — What pharmacological interventions have improved a relevant phenotype in BUB1B-deficient cells, "
     "MVA cells or BUB1B models?",
     "Lane B: SPEC_001 route B — direct evidence in the deficient biology, even if BUBR1 is untouched.",
     ["BUB1B deficient cells drug treatment chromosome segregation improved",
      "mosaic variegated aneuploidy cells compound rescue phenotype",
      "aneuploidy reduced small molecule checkpoint deficient cells"]),
    (Lane.D_FAILURE,
     "KT_D03 — What interventions have been tested in BUB1B/MVA-related biology and failed to improve the "
     "intended phenotype?",
     "Lane D: observed failure is evidence. Absence of evidence is not.",
     ["BUB1B treatment failed no improvement",
      "mosaic variegated aneuploidy therapy unsuccessful outcome",
      "chromosome instability compound no significant effect aneuploidy"]),
    (Lane.D_FAILURE,
     "KT_D04 — What approved medicines or mechanisms reduce BUBR1, weaken the mitotic checkpoint or increase "
     "missegregation?",
     "The forbidden direction. Anything here disqualifies a candidate however well it matches the pathway.",
     ["drug weakens spindle assembly checkpoint aneuploidy induced",
      "compound reduces BUBR1 expression mitotic",
      "chemotherapy chromosome missegregation increased checkpoint inhibition"]),
    (Lane.C_MECHANISTIC_LEAD,
     "KT_D05 — Have any approved medicines been proposed or tested for MVA, BUB1B deficiency or mechanistically "
     "adjacent chromosome-instability syndromes?",
     "Lane C: a proposal is not evidence, and the distinction must survive into the artifact.",
     ["mosaic variegated aneuploidy management treatment reported",
      "chromosome instability syndrome drug repurposing proposed",
      "aneuploidy syndrome therapeutic approach patient"]),
]


def check_intervention_query(query: str) -> str:
    """Case-identity guard only. The therapy filter is lifted here, and nowhere else."""
    check_query(query)
    return query
