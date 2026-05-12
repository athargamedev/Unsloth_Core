#!/usr/bin/env python3
"""
dashboard.py — FastAPI training monitoring dashboard.

Usage:
    python scripts/dashboard.py [--port 8000] [--host 0.0.0.0]

Provides:
  - Real-time GPU/CPU/system metrics via WebSocket
  - Training config browser and one-click start/stop
  - Live loss chart from TensorBoard events
  - Model export and comparison viewer
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths

try:
    import GPUtil
    import psutil
except ImportError:
    GPUtil = None
    psutil = None

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger("unsloth-dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="Unsloth Training Dashboard", version="2.0.0")

# Template path
template_dir = Path(__file__).resolve().parent.parent / "templates"
template_dir.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(template_dir))

# Global state
training_processes: Dict[str, subprocess.Popen] = {}
training_start_times: Dict[str, str] = {}
training_metrics: Dict[str, List[Dict]] = {}
system_metrics: List[Dict] = []

# Paths
CONFIGS_PATH = paths.PROJECT_ROOT / "configs"
PRESETS_PATH = paths.PROJECT_ROOT / "configs" / "presets"
OUTPUTS_PATH = paths.output_root()
EXPORTS_PATH = paths.export_root()
DATASETS_PATH = paths.dataset_root()
EVAL_PATH = paths.eval_root()
SCRIPTS_PATH = paths.PROJECT_ROOT / "scripts"
VENV_PYTHON = paths.PROJECT_ROOT / "unsloth_env" / "bin" / "python"


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.active_connections.remove(conn)


manager = ConnectionManager()


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_available_configs() -> List[Dict]:
    configs = []
    for yaml_file in sorted(CONFIGS_PATH.glob("*.yaml"),
                            key=lambda f: f.stat().st_mtime, reverse=True):
        configs.append({
            "name": yaml_file.stem,
            "path": str(yaml_file),
            "modified": datetime.fromtimestamp(yaml_file.stat().st_mtime).isoformat(),
        })
    return configs


def get_subject_specs() -> List[Dict]:
    subjects_path = PROJECT_ROOT / "subjects"
    specs = []
    for json_file in sorted(subjects_path.glob("*.json")):
        specs.append({
            "name": json_file.stem,
            "path": str(json_file),
        })
    return specs


def get_exports() -> List[Dict]:
    exports = []
    if not EXPORTS_PATH.exists():
        return exports
    for export_dir in sorted(EXPORTS_PATH.iterdir()):
        if not export_dir.is_dir() or export_dir.name == "colab":
            continue
        gguf_files = list(export_dir.glob("*.gguf"))
        manifest = {}
        manifest_file = export_dir / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file) as f:
                    manifest = json.load(f)
            except Exception:
                pass
        exports.append({
            "name": export_dir.name,
            "gguf_files": [{"name": g.name, "path": str(g), "size_mb": round(g.stat().st_size / (1024*1024), 1)} for g in gguf_files],
            "manifest": manifest,
        })
    return exports


def get_system_metrics() -> Dict:
    gpu_info = []
    if GPUtil:
        try:
            gpus = GPUtil.getGPUs()
            gpu_info = [{
                "id": gpu.id,
                "name": gpu.name,
                "load": round(gpu.load * 100, 1),
                "memory_used": gpu.memoryUsed,
                "memory_total": gpu.memoryTotal,
                "memory_percent": round(gpu.memoryUtil * 100, 1),
                "temperature": gpu.temperature,
            } for gpu in gpus]
        except Exception:
            pass

    mem_info = {}
    if psutil:
        mem = psutil.virtual_memory()
        mem_info = {
            "used_gb": round(mem.used / (1024**3), 1),
            "total_gb": round(mem.total / (1024**3), 1),
            "percent": mem.percent,
        }
        cpu_percent = psutil.cpu_percent(interval=0)
    else:
        cpu_percent = 0

    return {
        "timestamp": datetime.now().isoformat(),
        "cpu_percent": cpu_percent,
        "memory": mem_info,
        "gpus": gpu_info,
    }


def get_training_processes() -> List[Dict]:
    processes = []
    for name, proc in list(training_processes.items()):
        rc = proc.poll()
        processes.append({
            "name": name,
            "pid": proc.pid,
            "status": "running" if rc is None else ("finished" if rc == 0 else "failed"),
            "return_code": rc,
            "start_time": training_start_times.get(name, "unknown"),
        })
    return processes


def get_leaderboard() -> List[Dict]:
    """Fetch best performing models from Supabase test_results."""
    import os
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return []

    try:
        from supabase import create_client
        client = create_client(url, key)
        # Fetch summary test results ordered by score
        response = client.table("test_results") \
            .select("*") \
            .eq("test_type", "summary") \
            .order("score", desc=True) \
            .limit(10) \
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return []


def get_presets() -> List[Dict]:
    """List available training presets from configs/presets/."""
    presets = []
    if not PRESETS_PATH.exists():
        return presets
    for yaml_file in sorted(PRESETS_PATH.glob("*.yaml")):
        with open(yaml_file) as f:
            first_line = f.readline().strip().lstrip("# ").strip()
        presets.append({
            "name": yaml_file.stem,
            "description": first_line,
            "path": str(yaml_file),
        })
    return presets


def get_datasets() -> List[Dict]:
    """List available datasets grouped by NPC and technique."""
    datasets = []
    if not DATASETS_PATH.exists():
        return datasets
    for npc_dir in sorted(DATASETS_PATH.iterdir()):
        if not npc_dir.is_dir():
            continue
        techniques = []
        for technique_dir in sorted(npc_dir.iterdir()):
            if technique_dir.is_dir():
                train_file = technique_dir / "train.jsonl"
                val_file = technique_dir / "validation.jsonl"
                train_count = sum(1 for _ in open(train_file)) if train_file.exists() else 0
                val_count = sum(1 for _ in open(val_file)) if val_file.exists() else 0
                techniques.append({
                    "name": technique_dir.name,
                    "train_count": train_count,
                    "val_count": val_count,
                })
        datasets.append({
            "npc_key": npc_dir.name,
            "techniques": techniques,
        })
    return datasets


def get_runs() -> List[Dict]:
    """List all training runs across all NPCs."""
    runs = []
    if not OUTPUTS_PATH.exists():
        return runs
    for npc_dir in sorted(OUTPUTS_PATH.iterdir()):
        if not npc_dir.is_dir():
            continue
        runs_dir = npc_dir / "runs"
        if not runs_dir.exists():
            continue
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            config_file = run_dir / "config.yaml"
            metrics_file = run_dir / "metrics.json"
            metrics = {}
            if metrics_file.exists():
                try:
                    with open(metrics_file) as f:
                        metrics = json.load(f)
                except Exception:
                    pass
            runs.append({
                "npc_key": npc_dir.name,
                "run_id": run_dir.name,
                "path": str(run_dir),
                "has_config": config_file.exists(),
                "metrics": metrics,
            })
    return runs


def get_eval_reports() -> Dict:
    """List evaluation reports and comparisons."""
    reports = []
    reports_dir = EVAL_PATH / "reports"
    if reports_dir.exists():
        for npc_dir in sorted(reports_dir.iterdir()):
            if not npc_dir.is_dir():
                continue
            files = sorted(npc_dir.glob("*.*"))
            reports.append({
                "npc_key": npc_dir.name,
                "files": [{"name": f.name, "path": str(f)} for f in files],
            })
    comparisons = []
    comp_dir = EVAL_PATH / "comparisons"
    if comp_dir.exists():
        comparisons = [{"name": f.name, "path": str(f)} for f in sorted(comp_dir.glob("*.*"))]
    return {"reports": reports, "comparisons": comparisons}


async def metrics_collector():
    """Background task: collect system and training metrics every 2s."""
    while True:
        try:
            sys_metrics = get_system_metrics()
            system_metrics.append(sys_metrics)
            if len(system_metrics) > 500:
                system_metrics[:] = system_metrics[-500:]

            # Read training loss from log files
            active = [(n, p) for n, p in training_processes.items() if p.poll() is None]
            if active:
                # Scan for TensorBoard event files across all runs
                for npc_dir in sorted(OUTPUTS_PATH.iterdir()):
                    if not npc_dir.is_dir():
                        continue
                    runs_base = npc_dir / "runs"
                    if not runs_base.exists():
                        continue
                    for rd in sorted(runs_base.iterdir()):
                        if not rd.is_dir():
                            continue
                        event_files = sorted(rd.glob("events.out.tfevents.*"))
                        if event_files:
                            try:
                                from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
                                ea = EventAccumulator(str(rd))
                                ea.Reload()
                                for tag in ea.Tags().get("scalars", []):
                                    events = ea.Scalars(tag)
                                    if events:
                                        parsed = [{"step": e.step, "value": round(e.value, 4)}
                                                  for e in events[-50:]]
                                        if parsed:
                                            training_metrics[f"{npc_dir.name}:{rd.name}:{tag}"] = parsed[-100:]
                            except Exception:
                                pass

            # Broadcast
            await manager.broadcast({
                "type": "metrics_update",
                "system": system_metrics[-60:],
                "training": {k: v[-30:] for k, v in training_metrics.items() if v},
                "processes": get_training_processes(),
            })
        except Exception as e:
            logger.error(f"Metrics error: {e}")
        await asyncio.sleep(2)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(metrics_collector())
    logger.info("Dashboard started")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "configs": get_available_configs(),
            "processes": get_training_processes(),
            "subjects": get_subject_specs(),
            "exports": get_exports(),
            "leaderboard": get_leaderboard(),
        }
    )


@app.get("/api/leaderboard")
async def api_leaderboard():
    return get_leaderboard()


@app.get("/api/configs")
async def list_configs():
    return get_available_configs()


@app.get("/api/subjects")
async def list_subjects():
    return get_subject_specs()


@app.get("/api/exports")
async def list_exports():
    return get_exports()


@app.get("/api/presets")
async def list_presets():
    return get_presets()


@app.get("/api/datasets")
async def list_datasets():
    return get_datasets()


@app.get("/api/runs")
async def list_runs():
    return get_runs()


@app.get("/api/eval-reports")
async def list_eval_reports():
    return get_eval_reports()


@app.get("/api/dataset/{npc_key}/{technique}")
async def view_dataset(npc_key: str, technique: str, n: int = 10):
    """View N samples from a dataset."""
    if ".." in npc_key or ".." in technique:
        raise HTTPException(status_code=400, detail="Invalid path")
    train_path = paths.dataset_train_path(npc_key, technique)
    if not train_path.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")
    samples = []
    with open(train_path) as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                samples.append({"error": "Invalid JSON", "raw": line[:200]})
    total = sum(1 for _ in open(train_path) if _.strip())
    return {"npc_key": npc_key, "technique": technique, "total_samples": total, "samples": samples}


@app.get("/api/run/{npc_key}/{run_id}")
async def view_run(npc_key: str, run_id: str):
    """View details of a specific run."""
    if ".." in npc_key or ".." in run_id:
        raise HTTPException(status_code=400, detail="Invalid path")
    run_path = paths.run_dir(npc_key, run_id)
    if not run_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    
    config = {}
    config_file = run_path / "config.yaml"
    if config_file.exists():
        try:
            import yaml
            with open(config_file) as f:
                config = yaml.safe_load(f)
        except Exception:
            pass

    metrics = {}
    metrics_file = run_path / "metrics.json"
    if metrics_file.exists():
        try:
            with open(metrics_file) as f:
                metrics = json.load(f)
        except Exception:
            pass

    return {
        "npc_key": npc_key,
        "run_id": run_id,
        "path": str(run_path),
        "config": config,
        "metrics": metrics,
    }


@app.get("/api/processes")
async def list_processes():
    return get_training_processes()


@app.post("/api/train/{config_name}")
async def start_training(config_name: str):
    if ".." in config_name or "/" in config_name:
        raise HTTPException(status_code=400, detail="Invalid config name")

    config_path = CONFIGS_PATH / f"{config_name}.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config '{config_name}' not found")

    if config_name in training_processes and training_processes[config_name].poll() is None:
        raise HTTPException(status_code=409, detail=f"Training '{config_name}' already running")

    # Use the venv python to run train.py
    train_script = SCRIPTS_PATH / "train.py"
    cmd = [str(VENV_PYTHON), str(train_script), str(config_path)]

    if not VENV_PYTHON.exists():
        # Fall back to system python
        cmd = [sys.executable, str(train_script), str(config_path)]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=str(PROJECT_ROOT),
        )
        training_processes[config_name] = proc
        training_start_times[config_name] = datetime.now().isoformat()
        logger.info(f"Started training: {config_name} (PID {proc.pid})")
        return {"status": "started", "config": config_name, "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start: {str(e)}")


@app.post("/api/stop/{config_name}")
async def stop_training(config_name: str):
    if ".." in config_name or "/" in config_name:
        raise HTTPException(status_code=400, detail="Invalid config name")

    if config_name not in training_processes:
        raise HTTPException(status_code=404, detail=f"No process for '{config_name}'")

    proc = training_processes[config_name]
    if proc.poll() is not None:
        raise HTTPException(status_code=409, detail=f"Training '{config_name}' is not running")

    try:
        proc.terminate()
        await asyncio.sleep(2)
        if proc.poll() is None:
            proc.kill()
        logger.info(f"Stopped training: {config_name}")
        return {"status": "stopped", "config": config_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export/{output_name}")
async def export_model(output_name: str):
    """Trigger GGUF export from a completed training output."""
    if ".." in output_name or "/" in output_name:
        raise HTTPException(status_code=400, detail="Invalid output name")

    output_dir = OUTPUTS_PATH / output_name
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Output '{output_name}' not found")

    # Check for LoRA adapter
    if not (output_dir / "adapter_config.json").exists():
        raise HTTPException(status_code=400, detail=f"Output '{output_name}' has no LoRA adapter")

    export_script = SCRIPTS_PATH / "export.py"
    cmd = [str(VENV_PYTHON), str(export_script), str(output_dir)]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )
        return {"status": "exporting", "output": output_name, "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Clients can send ping to keep alive
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.on_event("shutdown")
async def shutdown_event():
    for name, proc in training_processes.items():
        if proc.poll() is None:
            proc.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=5)
            except Exception:
                proc.kill()
    logger.info("Dashboard shutdown complete")


if __name__ == "__main__":
    import uvicorn

    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    args = parser.parse_args()

    print(f"Unsloth Training Dashboard")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Configs:   {CONFIGS_PATH}")
    print(f"  Outputs:   {OUTPUTS_PATH}")
    print(f"  Datasets:  {DATASETS_PATH}")
    print(f"  Exports:   {EXPORTS_PATH}")
    print(f"  Eval:      {EVAL_PATH}")
    print(f"  Python:    {VENV_PYTHON if VENV_PYTHON.exists() else 'system'}")
    print()

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
