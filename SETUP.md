# Setup Guide: Unsloth_Core

Complete environment setup for training llama3.2 3B GGUF LoRA adapters on a local RTX 3060-class (6GB VRAM) machine.

## Prerequisites

- Linux (Ubuntu 22.04+ recommended)
- CUDA 12.x + compatible NVIDIA driver
- Python 3.10+
- Node.js 18+ (for dashboard)
- Docker + Supabase CLI (for Supabase)

## 1. Clone & Venv

```bash
git clone <repo-url> unsloth_core
cd unsloth_core

python3 -m venv unsloth_env
source unsloth_env/bin/activate
```

## 2. Install Python Dependencies

```bash
# Core dependencies
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Unsloth (CUDA 12.x)
pip install "unsloth[cu124-ampere] @ git+https://github.com/unslothai/unsloth.git"

# Project deps
pip install -r requirements.txt
```

If no `requirements.txt` exists, install manually:

```bash
pip install transformers datasets accelerate peft bitsandbytes
pip install python-dotenv pyyaml tqdm
pip install pytest pytest-xdist
```

## 3. Verify Unsloth + CUDA

```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0)}')"
python -c "from unsloth import FastLanguageModel; print('Unsloth OK')"
```

Expected output:
```
CUDA: True, Device: NVIDIA GeForce RTX 3060
Unsloth OK
```

## 4. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Then pull the judge model:

```bash
ollama pull qwen2.5:7b
```

Verify:

```bash
ollama list
```

## 5. Supabase Local Stack

Install Supabase CLI if not present:

```bash
# npm
npm install -g supabase
# Or brew on macOS
brew install supabase/tap/supabase
```

Start:

```bash
cd unsloth_core
supabase start
```

Verify services (ports from `supabase status`):

| Service | Port  |
|---------|-------|
| DB      | 15434 |
| API     | 16437 |
| Studio  | 16438 |

## 6. Dashboard (Optional)

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm install
npm run dev
```

Dashboard runs on http://localhost:3100.

## 7. Full Verification

```bash
source unsloth_env/bin/activate

# Health check
./ucore audit check

# Validate NPC specs
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready

# Quick train test (smoke, 3 steps)
./ucore train data/npcs/specs/history_guide.json --technique template --preset test-readiness --dry-run
```

If `./ucore` is not found, you may need to make it executable:

```bash
chmod +x ucore
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gcc` not found during Unsloth install | `sudo apt install build-essential` |
| CUDA out of memory | Unload Ollama (`ollama stop <model>`), reduce batch size, or use `safe-any` preset |
| Triton compile error | Ensure `/usr/bin/gcc` and `as` (binutils) are on PATH |
| Supabase won't start | Check Docker is running and ports 15434/16437/16438 are free |
| Ollama model not responding | Restart Ollama: `systemctl --user restart ollama` |
| Dashboard port conflict | Edit `vite.config.ts` to change port |
