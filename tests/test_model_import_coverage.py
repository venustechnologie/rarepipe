"""Importing a published checkpoint model would supply none of this chain's unknowns."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "network"))

from model_import_coverage import CHECKPOINT_MODEL_SUPPLIES, DOMAIN_OF, check  # noqa: E402

from rarepipe.stages.simulate.mva import mva_chain  # noqa: E402


def test_the_import_would_supply_none_of_the_unknowns():
    """The decisive answer to 'should we import BioModels SAC models to fill our parameters'.

    All six sit upstream of the checkpoint — pharmacokinetics, transport, sirtuin enzymology,
    protein stability, and this variant's residual function. A SAC kinetic model parameterises MCC
    assembly and checkpoint signalling, which is downstream and already supported.
    """
    report = check()
    # The property is that the import supplies none of them, not how many there are. Asserting a
    # count would mean that connecting a new piece of evidence broke a test about coverage.
    assert report["unmeasured_parameters"] > 0
    assert report["a_checkpoint_model_could_supply"] == 0
    for row in report["parameters"]:
        assert row["a_published_checkpoint_model_could_supply_it"] is False
        assert row["why_not"], row["parameter"]


def test_the_edges_an_import_would_cover_carry_no_unknowns():
    """It would add dynamics to the part that is already supported."""
    report = check()
    assert report["edges_an_imported_model_would_cover"]
    assert report["unmeasured_parameters_on_those_edges"] == []


def test_every_unmeasured_parameter_has_a_recorded_domain():
    """An unassigned parameter would silently count as unsuppliable, which is the wrong default:
    it would make the conclusion look stronger than the analysis."""
    for parameter in mva_chain().unknown_parameters():
        assert parameter.name in DOMAIN_OF, parameter.name
        assert DOMAIN_OF[parameter.name] != "unassigned"


def test_the_conclusion_would_flip_if_a_domain_were_suppliable():
    """The analysis must follow from the domain assignment, not be hard-coded.

    If a parameter's domain were one a checkpoint model covers, the report must say so — otherwise
    the tool is asserting its conclusion rather than deriving it.
    """
    original = DOMAIN_OF["k_nad_to_sirt2"]
    try:
        DOMAIN_OF["k_nad_to_sirt2"] = CHECKPOINT_MODEL_SUPPLIES[0]
        report = check()
        assert report["a_checkpoint_model_could_supply"] == 1
        row = next(r for r in report["parameters"] if r["parameter"] == "k_nad_to_sirt2")
        assert row["a_published_checkpoint_model_could_supply_it"] is True
        assert row["why_not"] is None
    finally:
        DOMAIN_OF["k_nad_to_sirt2"] = original

    assert check()["a_checkpoint_model_could_supply"] == 0


def test_the_report_names_what_would_change_the_answer():
    report = check()
    assert "NAD transport" in report["what_would_change_this"]
    assert any("biological judgement" in n for n in report["not_checked"])
