"""A controlled functional vocabulary, so one transformation does not become fifty phrasings.

Two sources can describe the same capability in different words — "enhances the spindle checkpoint"
and "increases mitotic arrest competence". Agents may propose that those are the same thing; the
normalisation that actually counts resolves against a closed vocabulary, which is the state model's
own variables plus the nodes the evidence inventory uses. A term that resolves to nothing is not
added: it is reported as outside the vocabulary, because a capability the compiler cannot connect to
a state variable cannot change any verdict.

The synonym table is small and explicit on purpose. It is not a general ontology, and nothing is
inferred from string similarity — "checkpoint-associated marker" is not "checkpoint activation", and
guessing that it is would be exactly the false equivalence this layer exists to catch.
"""
from __future__ import annotations

from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.realization.evidence import EvidenceInventory
from rarepipe.stages.control.state_space import StateSpace

# Phrasings a source may use for a vocabulary term. Each entry is a restatement of the same
# transformation, never a related or downstream one.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "checkpoint_activation": ("mitotic arrest competence", "spindle assembly checkpoint activation",
                              "arrest competence"),
    "checkpoint_silencing": ("checkpoint silencing", "timely mitotic exit",
                             "checkpoint satisfaction"),
    "chromosome_alignment": ("chromosome alignment", "metaphase alignment"),
    "nad_intracellular": ("intracellular NAD", "intracellular NAD pool"),
    "nad_whole_blood": ("whole-blood NAD", "circulating NAD"),
    "bubr1_abundance": ("BubR1 abundance", "BubR1 protein level"),
    "bubr1_residual_function": ("BubR1 residual function", "checkpoint-competent BubR1 activity"),
    "pp2a_b56_recruitment": ("PP2A-B56 recruitment", "phosphatase recruitment"),
}


class Vocabulary(Immutable):
    terms: tuple[str, ...]
    synonyms: tuple[tuple[str, str], ...] = ()

    def resolve(self, term: str) -> str | None:
        """The vocabulary term a phrase denotes, or None. Never a guess."""
        cleaned = term.strip()
        if cleaned in self.terms:
            return cleaned
        lowered = cleaned.lower()
        for phrase, canonical in self.synonyms:
            if phrase.lower() == lowered:
                return canonical
        return None

    def outside(self, term: str) -> bool:
        return self.resolve(term) is None


def vocabulary(space: StateSpace, inventory: EvidenceInventory) -> Vocabulary:
    """Derived: the state model's variables and the inventory's nodes, nothing invented."""
    terms = set(space.names)
    for edge in inventory.edges:
        terms.update({edge.source, edge.target})
    pairs = tuple(sorted((phrase, canonical) for canonical, phrases in SYNONYMS.items()
                         if canonical in terms for phrase in phrases))
    return Vocabulary(terms=tuple(sorted(terms)), synonyms=pairs)


def dedup_key(candidate) -> tuple[str, ...]:
    """Two candidates asserting the same transformation from the same sources are one candidate."""
    return (candidate.claimed_output, candidate.claimed_direction.value,
            *sorted(candidate.required_inputs), *sorted(candidate.supporting_evidence_refs))
