"""External models are admitted for a reason, not because they exist.

A model may be integrated only if it intersects an unresolved control relationship or a required
benchmark. This generalises a measured result from the simulator phase: a published spindle-
assembly-checkpoint kinetic model would have supplied none of that chain's six unmeasured
parameters, because every one of them sat upstream of the checkpoint, while the SAC model
parameterises the downstream part that was already supported.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from rarepipe.stages.control.provenance import Immutable, Provenance


class Formalism(StrEnum):
    FINITE_STATE = "finite_state"
    LOGICAL = "logical"
    RULE_SYSTEM = "rule_system"
    ALGEBRAIC = "algebraic"
    MONOTONIC = "monotonic"
    INTERVAL = "interval"
    REACTION_NETWORK = "reaction_network"
    ODE = "ode"
    STOCHASTIC = "stochastic"
    STRUCTURAL = "structural"
    EXTERNAL_SIMULATOR = "external_simulator"


class ModelRegistryEntry(Immutable):
    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    formalism: Formalism
    biological_domains: tuple[str, ...] = Field(min_length=1)
    variables_supplied: tuple[str, ...] = ()
    relationship_outputs_supplied: tuple[str, ...] = Field(
        (), description="State variables whose defining relationship this model could supply.")
    parameters_supplied: tuple[str, ...] = ()
    organism: str = Field(min_length=1)
    cell_type: str = Field(min_length=1)
    experimental_context: str = Field(min_length=1)
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    units: str = Field(min_length=1)
    validity_domain: str = Field(min_length=1)
    known_omissions: tuple[str, ...] = ()
    uncertainty: str = Field(min_length=1)
    provenance: Provenance
    license: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    benchmark_for: tuple[str, ...] = ()


class Admission(Immutable):
    model_id: str
    admitted: bool
    reason: str


def admit(entry: ModelRegistryEntry, unresolved_outputs: tuple[str, ...],
          required_benchmarks: tuple[str, ...] = ()) -> Admission:
    supplies = sorted(set(entry.relationship_outputs_supplied) & set(unresolved_outputs))
    benchmarks = sorted(set(entry.benchmark_for) & set(required_benchmarks))
    if supplies:
        return Admission(model_id=entry.model_id, admitted=True,
                         reason=f"supplies an unresolved control relationship for {supplies}")
    if benchmarks:
        return Admission(model_id=entry.model_id, admitted=True,
                         reason=f"required benchmark {benchmarks}")
    return Admission(
        model_id=entry.model_id, admitted=False,
        reason=(f"supplies relationships for {list(entry.relationship_outputs_supplied) or 'none'}; "
                f"the unresolved control relationships are for {list(unresolved_outputs) or 'none'}. "
                "It would add detail where nothing is in doubt and resolve nothing that is."),
    )
