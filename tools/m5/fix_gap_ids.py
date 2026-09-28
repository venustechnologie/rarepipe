"""Correct the proposal gap IDs against the real validator output.

I wrote some E02 gap IDs by hand and got them wrong: the optional endpoints (SIRT2, K668, total
aneuploidy) produce no readiness gaps, while two required ones (cell death, division rate) do and
were missed. Gap IDs are now derived from the register rather than typed.
"""
import json
import pathlib

W = pathlib.Path("/Volumes/Lexar/rarepipe_work/MVA_001/m5_packet")
register = json.loads((W / "gap_register.json").read_text())
doc = json.loads((W / "proposals.json").read_text())
real = {g["gap_id"] for g in register["source_gap_records"]}
by_package = {p["id"]: p["source_gap_ids"] for p in register["work_packages"]}
items = {i["id"]: i for i in doc["items"]}

for item_id, package_id in [("M5_W001", "WP_001"), ("M5_W002", "WP_002"), ("M5_W003", "WP_003"),
                            ("M5_W004", "WP_004"), ("M5_W005", "WP_005"), ("M5_W006", "WP_006"),
                            ("M5_W007", "WP_007")]:
    items[item_id]["source_gap_ids"] = by_package[package_id]

value = items["M5_W002"]["proposal"]["value"]
value["E02_DEATH"] = {
    "method": "Direct measurement of cell death on the same preparations and window as the functional endpoints, "
              "rather than inferring death from a fall in viability.",
    "validity_criteria": "Reported with its denominator per preparation, at the same timepoints as the divisions "
                         "scored, so that a rise in death can be aligned with the divisions that contributed to the "
                         "missegregation rate.",
}
value["E02_DIV"] = {
    "method": "Division rate from the same live imaging: divisions entered per imaged cell per unit time.",
    "validity_criteria": "Reported per preparation with its denominator. A fall in the number of scored divisions is "
                         "reported as such and never read as improved fidelity.",
}
for key in ("E02_SIRT2", "E02_K668"):
    value[key]["note"] = ("Optional endpoint in the current plan, so it carries no readiness gap. The method is "
                          "proposed anyway because leaving it unspecified is how an unmeasured mechanism quietly "
                          "becomes an assumed one; recording it NOT_MEASURED is the required behaviour.")
items["M5_W002"]["proposal"]["limitations"].append(
    "Total aneuploidy, SIRT2 activity and K668 acetylation are optional endpoints in this plan version, so the "
    "validator raises no gap for them. Their methods are proposed here so that 'optional' cannot drift into "
    "'assumed satisfied'.")

corrections = doc.setdefault("corrections", [])
corrections.append({
    "at": "2026-09-28",
    "finding": "Several E02 gap IDs in the first draft were written from memory rather than read from the validator "
               "output. E02_SIRT2 and E02_K668 are optional endpoints and raise no gaps; E02_DEATH and E02_DIV are "
               "required and their eight gaps were missing from the proposals.",
    "correction": "All source_gap_ids are now derived from gap_register.json, which is generated directly from the "
                  "validator output. Methods for cell death and division rate were added to M5_W002.",
    "found_by": "coverage cross-check of proposals against the validator output, not by the format checker",
})
(W / "proposals.json").write_text(json.dumps(doc, indent=2) + "\n")

covered = {x for i in doc["items"] for x in i["source_gap_ids"]}
print("invented gap ids:", sorted(covered - real) or "none")
print("uncovered validator gaps:", sorted(real - covered) or "none")
print("total covered:", len(covered), "of", len(real))
