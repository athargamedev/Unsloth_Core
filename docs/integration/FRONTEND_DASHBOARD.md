# Frontend Control Dashboard

The **Frontend Control Dashboard** is a React-based orchestration layer for the Unsloth_Core pipeline. it provides a visual interface for managing NPC creation, monitoring training metrics in real-time, and deploying models.

## 🏗️ Architecture

The dashboard operates as a standalone Node.js application that interacts directly with the project root.

- **Frontend**: React + Vite + TailwindCSS.
- **Backend**: Express.js server (`server.ts`) that manages process lifecycle.
- **Process Management**: Spawns `./ucore` commands as child processes.
- **Telemetry**: Real-time extraction of GPU (via `nvidia-smi`), CPU, and Network metrics.
- **Persistence**: Job history and server state are stored in `frontend_control/unity-npc-llm-training-dashboard/.runtime/registry.json`.

## 🚀 Getting Started

### Prerequisites
- **Node.js**: v18+ recommended.
- **npm**: v9+.
- **NVIDIA GPU**: Required for training and telemetry monitoring.
- **unsloth_env**: The Python environment must be accessible (dashboard calls `./ucore`).

### Installation
```bash
cd frontend_control/unity-npc-llm-training-dashboard
npm install
```

### Running Locally
```bash
npm run dev
```
The dashboard will be available at `http://localhost:3100` (by default).

### Environment Variables
Create a `.env` file in the dashboard directory:
```env
PORT=3100
GEMINI_API_KEY=your_key_here # Optional: For the AI Assistant sidebar
```

## 🛠️ Core Features

### 1. Control Center (Job Management)
Trigger any stage of the NPC pipeline with visual progress tracking:
- **Generate**: Create datasets from subject specs.
- **Sanitize**: Clean and validate training data.
- **Train**: Fine-tune models with model-aware presets.
- **Pipeline**: Run the full Gen -> Sanitize -> Train -> Export loop in one click.
- **Evaluate/Smoke**: Benchmark and validate exported GGUF models.

### 2. W&B Integration
Weights & Biases is fully integrated for experiment tracking and artifact versioning.

**Dashboard surface:**
- **W&B column** in the Operations Matrix table — click the icon to open a run's W&B dashboard in a new tab.
- **W&B Run Active card** in the job detail panel below the table — shows the full wandb.ai URL with a live indicator.
- **Enable W&B Tracking checkbox** in the Training Suite — when checked, `--wandb` is appended to the `./ucore train` command.

**How it works (server-side):**
- The server parses stdout for wandb.ai run URLs as they stream in from `wandb.init()` output.
- When a URL is detected (`https://wandb.ai/.../runs/<id>`), it's stored on the `Job` object as `wandbUrl`.
- The URL is broadcasted immediately via WebSocket `job_update` event.
- Only the first URL per job is captured — subsequent wandb output is ignored.

**CLI equivalent:**
```bash
./ucore train subjects/my_npc.json --preset fast-3b --wandb
```

### 3. Log Streaming

The dashboard captures all stdout/stderr from spawned child processes in real-time.

**Architecture:**
| Component | Role |
|-----------|------|
| `spawn()` in server.ts | Launches `./ucore` as child process |
| `consume()` callback | Splits stdout/stderr chunks into lines, timestamps them |
| `job.logs` | Per-job log buffer (capped at 2,000 lines) |
| `stage.logs` | Per-pipeline-stage log buffer (capped at 50 lines) |
| `registry.logs` | Global shared log buffer (capped at 600 lines, **cleared on server restart**) |
| WebSocket broadcast | Streams `job_update` events to connected clients |
| HTTP polling | Frontend falls back to polling `/api/logs` every 5s |

**Reliability improvements:**
- **Debounced persistence**: `persistRegistry()` debounces disk writes to `registry.json` (500ms window). High-frequency log output during training no longer floods the disk.
- **Flush on critical events**: Job completion, failure, stop, and escalation all use `flushPersist()` for immediate durability — no data loss on crash.
- **Increased log capacity**: Job logs increased from 600 to 2,000 lines to cover multi-hour training runs.
- **Transient global buffer**: `registry.logs` is wiped on server restart — stale sync messages from previous sessions don't accumulate.

**Log data flow:**
```
Child process stdout/stderr
  → consume() splits lines, adds timestamps
    → job.logs (2,000 line cap, persisted via .debounce)
    → stage.logs (50 line cap)
    → registry.logs (600 line cap, transient)
    → parseLoss() extracts numeric loss for progress tracking
    → wandb URL regex extracts run links
    → persistRegistry(debounced)
      → registry.json on disk
```

### 4. Asset Explorer
- **Subjects**: Browse available NPC specifications.
- **Datasets**: View generated training data, entry counts, and versions.
- **Exports**: Quick access to quantized GGUF models ready for Unity.

### 5. AI Assistant
A specialized sidebar trained on Unity and Unsloth best practices. It provides contextual advice on hyperparameter tuning and NPC persona design.

## 🔌 Integration Details

### How it talks to the CLI
The dashboard acts as a wrapper around the `ucore` CLI. When you click "Train", the server executes:
```bash
./ucore train subjects/npc_key.json --from-spec --preset fast-3b
```
It then parses the STDOUT stream for `[stage]` markers and `loss: 0.123` patterns to update the UI progress and charts.

### Directory Mapping
The dashboard expects the following structure relative to its root:
- `../../subjects/`: Source of NPC specs.
- `../../datasets/`: Source/Target for training data.
- `../../outputs/`: Target for LoRA adapters.
- `../../exports/`: Target for GGUF models.

---
> [!TIP]
> If telemetry is not showing GPU data, ensure `nvidia-smi` is in your system PATH and accessible by the user running the dashboard server.
