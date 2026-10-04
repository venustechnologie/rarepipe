"""Capability Gap Discovery & Grounding Compiler (Part 2).

The previous phase could say "to build this we would need a piece that does X". This one asks
whether any known piece satisfies that functional specification:

    missing function -> search specification -> candidate -> evidence -> capability -> recompile

**Build authorization: this phase only.** No exhaustive catalogue of genes, drugs, molecules or
proteins. No chemical search engine, no docking, no structure prediction, no molecular dynamics, no
universal biomedical knowledge graph. Those become *providers* behind one interface later; they are
not this compiler.

Three rules carry the design:

* **Agents discover possibilities. Evidence establishes claims. Deterministic code decides whether a
  capability exists.** `CapabilityCandidate -> GroundedCapability` is a transition the validators
  perform and nobody else, and the proposals gate refuses to assign the provenance type a grounded
  capability requires.
* **A component cannot grade its own evidence.** A candidate carries what it asserts separately from
  what any source says, so the two can be compared rather than conflated.
* **Nothing absent from the registry implies anything about biology.** Every negative result names
  the providers searched and the size of their corpora, because a negative from a fifteen-claim
  corpus and a negative from a literature index must not read the same.
"""
from __future__ import annotations

DISCOVERY_PRINCIPLE = (
    "Find anything capable of producing transformation T under constraints C — and when nothing "
    "found survives the audit, reduce the open problem to the one physical relation that no "
    "candidate could satisfy."
)
