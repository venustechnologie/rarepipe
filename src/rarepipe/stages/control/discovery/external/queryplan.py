"""Functional specifications become queries. A gap is not a topic.

"What papers discuss BUB1B" is the question this layer exists to stop asking. A query is derived
from the interface: the output required, the direction, the forbidden dependency, the context, and a
class of mechanism that might satisfy it. Searching by the name of the broken gene finds the
literature about the broken gene, which is precisely the literature that cannot contain a bypass.

The mechanism-class dimensions are the one place a model is allowed to be creative, and its output
is only ever a **query string**. It may say where to look. It may not say what was found.

Every query passes the repository's existing guards before it leaves: the case-identity guard from
Stage 04, which no phase lifts, and the therapy filter, so a functional search cannot drift into an
intervention hunt.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.discovery.gaps import CapabilityGap
from rarepipe.stages.control.provenance import Immutable

PLANNER_ID = "functional-literature-query-planner"
PLANNER_VERSION = "0.1.0"

# What a gap's output is called in the literature, so a query can be about the function rather than
# about our variable names. Nothing here is inferred from string similarity.
FUNCTION_TERMS: dict[str, tuple[str, ...]] = {
    "checkpoint_activation": ('"spindle assembly checkpoint"', '"mitotic checkpoint"',
                              '"mitotic arrest"', '"checkpoint signalling"'),
    "checkpoint_silencing": ('"checkpoint silencing"', '"mitotic exit"',
                             '"checkpoint satisfaction"', '"anaphase onset"'),
    "chromosome_alignment": ('"chromosome alignment"', '"chromosome congression"',
                             '"kinetochore-microtubule attachment"', '"error correction"'),
    "pp2a_b56_recruitment": ('"PP2A-B56"', '"phosphatase recruitment"', '"kinetochore phosphatase"'),
    "nad_intracellular": ('"intracellular NAD"', '"tissue NAD"', '"cellular NAD"',
                          '"NAD+ repletion"'),
}

# Mechanism classes to search for, per gap kind. These direct the search; they assert nothing.
MECHANISM_CLASSES: dict[str, tuple[str, ...]] = {
    "bypass": ("alternative signal generator", "downstream arrest machinery",
               "parallel pathway", "compensatory mechanism"),
    "chain": ("transport", "salvage pathway", "precursor supplementation"),
}

_SYSTEM_TERMS = ('"human cells"', '"human cell line"', '"primary human"', "patient-derived")


class PlannedQuery(Immutable):
    query_id: str
    query: str = Field(min_length=1)
    dimension: str = Field(min_length=1, description="What this query is looking for, not a topic.")
    generated_by: str = PLANNER_ID
    rationale: str = Field(min_length=10)


class QueryPlan(Immutable):
    gap_id: str
    planner: str = PLANNER_ID
    planner_version: str = PLANNER_VERSION
    objective: str = Field(min_length=10)
    search_dimensions: tuple[str, ...]
    queries: tuple[PlannedQuery, ...]
    excluded_from_queries: tuple[str, ...] = Field(
        description="What the plan deliberately does not search by, so the omission is visible.")


def plan(gap: CapabilityGap) -> QueryPlan:
    """Derive queries from the interface. Deterministic, so a plan can be audited and replayed."""
    terms = FUNCTION_TERMS.get(gap.required_output, (f'"{gap.required_output.replace("_", " ")}"',))
    kind = "bypass" if gap.forbidden_dependencies else "chain"
    classes = MECHANISM_CLASSES[kind]
    queries: list[PlannedQuery] = []

    for index, term in enumerate(terms, start=1):
        queries.append(PlannedQuery(
            query_id=f"Q{index:02d}", query=f"{term} AND ({' OR '.join(_SYSTEM_TERMS)})",
            dimension=f"the function itself, as {term} is named in the literature",
            rationale="finds work on the required function without naming the altered gene, which is "
                      "where a route independent of it could be reported"))
    for offset, mechanism in enumerate(classes, start=len(queries) + 1):
        queries.append(PlannedQuery(
            query_id=f"Q{offset:02d}",
            query=f'{terms[0]} AND "{mechanism}"',
            dimension=f"mechanism class: {mechanism}",
            rationale="a class of mechanism that could satisfy the interface; the class directs the "
                      "search and asserts nothing about what exists"))
    if kind == "bypass":
        for offset, term in enumerate(terms[:2], start=len(queries) + 1):
            queries.append(PlannedQuery(
                query_id=f"Q{offset:02d}",
                query=f"{term} AND (independent OR bypass OR \"does not require\")",
                dimension="explicit independence claims",
                rationale="papers that state a function occurs without a given component are the "
                          "only ones that could ground a bypass"))

    return QueryPlan(
        gap_id=gap.gap_id,
        objective=(f"{gap.required_transformation}"
                   + (f", without depending on {', '.join(gap.forbidden_dependencies)}"
                      if gap.forbidden_dependencies else "")),
        search_dimensions=tuple(sorted({q.dimension for q in queries})),
        queries=tuple(queries),
        excluded_from_queries=(
            "the case's variants, variant pair, coordinates and HPO terms — the Stage 04 "
            "case-identity guard refuses any query containing them, and this phase does not lift it",
            "intervention and therapy terms — the retrieval module's therapy filter refuses them, so "
            "a functional search cannot become a drug hunt",
        ))
