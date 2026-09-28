from pathlib import Path

from rarepipe.stages.track2.pitch_check import MappedSentence, check, sentences

PITCH = """# Pitch

Our top prediction matched the confirmed pair. Nicotinic acid treats lipid disorders.
We have not established a treatment.
"""


def test_every_sentence_must_trace_to_an_artifact():
    mapping = [MappedSentence(sentence="Our top prediction matched the confirmed pair.", status="supported",
                              supported_by=["SC_001"]),
               MappedSentence(sentence="Nicotinic acid treats lipid disorders.", status="not_in_artifact",
                              note="no indication recorded")]
    results = check(PITCH, mapping, artifact_text='{"id": "SC_001"}')
    by = {r.text: r for r in results}
    assert len(results) == 3 and sentences(PITCH)[0].startswith("Our top")
    assert not by["Our top prediction matched the confirmed pair."].fails
    assert by["Nicotinic acid treats lipid disorders."].fails
    assert by["We have not established a treatment."].status == "unmapped"


def test_a_cited_id_must_exist_and_absolutes_are_flagged():
    mapping = [MappedSentence(sentence="Our top prediction matched the confirmed pair.", status="supported",
                              supported_by=["SC_999"])]
    [first, *_] = check("Our top prediction matched the confirmed pair. It will never fail.", mapping, "SC_001")
    assert first.missing_ids == ["SC_999"] and first.fails
    second = check("It will never fail.", [MappedSentence(sentence="It will never fail.", status="editorial")], "")[0]
    assert any("never" in f for f in second.flags) and not second.fails
