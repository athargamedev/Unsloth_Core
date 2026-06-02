# Gemini Context: Unsloth_Core

## Project Overview

This is the `Unsloth_Core` project, a comprehensive pipeline for creating and evaluating GGUF LoRA (Low-Rank Adaptation) adapters for Large Language Models, specifically tailored for `llama-3.2-3b-instruct`.

The primary goal is to enable efficient deployment of customized Non-Player Characters (NPCs) in Unity games using the LLMUnity framework. This is achieved by loading a single shared base GGUF model and dynamically swapping lightweight, NPC-specific LoRA adapters at runtime. The project also integrates a local Supabase instance for managing dialogue history and session state.

The entire workflow is orchestrated through a unified command-line interface (CLI) named `./ucore`.

## Technologies Used

*   **LLM/ML:** Unsloth, PyTorch, Transformers, PEFT, Datasets, TRL, bitsandbytes
*   **Backend & CLI:** Python, FastAPI
*   **Frontend:** Node.js, likely a framework like React/Vue/Svelte (based on `npm run dev`)
*   **Database:** Supabase (PostgreSQL)
*   **Testing:** pytest
*   **Monitoring/Evaluation:** DeepEval, Ollama, TensorBoard, W&B (indicated by `wandb` directory)

## Getting Started

### 1. Environment Setup

Activate the pre-configured Python virtual environment.

```bash
source unsloth_env/bin/activate
```

### 2. Project Health Check

Run the audit command to ensure the environment is set up correctly.

```bash
./ucore audit check
```

### 3. Running the Dashboard

The project includes a web-based dashboard for monitoring.

```bash
cd frontend_control/unity-npc-llm-training-dashboard
npm install
npm run dev
```

The dashboard will be available at `http://localhost:3100`.

### 4. Local Supabase

The project uses a local Supabase instance for data persistence.

```bash
# Start the local Supabase services
supabase start
```

## Development Workflow

The core of the project is a multi-step pipeline managed by the `./ucore` CLI.

1.  **Validate Spec:** Validate the NPC specification file.
    ```bash
    ./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
    ```

2.  **Generate Dataset:** Generate a training dataset for the NPC.
    ```bash
    ./ucore generate data/npcs/specs/<npc>.json --technique template
    ```

3.  **Sanitize Dataset:** Clean and prepare the dataset for training.
    ```bash
    ./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl 
      --output data/datasets/<npc>/<technique>/train_clean.jsonl
    ```

4.  **Quality Gate:** Evaluate the dataset quality before training.
    ```bash
    ./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique>
    ```

5.  **Train & Export:** Train the LoRA adapter and export it to GGUF format.
    ```bash
    ./ucore train data/npcs/specs/<npc>.json 
      --technique <technique> --preset fast-3b --export-gguf
    ```

6.  **Evaluate:** Run an evaluation on the newly trained adapter.
    ```bash
    ./ucore evaluate --baseline <baseline> --candidate <candidate> 
      --base-model <base-gguf> --spec data/npcs/specs/<npc>.json
    ```

## Testing

The project uses `pytest` for testing. Tests are categorized with markers.

```bash
# Run all tests
pytest

# Run only unit tests
pytest -m unit

# Run tests that require a GPU
pytest -m requires_gpu
```

## Key Directories and Files

*   `./ucore`: The unified CLI for the entire pipeline.
*   `.gemini/skills/`: Local Gemini skills for project-specific operations:
    *   `unsloth-core-operator`: Pipeline management.
    *   `unsloth-core-low-vram-training`: 6GB VRAM survival.
    *   `unsloth-core-context-maintenance`: Context auditing.
    *   `llmunity-runtime-deploy`: Unity deployment.
*   `AGENTS.md`: A primary context file for AI agents interacting with this repository.
*   `README.md`: High-level project overview and quick start guide.
*   `requirements.txt`: Core Python dependencies.
*   `pytest.ini`: Pytest configuration, including custom markers.
*   `data/`: Contains NPC specs, reference documents, and generated datasets.
*   `artifacts/`: Default output directory for models, GGUF exports, and evaluation reports.
*   `src/`: Source code for the CLI, core logic, and dashboard.
*   `supabase/`: Configuration and migrations for the local Supabase instance.
*   `tests/`: Automated tests for the project.
*   `docs/`: Detailed documentation, including project state and workflow guides.
*   `colab/`: Jupyter notebooks related to the project workflow.
*   `unsloth_env/`: The Python virtual environment directory.
