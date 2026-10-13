"""The dependency boundary: the policy engine must not know what case it is solving.

The engine earns its keep only if the same solver handles a second domain without being rewritten.
That is a property of the import graph, not of anyone's good intentions, so it is checked here:

* nothing under ``stages/control/policy`` may import from outside that package (beyond the standard
  library), and in particular not from the control compiler, a stage, or an adapter;
* no case vocabulary may appear as a *code* identifier or string literal in the engine — node ids,
  capability tokens, control-variable names. Prose in a docstring explaining what the engine
  deliberately does not know is fine and is not scanned;
* the adapter imports the engine, which pins the direction of the arrow.

If this test fails because the engine grew a convenient import of the case it was written against,
the fix is to pass the thing in as an argument, not to relax the test.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/rarepipe/stages/control/policy"
ADAPTER = ROOT / "tools/control/solve_mva_policy.py"

ALLOWED_PREFIX = "rarepipe.stages.control.policy"

# Vocabulary that belongs to the case, not to the mathematics. Matched against code — identifiers
# and string literals — never against docstrings or comments.
CASE_TOKENS = (
    "S0_CASE", "FUNCTIONAL_CELLULAR_TARGET", "CANONICAL_CELLULAR_STATE", "ORGANISM_TARGET",
    "CELL_MODEL", "TISSUE_MODEL", "ORGANISM_MODEL", "GOVERNANCE_ABSENT",
    "BOUNDED_FRONTIER", "GOVERNANCE_BLOCKED", "DECLARED_SCIENTIFIC_FRONTIER",
    "PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE", "SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED",
    "FUNCTIONAL_TARGET_REACHED", "ORGANISM_TARGET_REACHED_IN_MODEL",
    "CV_", "BUB1B", "BUBR1", "BubR1", "FLUX01", "CHAR01", "STAB01", "TRIP13", "MVA",
    "_REPEAT", "PMID",
)


def _sources() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_engine_package_exists_and_is_not_empty():
    assert _sources(), f"no sources under {PACKAGE}"


def test_the_engine_imports_nothing_outside_itself():
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if not name.startswith("rarepipe"):
                    continue
                if not name.startswith(ALLOWED_PREFIX):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} imports {name}")
    assert not offenders, (
        "the policy engine must stay domain-neutral; pass the value in as an argument instead of "
        "importing it:\n  " + "\n  ".join(offenders))


def test_the_engine_does_not_read_files_or_parse_case_formats():
    """A solver that can load a map can be handed one, and then it has a domain after all."""
    forbidden = {"yaml", "json", "csv", "pathlib", "importlib"}
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                if name.split(".")[0] in forbidden:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {name}")
    assert not offenders, (
        "the engine takes structures, not files; serialisation belongs to the adapter:\n  "
        + "\n  ".join(offenders))


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the Constant nodes that are docstrings, so prose is excluded from the scan."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def test_no_case_vocabulary_appears_in_the_engines_code():
    offenders: list[str] = []
    for path in _sources():
        text = path.read_text()
        tree = ast.parse(text)
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue
                for token in CASE_TOKENS:
                    if token in node.value:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} string contains {token!r}")
            elif isinstance(node, ast.Name):
                for token in CASE_TOKENS:
                    if token in node.id:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} name {node.id!r}")
    assert not offenders, (
        "case vocabulary in the engine; it belongs in the adapter:\n  " + "\n  ".join(offenders))


def test_the_adapter_imports_the_engine_and_not_the_other_way_round():
    assert ADAPTER.exists(), f"{ADAPTER} is missing"
    tree = ast.parse(ADAPTER.read_text())
    imported = {
        name
        for node in ast.walk(tree)
        for name in ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
    }
    assert any(name.startswith(ALLOWED_PREFIX) for name in imported), (
        "the adapter is supposed to use the engine")
    # And the engine never names the adapter.
    for path in _sources():
        assert "solve_mva_policy" not in path.read_text(), (
            f"{path.relative_to(ROOT)} refers to the adapter; the arrow points the other way")


def test_the_engine_depends_on_nothing_but_the_standard_library():
    """What makes extraction a move rather than a port.

    The repository's own dependencies — pydantic, pysam, typer, pyyaml — are all reasonable, and
    none of them belongs in a graph search. A single import of one here would make lifting this
    package out drag the pipeline's dependency set with it.
    """
    third_party = {"pydantic", "pysam", "typer", "yaml", "pypdf", "alphagenome", "numpy",
                   "pandas", "scipy", "networkx"}
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                if name.split(".")[0] in third_party:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {name}")
    assert not offenders, "\n  ".join(["the engine must stay standard-library only:", *offenders])


def test_the_entry_point_signature_is_domain_neutral():
    """`solve_policy(graph, knowledge_state, target, constraints, horizon)` and nothing case-shaped."""
    import inspect

    from rarepipe.stages.control.policy import solve_policy

    parameters = list(inspect.signature(solve_policy).parameters)
    assert parameters[:5] == ["graph", "knowledge_state", "target", "constraints", "horizon"], (
        f"the entry point's shape is the contract; got {parameters[:5]}")
