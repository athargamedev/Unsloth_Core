#!/usr/bin/env python3
"""Launch long-running chef_assistant generation as detached process."""

import os
import subprocess
import sys

logfile = "/tmp/chef_gen_full.log"
pidfile = "/tmp/chef_gen_full.pid"

# Check if already running
if os.path.exists(pidfile):
    with open(pidfile) as f:
        try:
            pid = int(f.read().strip())
            os.kill(pid, 0)
            print(f"Already running: PID {pid}")
            sys.exit(0)
        except (ProcessLookupError, ValueError, OSError):
            pass  # stale pid

os.chdir("/home/athar/Projects/Unsloth_Core")

env = os.environ.copy()
env["PATH"] = f"/home/athar/Projects/Unsloth_Core/unsloth_env/bin:{env.get('PATH', '')}"

with open(logfile, "w") as log:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "src/core/dataset/generate_dataset_ollama.py",
            "data/npcs/specs/chef_assistant.json",
            "--model",
            "qwen2.5:7b",
            "--fresh",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from parent process group
    )

with open(pidfile, "w") as f:
    f.write(str(proc.pid))

print(f"Started PID {proc.pid}")
print(f"Log: {logfile}")
