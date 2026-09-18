"""The disclosure boundary must be enforced, not merely documented."""

from __future__ import annotations

import pytest

from rarepipe.stages.adjudicate.disclosure import DisclosureRefused, approval_gate, case_specific_reasons, check_query

SAFE = [
    "BUB1B",
    "BUB1B[gene] AND (functional assay OR mitotic checkpoint)",
    "BUB1B mosaic variegated aneuploidy compound heterozygous",
    "https://rest.uniprot.org/uniprotkb/O60566.json",
    "clinvar variant_summary.txt.gz",
]
# Invented, and deliberately so: a guard against disclosing case identity must not be tested
# with the case's own identifiers. Every value below is fabricated for the shape, not the content.
CASE_SPECIFIC = [
    "chr7:11111111 C>T",
    "7:11111111",
    "NM_999999.9:c.1111G>A",
    "p.(Arg111Cys)",
    "R111C EXAMPLE1",
    "rs111111111",
    "ClinVar VariationID: 111111",
    "HP:0000001 HP:0000002",
]


@pytest.mark.parametrize("query", SAFE)
def test_gene_level_queries_are_allowed(query):
    assert check_query(query) == query
    assert case_specific_reasons(query) == []


@pytest.mark.parametrize("query", CASE_SPECIFIC)
def test_case_specific_queries_are_refused(query):
    with pytest.raises(DisclosureRefused) as exc:
        check_query(query)
    assert "gene-level or bulk retrieval only" in str(exc.value).lower()
    assert case_specific_reasons(query)


def test_exact_variant_retrieval_requires_an_approval_gate():
    with pytest.raises(DisclosureRefused) as exc:
        approval_gate("exact-variant ClinVar API lookup")
    assert "explicit operator approval" in str(exc.value)
