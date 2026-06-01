#!/usr/bin/env python3
"""Audit pytest files and map them to Unsloth_Core process owners."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = PROJECT_ROOT / "tests"

OWNER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("dataset-eval", ("dataset_eval", "quality", "deepeval")),
    ("dataset", ("generate_dataset", "generation", "dataset_contract", "sanitize", "schema", "llm_generator", "ollama_generator")),
    ("training", ("training", "train", "preflight", "model_preset", "wandb")),
    ("export", ("export", "smoke")),
    ("evaluation", ("evaluate", "eval_", "npc_model", "judge", "scoring", "reporting", "metrics")),
    ("orchestration", ("workflow", "pipeline", "ucore", "track", "db", "alias", "legacy")),
    ("contract", ("contract", "coherence", "boundary", "path", "reference")),
]

DEPRECATED_PATTERNS = [
    "subjects/{npc}.json",
    "--resume-from",
    "eval/results/feedback/{npc}.json",
]


def _repo_rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _extract_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return sorted(set(imports))


def _extract_tests(tree: ast.AST) -> list[str]:
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def _extract_markers(tree: ast.AST) -> list[str]:
    markers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain = []
            cur: ast.AST = node
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                chain.append(cur.id)
            dotted = ".".join(reversed(chain))
            if dotted.startswith("pytest.mark."):
                markers.add(dotted.replace("pytest.mark.", "", 1))
    return sorted(markers)


def infer_owner(path: Path, imports: list[str], tests: list[str]) -> str:
    haystack = " ".join([_repo_rel(path), *imports, *tests]).lower()
    for owner, needles in OWNER_RULES:
        if any(needle in haystack for needle in needles):
            return owner
    if "/evals/" in _repo_rel(path):
        return "evaluation"
    return "unknown"


def detect_risks(path: Path, text: str, imports: list[str], markers: list[str]) -> list[str]:
    risks: list[str] = []
    rel = _repo_rel(path)
    if any(imp.startswith("scripts.") and imp.count(".") == 1 for imp in imports):
        risks.append("legacy-root-script-import")
    if any(token in text for token in ("subjects/", "outputs/", "exports/", "eval/")) and "tmp_path" not in text:
        risks.append("real-artifact-path-without-tmp-fixture")
    if "template" in text and "smoke_template_only" not in markers and "test_generation_profiles.py" not in rel:
        risks.append("template-mentioned-without-smoke-marker")
    for pattern in DEPRECATED_PATTERNS:
        if pattern in text:
            risks.append(f"deprecated-pattern:{pattern}")
    if "--resume-from" in text and "rejects_resume_from" not in text:
        risks.append("deprecated-flag-reference")
    return sorted(set(risks))


def audit_tests() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        imports = _extract_imports(tree)
        tests = _extract_tests(tree)
        markers = _extract_markers(tree)
        owner = infer_owner(path, imports, tests)
        items.append(
            {
                "file": _repo_rel(path),
                "owner": owner,
                "test_count": len(tests),
                "tests": tests,
                "repo_imports": [imp for imp in imports if imp.startswith(("scripts", "_config", "tests"))],
                "markers": markers,
                "risks": detect_risks(path, text, imports, markers),
            }
        )
    return {
        "summary": {
            "test_files": len(items),
            "test_functions": sum(item["test_count"] for item in items),
            "unknown_owners": sum(1 for item in items if item["owner"] == "unknown"),
            "risk_count": sum(len(item["risks"]) for item in items),
        },
        "tests": items,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Test Process Matrix", "", "## Summary", ""]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Files", "", "| File | Owner | Tests | Risks |", "|---|---:|---:|---|"]
    for item in payload["tests"]:
        risks = ", ".join(item["risks"]) if item["risks"] else "none"
        lines.append(f"| `{item['file']}` | {item['owner']} | {item['test_count']} | {risks} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit pytest files against process owners and stale references")
    parser.add_argument("--write", help="Write JSON matrix to path")
    parser.add_argument("--markdown", help="Write Markdown matrix to path")
    args = parser.parse_args()

    payload = audit_tests()
    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        path = Path(args.markdown)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
