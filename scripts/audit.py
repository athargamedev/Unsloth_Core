#!/usr/bin/env python3
"""
Unsloth_Core Context Audit: Verify environment, NPC state, dataset quality, training history.

Usage:
  python audit.py check           # Quick environment check
  python audit.py check --full    # Full health check (env + NPC state + datasets)
  python audit.py diagnose --npc <key>  # Why did this NPC fail? (requires Supabase)
  python audit.py resume          # What was pending? Recover session context
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import subprocess


class ProjectAudit:
    def __init__(self, project_root="/home/athar/Projects/Unsloth_Core"):
        self.root = Path(project_root)
        self.state_file = self.root / "eval/results/pipeline_state.json"
        self.supabase_db_url = "postgresql://postgres:postgres@127.0.0.1:15434/postgres"
        
    def check_environment(self):
        """Verify Docker, Supabase, ports, disk space."""
        result = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "score": 0.0
        }
        
        # Docker memory
        try:
            mem_info = subprocess.check_output(
                "docker info | grep 'Total Memory'", 
                shell=True, text=True, stderr=subprocess.DEVNULL
            ).strip()
            result["checks"]["docker_memory"] = mem_info
            # Flag if less than 16GB
            if "11.68" in mem_info or "12." in mem_info or "13." in mem_info or "14." in mem_info or "15." in mem_info:
                result["checks"]["docker_memory_low"] = True
            else:
                result["checks"]["docker_ok"] = True
        except Exception as e:
            result["checks"]["docker_error"] = f"Could not check: {e}"
            
        # Supabase health
        try:
            health = subprocess.run(
                ["curl", "-s", "-m", "5", "http://127.0.0.1:16437/rest/v1/"],
                capture_output=True, timeout=6
            ).returncode == 0
            result["checks"]["supabase_ok"] = health
        except Exception as e:
            result["checks"]["supabase_ok"] = False
            
        # Port availability (key ports)
        ports = {16437: "Supabase API", 16438: "Studio", 15434: "Postgres", 5432: "Postgres Alt"}
        port_status = {}
        for port, label in ports.items():
            try:
                res = subprocess.run(
                    f"nc -zv 127.0.0.1 {port} 2>&1", 
                    shell=True, capture_output=True, timeout=1
                )
                port_status[f"{label} ({port})"] = res.returncode == 0
            except:
                port_status[f"{label} ({port})"] = False
        result["checks"]["ports"] = port_status
        
        # Disk space
        try:
            stat = os.statvfs(self.root)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            result["checks"]["disk_free_gb"] = round(free_gb, 1)
            result["checks"]["disk_ok"] = free_gb > 50
        except Exception as e:
            result["checks"]["disk_error"] = str(e)
        
        # Calculate score
        true_count = sum(1 for k, v in result["checks"].items() if v is True)
        bool_count = sum(1 for k, v in result["checks"].items() if isinstance(v, bool))
        if bool_count > 0:
            result["score"] = true_count / bool_count
        
        return result
    
    def audit_npc_state(self):
        """Read pipeline_state.json and show NPC status."""
        state = {}
        
        # Load local state
        if self.state_file.exists():
            with open(self.state_file) as f:
                state = json.load(f)
        
        return {
            "local_state": state,
            "timestamp": datetime.now().isoformat()
        }
    
    def audit_datasets(self):
        """Check all datasets for consistency and quality."""
        dataset_dir = self.root / "subjects/datasets"
        audit = {"datasets": {}, "issues": []}
        
        if not dataset_dir.exists():
            audit["issues"].append("❌ No datasets directory found")
            return audit
        
        for npc_dir in dataset_dir.iterdir():
            if not npc_dir.is_dir():
                continue
            npc_key = npc_dir.name
            
            for technique_dir in npc_dir.iterdir():
                if not technique_dir.is_dir():
                    continue
                    
                train_file = technique_dir / "train.jsonl"
                clean_file = technique_dir / "train_clean.jsonl"
                
                if train_file.exists():
                    try:
                        with open(train_file) as f:
                            train_lines = len(f.readlines())
                        clean_lines = 0
                        if clean_file.exists():
                            with open(clean_file) as f:
                                clean_lines = len(f.readlines())
                        
                        audit["datasets"][f"{npc_key}/{technique_dir.name}"] = {
                            "train_rows": train_lines,
                            "clean_rows": clean_lines,
                            "sanitization_ratio": round(clean_lines / train_lines, 2) if train_lines > 0 else 0
                        }
                        
                        if clean_lines < 100:
                            audit["issues"].append(f"⚠️  {npc_key}: Only {clean_lines} clean rows (minimum 100 recommended)")
                        elif clean_lines == 0:
                            audit["issues"].append(f"❌ {npc_key}: No clean data! Run sanitize.")
                    except Exception as e:
                        audit["issues"].append(f"❌ {npc_key}: Could not read dataset ({e})")
        
        if not audit["datasets"]:
            audit["issues"].append("ℹ️  No datasets found yet")
        
        return audit
    
    def audit_training_outputs(self):
        """Check training outputs and recent runs."""
        outputs_dir = self.root / "outputs"
        audit = {"models": {}, "issues": []}
        
        if not outputs_dir.exists():
            audit["issues"].append("ℹ️  No training outputs yet")
            return audit
        
        for npc_dir in outputs_dir.iterdir():
            if not npc_dir.is_dir():
                continue
            npc_key = npc_dir.name
            
            # Check for runs subdirectory
            runs_dir = npc_dir / "runs"
            if runs_dir.exists():
                run_folders = list(runs_dir.iterdir())
                if run_folders:
                    latest_run = sorted(run_folders, key=lambda x: x.stat().st_mtime, reverse=True)[0]
                    audit["models"][npc_key] = {
                        "last_run": latest_run.name,
                        "run_count": len(run_folders)
                    }
            else:
                audit["issues"].append(f"⚠️  {npc_key}: No runs directory")
        
        if not audit["models"]:
            audit["issues"].append("ℹ️  No training runs yet")
        
        return audit
    
    def audit_eval_results(self):
        """Check evaluation results."""
        eval_dir = self.root / "eval/results"
        audit = {"results": {}, "issues": []}
        
        if not eval_dir.exists():
            audit["issues"].append("ℹ️  No eval directory")
            return audit
        
        # Check pipeline_state.json
        state_file = eval_dir / "pipeline_state.json"
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
            audit["results"]["pipeline_state"] = state
        else:
            audit["issues"].append("ℹ️  No pipeline_state.json yet")
        
        return audit
    
    def report(self, audit_type="env"):
        """Generate human-readable report."""
        print(f"\n{'='*70}")
        print(f"🔍 Unsloth_Core Context Audit — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")
        
        if audit_type in ("full", "env"):
            env = self.check_environment()
            health_pct = int(env['score'] * 100)
            health_emoji = "✅" if health_pct >= 80 else "⚠️ " if health_pct >= 50 else "❌"
            print(f"📊 Environment Health: {health_emoji} {health_pct}%\n")
            
            for key, val in env["checks"].items():
                if isinstance(val, bool):
                    status = "✅" if val else "❌"
                elif isinstance(val, dict):
                    # Ports dict
                    status = f"({sum(1 for v in val.values() if v)}/{len(val)} available)"
                    print(f"  🔌 {key}: {status}")
                    for port_label, port_ok in val.items():
                        port_emoji = "✅" if port_ok else "❌"
                        print(f"      {port_emoji} {port_label}")
                    continue
                else:
                    status = "ℹ️ "
                print(f"  {status} {key}: {val}")
        
        if audit_type in ("full", "state"):
            state_audit = self.audit_npc_state()
            npc_state = state_audit["local_state"]
            print(f"\n📋 NPC Pipeline State ({len(npc_state)} NPCs):")
            if npc_state:
                for npc_key, info in npc_state.items():
                    status = info.get('status', 'unknown')
                    status_emoji = "✅" if status == "idle" else "🔄" if status == "training" else "⚠️ "
                    print(f"  {status_emoji} {npc_key}: {status}")
                    if info.get("weak_concepts_count", 0) > 0:
                        print(f"      ⚠️  {info['weak_concepts_count']} weak concepts: {info.get('focus_categories', [])}")
                    if info.get("knowledge_gaps", 0) > 0:
                        print(f"      ⚠️  {info['knowledge_gaps']} knowledge gaps detected")
            else:
                print(f"  ℹ️  No NPC state data yet")
        
        if audit_type in ("full", "dataset"):
            datasets = self.audit_datasets()
            print(f"\n📦 Dataset Quality ({len(datasets['datasets'])} datasets):")
            if datasets["datasets"]:
                for dataset, metrics in datasets["datasets"].items():
                    ratio = metrics["sanitization_ratio"]
                    ratio_emoji = "✅" if ratio > 0.85 else "⚠️ " if ratio > 0.50 else "❌"
                    print(f"  {ratio_emoji} {dataset}: {metrics['clean_rows']} clean / {metrics['train_rows']} raw ({ratio:.0%})")
            else:
                print(f"  ℹ️  No datasets found")
            
            if datasets["issues"]:
                print(f"\n  Issues:")
                for issue in datasets["issues"]:
                    print(f"    {issue}")
        
        if audit_type == "full":
            # Add training outputs and eval results to full report
            training = self.audit_training_outputs()
            print(f"\n🏋️  Training Outputs ({len(training['models'])} models):")
            if training["models"]:
                for model, info in training["models"].items():
                    print(f"  • {model}: {info['run_count']} run(s), latest: {info['last_run']}")
            else:
                print(f"  ℹ️  No training outputs yet")
            
            if training["issues"]:
                for issue in training["issues"]:
                    print(f"  {issue}")
            
            eval_audit = self.audit_eval_results()
            print(f"\n📊 Evaluation Results:")
            if eval_audit["results"].get("pipeline_state"):
                print(f"  ✅ pipeline_state.json found")
            else:
                print(f"  ℹ️  No eval results yet")
            
            if eval_audit["issues"]:
                for issue in eval_audit["issues"]:
                    print(f"  {issue}")
        
        print(f"\n{'='*70}\n")
    
    def diagnose_npc(self, npc_key):
        """Diagnose why a specific NPC failed."""
        print(f"\n{'='*70}")
        print(f"🔍 Diagnosing: {npc_key}")
        print(f"{'='*70}\n")
        
        # Check local state
        state_audit = self.audit_npc_state()
        npc_info = state_audit["local_state"].get(npc_key)
        
        if npc_info:
            print(f"📋 Current State: {npc_info.get('status')}")
            print(f"   Last updated: {npc_info.get('last_updated')}")
            if npc_info.get("weak_concepts_count", 0) > 0:
                print(f"   ⚠️  Weak concepts: {npc_info.get('focus_categories', [])}")
        else:
            print(f"⚠️  No state info for {npc_key}")
        
        # Check datasets
        datasets = self.audit_datasets()
        npc_datasets = {k: v for k, v in datasets["datasets"].items() if k.startswith(npc_key)}
        if npc_datasets:
            print(f"\n📦 Dataset Status:")
            for dataset, metrics in npc_datasets.items():
                print(f"   {dataset}: {metrics['clean_rows']} clean rows")
        
        # Check training outputs
        training = self.audit_training_outputs()
        if npc_key in training["models"]:
            print(f"\n🏋️  Training Status:")
            print(f"   {training['models'][npc_key]['run_count']} run(s) completed")
            print(f"   Latest: {training['models'][npc_key]['last_run']}")
        else:
            print(f"\n🏋️  No training outputs for {npc_key} yet")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if not npc_datasets or all(m['clean_rows'] < 100 for m in npc_datasets.values()):
            print(f"   1. Generate and sanitize dataset: ./ucore pipeline {npc_key}")
        elif npc_info and npc_info.get('weak_concepts_count', 0) > 0:
            print(f"   1. Focus on weak concepts: {npc_info.get('focus_categories', [])}")
            print(f"   2. Re-run pipeline with feedback: ./ucore feedback <feedback_file>")
        else:
            print(f"   1. Run a training cycle: ./ucore train subjects/NPC_specs/{npc_key}.json --preset fast-3b")
        
        print(f"\n{'='*70}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unsloth_Core Context Audit")
    subparsers = parser.add_subparsers(dest="command", help="Audit command")
    
    # Check subcommand
    check_p = subparsers.add_parser("check", help="Health check")
    check_p.add_argument("--full", action="store_true", help="Full audit (env + NPC + datasets + training + eval)")
    
    # Diagnose subcommand
    diag_p = subparsers.add_parser("diagnose", help="Diagnose NPC issue")
    diag_p.add_argument("--npc", required=True, help="NPC key to diagnose")
    
    # Resume subcommand
    subparsers.add_parser("resume", help="Recover session context (full audit)")
    
    args = parser.parse_args()
    
    audit = ProjectAudit()
    
    if args.command == "check":
        audit.report("full" if args.full else "env")
    elif args.command == "diagnose":
        audit.diagnose_npc(args.npc)
    elif args.command == "resume":
        audit.report("full")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
