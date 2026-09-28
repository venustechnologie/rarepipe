"""Stage 06F — experiments, not sentences.

A matching sentence says a variant was mentioned. An experiment says what was expressed, at what
level, and what it could still do. The question this module answers is narrow: when BUBR1 abundance
is restored, does the altered protein work? That is what decides whether raising abundance is a
coherent strategy for this child.

Three rules shape it:

  * Every readout is a verbatim quote re-found in the stored corpus. Nothing is paraphrased into
    evidence.
  * The altered protein is kept apart from normal-protein replacement. Wild-type BUBR1 rescuing a
    cell says the gene matters; it says nothing about whether the child's protein works.
  * How directly an experiment applies to this child (exact / same position / nearby / same domain /
    different region) is computed locally from the private adjudication and held only in restricted
    fields. A nearby published variant plus its position would localise the child's residue, so the
    public artifact carries the decision, not the geometry.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from rarepipe.core.redaction import restricted

# UniProt O60566-1 (BUBR1, 1050 aa), which is the protein encoded by the canonical Ensembl transcript
# ENST00000287598 (MANE Select). Published MVA papers number residues on this same isoform.
CANONICAL_TRANSCRIPT = "ENST00000287598"
PROTEIN_LENGTH = 1050
REGIONS: list[tuple[str, int, int]] = [
    ("BUB1 N-terminal (TPR) domain", 62, 226),
    ("central region", 227, 765),
    ("protein kinase domain", 766, 1050),
]
NEARBY_RESIDUES = 10

THREE = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln", "E": "Glu", "G": "Gly",
         "H": "His", "I": "Ile", "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser",
         "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val"}
ONE = {v: k for k, v in THREE.items()}


class ExperimentError(ValueError):
    pass


class Directness(StrEnum):
    EXACT = "EXACT"
    SAME_POSITION = "SAME_POSITION"
    NEARBY = "NEARBY_WITHIN_10_RESIDUES"
    SAME_REGION = "SAME_REGION"
    DIFFERENT_REGION = "DIFFERENT_REGION"
    NOT_A_VARIANT_TEST = "NOT_A_VARIANT_TEST"
    NUMBERING_UNVERIFIED = "NUMBERING_UNVERIFIED"


READOUT_KINDS = ("protein_abundance", "mrna_level", "protein_turnover", "chaperone_dependence",
                 "checkpoint_activity", "chromosome_segregation", "chromosome_alignment",
                 "kinetochore_localization")
RESULTS = ("normal", "reduced", "increased", "restored", "not_restored", "not_reported")


class Readout(BaseModel):
    kind: Literal[READOUT_KINDS]  # type: ignore[valid-type]
    result: Literal[RESULTS]  # type: ignore[valid-type]
    detail: str = ""
    quote: str = Field(description="Verbatim from the stored source; re-found on import.")
    figure: str | None = None


class VariantExperiment(BaseModel):
    """One construct, one condition, the readouts measured on it."""

    experiment_id: str
    source_id: str
    variant_label: str = Field(description="As published, e.g. I909T, 731X, WT.")
    notation_aliases: list[str] = Field(default_factory=list)
    position: int | None = Field(None, description="Published residue, canonical isoform numbering.")
    ref_residue: str | None = None
    alt_residue: str | None = Field(None, description="One-letter; X for a truncation.")
    region: str | None = None
    pooled: bool = Field(False, description="The source reports several substitutions together without naming them.")
    protein_tested: Literal["altered_protein", "truncated_protein", "normal_protein_replacement",
                            "normal_protein_titration"]
    construct_name: str = ""
    system: str = ""
    abundance_condition: Literal["patient_endogenous", "ectopic_below_wild_type", "restored_to_wild_type_level",
                                 "ectopic_at_or_above_wild_type", "titrated_down", "not_applicable"]
    readouts: list[Readout]
    function_at_restored_abundance: Literal["restored", "impaired", "partial", "not_tested"] = "not_tested"
    authors_interpretation: str | None = Field(None, description="The authors' own words, verbatim.")
    limitations: list[str] = Field(default_factory=list)
    directness: Directness | None = restricted(None)


class ResidualFunctionAssessment(BaseModel):
    """The decision the PM asked for, stated at two levels that must not be merged."""

    question: str = ("When BUBR1 abundance is restored, does the altered protein retain function? "
                     "(Decides whether an abundance-raising strategy is coherent.)")
    class_level: Literal["function_persists", "function_impaired", "mixed", "insufficient"]
    class_level_basis: str
    exact_allele: Literal["function_persists", "function_impaired", "insufficient"]
    exact_allele_basis: str
    decision: Literal["STRENGTHENS_STABILIZATION", "WEAKENS_ABUNDANCE_ONLY", "INSUFFICIENT"]
    decision_meaning: str
    readouts_not_reported_at_restored_abundance: list[str] = Field(default_factory=list)
    distinguishing_experiment: str
    what_remains_open: list[str] = Field(default_factory=list)
    supporting_observations: list[str] = Field(default_factory=list,
                                               description="Findings that bear on the strategy but not on the decision.")
    experiments_considered: list[str] = Field(default_factory=list)
    numbering_check: str = ""
    directness_counts: dict[str, int] = restricted(dict)
    closest_experiment: str | None = restricted(None)


def notation_aliases(label: str) -> list[str]:
    """I909T → Ile909Thr, p.I909T, p.(Ile909Thr), LAP-I909T … ; 731X → *731, Ter731, LAP-731X."""
    out = [label, f"LAP-{label}", f"LAP-BUBR1 {label}"]
    missense = re.fullmatch(r"([A-Z])(\d+)([A-Z])", label)
    truncation = re.fullmatch(r"(\d+)X", label)
    if missense:
        ref, pos, alt = missense.groups()
        three = f"{THREE.get(ref, ref)}{pos}{THREE.get(alt, alt)}"
        out += [three, f"p.{label}", f"p.{three}", f"p.({three})"]
    elif truncation:
        pos = truncation.group(1)
        out += [f"*{pos}", f"Ter{pos}", f"{pos}*", f"p.*{pos}"]
    return list(dict.fromkeys(out))


def _normalise(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _join(kinds: list[str]) -> str:
    words = [k.replace("_", " ") for k in kinds]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _region(position: int | None) -> str | None:
    if position is None:
        return None
    return next((name for name, lo, hi in REGIONS if lo <= position <= hi), None)


def load_experiments(path: Path, corpus_run: Path) -> list[VariantExperiment]:
    """Parse, then verify every quote against the stored document. One failure rejects the file."""
    raw = yaml.safe_load(path.read_text()) or {}
    experiments = [VariantExperiment(**item) for item in raw.get("experiments", [])]
    problems: list[str] = []
    seen: set[str] = set()
    for exp in experiments:
        if exp.experiment_id in seen:
            problems.append(f"{exp.experiment_id}: duplicate id")
        seen.add(exp.experiment_id)
        doc = corpus_run / "docs" / f"{exp.source_id.replace(':', '_')}.txt"
        if not doc.exists():
            problems.append(f"{exp.experiment_id}: {exp.source_id} is not in the corpus")
            continue
        body = _normalise(doc.read_text())
        for readout in exp.readouts:
            if _normalise(readout.quote) not in body:
                problems.append(f"{exp.experiment_id}: quote not found verbatim in {exp.source_id}: "
                                f"{readout.quote[:60]!r}")
        if exp.authors_interpretation and _normalise(exp.authors_interpretation) not in body:
            problems.append(f"{exp.experiment_id}: authors_interpretation must be the authors' words, verbatim")
        if exp.pooled and not exp.region:
            problems.append(f"{exp.experiment_id}: a pooled experiment must state the region its source gives")
        if exp.protein_tested in ("altered_protein", "truncated_protein") and not exp.pooled:
            aliases = [a.lower() for a in notation_aliases(exp.variant_label) + exp.notation_aliases]
            if not any(a in _normalise(r.quote + " " + (r.figure or "")) for r in exp.readouts for a in aliases):
                problems.append(f"{exp.experiment_id}: no quote names {exp.variant_label} in any notation")
            if exp.position is None:
                problems.append(f"{exp.experiment_id}: a variant test needs its published position")
        if exp.region is None:
            exp.region = _region(exp.position)
        if exp.function_at_restored_abundance != "not_tested" and \
                exp.abundance_condition not in ("restored_to_wild_type_level", "ectopic_at_or_above_wild_type"):
            problems.append(f"{exp.experiment_id}: function_at_restored_abundance is set, but abundance was "
                            f"{exp.abundance_condition}, which is not a restored-abundance test")
        if exp.protein_tested.startswith("normal_protein") and exp.function_at_restored_abundance != "not_tested":
            problems.append(f"{exp.experiment_id}: normal-protein replacement cannot answer whether the altered "
                            "protein works at restored abundance")
    if problems:
        raise ExperimentError("; ".join(problems))
    return experiments


def child_missense(adjudication: dict) -> tuple[int, str, str, bool] | None:
    """(position, ref, alt, numbering_is_canonical) for the child's missense allele. Local only."""
    for variant in adjudication.get("variants", []):
        consequence = (variant.get("molecular_consequence") or "").lower()
        if consequence and "missense" not in consequence:
            continue
        match = re.search(r"p\.\(?([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)?", variant.get("hgvs_protein") or "")
        if match and match.group(3) in ONE:
            ref3, pos, alt3 = match.groups()
            canonical = CANONICAL_TRANSCRIPT in (variant.get("transcript") or "") or \
                CANONICAL_TRANSCRIPT in (variant.get("hgvs") or "")
            return int(pos), ONE.get(ref3, "?"), ONE.get(alt3, "?"), canonical
    return None


def grade(exp: VariantExperiment, child: tuple[int, str, str, bool] | None) -> Directness:
    if exp.protein_tested.startswith("normal_protein"):
        return Directness.NOT_A_VARIANT_TEST
    if child is None or not child[3]:
        return Directness.NUMBERING_UNVERIFIED
    if exp.pooled:
        return Directness.SAME_REGION if exp.region == _region(child[0]) else Directness.DIFFERENT_REGION
    if exp.position is None:
        return Directness.NOT_A_VARIANT_TEST
    position, ref, alt, _ = child
    if exp.position == position:
        return Directness.EXACT if exp.alt_residue == alt else Directness.SAME_POSITION
    if abs(exp.position - position) <= NEARBY_RESIDUES:
        return Directness.NEARBY
    if _region(exp.position) and _region(exp.position) == _region(position):
        return Directness.SAME_REGION
    return Directness.DIFFERENT_REGION


def assess(experiments: list[VariantExperiment], child: tuple[int, str, str, bool] | None) -> ResidualFunctionAssessment:
    """Grade every experiment, then decide at class level and at exact-allele level separately."""
    for exp in experiments:
        exp.directness = grade(exp, child)
    child_region = _region(child[0]) if child else None

    in_class = [e for e in experiments
                if e.protein_tested == "altered_protein" and e.directness in
                (Directness.EXACT, Directness.SAME_POSITION, Directness.NEARBY, Directness.SAME_REGION)]
    restored_tests = [e for e in in_class if e.function_at_restored_abundance != "not_tested"]
    outcomes = {e.function_at_restored_abundance for e in restored_tests}
    region_name = child_region or "the child's region"

    if not restored_tests:
        class_level, class_basis = "insufficient", (
            f"no experiment in the corpus restored the abundance of an altered BUBR1 protein in the {region_name} "
            "and then measured function")
    elif outcomes == {"restored"}:
        class_level = "function_persists"
        names = ", ".join(e.variant_label for e in restored_tests)
        class_basis = (f"{len(restored_tests)} altered protein(s) in the {region_name} ({names}) were expressed at "
                       "wild-type-comparable levels and the measured function was restored")
    elif outcomes <= {"impaired"}:
        class_level, class_basis = "function_impaired", (
            f"altered proteins in the {region_name} remained impaired at restored abundance")
    else:
        class_level, class_basis = "mixed", (
            f"altered proteins in the {region_name} differ at restored abundance: "
            + ", ".join(f"{e.variant_label} {e.function_at_restored_abundance}" for e in restored_tests))

    measured = {r.kind for e in restored_tests for r in e.readouts if r.result != "not_reported"}
    not_reported = [k for k in ("checkpoint_activity", "chromosome_segregation", "chromosome_alignment")
                    if restored_tests and k not in measured]
    if class_level == "function_persists" and not_reported:
        reported = sorted(measured & {"checkpoint_activity", "chromosome_segregation", "chromosome_alignment"})
        class_basis += (f". Only {_join(reported)} was reported at restored abundance; {_join(not_reported)} "
                        f"{'were' if len(not_reported) > 1 else 'was'} not reported at restored abundance")

    exact = [e for e in experiments if e.directness == Directness.EXACT and e.function_at_restored_abundance != "not_tested"]
    if exact:
        result = exact[0].function_at_restored_abundance
        exact_level = "function_persists" if result == "restored" else "function_impaired"
        exact_basis = f"the child's exact substitution was tested at restored abundance ({exact[0].experiment_id})"
    else:
        exact_level = "insufficient"
        exact_basis = ("no experiment in the corpus expressed this child's exact substitution, so its function at "
                       "restored abundance is not measured. Class-level evidence from other substitutions in the "
                       "same region is suggestive, not a measurement: sharing a domain does not settle residual "
                       "function")
        restored_labels = {e.variant_label for e in restored_tests}
        unexpressible = list(dict.fromkeys(
            e.variant_label for e in in_class if not e.pooled and e.abundance_condition == "ectopic_below_wild_type"
            and e.variant_label not in restored_labels))
        if unexpressible:
            exact_basis += (f", and within this class {', '.join(unexpressible)} could not be brought to "
                            "wild-type levels, so not every substitution here is even testable that way")

    if exact_level == "function_persists":
        decision = "STRENGTHENS_STABILIZATION"
    elif exact_level == "function_impaired":
        decision = "WEAKENS_ABUNDANCE_ONLY"
    else:
        decision = "INSUFFICIENT"
    meaning = {
        "STRENGTHENS_STABILIZATION": "function persists when abundance is restored: the stabilization rationale is "
                                     "strengthened; the biochemical link from any medication to BUBR1 still needs testing",
        "WEAKENS_ABUNDANCE_ONLY": "function remains impaired at restored abundance: an abundance-only strategy is weakened",
        "INSUFFICIENT": "the residual-function dependency stays unresolved for this child; the distinguishing "
                        "experiment is specified below",
    }[decision]
    if decision == "INSUFFICIENT" and class_level == "function_persists":
        meaning += (". The class-level evidence now leans toward function persisting, which makes the abundance "
                    "premise more plausible than the frozen result stated, but it does not substitute for the "
                    "exact-allele measurement")
    elif decision == "INSUFFICIENT" and class_level in ("function_impaired", "mixed"):
        meaning += ". The class-level evidence does not favour an abundance-only strategy"

    counts: dict[str, int] = {}
    for e in experiments:
        counts[e.directness.value] = counts.get(e.directness.value, 0) + 1
    order = list(Directness)
    closest = min((e for e in experiments if e.directness not in (Directness.NOT_A_VARIANT_TEST,)),
                  key=lambda e: order.index(e.directness), default=None)

    open_items = []
    if not_reported:
        open_items.append(f"{_join(not_reported)} at restored abundance "
                          f"{'were' if len(not_reported) > 1 else 'was'} not reported for the substitutions tested")
    open_items.append("whether this child's substitution is expressible at wild-type-comparable levels at all")
    open_items.append("whether a medication raises BUBR1 abundance in this child's cells — the biochemical link "
                      "is a separate dependency and is not addressed by these experiments")
    return ResidualFunctionAssessment(
        class_level=class_level, class_level_basis=class_basis, exact_allele=exact_level, exact_allele_basis=exact_basis,
        decision=decision, decision_meaning=meaning, readouts_not_reported_at_restored_abundance=not_reported,
        distinguishing_experiment=(
            "Deplete endogenous BUBR1 (shRNA in U2OS or HeLa, as in PMID:20516114 Fig. 4) and express an "
            "RNAi-insensitive construct carrying this child's exact substitution at wild-type-comparable levels, "
            "confirmed by immunoblot beside wild-type and a known restored-abundance control (I909T or L1012P) and "
            "a poorly expressed control (L844F). Measure the nocodazole response (MPM-2), chromosome segregation "
            "by live imaging, and chromosome alignment. Function persists → strengthens stabilization. Function "
            "impaired at matched abundance → weakens an abundance-only strategy. Not expressible at matched levels "
            "→ the premise that stabilising the protein is achievable needs its own test."),
        what_remains_open=open_items,
        supporting_observations=[
            f"{e.experiment_id} ({e.variant_label}, {e.protein_tested.replace('_', ' ')}): {e.authors_interpretation}"
            for e in experiments if e.authors_interpretation and (
                e.protein_tested in ("truncated_protein", "normal_protein_titration")
                or any(r.kind in ("chaperone_dependence", "protein_turnover") for r in e.readouts))],
        experiments_considered=[e.experiment_id for e in experiments],
        numbering_check=("the child's allele is numbered on the canonical transcript (UniProt O60566-1), the same "
                         "isoform the published variants use" if child and child[3] else
                         "numbering could not be confirmed against the canonical isoform: grades are withheld"),
        directness_counts=counts,
        closest_experiment=closest.experiment_id if closest else None,
    )
