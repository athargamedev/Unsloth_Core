"""Importable console-script entrypoint for the executable ``src/cli/ucore`` file."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
from types import ModuleType


def _load_ucore_module() -> ModuleType:
    """Load the extensionless Python CLI script used by the root ``./ucore`` wrapper."""
    ucore_path = Path(__file__).with_name("ucore")
    loader = importlib.machinery.SourceFileLoader("src_cli_ucore_script", str(ucore_path))
    spec = importlib.util.spec_from_loader("src_cli_ucore_script", loader, origin=str(ucore_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load ucore CLI from {ucore_path}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ucore_path)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    """Run the canonical ucore CLI."""
    return int(_load_ucore_module().main(argv) or 0)
