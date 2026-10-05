#!/usr/bin/env python3
"""Would importing a published mechanistic checkpoint model supply any of our unknowns?

The proposal is to import SAC models from BioModels — validated ODEs with fitted parameters — to
replace this chain's guessed rate constants. That is a reasonable instinct, and it is checkable
rather than arguable: compare what a published spindle-assembly-checkpoint model contains against
the parameters this chain actually cannot fill.

A SAC kinetic model describes checkpoint assembly and silencing: MCC formation, Mad2 and Cdc20
binding, APC/C inhibition, kinetochore attachment and Mps1 activity. Each of this chain's
unmeasured parameters is assigned to the domain it belongs to, and the report says which of them
such a model could and could not supply.

Domain assignment is a judgement about biology, recorded here so it can be argued with rather than
buried in a conclusion. Change DOMAIN_OF if you disagree; the report follows from it.

Usage: uv run python tools/network/model_import_coverage.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rarepipe.stages.simulate.mva import mva_chain  # noqa: E402

# What a published SAC kinetic model from BioModels actually parameterises.
CHECKPOINT_MODEL_SUPPLIES = (
    "mcc_assembly_and_disassembly",
    "mad2_cdc20_binding",
    "apc_c_inhibition",
    "kinetochore_attachment",
    "mps1_activity",
    "checkpoint_signal_propagation",
)

# Which domain each of this chain's unmeasured parameters belongs to.
DOMAIN_OF: dict[str, str] = {
    "k_niacin_to_blood_nad": "human_pharmacokinetics",
    # Added when the human trial already in the repository was connected to the tissue pool. Its
    # domain is human pharmacokinetics in a tissue, which is exactly the domain a spindle-checkpoint
    # model does not cover — so the import's coverage of the unknowns is unchanged.
    "f_niacin_to_tissue_nad": "human_pharmacokinetics",
    "f_blood_to_intracellular": "membrane_transport_into_the_relevant_cell_type",
    "k_nad_to_sirt2": "sirtuin_enzymology",
    "k_sirt2_deacetylation": "sirtuin_enzymology",
    "k_acetylation_to_stability": "post_translational_protein_stability",
    "residual_function_fraction": "this_variant_s_residual_function",
}

WHY_NOT: dict[str, str] = {
    "human_pharmacokinetics": "a checkpoint model has no dosing or circulating compartment",
    "membrane_transport_into_the_relevant_cell_type":
        "a checkpoint model starts inside the cell; it does not model getting there",
    "sirtuin_enzymology":
        "SIRT2 is upstream of the checkpoint and is not a component of SAC assembly",
    "post_translational_protein_stability":
        "a checkpoint model takes BubR1 abundance as an input rather than deriving it",
    "this_variant_s_residual_function":
        "no published model contains this child's allele; this is the quantity the case turns on",
}


def check() -> dict:
    chain = mva_chain()
    unknown = chain.unknown_parameters()
    rows = []
    for parameter in unknown:
        domain = DOMAIN_OF.get(parameter.name, "unassigned")
        suppliable = domain in CHECKPOINT_MODEL_SUPPLIES
        rows.append({
            "parameter": parameter.name,
            "unit": parameter.unit,
            "domain": domain,
            "a_published_checkpoint_model_could_supply_it": suppliable,
            "why_not": None if suppliable else WHY_NOT.get(domain, "domain not assigned"),
        })

    # Which edges would an imported checkpoint model actually cover, and do they carry unknowns?
    downstream = tuple(
        e.key for e in chain.edges
        if e.source in {"bubr1_residual_function", "checkpoint_activation", "checkpoint_silencing",
                        "chromosome_alignment", "missegregation"}
    )
    downstream_unknowns = [
        e.key for e in chain.edges
        if e.key in downstream and e.parameter is not None and e.parameter.value is None
    ]

    suppliable = [r for r in rows if r["a_published_checkpoint_model_could_supply_it"]]
    return {
        "chain_id": chain.chain_id,
        "unmeasured_parameters": len(rows),
        "a_checkpoint_model_could_supply": len(suppliable),
        "parameters": rows,
        "edges_an_imported_model_would_cover": list(downstream),
        "unmeasured_parameters_on_those_edges": downstream_unknowns,
        "reading": (
            "An imported SAC model would cover the downstream edges — BubR1 function through "
            "checkpoint behaviour to missegregation — which already carry model_experimental "
            "support and no unmeasured parameters. Every parameter this chain cannot fill sits "
            "upstream of the checkpoint, in pharmacokinetics, transport, sirtuin enzymology, "
            "protein stability, or this variant's residual function. So the import would add "
            "quantitative dynamics to the part that is already supported, and supply none of the "
            "unknowns the sensitivity ranking says dominate."
        ),
        "what_would_change_this": (
            "A published model that parameterises NAD transport into the relevant cell type, or "
            "SIRT2-dependent BubR1 stability, would supply real unknowns. That is a different "
            "search than BioModels' SAC entries, and worth doing on its own terms."
        ),
        "not_checked": [
            "whether a specific BioModels entry is well fitted or appropriate",
            "whether quantitative checkpoint dynamics are worth having for another reason",
            "the domain assignment itself, which is a biological judgement recorded in DOMAIN_OF",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = check()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"{report['a_checkpoint_model_could_supply']} of "
          f"{report['unmeasured_parameters']} unmeasured parameters could come from a published "
          "checkpoint model\n")
    for row in report["parameters"]:
        mark = "yes" if row["a_published_checkpoint_model_could_supply_it"] else "no "
        print(f"  [{mark}] {row['parameter']:30} {row['domain']}")
        if row["why_not"]:
            print(f"        {row['why_not']}")
    print(f"\nEdges an imported model would cover: {len(report['edges_an_imported_model_would_cover'])}")
    print(f"Unmeasured parameters on those edges: "
          f"{report['unmeasured_parameters_on_those_edges'] or 'none'}")
    print(f"\n{report['reading']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
