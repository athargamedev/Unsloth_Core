#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build_goldens.sh — Build the golden evaluation dataset from NPC training files.
#
# Usage:
#   ./scripts/evaluation/build_goldens.sh
#   ./scripts/evaluation/build_goldens.sh --npc-keys history_guide,chef_assistant
#   ./scripts/evaluation/build_goldens.sh --per-category 5
#
# All flags are forwarded to build_npc_goldens.py. See --help for the full list.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

source unsloth_env/bin/activate

exec python "$SCRIPT_DIR/build_npc_goldens.py" "$@"
