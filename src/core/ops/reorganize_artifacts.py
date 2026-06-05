import os
import shutil
import subprocess
from pathlib import Path

repo_dir = Path("/home/athar/Projects/Unsloth_Core")


def run_cmd(args, cwd=repo_dir, capture=True):
    res = subprocess.run(args, cwd=cwd, capture_output=capture, text=True)
    return res


def is_tracked(path):
    # Check if a file/dir is tracked in git
    res = run_cmd(["git", "ls-files", "--error-unmatch", str(path)])
    return res.returncode == 0


def move_recursively(src_dir_name, dest_dir_name):
    src_dir = repo_dir / src_dir_name
    dest_dir = repo_dir / dest_dir_name

    if not src_dir.exists():
        print(f"Source dir {src_dir_name} does not exist. Skipping.")
        return

    print(f"Moving contents of {src_dir_name} to {dest_dir_name}...")

    # We walk the source directory recursively
    for root, _dirs, files in os.walk(src_dir):
        for name in files:
            file_path = Path(root) / name
            rel_path = file_path.relative_to(src_dir)
            target_path = dest_dir / rel_path

            # Ensure target parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # If the source is a symlink, handle it manually
            if file_path.is_symlink():
                link_target = os.readlink(file_path)
                if target_path.exists() or target_path.is_symlink():
                    if target_path.is_symlink() or target_path.is_file():
                        target_path.unlink()
                    else:
                        shutil.rmtree(target_path)
                os.symlink(link_target, target_path)
                # If tracked, we must remove old and add new
                if is_tracked(file_path.relative_to(repo_dir)):
                    run_cmd(["git", "rm", "--cached", str(file_path.relative_to(repo_dir))])
                continue

            if is_tracked(file_path.relative_to(repo_dir)):
                print(
                    f"Git move: {file_path.relative_to(repo_dir)} -> {target_path.relative_to(repo_dir)}"
                )
                # Git mv needs target dir to exist, which we created
                run_cmd(
                    [
                        "git",
                        "mv",
                        str(file_path.relative_to(repo_dir)),
                        str(target_path.relative_to(repo_dir)),
                    ]
                )
            else:
                print(
                    f"FS move: {file_path.relative_to(repo_dir)} -> {target_path.relative_to(repo_dir)}"
                )
                if target_path.exists():
                    os.remove(target_path)
                shutil.move(str(file_path), str(target_path))

    # Clean up old empty subdirectories
    shutil.rmtree(src_dir)
    print(f"Removed old dir {src_dir_name}")

    # Create symlink from old to new
    if src_dir.exists() or src_dir.is_symlink():
        src_dir.unlink()

    # Symlink target should be relative for portability
    # outputs/ is at root, artifacts/models/ is at root, so relative is: artifacts/models
    rel_symlink_target = os.path.relpath(dest_dir, src_dir.parent)
    os.symlink(rel_symlink_target, src_dir)
    print(f"Created symlink {src_dir_name} -> {rel_symlink_target}")

    # Git track the symlink
    run_cmd(["git", "add", src_dir_name])
    print(f"Staged symlink {src_dir_name} in Git")


# 1. Clean and symlink configs -> etc
configs_dir = repo_dir / "configs"
if configs_dir.exists() and not configs_dir.is_symlink():
    shutil.rmtree(configs_dir)
    print("Removed old configs/ directory on disk")
os.symlink("etc", configs_dir)
run_cmd(["git", "add", "configs"])
print("Created symlink configs -> etc and staged in Git")

# 2. Reorganize artifact directories
move_recursively("outputs", "artifacts/models")
move_recursively("exports", "artifacts/exports")
move_recursively("eval", "artifacts/eval")
move_recursively("logs", "artifacts/logs")

# 3. Move .pipeline to var/.pipeline (untracked)
pipeline_dir = repo_dir / ".pipeline"
var_pipeline_dir = repo_dir / "var" / ".pipeline"
if pipeline_dir.exists() and not pipeline_dir.is_symlink():
    var_pipeline_dir.parent.mkdir(parents=True, exist_ok=True)
    if var_pipeline_dir.exists():
        shutil.rmtree(var_pipeline_dir)
    shutil.move(str(pipeline_dir), str(var_pipeline_dir))
    os.symlink("var/.pipeline", pipeline_dir)
    print("Moved .pipeline -> var/.pipeline and created symlink")

# 4. Move unsloth compiled cache to var/.cache/unsloth
unsloth_cache = repo_dir / "unsloth_compiled_cache"
var_unsloth_cache = repo_dir / "var" / ".cache" / "unsloth"
if unsloth_cache.exists() and not unsloth_cache.is_symlink():
    var_unsloth_cache.parent.mkdir(parents=True, exist_ok=True)
    if var_unsloth_cache.exists():
        shutil.rmtree(var_unsloth_cache)
    shutil.move(str(unsloth_cache), str(var_unsloth_cache))
    print("Moved unsloth_compiled_cache -> var/.cache/unsloth")

# 5. Move .pytest_cache to var/.cache/pytest
pytest_cache = repo_dir / ".pytest_cache"
var_pytest_cache = repo_dir / "var" / ".cache" / "pytest"
if pytest_cache.exists() and not pytest_cache.is_symlink():
    var_pytest_cache.parent.mkdir(parents=True, exist_ok=True)
    if var_pytest_cache.exists():
        shutil.rmtree(var_pytest_cache)
    shutil.move(str(pytest_cache), str(var_pytest_cache))
    print("Moved .pytest_cache -> var/.cache/pytest")

print("=== MIGRATION SCRIPT EXECUTED SUCCESSFUL ===")
