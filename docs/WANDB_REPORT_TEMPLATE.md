# W&B Report Template: NPC Training Portfolio

## Overview

This guide walks through creating a polished, shareable W&B Report in the web UI — a portfolio artifact that shows the full NPC training pipeline at a glance. The report aggregates training curves, evaluation results with per-category breakdowns, artifact references, and optional model comparison data from PeerLM evaluations.

Once saved as a template, generating an updated report for a new training cycle is a single click.

---

## Step-by-Step Instructions

### 1. Navigate to W&B Reports

1. Go to [wandb.ai](https://wandb.ai) and sign in.
2. Select the project: `andreabenathar-twl-games/unsloth-core`.
3. Click **Reports** in the left sidebar.
4. Click **Create new report** → **Blank report**.

---

### 2. Add Report Header

1. Click **Add block** → **Text**.
2. Insert a title:

   ```markdown
   # Unsloth_Core: NPC Fine-Tuning Portfolio
   ```

3. Below the title, add a subtitle with the date and project link:

   ```markdown
   **Generated:** {{date}}
   **Project:** [andreabenathar-twl-games/unsloth-core](https://wandb.ai/andreabenathar-twl-games/unsloth-core)
   ```

   *(W&B supports `{{date}}` as a dynamic macro that renders the current date.)*

---

### 3. Training Progress Section

This section shows loss curves for each active NPC, letting you compare convergence across training runs.

1. Click **Add block** → **Heading 2** and enter: `Training Progress`
2. Click **Add panel** → **Run compare**.

   For each active NPC (e.g., `history_guide`, `chef_assistant`):

   | Setting | Value |
   |---------|-------|
   | **Filter** | `tags:train`, `config.npc_key:<npc_key>` |
   | **Chart type** | Line chart |
   | **X-axis** | `Step` |
   | **Y-axis** | `train/loss` |
   | **Display** | Latest 3 runs per NPC (smooth: 0.8) |

3. (Optional) Add a second **Run compare** panel showing learning rate:

   | Setting | Value |
   |---------|-------|
   | **Filter** | `tags:train`, `config.npc_key:<npc_key>` |
   | **Y-axis** | `train/learning_rate` |

4. Group the panels into a **Section** block with a heading naming which NPC they cover.

---

### 4. Evaluation Results Section

This section shows win rates from the evaluation pipeline.

1. Click **Add block** → **Heading 2** and enter: `Evaluation Results`
2. Click **Add panel** → **Run compare**.

   | Setting | Value |
   |---------|-------|
   | **Filter** | `tags:eval`, `config.npc_key:<npc_key>` |
   | **Chart type** | Bar chart |
   | **Y-axis** | `eval/win_rate` |
   | **Group by** | `config.npc_key` |
   | **Color by** | `config.npc_key` |

3. Add a supporting metric panel (bar chart):

   | Setting | Value |
   |---------|-------|
   | **Y-axis** | `eval/candidate_wins`, `eval/baseline_wins`, `eval/ties` |
   | **Group by** | `config.npc_key` |

4. Add a **Text** block summarizing the current best-performing NPC:

   ```markdown
   **Current leader:** {{npc_key}} — win rate {{eval/win_rate}}%
   Last evaluated: {{date}}
   ```

   *(Replace `{{npc_key}}` and `{{eval/win_rate}}` with actual values after adding the panel data.)*

---

### 5. Category Breakdown Section

Per-category win rates reveal which concept areas each NPC handles well or poorly.

1. Click **Add block** → **Heading 2** and enter: `Category Breakdown`
2. For each NPC, click **Add panel** → **Run compare**.

   | Setting | Value |
   |---------|-------|
   | **Filter** | `tags:eval`, `config.npc_key:<npc_key>` |
   | **Chart type** | Bar chart or Parallel coordinates |
   | **Y-axis** | `eval/category/identity/win_rate`, `eval/category/teaching/win_rate`, `eval/category/dialogue/win_rate`, `eval/category/quest/win_rate`, `eval/category/refusal/win_rate` |

3. Alternatively, add a **Table** panel with the same metrics for a compact readout.
4. Add a **Text** block noting any weak categories:

   ```markdown
   **Weakness alert ({{npc_key}}):** Lowest category = {{category}} ({{win_rate}}%).
   Consider regenerating with `./ucore generate --concept-focus {{category}}`.
   ```

---

### 6. Artifact Summary Section

Keep a quick-reference list of the latest artifact versions for each NPC.

1. Click **Add block** → **Heading 2** and enter: `Artifact Summary`
2. Click **Add block** → **Text** and insert a table:

   ```markdown
   | NPC | Dataset | LoRA Weights | GGUF Export |
   |-----|---------|--------------|-------------|
   | history_guide | `history_guide-dataset:v9` | `lora-history_guide:v5` | `gguf-history_guide:v3` |
   | chef_assistant | `chef_assistant-dataset:v7` | `lora-chef_assistant:v4` | `gguf-chef_assistant:v2` |
   ```

   *To get actual versions: open the **Artifacts** tab in W&B and look for the latest alias (`latest`) for each artifact type.*

3. Add a note about the base model:

   ```markdown
   **Base model:** `llama-3.2-3b-instruct-q4_k_m.gguf` (1.9 GB)
   **Deployment:** Unity LLMUnity `NPCLoraAgent` — switches NPCs via adapter swap.
   ```

---

### 7. Model Comparison Section (Optional)

---

### 8. Save as Template

1. Click the **gear icon** (settings) in the top-right of the report.
2. Select **Save as template**.
3. **Template name:** `NPC Training Report`
4. **Description:**

   ```
   Portfolio template for Unsloth_Core NPC fine-tuning runs showing training
   curves, evaluation results, category breakdowns, and model comparison data.
   ```

5. Click **Save**.

> Templates are scoped to the project. All project members can see and use them.

---

## Maintenance

| Aspect | Detail |
|--------|--------|
| **Auto-apply** | Template is auto-applied to new reports created from it. |
| **Snapshots** | Each report is a static, point-in-time snapshot. Data does not refresh. |
| **Updating** | Create a new report from the template → latest W&B runs auto-populate into the panels. |
| **Sharing** | Use the **Share** button to generate a public link or invite collaborators. |

---

## Companion CLI Tool

For offline or CI/CD workflows, the `wb_report.py` script generates equivalent markdown reports directly:

```bash
# Latest eval run for each active NPC
python scripts/evaluation/wb_report.py

# Specific NPC only
python scripts/evaluation/wb_report.py --npc history_guide

# Specific W&B run
python scripts/evaluation/wb_report.py --run-id <run_id>

# Custom output path
python scripts/evaluation/wb_report.py --output eval/reports/wandb_portfolio_$(date +%F).md
```

**Requirements:**

```bash
pip install wandb
wandb.login()  # via ~/.netrc or WANDB_API_KEY env var
```

See `scripts/evaluation/wb_report.py` for the full interface.

---

## Required W&B Runs

For the template to display data, the following runs must exist in the project:

| Type | Source | W&B Tags |
|------|--------|----------|
| Training | `./ucore pipeline <spec> --wandb` | `train`, `<npc_key>` |
| Evaluation | `./ucore evaluate <spec> --wandb` | `eval`, `<npc_key>` |

**Minimum viable data:** At least one training run and one evaluation run for at least one NPC.

---

## Philosophy

This report follows the same principles as the rest of the Unsloth_Core codebase:

- **Early Exit** — Panels show the most important signal (loss, win rate) first; detail sections are opt-in.
- **Fail Fast** — If no runs match the filters, panels display transparently instead of silently hiding.
- **Intentional Naming** — Every section heading and panel title names its content precisely so the report reads like a dashboard, not a mystery.
