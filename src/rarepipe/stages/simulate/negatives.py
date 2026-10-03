"""Private, append-only negative evidence; no campaign or reward integration.

Source records retain their origin. This module generates no simulated biological findings.
External descriptions and references are inert data, not instructions or public exports.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from rarepipe.stages.network.model import (
    AdditionalResponseState, ImmutableModel, Lineage, Origin, inherited_origin,
)
from rarepipe.stages.prospective.model import Knowledge
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.store import ImmutableError, content_digest
from rarepipe.stages.simulate.chain import Support
from rarepipe.stages.simulate.mva import EV_NIACIN_NULL, mva_chain


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MeasuredNull(ImmutableModel):
    state: Literal[ResponseState.MEASURED_NO_EFFECT] = ResponseState.MEASURED_NO_EFFECT
    measured: Text
    finding: Text


class InformativeNegative(ImmutableModel):
    state: Literal[AdditionalResponseState.INFORMATIVE_NEGATIVE] = (
        AdditionalResponseState.INFORMATIVE_NEGATIVE)
    measured: Text
    finding: Text
    validated_controls: Literal[True]
    controls_evidence_ref: Text
    adequate_power: Literal[True]
    power_evidence_ref: Text


class NonResult(ImmutableModel):
    state: Literal[
        ResponseState.NO_RESPONSE, ResponseState.NO_RELEVANT_DATA,
        ResponseState.NOT_SEARCHED, ResponseState.ACCESS_DENIED,
        AdditionalResponseState.NO_RELEVANT_RESOURCE,
        AdditionalResponseState.CANNOT_DISCLOSE, AdditionalResponseState.DECLINED,
        AdditionalResponseState.INVALID_MEASUREMENT,
    ]
    intended_measurement: Text
    reason: Text


Result = Annotated[MeasuredNull | InformativeNegative | NonResult, Field(discriminator="state")]


class NegativeRecord(ImmutableModel):
    target: Text
    tried: Text
    result: Result
    evidence_ref: Text
    origin: Origin
    derived_from: tuple[Lineage, ...] = ()
    predecessor_id: str | None = None
    correction_reason: Text | None = None
    scope_note: str = ""
    chain_measurement: Knowledge = Knowledge.UNKNOWN
    digest_coverage: Literal["all serialized fields except id; canonical-json-v1"] = (
        "all serialized fields except id; canonical-json-v1")
    id: str = ""

    @model_validator(mode="after")
    def _validate_identity(self):
        if self.derived_from and self.origin != inherited_origin(self.derived_from):
            raise ValueError("origin must inherit source lineage")
        if bool(self.predecessor_id) != bool(self.correction_reason):
            raise ValueError("a correction requires both predecessor and reason")
        expected = content_digest(self, exclude={"id"})
        if self.id and self.id != expected:
            raise ValueError("id does not match record content")
        object.__setattr__(self, "id", expected)
        return self


class NegativeStore:
    """In-memory history. Queries include predecessors so corrections cannot erase evidence.

    No general update/delete operation or conversion to network contributions is provided.
    """

    def __init__(self):
        self.__records: dict[str, NegativeRecord] = {}

    def append(self, record: NegativeRecord) -> NegativeRecord:
        # Revalidate at the boundary even if a caller bypassed a model constructor.
        record = NegativeRecord.model_validate(record.model_dump(mode="json"))
        if record.predecessor_id is not None:
            parent = self.get(record.predecessor_id)
            if record.origin != parent.origin:
                raise ImmutableError("a correction cannot change origin")
            if record.target != parent.target:
                raise ImmutableError("a correction cannot change target")
            if record.derived_from != parent.derived_from:
                raise ImmutableError("a correction cannot remove or replace source lineage")
        self.__records.setdefault(record.id, record)
        return self.__records[record.id]

    def get(self, record_id: str) -> NegativeRecord:
        return self.__records[record_id]

    def query(self, target: str, *, origin: Origin | None = None) -> tuple[NegativeRecord, ...]:
        """Return private source records, preserving each result and origin explicitly."""
        selected = Origin(origin) if origin is not None else None
        return tuple(record for record in self.__records.values()
                     if record.target == target and (selected is None or record.origin == selected))

    def authentic_evidence(self, target: str) -> tuple[NegativeRecord, ...]:
        return self.query(target, origin=Origin.AUTHENTIC_INSTITUTIONAL)


def seed_mva_null(store: NegativeStore) -> NegativeRecord:
    """Retain the chain's source assertion, including its unverified retrieval status.

    The chain does not identify the experimental readout; do not invent one from its target.
    A reported null and missing mechanistic measurements are distinct facts.
    """
    edge = next(edge for edge in mva_chain().edges
                if edge.support is Support.CONTRADICTED and edge.evidence_ref == EV_NIACIN_NULL)
    return store.append(NegativeRecord(
        target=edge.target, tried=edge.source,
        result=MeasuredNull(measured="Experimental readout unspecified in the chain source",
                            finding=edge.scope_note),
        evidence_ref=EV_NIACIN_NULL, origin=Origin.PUBLIC_EVIDENCE,
        scope_note=f"{edge.scope_note}; {edge.caveat}",
        chain_measurement=Knowledge.NOT_REPORTED,
    ))
