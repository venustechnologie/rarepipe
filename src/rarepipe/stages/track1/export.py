"""Writing the predictions file, and proving it parses before it is ever uploaded.

One submission of six is too expensive to lose to a formatting mistake, so the file is
checked twice: against the documented schema here, and by the evaluator's own public
parser run locally, without the answer key.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import re
import sys
from pathlib import Path

from rarepipe.stages.track1.model import CSV_COLUMNS, MAX_ROWS, OfficialScorerCheck, SubmissionRow, ValidationCheck

ALLELE = re.compile(r"[ACGTN]+")
SCORER_URL = "https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/raw/main/evaluation.py"


def render_csv(proband_id: str, rows: list[SubmissionRow]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        v = row.variants
        second = v[1] if len(v) == 2 else None
        writer.writerow([proband_id, v[0].chrom, v[0].pos, v[0].ref, v[0].alt,
                         second.chrom if second else "", second.pos if second else "",
                         second.ref if second else "", second.alt if second else "",
                         f"{row.epcr:.2f}", row.finding_type, row.notes])
    return buf.getvalue()


def checks(proband_id: str, rows: list[SubmissionRow], csv_text: str) -> list[ValidationCheck]:
    parsed = list(csv.DictReader(io.StringIO(csv_text)))
    header = next(csv.reader(io.StringIO(csv_text)))
    out: list[ValidationCheck] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        out.append(ValidationCheck(check=name, passed=ok, detail=detail))

    check("header matches the official schema", header == CSV_COLUMNS, f"{header}")
    check("proband id is the one the evaluator accepts",
          all(r["proband_id"] == proband_id for r in parsed) and proband_id == "PROBAND01", proband_id)
    check(f"at most {MAX_ROWS} rows", len(parsed) <= MAX_ROWS, f"{len(parsed)} row(s)")
    check("every row carries a primary variant", all(r["chrom_1"] and r["pos_1"] for r in parsed))
    check("chromosomes are chr-prefixed GRCh38 names",
          all(re.fullmatch(r"chr(\d{1,2}|X|Y|M)", r["chrom_1"]) and (not r["chrom_2"] or re.fullmatch(r"chr(\d{1,2}|X|Y|M)", r["chrom_2"]))
              for r in parsed))
    check("positions are positive integers",
          all(r["pos_1"].isdigit() and int(r["pos_1"]) > 0 and (not r["pos_2"] or (r["pos_2"].isdigit() and int(r["pos_2"]) > 0))
              for r in parsed))
    check("REF/ALT are non-empty unambiguous alleles",
          all(ALLELE.fullmatch(r["ref_1"]) and ALLELE.fullmatch(r["alt_1"])
              and (not r["chrom_2"] or (ALLELE.fullmatch(r["ref_2"]) and ALLELE.fullmatch(r["alt_2"]))) for r in parsed))
    check("REF and ALT differ", all(r["ref_1"] != r["alt_1"] and (not r["chrom_2"] or r["ref_2"] != r["alt_2"]) for r in parsed))
    check("EPCR lies in (0, 1]", all(0 < float(r["epcr"]) <= 1 for r in parsed))
    check("EPCR values are distinct, so the F-max sweep separates every rank",
          len({r["epcr"] for r in parsed}) == len(parsed))
    check("rows are pre-ranked by EPCR descending",
          [float(r["epcr"]) for r in parsed] == sorted((float(r["epcr"]) for r in parsed), reverse=True))
    configs = [frozenset({(r["chrom_1"], r["pos_1"], r["ref_1"], r["alt_1"])}
                         | ({(r["chrom_2"], r["pos_2"], r["ref_2"], r["alt_2"])} if r["chrom_2"] else set()))
               for r in parsed]
    check("no duplicate configurations", len(set(configs)) == len(configs))
    check("pair rows fill all four second-variant columns, single rows leave them blank",
          all((bool(r["chrom_2"]) == bool(r["pos_2"]) == bool(r["ref_2"]) == bool(r["alt_2"])) for r in parsed))
    check("the two alleles of a pair are in genomic coordinate order",
          all(not r["chrom_2"] or (r["chrom_1"], int(r["pos_1"])) <= (r["chrom_2"], int(r["pos_2"]))
              or r["chrom_1"] != r["chrom_2"] for r in parsed))
    check("a pair row never repeats the same allele twice",
          all(not r["chrom_2"] or (r["chrom_1"], r["pos_1"], r["ref_1"], r["alt_1"]) != (r["chrom_2"], r["pos_2"], r["ref_2"], r["alt_2"])
              for r in parsed))
    check("finding_type is primary or secondary", all(r["finding_type"] in ("primary", "secondary") for r in parsed))
    check("row order matches the package's ranking", [float(r["epcr"]) for r in parsed] == [row.epcr for row in rows])
    return out


def run_official_parser(scorer_path: Path | None, csv_path: Path, expected_rows: list[SubmissionRow]) -> OfficialScorerCheck:
    """Run the evaluator's own `load_submission` on our file. It never sees the answer key."""
    if scorer_path is None or not scorer_path.exists():
        return OfficialScorerCheck(available=False, source_url=SCORER_URL,
                                   error="official evaluation.py not provided; pass --official-scorer to run it")
    sha = hashlib.sha256(scorer_path.read_bytes()).hexdigest()
    check = OfficialScorerCheck(available=True, path=str(scorer_path), sha256=sha, source_url=SCORER_URL)
    try:
        spec = importlib.util.spec_from_file_location("hf_track1_evaluation", scorer_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses in the loaded module resolve types through sys.modules
        try:
            spec.loader.exec_module(module)
            submissions = module.load_submission(str(csv_path))
        finally:
            sys.modules.pop(spec.name, None)
        if len(submissions) != 1:
            raise ValueError(f"parser grouped the file into {len(submissions)} proband(s); expected exactly 1")
        rows = next(iter(submissions.values()))
        check.parsed_ok = True
        check.rows_parsed = len(rows)
        check.ranks_as_submitted = all(
            r.rank == i + 1 and abs(r.epcr - expected_rows[i].epcr) < 1e-9 for i, r in enumerate(rows))
    except Exception as exc:  # the point of the check is to see this before uploading, not after
        check.parsed_ok = False
        check.error = f"{type(exc).__name__}: {exc}"
    return check
