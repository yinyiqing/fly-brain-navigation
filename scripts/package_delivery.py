#!/usr/bin/env python3
"""Export a pinned Git snapshot, final paper and static publication figures.

Only the Python standard library and Git are needed. Existing output folders
are never overwritten. Raw downloaded datasets and environments are excluded
because they are not tracked by Git.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PAPER = "数字果蝇归巢研究_24025110_尹一清.docx"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def export(output, revision):
    # Resolve first so a moving branch cannot change halfway through export.
    object_id = git("rev-parse", "--verify", revision).decode().strip()
    tree_id = git("rev-parse", f"{object_id}^{{tree}}").decode().strip()
    kind = git("cat-file", "-t", object_id).decode().strip()
    archive = zipfile.ZipFile(io.BytesIO(git("archive", "--format=zip", object_id)))
    required = [f"reports/{PAPER}", "reports/assets/paper_trajectory.pdf",
                "examples/validation-20261104/robustness_summary.csv"]
    for name in required:
        if name not in archive.namelist():
            raise ValueError(f"Not present in revision {revision}: {name}")
    output.mkdir(parents=True, exist_ok=False)
    source = output / "04_完整项目"
    source.mkdir()
    for entry in archive.infolist():
        path = Path(entry.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Invalid archive path: {entry.filename}")
        archive.extract(entry, source)

    def copy(relative, destination):
        target = output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)

    copy(f"reports/{PAPER}", f"01_论文/{PAPER}")
    results = "examples/validation-20261104"
    figures = [("reports/assets/paper_trajectory", "图1_出发返程与搜索"),
               (f"{results}/figure1_neural_controls", "图2_神经方向对照"),
               (f"{results}/figure2_return_robustness", "图3_返程执行误差"),
               (f"{results}/figure3_budget_tradeoff", "图4_搜索预算与代价")]
    for source_stem, destination_stem in figures:
        for suffix in ["png", "pdf"]:
            copy(f"{source_stem}.{suffix}", f"02_论文插图/{destination_stem}.{suffix}")
    copy("docs/paper_figures.md", "02_论文插图/图注与插图说明.md")
    copy(f"{results}/homing_demo.gif", "03_结果数据/补充演示/归巢演示_旧版.gif")
    copy(f"{results}/demo_final_frame.png", "03_结果数据/补充演示/轨迹终帧_旧版.png")
    for path in sorted((source / results).glob("*.csv")):
        copy(f"{results}/{path.name}", f"03_结果数据/数据表/{path.name}")
    copy("docs/validation_results.md", "03_结果数据/实验结果说明.md")
    copy("docs/final_delivery.md", "00_阅读说明.md")

    files = sorted(p for p in output.rglob("*") if p.is_file())
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "https://github.com/yinyiqing/fly-brain-navigation",
        "source_revision": object_id,
        "source_object_type": kind,
        "source_tree": tree_id,
        "presentation": "Static paper figures in PNG and PDF; no HTML entry point",
        "note": "Tracked source snapshot; no Git history, environments or downloaded raw datasets. Hashes exclude this manifest.",
        "files": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in files},
    }
    (output / "版本与文件校验.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "source_revision": object_id,
                      "files": len(files) + 1}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="A new directory, preferably outside the repository")
    parser.add_argument("--revision", default="HEAD", help="Git commit or tree to export")
    args = parser.parse_args()
    export(args.output.resolve(), args.revision)
