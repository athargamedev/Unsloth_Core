# Unity NPC LLM Training Dashboard

This dashboard is a visual orchestration layer for the **Unsloth_Core** pipeline. It allows you to monitor training metrics, manage hardware resources, and trigger pipeline stages via a web interface.

## 📖 Main Documentation
For detailed architecture, integration details, and technical references, see:
👉 **[Frontend Dashboard Technical Guide](../../docs/integration/FRONTEND_DASHBOARD.md)**

## 🚀 Quick Start

### 1. Installation
```bash
npm install
```

### 2. Configuration
Create a `.env` file based on `.env.example`:
```env
PORT=3100
GEMINI_API_KEY=your_key_here
```

### 3. Launch
```bash
npm run dev
```
Open `http://localhost:3100` in your browser.

## 🛠️ Key Components
- **Control Center**: Trigger `generate`, `sanitize`, `train`, `evaluate`, `smoke`, `export`, and full pipeline jobs.
- **Monitoring**: Real-time loss curves and GPU telemetry (requires `nvidia-smi`).
- **W&B Tracking**: Clickable W&B links per training run; toggle in Training Suite to enable tracking.
- **Log Streaming**: Real-time stdout/stderr capture with debounced persistence and W&B URL auto-extraction.
- **Asset Library**: Browse your `subjects`, `datasets`, and `exports`.
- **AI Assistant**: Specialized chat for NPC tuning advice.

## ✅ Recent Hardening (Reliability + Observability)
- External workflow visibility via artifact import and process discovery (`ext_*` jobs).
- WebSocket replay + heartbeat support with event IDs and HTTP replay fallback (`/api/events`).
- Schema-driven command forms (`/api/command-schemas`) with typed fields/defaults/required validation.
- Deterministic stage/progress truth (extracted to `progressTruth.ts`).
- Automated tests:
  - `progressTruth.test.ts` (unit)
  - `api.jobs.integration.test.ts` (API lifecycle integration)

Run verification:
```bash
npm run lint
npm run test
```

---
*For the underlying CLI documentation, see [CLI_REFERENCE.md](../../docs/reference/CLI_REFERENCE.md).*
