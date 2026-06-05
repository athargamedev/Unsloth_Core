import re
import shutil
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
docs_dir = repo_root / "docs"

# 1. Map old file paths to new file paths (relative to docs directory)
file_map = {
    "PROJECT_STATE.md": "project-state.md",
    "TRAINING_WORKFLOW_CONTEXT.md": "training-workflow.md",
    "MAP.md": "index.md",
    "COMMANDS_DICTIONARY.md": "reference/cli-commands.md",
    "DEEPEVAL_CHEAT_SHEET.md": "guides/deepeval-cheat-sheet.md",
    "UNSLOTH_CORE_OPERATOR_RUNBOOK.md": "guides/operator-runbook.md",
    "OLLAMA_DATASET_GENERATOR.md": "guides/ollama-dataset-generator.md",
    "OLLAMA_LOCAL_PERFORMANCE.md": "guides/ollama-local-performance.md",
    "NPC_TRAINING_EVOLUTION.md": "guides/npc-training-evolution.md",
    "RUN_COMPARISON_SCHEMA.md": "reference/run-comparison-schema.md",
    "NPC_DATA_RL_EXECUTION_CONTRACT.md": "reference/npc-data-rl-execution-contract.md",
    "Code_Review_Report.md": "planning/code-review-report.md",
    "WORKFLOW_ASSISTANT_ARCHITECTURE_PLAN.md": "planning/workflow-assistant-architecture.md",
    "WORKFLOW_ASSISTANT_SUPABASE_RAG_PLAN.md": "planning/workflow-assistant-rag.md",
    "reference/SUBJECT_SPEC.md": "reference/subject-spec.md",
    "architecture/AUTH_SYSTEM.md": "architecture/auth-system.md",
    "architecture/JOB_QUEUE.md": "architecture/job-queue.md",
    "architecture/MODULAR_BACKEND.md": "architecture/modular-backend.md",
    "architecture/PIPELINE_DB.md": "architecture/pipeline-db.md",
    "architecture/PIPELINE_FLOW.md": "architecture/pipeline-flow.md",
    "architecture/SUPABASE_SCHEMA.md": "architecture/supabase-schema.md",
    "integration/FRONTEND_DASHBOARD.md": "integration/frontend-dashboard.md",
    "12-AI-Visuals.pdf": "visuals/12-ai-visuals.pdf",
    "NPC_Best_Practices.html": "visuals/npc-best-practices.html",
    "NPC_Math_And_Balancing.html": "visuals/npc-math-and-balancing.html",
    "NPC_Pipeline_Visuals.html": "visuals/npc-pipeline-visuals.html",
    "workflow_dataflow_graph.html": "visuals/workflow-dataflow-graph.html",
    "dataflow_graph.html": "visuals/legacy-dataflow-graph.html",
}

# Add the old reference/CLI_REFERENCE.md to delete or move
if (docs_dir / "reference" / "CLI_REFERENCE.md").exists():
    file_map["reference/CLI_REFERENCE.md"] = "reference/legacy-cli-reference.md"

# Reverse map to find new path from old path
old_to_new = {old: new for old, new in file_map.items()}

# Create directories
for d in ["guides", "reference", "planning", "visuals", "architecture", "integration"]:
    (docs_dir / d).mkdir(parents=True, exist_ok=True)

# 2. Rename/Move files
moved_files = {}
for old_rel, new_rel in file_map.items():
    old_path = docs_dir / old_rel
    new_path = docs_dir / new_rel
    if old_path.exists() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        moved_files[old_rel] = new_rel

print(f"Moved {len(moved_files)} files.")


# 3. Update links in all markdown and html files
def get_depth(rel_path: str) -> int:
    return rel_path.count("/")


def compute_relative_link(source_rel: str, target_rel: str) -> str:
    # Compute relative path from docs/source_rel to docs/target_rel
    source_parts = source_rel.split("/")[:-1]  # dir parts
    target_parts = target_rel.split("/")

    # Find common prefix
    i = 0
    while (
        i < len(source_parts) and i < len(target_parts) - 1 and source_parts[i] == target_parts[i]
    ):
        i += 1

    ups = len(source_parts) - i
    downs = target_parts[i:]

    if ups == 0:
        return "./" + "/".join(downs) if not downs[0] else "/".join(downs)
    else:
        return "../" * ups + "/".join(downs)


# Let's read all files in docs + AGENTS.md + README.md
targets = list(docs_dir.rglob("*.md")) + list(docs_dir.rglob("*.html"))
targets.append(repo_root / "AGENTS.md")
targets.append(repo_root / "README.md")

for fpath in targets:
    if not fpath.exists():
        continue

    content = fpath.read_text(encoding="utf-8")
    original_content = content

    # Is it inside docs/?
    try:
        f_rel_to_docs = fpath.relative_to(docs_dir).as_posix()
        in_docs = True
    except ValueError:
        in_docs = False

    for old_path_key, new_path_key in old_to_new.items():
        # Heuristic 1: If file is outside docs (like AGENTS.md), look for "docs/OLD_NAME"
        if not in_docs:
            content = content.replace(f"docs/{old_path_key}", f"docs/{new_path_key}")
            # Also replace bare old name just in case
            # But only if it's explicitly referenced like `OLD_NAME.md`
            old_name_only = old_path_key.split("/")[-1]
            new_name_only = new_path_key.split("/")[-1]
            if old_name_only != new_name_only:
                content = re.sub(r"\b" + re.escape(old_name_only) + r"\b", new_name_only, content)
        else:
            # Inside docs, it's trickier.
            # Replace absolute-like references or bare names
            old_name = old_path_key.split("/")[-1]
            new_name = new_path_key.split("/")[-1]

            # calculate relative path
            correct_rel_link = compute_relative_link(f_rel_to_docs, new_path_key)

            # Simple replace of the old filename with the correct relative path if it looks like a link
            # E.g. [Link](OLD_NAME.md) -> [Link](correct_rel_link)
            # or `OLD_NAME.md` -> `correct_rel_link`
            # This regex looks for the old filename and replaces it.
            # It's a bit naive, but works for most cases

            # Replace markdown links: ](old_path) or ](../old_path) or ](docs/old_path)
            content = re.sub(
                r"\]\([^)]*" + re.escape(old_name) + r"\)", f"]({correct_rel_link})", content
            )

            # Replace raw mentions like `OLD_NAME.md`
            content = re.sub(r"\b" + re.escape(old_name) + r"\b", new_name, content)

            # Replace docs/OLD_NAME
            content = content.replace(f"docs/{old_path_key}", f"docs/{new_path_key}")

    if content != original_content:
        fpath.write_text(content, encoding="utf-8")
        print(f"Updated links in {fpath.name}")

print("Done reorganization.")
