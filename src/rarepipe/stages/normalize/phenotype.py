"""HPO identity normalization against a pinned ontology release.

For each supplied identifier: is it a real concept, is it current, what is its
canonical id and label. Obsolete terms are never silently replaced: an
unambiguous `replaced_by` is followed and recorded; `consider`-only terms stay
unresolved. Polarity is never inferred from a term merely being listed.
"""

from __future__ import annotations

from rarepipe.resources.hpo import Ontology
from rarepipe.stages.normalize.model import HpoTermNormalized


def normalize_term(source_id: str, source_polarity: str, asset_id: str, onto: Ontology | None) -> HpoTermNormalized:
    polarity = source_polarity if source_polarity in ("observed", "excluded") else "unspecified"
    basis = "source_document" if polarity != "unspecified" else "default_unspecified"
    base = dict(source_id=source_id, polarity=polarity, polarity_basis=basis, source_asset_id=asset_id)
    if onto is None:
        return HpoTermNormalized(**base, status="not_validated")

    term = onto.terms.get(source_id)
    if term is None and source_id in onto.alt_index:
        primary = onto.terms[onto.alt_index[source_id]]
        return HpoTermNormalized(**base, status="secondary_id", canonical_id=primary.id, label=primary.name,
                                 replacement_basis="ontology_alt_id", branches=onto.branches(primary.id))
    if term is None:
        return HpoTermNormalized(**base, status="unknown")
    if not term.is_obsolete:
        return HpoTermNormalized(**base, status="active", canonical_id=term.id, label=term.name, branches=onto.branches(term.id))
    replacements = [r for r in term.replaced_by if r in onto.terms and not onto.terms[r].is_obsolete]
    if len(replacements) == 1:
        new = onto.terms[replacements[0]]
        return HpoTermNormalized(**base, status="obsolete_replaced", canonical_id=new.id, label=new.name,
                                 replacement_basis="ontology_replaced_by", consider_ids=term.consider, branches=onto.branches(new.id))
    return HpoTermNormalized(**base, status="obsolete_no_replacement", label=term.name, consider_ids=term.consider)
