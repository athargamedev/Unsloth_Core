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
- **Control Center**: Trigger `generate`, `sanitize`, `train`, and `export` jobs.
- **Monitoring**: Real-time loss curves and GPU telemetry (requires `nvidia-smi`).
- **Asset Library**: Browse your `subjects`, `datasets`, and `exports`.
- **AI Assistant**: Specialized chat for NPC tuning advice.

---
*For the underlying CLI documentation, see [CLI_REFERENCE.md](../../docs/reference/CLI_REFERENCE.md).*
