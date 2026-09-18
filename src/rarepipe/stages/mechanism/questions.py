"""The questions the stage asks, and the rule that makes it stop asking.

Seeded from PRD 006 §37. A planner (deterministic here, an LLM when one is configured) may
add queries to a task, but never a task whose disclosure level is not gene/disease-level.
"""

from __future__ import annotations

from rarepipe.stages.mechanism.model import DisclosureLevel, KnowledgeTask

PRIORITY_SEED_PMIDS = ["20516114"]
SEED_RATIONALE = ("Named during architecture design as a likely patient-cell study. It enters the graph only "
                  "through retrieval and extraction from the source itself, never from prior belief about it.")

# question, reason, queries
SEED_TASKS: list[tuple[str, str, list[str]]] = [
    ("What is the experimentally established cellular function of BUBR1 relevant to MVA?",
     "Everything downstream depends on what the protein actually does in human cells.",
     ["BUB1B BUBR1 mitotic checkpoint complex function",
      "BUBR1 kinetochore microtubule attachment chromosome alignment",
      "BUBR1 CDC20 APC/C inhibition spindle assembly checkpoint"]),
    ("What mechanisms have been experimentally observed in biallelic BUB1B MVA patient cells?",
     "Patient-derived cells are the highest-ranked experimental evidence available for this disease.",
     ["BUB1B mosaic variegated aneuploidy patient cells mitotic checkpoint",
      "mosaic variegated aneuploidy BUBR1 fibroblast lymphoblastoid functional assay",
      "BUB1B mutation premature chromatid separation patient"]),
    ("What is known about truncating BUB1B alleles?",
     "Allele A is truncating; 'stop_gained' must not become 'complete null' without evidence.",
     ["BUB1B nonsense frameshift truncating mutation BUBR1 protein",
      "BUB1B nonsense mediated decay transcript",
      "BUB1B truncating allele mosaic variegated aneuploidy"]),
    ("What mechanisms have been observed for kinase-domain missense BUB1B variants?",
     "Allele B is a kinase-domain missense variant whose effect is the central unresolved question.",
     ["BUB1B BUBR1 missense kinase domain protein stability abundance",
      "BUBR1 kinase activity missense variant checkpoint function",
      "BUB1B missense variant mosaic variegated aneuploidy functional characterisation"]),
    ("Is this exact missense residue represented in any accessible functional evidence?",
     "Distinguishes exact-variant evidence from variant-class evidence. Searched locally, never transmitted.",
     []),  # answered by local search over the corpus, by construction
    ("What assay outputs distinguish the known BUB1B mutation classes?",
     "Determines what an external experiment would have to measure to resolve allele B.",
     ["BUBR1 protein abundance western blot mosaic variegated aneuploidy",
      "BUB1B mutation classes functional heterogeneity",
      "BUBR1 complementation rescue checkpoint activity"]),
    ("What downstream cellular defect is most directly linked to MVA biology?",
     "Establishes whether chromosome instability is the accepted disease-level bridge.",
     ["mosaic variegated aneuploidy constitutional aneuploidy chromosome instability",
      "BUB1B aneuploidy chromosome missegregation human",
      "mosaic variegated aneuploidy clinical cytogenetics BUB1B"]),
]

CONTRADICTION_QUERIES = [
    "BUB1B missense variant normal BUBR1 protein level",
    "BUBR1 kinase activity dispensable checkpoint",
    "mosaic variegated aneuploidy without BUB1B mutation cause",
    "BUBR1 mutation preserved mitotic checkpoint function",
]

STOP_RULES = {
    "A": "direct high-quality evidence found for the claim",
    "B": "multiple independent indirect sources converge",
    "C": "search space exhausted to the configured threshold",
    "D": "contradiction prevents resolution",
    "E": "marginal value of further search is low",
}


def seed_tasks() -> list[KnowledgeTask]:
    tasks = []
    for i, (question, reason, queries) in enumerate(SEED_TASKS, start=1):
        local_only = not queries
        tasks.append(KnowledgeTask(
            id=f"KT_{i:04d}", question=question, reason=reason,
            disclosure_level=DisclosureLevel.LOCAL_ONLY if local_only else DisclosureLevel.PUBLIC_GENE_LEVEL,
            retrieval_plan=["local corpus search only"] if local_only else ["Europe PMC", "PMC open-access full text"],
            queries=list(queries)))
    tasks.append(KnowledgeTask(
        id=f"KT_{len(tasks) + 1:04d}",
        question="What evidence is inconsistent with the proposed mechanism?",
        reason="A dossier with only supporting evidence is unacceptable (PRD 006 §15).",
        disclosure_level=DisclosureLevel.PUBLIC_GENE_LEVEL,
        retrieval_plan=["Europe PMC"], queries=list(CONTRADICTION_QUERIES)))
    tasks.append(KnowledgeTask(
        id=f"KT_{len(tasks) + 1:04d}",
        question="What does the priority-seed study report, in its own words?",
        reason=SEED_RATIONALE, disclosure_level=DisclosureLevel.PUBLIC_GENE_LEVEL,
        retrieval_plan=["Europe PMC by identifier"],
        queries=[f"EXT_ID:{pmid}" for pmid in PRIORITY_SEED_PMIDS]))
    return tasks
