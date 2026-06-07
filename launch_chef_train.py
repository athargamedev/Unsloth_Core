#!/usr/bin/env python3
"""Launch long-running chef_assistant training as detached process."""

import os
import subprocess
import sys

logfile = "/tmp/chef_train.log"
pidfile = "/tmp/chef_train.pid"

if os.path.exists(pidfile):
    with open(pidfile) as f:
        try:
            pid = int(f.read().strip())
            os.kill(pid, 0)
            print(f"Already running: PID {pid}")
            sys.exit(0)
        except (ProcessLookupError, ValueError, OSError):
            pass

os.chdir("/home/athar/Projects/Unsloth_Core")

# Use unsloth_env python directly
PYTHON = "/home/athar/Projects/Unsloth_Core/unsloth_env/bin/python3"

env = os.environ.copy()
env["PATH"] = f"/home/athar/Projects/Unsloth_Core/unsloth_env/bin:{env.get('PATH', '')}"
env["VIRTUAL_ENV"] = "/home/athar/Projects/Unsloth_Core/unsloth_env"

with open(logfile, "w") as log:
    proc = subprocess.Popen(
        [
            PYTHON,
            "-u",
            "src/cli/ucore",
            "train",
            "data/npcs/specs/chef_assistant.json",
            "--technique",
            "ollama",
            "--preset",
            "fast-3b",
            "--allow-ungated-dataset",
            "--export-gguf",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

with open(pidfile, "w") as f:
    f.write(str(proc.pid))

print(f"Started chef_assistant training PID {proc.pid}")
print(f"Log: {logfile}")
