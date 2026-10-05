import pytest
from pydantic import ValidationError

from rarepipe.stages.network.model import AdditionalResponseState, Lineage, Origin
from rarepipe.stages.prospective.model import Knowledge
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.store import ImmutableError, content_digest
from rarepipe.stages.simulate.mva import BUBR1
from rarepipe.stages.simulate.negatives import (
    InformativeNegative, MeasuredNull, NegativeRecord, NegativeStore, NonResult,
    seed_mva_direct_route_record,
)


def record(**changes):
    data = dict(target="target", tried="intervention", origin=Origin.SYNTHETIC,
                evidence_ref="synthetic fixture", result=MeasuredNull(
                    measured="assay endpoint", finding="No effect detected"))
    data.update(changes)
    return NegativeRecord(**data)


def test_append_only_and_content_addressing():
    store = NegativeStore()
    first = store.append(record())
    assert first.id == content_digest(first, exclude={"id"})
    assert store.append(record()) == first
    assert len(store.query("target")) == 1
    with pytest.raises(ValidationError):
        first.origin = Origin.AUTHENTIC_INSTITUTIONAL
    with pytest.raises(ValidationError):
        first.result.finding = "changed"
    with pytest.raises(ValueError):
        first.model_copy(update={"origin": Origin.AUTHENTIC_INSTITUTIONAL})
    successor = store.append(record(predecessor_id=first.id, correction_reason="Readout corrected",
                                   result=MeasuredNull(measured="corrected endpoint", finding="null")))
    assert successor.id != first.id
    assert store.get(first.id) == first
    assert store.query("target") == (first, successor)
    assert not hasattr(store, "delete") and not hasattr(store, "update")
    with pytest.raises(ValidationError):
        record(id=first.id, tried="different intervention")
    with pytest.raises(KeyError):
        store.append(record(predecessor_id="missing", correction_reason="correction"))


@pytest.mark.parametrize("state", [ResponseState.NO_RESPONSE,
    AdditionalResponseState.DECLINED, AdditionalResponseState.NO_RELEVANT_RESOURCE,
    AdditionalResponseState.INVALID_MEASUREMENT])
def test_measured_null_cannot_be_non_result(state):
    with pytest.raises(ValidationError):
        MeasuredNull(state=state, measured="endpoint", finding="null")
    with pytest.raises(ValidationError):
        NonResult(state=ResponseState.MEASURED_NO_EFFECT, intended_measurement="endpoint",
                  reason="missing")
    data = record().model_dump(mode="json")
    data["result"]["state"] = state.value
    data["id"] = ""
    with pytest.raises(ValidationError):
        NegativeRecord.model_validate(data)
    failure = record(result=NonResult(state=state, intended_measurement="endpoint", reason="failed"))
    store = NegativeStore()
    store.append(failure)
    assert store.query("target")[0].result.state == state
    assert not hasattr(failure.result, "finding")


@pytest.mark.parametrize("field", ["validated_controls", "adequate_power",
                                   "controls_evidence_ref", "power_evidence_ref"])
def test_informative_negative_requires_controls_and_power(field):
    data = dict(measured="endpoint", finding="null", validated_controls=True,
                adequate_power=True, controls_evidence_ref="controls record",
                power_evidence_ref="power analysis record")
    assert InformativeNegative(**data).state == AdditionalResponseState.INFORMATIVE_NEGATIVE
    del data[field]
    with pytest.raises(ValidationError):
        InformativeNegative(**data)
    data[field] = False if field in {"validated_controls", "adequate_power"} else " "
    with pytest.raises(ValidationError):
        InformativeNegative(**data)


def test_seed_preserves_unverified_null_and_missing_chain_measurements():
    store = NegativeStore()
    seeded = seed_mva_direct_route_record(store)
    assert seed_mva_direct_route_record(store) == seeded
    retrieved, = store.query(BUBR1)
    # A store of negative results must not hold a null nobody measured. The invariant is that the
    # recorded state matches what the evidence supports, not that it stays what it once was.
    assert retrieved.result.state == ResponseState.NO_RELEVANT_DATA
    assert "does not support it" in retrieved.result.reason
    assert retrieved.chain_measurement == Knowledge.NOT_REPORTED
    assert "no retrieved source addresses this relation" in retrieved.scope_note
    assert retrieved.origin == Origin.PUBLIC_EVIDENCE
    assert NegativeRecord.model_validate_json(retrieved.model_dump_json()) == retrieved


def test_synthetic_cannot_be_authentic_or_relabelled_by_correction():
    store = NegativeStore()
    first = store.append(record())
    real = store.append(record(origin=Origin.AUTHENTIC_INSTITUTIONAL, evidence_ref="reply"))
    assert store.authentic_evidence("target") == (real,)
    for origin in (Origin.AUTHENTIC_INSTITUTIONAL, Origin.PUBLIC_EVIDENCE):
        with pytest.raises(ImmutableError):
            store.append(record(origin=origin, predecessor_id=first.id, correction_reason="relabel"))
    parent = Lineage(record_id=first.id, origin=Origin.SYNTHETIC)
    with pytest.raises(ValidationError):
        record(origin=Origin.AUTHENTIC_INSTITUTIONAL, derived_from=(parent,))
    forged = NegativeRecord.model_construct(**{
        **first.model_dump(), "result": first.result, "origin": Origin.AUTHENTIC_INSTITUTIONAL})
    with pytest.raises(ValidationError):
        store.append(forged)
    assert store.authentic_evidence("target") == (real,)
