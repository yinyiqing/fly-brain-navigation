#!/usr/bin/env python3
"""Export a pinned Git snapshot, final paper and an offline results page.

Only the Python standard library and Git are needed. Existing output folders
are never overwritten. Raw downloaded datasets and environments are excluded
because they are not tracked by Git.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
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
    required = [f"reports/{PAPER}", "docs/delivery_preview.html",
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
    copy(f"{results}/homing_demo.gif", "02_演示/归巢演示.gif")
    copy(f"{results}/demo_final_frame.png", "02_演示/轨迹终帧.png")
    for name in ["figure1_neural_controls.png", "figure2_return_robustness.png",
                 "figure3_budget_tradeoff.png"]:
        copy(f"{results}/{name}", f"03_结果图表/{name}")
    for path in sorted((source / results).glob("*.csv")):
        copy(f"{results}/{path.name}", f"03_结果图表/数据表/{path.name}")
    copy("docs/validation_results.md", "03_结果图表/实验结果说明.md")
    copy("docs/final_delivery.md", "00_阅读说明.md")

    with (source / results / "robustness_summary.csv").open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    display = []
    for noise in [0, 5, 15]:
        conditions = []
        for execution in [0, 2]:
            match = [r for r in rows if r["method"] == "cx"
                     and float(r["noise_deg"]) == noise
                     and float(r["execution_noise_deg"]) == execution
                     and float(r["budget"]) == 72]
            if len(match) != 1:
                raise ValueError(f"Ambiguous summary for {noise}/{execution}")
            conditions.append(match[0])
        exact, noisy = conditions
        display.append(
            f'<tr><th scope="row">{noise}°</th>'
            f'<td>{int(exact["successes"])}/{int(exact["trials"])}</td>'
            f'<td>{int(noisy["successes"])}/{int(noisy["trials"])}</td>'
            f'<td>{float(noisy["mean_return_distance"]):.2f}</td></tr>')
    page = (source / "docs/delivery_preview.html").read_text(encoding="utf-8")
    page = page.replace("{{RESULT_ROWS}}", "\n".join(display))
    page = page.replace("{{REVISION}}", html.escape(object_id[:12]))
    page = page.replace("{{PAPER}}", html.escape(PAPER, quote=True))
    (output / "00_打开看效果.html").write_text(page, encoding="utf-8")
    files = sorted(p for p in output.rglob("*") if p.is_file())
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "https://github.com/yinyiqing/fly-brain-navigation",
        "source_revision": object_id,
        "source_object_type": kind,
        "source_tree": tree_id,
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
