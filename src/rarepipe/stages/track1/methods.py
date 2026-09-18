"""The methods report, generated from pipeline provenance rather than written by hand.

It is judged separately for scientific rigor, so it states what the pipeline did, what it
could not establish, and where it might be wrong — including the parts that weaken our own
submission. It carries no exact variant identity: that lives only in the predictions file.
"""

from __future__ import annotations

from typing import Any

from rarepipe.stages.track1.model import Track1SubmissionPackage

PLACEHOLDER_MARKERS = ("[", "]", "to be confirmed", "submitter to confirm", "TODO")

DEFAULT_LLM_DISCLOSURE = (
    "Anthropic Claude (Claude Code) [plan/tier and data-handling setting] and OpenAI ChatGPT "
    "[plan/tier and data-handling setting] were used for software development, methodology, and review of "
    "sanitized/derived findings. Raw VCF/FASTQ data, exact patient variant coordinates/alleles, and "
    "genome-scale genotype tables were not provided to either service. Controlled genomic analysis ran locally."
)


def disclosure_is_complete(text: str) -> tuple[bool, str]:
    """The organizers require provider, plan/tier and data-handling setting for every AI assistant used.
    An unfilled placeholder is worse than no disclosure, so it blocks the package rather than shipping."""
    unresolved = [m for m in PLACEHOLDER_MARKERS if m.lower() in text.lower()]
    if unresolved:
        return False, f"unresolved placeholder(s) in the AI disclosure: {', '.join(unresolved)}"
    named = [p for p in ("anthropic", "openai") if p in text.lower()]
    if not named:
        return False, "the AI disclosure names no provider"
    return True, f"providers named: {', '.join(named)}"



def render(pkg: Track1SubmissionPackage, adjudication: dict[str, Any], candidate_set: dict[str, Any],
           llm_disclosure: str = DEFAULT_LLM_DISCLOSURE) -> str:
    out: list[str] = []
    w = out.append
    snap = pkg.provenance.validation_snapshot
    stability = candidate_set.get("stability", {})
    profiles = candidate_set.get("profiles", [])
    summary = adjudication.get("evidence_summary", {})

    w("# Track 1 methods — rarepipe\n")
    w(f"**Proband:** {pkg.proband_id} · **Assembly:** {pkg.assembly} · **Submission:** "
      f"{pkg.submission.submission_number} of {pkg.submission.submission_budget}\n")
    w(f"**Snapshot digest:** `{pkg.provenance.snapshot_digest}` · **Predictions digest:** "
      f"`{pkg.provenance.prediction_digest}`\n")
    w("> This submission was generated from a pipeline state frozen before any query to the hidden answer "
      "key. The snapshot above pins the exact upstream runs and the source commit.\n")

    w("## Summary\n")
    w("A five-stage pipeline took the case as delivered, established what the inputs actually were, "
      "normalized them, generated causal hypotheses with an established phenotype-driven solver under four "
      "deliberately different sensitivity profiles, and then adjudicated the leading hypothesis against "
      "independent evidence before ranking this submission. No stage was tuned against any benchmark score; "
      "this is the pipeline's first prospective external query.\n")

    w("## Pipeline\n")
    w("**Stage 01 — case intake.** Every delivered file is identified by content rather than by extension, "
      "hashed, and checked for truncation and for modification during intake. Nothing is interpreted or "
      "transformed. The stage's output is a manifest stating what we were given, including what we could not "
      "read.\n")
    w("**Stage 02 — normalization.** Implicit assumptions are made explicit: genome build is determined from "
      "the VCF's own contig-length fingerprint rather than from a header claim, contigs are bound to an NCBI "
      "assembly report, caller and filter provenance are extracted from the header, and phenotype terms are "
      "bound to a pinned HPO release. Readiness is reported per capability, so a capability we cannot support "
      "is refused rather than silently approximated.\n")
    exomiser = next((s for s in (candidate_set.get("provenance", {}).get("solver"), None) if s), {})
    w(f"**Stage 03 — baseline hypothesis generation.** {exomiser.get('name', 'Exomiser')} "
      f"{exomiser.get('version', '')} was run under {len(profiles)} analysis profiles that differ only in "
      "stated ways (whether variants failing the caller's filters are admitted, and the phenotype term set). "
      "Running the same case under several profiles is a sensitivity analysis: a candidate that survives all "
      "of them is not an artifact of one filtering choice.\n")
    if stability:
        w(f"Stability across profiles: **{stability.get('verdict', 'n/a')}** — {stability.get('verdict_basis', '')}\n")
    w("**Stage 04 — evidence adjudication.** The leading hypothesis was decomposed into separate claims — is "
      "the gene–disease mechanism appropriate, does each allele impair function, is the configuration causal — "
      "and each claim was answered with individually sourced evidence assertions carrying a class, a direction, "
      "a strength with its documented basis, and its limitations. Claims are never collapsed into a single "
      "score, and evidence classes are ranked so that a computational predictor cannot outrank an assay or a "
      "human observation. Contradicting evidence is recorded explicitly.\n")
    w("**Stage 05 — this submission.** Row 1 is the adjudicated hypothesis. Rows 2–10 are read off the Stage 03 "
      "output by a rule fixed before generation (below). Nothing was reranked by hand.\n")

    w("## Evidence for the leading hypothesis\n")
    w(f"Gene **{adjudication.get('gene_symbol')}**, {adjudication.get('inheritance_model')} model, proposed as a "
      f"candidate compound heterozygous pair. Overall: **{summary.get('overall')}** — {summary.get('overall_basis')}\n")
    w("| claim | assessment |")
    w("|---|---|")
    for c in adjudication.get("claims", []):
        w(f"| {c['statement']} | **{c['assessment']}** |")
    w("")
    w("| evidence class | state |")
    w("|---|---|")
    for label, key in (("human observation", "human_observation"), ("functional", "functional"), ("population", "population"),
                       ("molecular/mechanistic", "molecular_mechanistic"), ("computational", "computational"),
                       ("technical call", "technical_call"), ("phase", "phase")):
        w(f"| {label} | {summary.get(key)} |")
    w("")

    w("## Candidate ordering\n")
    rule = pkg.selection_rule
    w(f"{rule.description}\n")
    for i, step in enumerate(rule.steps, 1):
        w(f"{i}. {step}")
    w("")
    w(f"Ties are broken by {', then '.join(rule.tie_breaks)}. "
      f"{rule.rows_considered} candidate configurations were considered; {rule.rows_emitted} rows were emitted.\n")
    w("## EPCR\n")
    w(f"{pkg.epcr_schedule.description}\n")
    w(f"**{pkg.epcr_schedule.disclaimer}**\n")
    w("Values: " + ", ".join(f"{v:.2f}" for v in pkg.epcr_schedule.values) + "\n")

    w("## Representation of the leading pair\n")
    w("The two alleles are submitted as a single compound-heterozygous row, in genomic coordinate order. "
      "This asserts a proposed causal configuration. It does **not** assert experimentally established trans "
      "phase: the supplied singleton VCF contains no read-backed phase linking the two loci, and no parental "
      "data was available to us. Phase is recorded as unresolved in the internal artifact.\n")

    w("## Privacy and data handling\n")
    for control in ("All analysis of controlled data ran locally, in a sandbox with network access denied.",
                    "Every stage emits two artifacts: a private one and a sanitized one in which case-identifying "
                    "fields are cleared by the schema itself rather than by hand. Reports are rendered only from "
                    "the sanitized artifact.",
                    "External evidence retrieval is restricted to local, bulk, or gene-level public resources. A "
                    "disclosure guard rejects any outbound query containing a coordinate, HGVS string, protein "
                    "change, rsID, ClinVar id or HPO term; exact-variant external querying requires an explicit "
                    "human approval gate and was never performed.",
                    "The predictions file is the only artifact carrying exact variant identity, and it goes only to "
                    "the evaluator, which already holds authorized access to this case.",
                    "Data is held on encrypted local storage for deletion within 30 days of the hackathon's close, "
                    "with notification to the organizers as the rules require."):
        w(f"- {control}")
    w("")
    w(f"- {llm_disclosure}")
    w("")

    w("## Limitations\n")
    for lim in ("Singleton case: no pedigree, no parental genotypes, no trio-based de novo or transmission analysis.",
                "Phase between the two proposed alleles is unresolved. Absence of read-backed phase is absence of "
                "evidence, not evidence of cis.",
                "The second allele is a missense variant of uncertain significance. It is rare and technically "
                "well-called, but we found no human or functional evidence bearing on that specific residue, and "
                "the computational predictors we consulted are indeterminate under their own calibrated thresholds.",
                "The supplied FASTQs were not realigned and no independent variant calling was performed; the "
                "submitted variants come from the supplied VCF.",
                "Structural variants, repeat expansions, mitochondrial and non-coding mechanisms were not "
                "systematically evaluated.",
                "EPCR values are rank-preserving surrogates, not calibrated probabilities.",
                "Candidates 2–10 received no individual evidence adjudication; they carry the baseline's judgement "
                "only, and their ordering reflects cross-profile robustness rather than biological review."):
        w(f"- {lim}")
    w("")

    w("## Reproducibility\n")
    w("Every stage writes an immutable, sealed run directory (`SHA256SUMS`, verifiable with `rarepipe verify-run`) "
      "and a semantic digest that excludes execution-specific values, so two identical runs produce the same "
      "digest. This submission's inputs:\n")
    w("```")
    w(f"baseline run       {snap.baseline_run}")
    w(f"baseline digest    {snap.baseline_digest}")
    w(f"adjudication run   {snap.adjudication_run}")
    w(f"adjudication dgst  {snap.adjudication_digest}")
    w(f"normalization run  {snap.normalization_run}")
    w(f"intake run         {snap.intake_run}")
    w(f"source commit      {snap.git_commit} ({snap.git_describe})")
    w(f"frozen at          {snap.created_at}  before_ground_truth_query={str(snap.created_before_ground_truth_query).lower()}")
    w("```\n")
    w("## What a result would mean to us\n")
    w("A full match confirms the causal pair for hackathon purposes and moves the open work to mechanism, not "
      "ranking. A partial match tells us precisely which half of the hypothesis is wrong. No match triggers "
      "error attribution — was the gene wrong, did the true pair fall below rank 10, did the solver miss a "
      "variant, was the representation wrong — rather than parameter tuning. Benchmark feedback is treated as "
      "evidence about the case, not as a training signal: a further submission requires an independently "
      "justified pipeline change.\n")
    return "\n".join(out)
