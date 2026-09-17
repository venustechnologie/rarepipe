"""Cross-profile stability. A plain comparison table, deliberately not a statistical model.

The question is only: do the top hypotheses survive reasonable analytical choices,
and which candidates exist *only* because of one of the two varied decisions?
"""

from __future__ import annotations

from rarepipe.stages.baseline.model import GeneRankRow, PairOverlap, ProfileResult, Stability

TOP_TABLE_SIZE = 20


def best_rank_by_gene(result: ProfileResult) -> dict[str, int]:
    """A gene may appear once per mode of inheritance; its best (lowest) rank represents it."""
    best: dict[str, int] = {}
    for c in result.candidates:
        if c.gene_symbol not in best or c.rank < best[c.gene_symbol]:
            best[c.gene_symbol] = c.rank
    return best


def top_genes(ranks: dict[str, int], n: int) -> list[str]:
    return [g for g, _ in sorted(ranks.items(), key=lambda kv: (kv[1], kv[0]))[:n]]


def comp_het_genes(result: ProfileResult) -> set[str]:
    return {c.gene_symbol for c in result.candidates if c.is_variant_pair}


def compare(results: list[ProfileResult], profile_filter_policy: dict[str, bool], profile_term_count: dict[str, int]) -> Stability:
    completed = [r for r in results if r.status == "completed"]
    if len(completed) < 2:
        return Stability(profiles_compared=[r.profile_id for r in completed], pairwise=[], top_gene_table=[],
                         genes_only_when_non_pass_permitted=[], genes_only_with_eighth_term=[], genes_in_all_profiles=[],
                         verdict="insufficient", verdict_basis=f"{len(completed)} profile(s) completed; at least 2 are needed to compare.")

    ranks = {r.profile_id: best_rank_by_gene(r) for r in completed}
    ids = [r.profile_id for r in completed]

    pairwise = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ta, tb = top_genes(ranks[a], 1), top_genes(ranks[b], 1)
            pairwise.append(PairOverlap(
                profile_a=a, profile_b=b,
                top1_same_gene=(ta[0] == tb[0]) if ta and tb else None,
                top5_gene_overlap=len(set(top_genes(ranks[a], 5)) & set(top_genes(ranks[b], 5))),
                top10_gene_overlap=len(set(top_genes(ranks[a], 10)) & set(top_genes(ranks[b], 10))),
                top20_gene_overlap=len(set(top_genes(ranks[a], 20)) & set(top_genes(ranks[b], 20))),
                compound_het_gene_overlap=len(comp_het_genes(next(r for r in completed if r.profile_id == a))
                                              & comp_het_genes(next(r for r in completed if r.profile_id == b))),
            ))

    union_top = sorted({g for pid in ids for g in top_genes(ranks[pid], TOP_TABLE_SIZE)},
                       key=lambda g: (min(ranks[pid].get(g, 10**9) for pid in ids), g))
    table = [GeneRankRow(gene_symbol=g, ranks={pid: ranks[pid].get(g) for pid in ids},
                         best_rank=min(ranks[pid].get(g, 10**9) for pid in ids),
                         appears_in_profiles=sum(1 for pid in ids if g in ranks[pid]))
             for g in union_top[:TOP_TABLE_SIZE]]

    # a gene present only in profiles that permit non-PASS records (and in none that drop them)
    permits = [p for p in ids if profile_filter_policy.get(p)]
    drops = [p for p in ids if not profile_filter_policy.get(p)]
    only_non_pass = sorted({g for p in permits for g in top_genes(ranks[p], TOP_TABLE_SIZE)}
                           - {g for p in drops for g in ranks[p]}) if permits and drops else []

    max_terms = max(profile_term_count.values(), default=0)
    wider = [p for p in ids if profile_term_count.get(p) == max_terms]
    narrower = [p for p in ids if profile_term_count.get(p, 0) < max_terms]
    only_eighth = sorted({g for p in wider for g in top_genes(ranks[p], TOP_TABLE_SIZE)}
                         - {g for p in narrower for g in ranks[p]}) if wider and narrower else []

    in_all = sorted(set.intersection(*[set(top_genes(ranks[p], TOP_TABLE_SIZE)) for p in ids])) if ids else []
    movement = {g: max(r for r in (row.ranks[p] for p in ids for row in [next(x for x in table if x.gene_symbol == g)]) if r is not None)
                - min(r for r in (row.ranks[p] for p in ids for row in [next(x for x in table if x.gene_symbol == g)]) if r is not None)
                for g in [row.gene_symbol for row in table if row.appears_in_profiles == len(ids)]}

    top1 = {top_genes(ranks[p], 1)[0] for p in ids if top_genes(ranks[p], 1)}
    top5_overlaps = [p.top5_gene_overlap for p in pairwise]
    if len(top1) == 1 and all(o >= 4 for o in top5_overlaps):
        verdict, basis = "stable", "every profile agrees on the top gene and ≥4/5 of the top-5 genes."
    elif len(top1) == 1:
        verdict, basis = "partially_stable", "profiles agree on the top gene but their top-5 sets differ."
    elif any(o >= 3 for o in top5_overlaps):
        verdict, basis = "partially_stable", f"top gene differs across profiles ({len(top1)} distinct), but top-5 sets overlap substantially."
    else:
        verdict, basis = "unstable", f"profiles disagree on the top gene ({len(top1)} distinct) with little top-5 overlap."

    return Stability(profiles_compared=ids, pairwise=pairwise, top_gene_table=table,
                     genes_only_when_non_pass_permitted=only_non_pass, genes_only_with_eighth_term=only_eighth,
                     genes_in_all_profiles=in_all, max_rank_movement=movement, verdict=verdict, verdict_basis=basis)
