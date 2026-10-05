"""The evidence inventory, derived from the repository rather than typed in.

This is the module that makes fabrication structurally impossible. A capability claim does not
cite a bare identifier it could have invented; it cites an **evidence edge** that already exists in
the case's causal chain, with the support level and scope the chain already records. The inventory
is built by walking `simulate.mva.mva_chain()`, so:

* a capability citing an edge the chain does not contain is refused, not graded;
* a capability cannot improve its own evidence, because the support level comes from the chain;
* when the chain's evidence changes, every entitlement recomputes, and the committed report goes
  stale.

**Why the support level alone is not enough.** Two of the chain's labels are *relative to the
intervention the case was considering*. `different_agent` on the SIRT2 step means the effect was
produced by a different precursor than nicotinic acid; `different_compartment` means the readout
was whole blood rather than the intracellular pool. Those labels are correct for that intervention
and wrong for a different one — a realization that actually uses the agent the experiment used is
not making an agent substitution. So the inventory also carries, per citation, what the measurement
was made *with* and *in*, transcribed from the chain's own scope notes, and the relative penalty
lifts only when the realization matches. A test asserts each transcription still matches the scope
note it came from, so the two cannot drift apart.

**Two questions, kept apart.** Whether the evidence supports a mechanism at all is not whether it
transfers to this child's cells. Folding the second into the first makes every step fail for the
same blanket reason and throws away the only information worth having — *which* step breaks, and
why. So:

* `entitle` answers the mechanistic question, and the chain's own label is authoritative. Where the
  chain flagged a substitution (`different_agent`, `different_compartment`) the realization must
  match on that dimension or the claim does not transfer; where it did not flag one, the support
  level already accounts for it and this module does not second-guess it.
* `transfer_gap` answers the other question separately: the system a measurement was made in versus
  the one the case needs. Almost nothing was measured in patient-derived cells, which is precisely
  why an experiment is needed — and recording that as a gap, rather than as a failure of the
  mechanism, is what lets `CONTEXT_MISMATCH` mean "the mechanism exists, but not here".
"""
from __future__ import annotations

import re

from pydantic import Field

from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.realization.kinds import Effect, Entitlement
from rarepipe.stages.simulate.chain import Support
from rarepipe.stages.simulate.mva import mva_chain

# What each support level entitles us to say, before context is considered. The two relative
# levels are not verdicts about the measurement; they are verdicts about a substitution, and are
# resolved against the required context instead.
_FROM_SUPPORT: dict[Support, Entitlement] = {
    Support.HUMAN_EXPERIMENTAL: Entitlement.SUPPORTED,
    Support.MODEL_EXPERIMENTAL: Entitlement.SUPPORTED,
    Support.CLASS_LEVEL: Entitlement.CONDITIONAL,
    Support.COMPUTATIONAL: Entitlement.CONDITIONAL,
    Support.DIFFERENT_AGENT: Entitlement.CONTEXT_MISMATCH,
    Support.DIFFERENT_COMPARTMENT: Entitlement.CONTEXT_MISMATCH,
    Support.ASSERTED_ONLY: Entitlement.UNSUPPORTED,
    Support.CONTRADICTED: Entitlement.CONTRADICTED,
}

_RELATIVE = {Support.DIFFERENT_AGENT: "agent", Support.DIFFERENT_COMPARTMENT: "compartment"}

# Transcribed from the scope notes of the chain edges named in `transcribed_from`. Nothing here is
# new biology: it is the same sentence, in fields a check can read. `test_realization_evidence.py`
# asserts every `must_appear` term is still present in that edge's scope note.
_CONTEXT: dict[str, dict] = {
    "PMID:42628241": {
        "measured_with": "nicotinic acid",
        "measured_in_compartment": "whole blood",
        "measured_in_system": "healthy adults",
        "transcribed_from": "nicotinic_acid_exposure->nad_whole_blood",
        "must_appear": ("whole-blood", "healthy adults"),
        # Retrieval confirmed this attribution verbatim, so the chain's UNVERIFIED label was lifted.
    },
    "PMID:24825348": {
        "measured_with": "nicotinamide mononucleotide",
        "measured_in_compartment": "",
        "measured_in_system": "aged mice",
        "transcribed_from": "sirt2_activity->k668_acetylation",
        "must_appear": ("NMN", "aged mice"),
    },
    "PMID:20516114": {
        "measured_with": "restored abundance of the altered protein",
        "measured_in_compartment": "",
        "measured_in_system": "model cell systems",
        "transcribed_from": "bubr1_residual_function->checkpoint_activation",
        "must_appear": ("restored-abundance", "checkpoint activation"),
    },
    "PMID:33207204": {
        "measured_with": "domain mutation or removal",
        "measured_in_compartment": "",
        "measured_in_system": "model cell systems",
        "transcribed_from": "bubr1_residual_function->checkpoint_silencing",
        "must_appear": ("domain mutation", "abstract"),
    },
    "PMID:32386566": {
        "measured_with": "nicotinic acid",
        "measured_in_compartment": "intracellular (tissue homogenate)",
        "measured_in_system": "human skeletal muscle",
        "transcribed_from": "nicotinic_acid_exposure->nad_intracellular",
        "must_appear": ("muscle NAD", "matched controls"),
    },
}


def normalise(ref: str) -> str:
    """The bare citation. The chain carries its verification status inside the string."""
    match = re.match(r"[A-Za-z]+:[0-9]+", ref or "")
    return match.group(0) if match else (ref or "")


class ContextRecord(Immutable):
    """What a citation's measurement was made with, and where. Empty means unrecorded, not any."""

    ref: str
    measured_with: str = Field(min_length=1)
    measured_in_compartment: str = ""
    measured_in_system: str = Field(min_length=1)
    transcribed_from: str = Field(min_length=1)

    def dimension(self, name: str) -> str:
        return {"agent": self.measured_with, "compartment": self.measured_in_compartment,
                "system": self.measured_in_system}[name]


class EvidenceEdge(Immutable):
    """One causal claim the repository already holds, with the evidence it already recorded."""

    edge_id: str
    source: str
    target: str
    effect: Effect
    mechanism: str
    support: Support
    ref: str = ""
    verified: bool = Field(
        True, description="False when the chain marks the citation as having no retrieval record.")
    scope: str = ""
    caveat: str = ""

    @property
    def relative_to_intervention(self) -> str:
        return _RELATIVE.get(self.support, "")


class Unentitled(ValueError):
    """A capability cites an evidence edge the repository does not hold."""


class EvidenceInventory(Immutable):
    edges: tuple[EvidenceEdge, ...]
    contexts: tuple[ContextRecord, ...] = ()

    @property
    def edge_ids(self) -> frozenset[str]:
        return frozenset(e.edge_id for e in self.edges)

    def edge(self, edge_id: str) -> EvidenceEdge:
        for item in self.edges:
            if item.edge_id == edge_id:
                return item
        raise Unentitled(
            f"no evidence edge {edge_id!r} in this inventory; a capability may only cite a claim "
            "the repository already holds, so an invented citation has nothing to resolve against")

    def context(self, ref: str) -> ContextRecord | None:
        return next((c for c in self.contexts if c.ref == normalise(ref)), None)

    def edges_into(self, node: str) -> tuple[EvidenceEdge, ...]:
        return tuple(e for e in self.edges if e.target == node)

    def intrinsic(self, ref: str) -> Support:
        """The strongest non-relative support among the edges citing this reference.

        Used only to lift a relative penalty once the realization is shown to match the context the
        measurement was made in. It never strengthens an edge whose own measurement was weak.
        """
        bare = normalise(ref)
        order = [Support.HUMAN_EXPERIMENTAL, Support.MODEL_EXPERIMENTAL, Support.CLASS_LEVEL,
                 Support.COMPUTATIONAL, Support.ASSERTED_ONLY]
        found = {e.support for e in self.edges if normalise(e.ref) == bare}
        for level in order:
            if level in found:
                return level
        return Support.ASSERTED_ONLY


class Entitling(Immutable):
    """Why one capability claim got the entitlement it did. Every field is derived."""

    edge_id: str
    entitlement: Entitlement
    support: Support
    ref: str
    verified: bool
    scope: str
    reason: str
    context_required: str = ""
    context_measured: str = ""
    context_mismatches: tuple[str, ...] = ()
    context_unrecorded: tuple[str, ...] = ()


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def entitle(inventory: EvidenceInventory, edge_id: str, *, agent: str = "",
            compartment: str = "") -> Entitling:
    """What the repository's evidence entitles this step to claim, mechanistically.

    `agent` and `compartment` are what this step declares it operates with and in. They are
    compared only where the chain itself flagged a substitution, because that is where the
    repository judged the dimension to matter; checking every dimension on every edge would flag
    substitutions nobody claimed.
    """
    edge = inventory.edge(edge_id)
    verdict = _FROM_SUPPORT[edge.support]
    context = inventory.context(edge.ref)
    reason = f"the chain records this claim as {edge.support.value}"
    declared = {"agent": agent, "compartment": compartment}
    required, measured = "", ""
    mismatches: list[str] = []

    relative = edge.relative_to_intervention
    if relative and context is not None:
        measured = context.dimension(relative)
        required = declared[relative]
        if _same(required, measured):
            verdict = _FROM_SUPPORT[inventory.intrinsic(edge.ref)]
            reason = (f"the chain labels this {edge.support.value} relative to the intervention it "
                      f"was considering, but this step uses {required!r}, which is what the "
                      "measurement used; the substitution does not apply, so the entitlement falls "
                      f"back to the measurement's own level ({inventory.intrinsic(edge.ref).value})")
        else:
            mismatches.append(f"{relative}: measured with {measured!r}, this step requires "
                              f"{required or 'something it does not declare'!r}")
            reason = (f"the measurement used {measured!r} and this step requires "
                      f"{required or 'something it does not declare'!r}; the {relative} differs, "
                      "so the claim does not transfer")
    elif relative:
        reason = (f"the chain records this as {edge.support.value} and no context was transcribed "
                  "for the citation, so the substitution cannot be checked")

    if verdict is Entitlement.SUPPORTED and not edge.verified:
        verdict = Entitlement.CONDITIONAL
        reason += ("; the citation has no retrieval record, so the claim is conditional on the "
                   "reference being confirmed")
    return Entitling(edge_id=edge_id, entitlement=verdict, support=edge.support, ref=edge.ref,
                     verified=edge.verified, scope=edge.scope, reason=reason,
                     context_required=required, context_measured=measured,
                     context_mismatches=tuple(mismatches))


def transfer_gap(inventory: EvidenceInventory, edge_id: str, *, system: str) -> str:
    """Whether this claim was measured in the system the case needs. Separate from entitlement.

    Almost nothing in this inventory was measured in patient-derived cells, which is the reason an
    experiment exists. Reporting that as a transfer gap rather than as a broken mechanism is what
    keeps `CONTEXT_MISMATCH` meaning "the mechanism exists, but not here".
    """
    edge = inventory.edge(edge_id)
    context = inventory.context(edge.ref)
    if not system:
        return ""
    if context is None:
        return (f"{edge_id}: the citation records no system, so transfer to {system!r} is "
                "unestablished")
    if _same(context.measured_in_system, system):
        return ""
    return (f"{edge_id}: measured in {context.measured_in_system!r}, the case requires "
            f"{system!r}")


def inventory_from_repo() -> EvidenceInventory:
    """Walk the case's causal chain. The inventory is what the repository holds, not a copy of it."""
    edges = []
    for item in mva_chain().edges:
        ref = item.evidence_ref or ""
        edges.append(EvidenceEdge(
            edge_id=f"{item.source}->{item.target}", source=item.source, target=item.target,
            effect=Effect.INCREASE if item.sign == 1 else Effect.DECREASE,
            mechanism=item.mechanism, support=item.support, ref=normalise(ref),
            verified="UNVERIFIED" not in ref, scope=item.scope_note, caveat=item.caveat))
    cited = {e.ref for e in edges if e.ref}
    contexts = tuple(ContextRecord(ref=ref, measured_with=data["measured_with"],
                                   measured_in_compartment=data["measured_in_compartment"],
                                   measured_in_system=data["measured_in_system"],
                                   transcribed_from=data["transcribed_from"])
                     for ref, data in sorted(_CONTEXT.items()) if ref in cited)
    return EvidenceInventory(edges=tuple(sorted(edges, key=lambda e: e.edge_id)),
                             contexts=contexts)
