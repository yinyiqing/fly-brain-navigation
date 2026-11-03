#!/usr/bin/env python3
"""Download the pinned public FlyWire files and verify their source checksums."""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path, entry):
    """Hash one file in bounded memory, including its original Git blob ID."""
    hashes = {name: hashlib.new(name) for name in ("sha256", "md5")}
    git_hash = hashlib.sha1()
    git_hash.update(("blob %d\0" % path.stat().st_size).encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            for digest in hashes.values():
                digest.update(chunk)
            git_hash.update(chunk)
    result = {name: digest.hexdigest() for name, digest in hashes.items()}
    result["git_blob_sha1"] = git_hash.hexdigest()
    if path.stat().st_size != entry["bytes"]:
        raise ValueError("Unexpected file size: %s" % path)
    for name in ("md5", "git_blob_sha1"):
        if name in entry and result[name] != entry[name]:
            raise ValueError("%s mismatch: %s" % (name, path))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    sources = json.loads((ROOT / "data/sources.json").read_text())
    pending_bytes = sum(e["bytes"] for e in sources["files"] if not (ROOT / e["path"]).exists())
    if not args.verify_only and shutil.disk_usage(ROOT).free < pending_bytes + 1024**3:
        raise RuntimeError("Insufficient disk space for the selected data files")
    results = []
    for entry in sources["files"]:
        target = ROOT / entry["path"]
        if not target.exists():
            if args.verify_only:
                raise FileNotFoundError(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".part")
            print("Downloading %s (%.1f MB)" % (target.name, entry["bytes"] / 1e6), flush=True)
            command = ["curl", "--fail", "--location", "--silent", "--show-error",
                       "--retry", "3", "--connect-timeout", "20", "--max-time", "1800",
                       "--continue-at", "-", "--output", str(partial)]
            for name, value in entry.get("headers", {}).items():
                command.extend(["--header", "%s: %s" % (name, value)])
            command.append(entry["url"])
            subprocess.run(command, check=True)
            digests = fingerprint(partial, entry)
            partial.replace(target)
        else:
            digests = fingerprint(target, entry)
        results.append(dict(entry, **digests))
        print("Verified %s" % target.name, flush=True)
    report = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "dataset": sources["dataset"], "files": results}
    output = ROOT / "data/metadata/download_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("All %d files verified" % len(results), flush=True)


if __name__ == "__main__":
    main()
