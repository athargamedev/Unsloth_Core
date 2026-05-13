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

### 2. Live Monitoring
- **Loss Curves**: Dynamic charts updated in real-time as `ucore` emits logs.
- **Hardware Telemetry**: Visual gauges for GPU Load, VRAM usage, and Temperature.
- **Process Logs**: Filterable, real-time terminal output for active jobs.

### 3. Asset Explorer
- **Subjects**: Browse available NPC specifications.
- **Datasets**: View generated training data, entry counts, and versions.
- **Exports**: Quick access to quantized GGUF models ready for Unity.

### 4. AI Assistant
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
