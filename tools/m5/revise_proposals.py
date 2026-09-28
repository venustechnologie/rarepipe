"""Apply the independent critique's accepted findings to proposals.json."""
import json
import pathlib

P = pathlib.Path("/Volumes/Lexar/rarepipe_work/MVA_001/m5_packet/proposals.json")
doc = json.loads(P.read_text())
items = {i["id"]: i for i in doc["items"]}

# F2 — the matched subset is selected on a quantity that correlates with the outcome.
expr = items["M5_W001"]["proposal"]["value"]["E01_EXPR"]
expr["validity_criteria"] += (
    " The intensity window is defined on the wild-type replacement arm and applied identically to both arms. "
    "Report what fraction of each arm falls inside it and the full per-arm intensity distributions: if the "
    "altered-protein arm contributes only its upper tail, those cells may differ systematically from the "
    "wild-type cells they are compared with, and that residual confounding is recorded as a limitation on the "
    "result rather than assumed away.")
items["M5_W001"]["proposal"]["limitations"].append(
    "Matching selects on expression, which is itself related to the outcome. If the altered-protein arm is "
    "systematically lower-expressed, its matched subset is drawn from its upper tail and may differ in other "
    "respects (cell size, general expression capacity). A neutral covariate should be reported alongside.")

# F5 — NEBD-to-anaphase alone cannot separate slow alignment from delayed silencing.
sil = items["M5_W001"]["proposal"]["value"]["E01_SIL"]
sil["validity_criteria"] = (
    "The alignment-to-anaphase interval is the primary silencing measure; the NEBD-to-anaphase interval is "
    "reported alongside it but cannot separate slow alignment from delayed silencing on its own. " +
    sil["validity_criteria"])

# F1 — the decision needs non-inferiority against a margin, not a difference test.
w4 = items["M5_W004"]["proposal"]["value"]
w4["estimand"]["EXP01"] = (
    "Whether the exact-allele arm is non-inferior to the wild-type replacement arm, within the matched-abundance "
    "population, on each functional endpoint in the specified model and imaging window, assessed against a "
    "prespecified margin. A difference test is the wrong frame for this decision in both directions: a small "
    "statistically detectable difference from wild type need not be a functional defect, and failing to detect a "
    "difference across three preparations is not evidence of adequacy. The difference estimate and its confidence "
    "interval are reported in every case; the margin comes from the M5_W003 pilot and is null until then.")
w4["multiplicity"] = (
    "The four functional endpoints (activation, silencing, alignment, missegregation) are co-primary, with Holm "
    "adjustment across them as the default. This interacts with the replication floor: with three preparations, a "
    "Holm-adjusted co-primary design may be unable to detect an effect the decision would care about. Multiplicity "
    "and replication are therefore settled together once the M5_W003 pilot reports variability; if three "
    "preparations prove insufficient, the options are more preparations or a prespecified hierarchical gate "
    "(silencing first, since it is the endpoint no restored-abundance experiment has reported) rather than "
    "accepting an underpowered adjusted design. Mechanistic endpoints are secondary, unadjusted, and never used "
    "alone to declare benefit.")
w4["confounding_rule"] += (
    " The trigger for 'death rises' or 'division rate falls' is itself a numeric criterion that does not yet exist: "
    "it depends on the same M5_W003 pilot, and until then the rule is stated qualitatively and the endpoints are "
    "reported side by side for the reviewer to judge.")
items["M5_W004"]["proposal"]["conditions"].append(
    "The non-inferiority margin, and the triggers in the confounding rule, both depend on the M5_W003 pilot. "
    "Until it reports, this plan is complete in structure but cannot be executed to a decision.")
items["M5_W004"]["proposal"]["alternatives"].append(
    "Frame EXP01 as a superiority-over-deficient-control test instead of non-inferiority to wild type: easier to "
    "power, but it answers a different and weaker question, since beating a null control does not show the protein "
    "works well enough.")
items["M5_W004"]["proposal"]["limitations"].append(
    "A non-inferiority design typically needs more replication than a difference test, so the three-preparation "
    "floor is more likely to rise than to hold once the pilot reports.")
items["M5_W004"]["reviewer_question"] = (
    "Do you accept the preparation as the independent experimental unit with a mixed-model analysis, the "
    "non-inferiority framing for EXP01 against a pilot-derived margin, and the joint interpretation rule for "
    "missegregation with death and division rather than adjusting for viability?")

doc["critique"] = {
    "record": "critique.md",
    "independence_limitation": "The critique was produced by the same model in the same session, reading the same "
                               "retrieved sources. It is a self-review, not independent review, and no finding "
                               "here counts as corroboration.",
    "findings_applied": ["F1", "F2", "F3", "F4", "F5"],
    "findings_recorded_without_change": ["F6"],
    "outcome": "REVISE_PROPOSAL (applied)",
}
P.write_text(json.dumps(doc, indent=2) + "\n")
print("revised", len(doc["items"]), "items")
