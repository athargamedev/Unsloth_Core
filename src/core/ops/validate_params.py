#!/usr/bin/env python3
"""
validate_params.py — Validate parameter-registry.yaml against actual code usage.

Reads etc/parameter-registry.yaml and checks that all referenced params
exist in some form in the codebase. This is a best-effort validation since
params can be referenced in many ways (argparse, env vars, YAML config keys).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml


def load_registry(registry_path: Path) -> dict:
    """Load the parameter registry YAML file."""
    with open(registry_path) as f:
        data = yaml.safe_load(f)
    return data


def validate_params(registry_path: Path, project_root: Path) -> list[str]:
    """Validate all params in the registry exist in the codebase."""
    data = load_registry(registry_path)
    params = data.get("parameters", {})
    env_vars = data.get("env_vars", {})
    issues = []

    # Check each parameter has required fields
    for name, p in params.items():
        if "type" not in p:
            issues.append(f"Parameter '{name}' missing 'type' field")
        if "stage" not in p:
            issues.append(f"Parameter '{name}' missing 'stage' field")
        if "description" not in p:
            issues.append(f"Parameter '{name}' missing 'description' field")

        # Check cli_flag references exist in codebase
        cli_flag = p.get("cli_flag", "")
        if cli_flag and cli_flag.startswith("--"):
            # Search for this flag in scripts/
            flag_name = cli_flag.lstrip("-").split("=")[0]
            matches = list(project_root.rglob("scripts/**/*.py"))
            found = False
            for py_file in matches:
                try:
                    content = py_file.read_text()
                    if (
                        f"'{flag_name}'" in content
                        or f'"{flag_name}"' in content
                        or f"'{cli_flag}'" in content
                        or f'"{cli_flag}"' in content
                    ):
                        found = True
                        break
                except (OSError, UnicodeDecodeError):
                    continue
            if not found:
                issues.append(f"CLI flag '{cli_flag}' (param '{name}') not found in any script")

    # Check env vars
    for name, ev in env_vars.items():
        if "description" not in ev:
            issues.append(f"Env var '{name}' missing 'description' field")

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Validate parameter-registry.yaml against codebase"
    )
    parser.add_argument("--registry", default=None, help="Path to parameter-registry.yaml")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    registry_path = (
        Path(args.registry)
        if args.registry
        else project_root / "configs" / "parameter-registry.yaml"
    )

    if not registry_path.exists():
        print(f"Error: {registry_path} not found")
        sys.exit(1)

    issues = validate_params(registry_path, project_root)

    if args.json:
        output = {
            "total_params": len(yaml.safe_load(open(registry_path)).get("parameters", {})),
            "total_env_vars": len(yaml.safe_load(open(registry_path)).get("env_vars", {})),
            "issues": issues,
            "status": "pass" if not issues else "fail",
        }
        print(json.dumps(output, indent=2))
    else:
        data = yaml.safe_load(open(registry_path))
        params = data.get("parameters", {})
        env_vars = data.get("env_vars", {})
        print(f"Parameter Registry: {len(params)} params, {len(env_vars)} env vars")
        print(f"Issues found: {len(issues)}")
        for issue in issues:
            print(f"  ⚠ {issue}")
        if not issues:
            print("  ✅ All parameters valid")

    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
