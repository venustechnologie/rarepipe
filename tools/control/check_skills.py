#!/usr/bin/env python3
"""Check the control skills against the compiler they serve.

A skill that names a type, field or identifier the code does not have is a skill that will make the
model reason about something that does not exist. This builds a vocabulary from the control package
itself and reports every backticked identifier a skill uses that is not in it, every required
section that is missing, and any content no skill may carry: doses, recommendations, or exact
variant notation.

Usage: uv run python tools/control/check_skills.py
Exit code 0 only if nothing was found.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SKILLS = sorted([*(ROOT / ".claude/skills").glob("control-*/SKILL.md"),
                 *(ROOT / ".claude/skills").glob("synthesis-*/SKILL.md")])
CONTROL = ROOT / "src/rarepipe/stages/control"
SYNTHESIS = CONTROL / "synthesis"
REQUIRED = ("skill_id", "version", "scope", "required_inputs", "reasoning_checklist", "allowed_tools",
            "forbidden_inferences", "output_schema", "uncertainty_language", "abstention_conditions",
            "validation_hooks", "benchmark_cases", "retention_criterion")
DOSE = re.compile(r"\b\d+(\.\d+)?\s?(mg|µg|ug|mcg|mmol|IU)(/kg)?\b", re.I)
RECOMMEND = re.compile(r"\bwe recommend\b|\bshould be (given|administered)\b|\bshould take\b", re.I)
IDENT = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)(?:\(\))?`")


SIMULATE = ROOT / "src/rarepipe/stages/simulate"


def vocabulary() -> set[str]:
    """Everything the control package defines or imports, plus the simulate package its actuator
    layer draws evidence from. A narrower vocabulary flags legitimate references as defects."""
    words: set[str] = set()
    sources = [(p, p.stem) for p in CONTROL.glob("*.py")]
    sources += [(p, f"synthesis.{p.stem}") for p in SYNTHESIS.glob("*.py")]
    sources += [(p, f"simulate.{p.stem}") for p in SIMULATE.glob("*.py")]
    for path, module in sources:
        words.add(module)
        words.add(module.split(".")[-1])
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                words.update(alias.asname or alias.name for alias in node.names)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                words.update({node.name, f"{module}.{node.name}"})
                if isinstance(node, ast.ClassDef):
                    words.add(f"{module.split('.')[-1]}.{node.name}")
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            words.update({item.target.id, f"{node.name}.{item.target.id}"})
                        if isinstance(item, ast.Assign):
                            for t in item.targets:
                                if isinstance(t, ast.Name):
                                    words.update({t.id, f"{node.name}.{t.id}"})
                        if isinstance(item, ast.FunctionDef):
                            words.update({item.name, f"{node.name}.{item.name}",
                                          f"{module}.{node.name}.{item.name}"})
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        words.update({t.id, f"{module}.{t.id}"})
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", node.value):
                    words.add(node.value)
    from rarepipe.stages.control.mva import problem
    p = problem()
    words.update(p.space.names)
    words.update(r.relationship_id for m in p.models for r in m.relationships)
    words.update(c.control_id for c in p.controls)
    words.update(a.actuator_id for a in p.actuators)
    words.update(c.constraint_id for c in p.target.constraints)
    words.update(c.constraint_id for c in p.unsafe.constraints)
    for e in p.experiments:
        words.add(e.experiment_id)
        words.update(e.observation.observed)
    # The synthesis layer's own identifiers: components, families and the policy, so a skill may
    # name the thing it is reasoning about without the checker calling it invented.
    from rarepipe.stages.control.synthesis import mva_synthesis
    sp = mva_synthesis.problem()
    words.update(b.building_block_id for b in sp.registry.blocks)
    words.update(f.family_id for f in sp.families)
    words.update(policy.policy_id for policy in sp.policies)
    words.update(rule.rule_id for policy in sp.policies for rule in policy.rules)
    words.update(m.mechanism_id for m in sp.population.mechanisms)
    words.update(c.process_id for c in sp.population.confounders)
    words.update(sp.population.population_variables)
    for enum_module in ("control.controls", "control.result_types", "control.provenance",
                        "control.dynamics", "control.actuator_registry", "control.model_registry",
                        "control.state_space", "control.proposals",
                        "control.synthesis.kinds", "control.synthesis.compiler",
                        "control.synthesis.population", "control.synthesis.feedback",
                        "control.synthesis.building_blocks", "control.synthesis.architecture",
                        "control.synthesis.experiments", "control.synthesis.requirements",
                        "control.synthesis.search", "control.synthesis.composition",
                        "simulate.chain"):
        mod = __import__(f"rarepipe.stages.{enum_module}", fromlist=["x"])
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and hasattr(obj, "__members__"):
                for member, value in obj.__members__.items():
                    words.update({member, f"{name}.{member}", str(value.value)})
    words.update({"H01", "H02", "H06", "B06", "B08", "B09", "B11", "B16", "B17", "B18",
                  "EXP01", "EXP02", "EXP03", "MVA_001", "INFERRED_HYPOTHESIS", "OBSERVED_EMPIRICAL"})
    return words


def check(skill_paths: list[Path] | None = None) -> dict:
    words = vocabulary()
    paths = SKILLS if skill_paths is None else skill_paths
    from rarepipe.stages.network.report import VARIANT_NOTATION, GENOMIC_COORDINATE
    findings = []
    for path in paths:
        text = path.read_text()
        rel = str(path)
        directory = path.parent.name
        front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not front or f"name: {directory}" not in front.group(1):
            findings.append({"skill": rel, "issue": "frontmatter missing or name does not match directory"})
        if front and "description:" not in front.group(1):
            findings.append({"skill": rel, "issue": "frontmatter has no description"})
        for section in REQUIRED:
            if not re.search(rf"^#+\s*`?{section}`?\s*$", text, re.M):
                findings.append({"skill": rel, "issue": f"missing section {section}"})
        for ident in sorted(set(IDENT.findall(text))):
            parts = ident.split(".")
            candidates = {ident, parts[-1], ".".join(parts[-2:]) if len(parts) > 1 else ident}
            if ident.startswith(("uv", "rarepipe", "tools", "src", "tests")):
                continue
            if not candidates & words:
                findings.append({"skill": rel, "issue": f"references `{ident}`, which the compiler does not define"})
        for pattern, why in ((DOSE, "dose"), (RECOMMEND, "recommendation"),
                             (VARIANT_NOTATION, "exact variant notation"),
                             (GENOMIC_COORDINATE, "genomic coordinate")):
            for match in pattern.finditer(text):
                findings.append({"skill": rel, "issue": f"contains {why}: {match.group(0)!r}"})
    return {"status": "SKILLS_CONSISTENT" if not findings else "SKILLS_INCONSISTENT",
            "skills_checked": [str(p) for p in paths], "findings": findings,
            "not_checked": ["whether the reasoning in a skill is scientifically sound",
                            "whether a skill's benchmark cases were actually run"]}


if __name__ == "__main__":
    report = check()
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report["findings"] else 0)
