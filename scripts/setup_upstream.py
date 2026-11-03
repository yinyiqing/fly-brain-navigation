#!/usr/bin/env python3
"""Fetch the pinned public model and its paired v783 inputs without modifying it."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ["model.py", "utils.py", "LICENSE", "Readme.md", "environment.yml",
         "environment_full.yml", "Completeness_783.csv", "Connectivity_783.parquet"]


def main():
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    target = ROOT / lock["local_path"]
    def git(*args):
        return subprocess.check_output(["git", "-C", str(target), *args], text=True).strip()
    if not target.exists():
        target.mkdir(parents=True)
        subprocess.run(["git", "init", str(target)], check=True)
        git("remote", "add", "origin", lock["repository"])
    if not (target / ".git").is_dir():
        raise RuntimeError("Existing upstream directory is not a Git repository")
    origin = git("remote", "get-url", "origin").rstrip("/").removesuffix(".git")
    expected = lock["repository"].rstrip("/").removesuffix(".git")
    if origin != expected:
        raise RuntimeError("Unexpected origin; leaving the existing checkout unchanged")
    head = subprocess.run(["git", "-C", str(target), "rev-parse", "--verify", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode:
        git("fetch", "--depth=1", "--filter=blob:none", "origin", lock["commit"])
        git("sparse-checkout", "init", "--no-cone")
        git("sparse-checkout", "set", "--no-cone", *["/" + name for name in FILES])
        git("checkout", "--detach", lock["commit"])
    elif head.stdout.strip() != lock["commit"]:
        raise RuntimeError("Existing checkout has another commit; inspect before replacing it")
    if git("status", "--porcelain"):
        raise RuntimeError("Upstream has local modifications; inspect before using it")
    missing = [name for name in FILES if not (target / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing pinned upstream inputs: " + ", ".join(missing))
    print("Pinned upstream and v783 inputs ready: " + str(target))


if __name__ == "__main__":
    main()
