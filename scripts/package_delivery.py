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
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PAPER = "果蝇连接组方向读出与归巢验证_24025110_尹一清.docx"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def export(output, revision):
    # Resolve first so a moving branch cannot change halfway through export.
    object_id = git("rev-parse", "--verify", revision).decode().strip()
    tree_id = git("rev-parse", f"{object_id}^{{tree}}").decode().strip()
    kind = git("cat-file", "-t", object_id).decode().strip()
    archive = zipfile.ZipFile(io.BytesIO(git("archive", "--format=zip", object_id)))
    results = "examples/validation-20261104"
    figures = [("reports/assets/paper_direction_readout", "图1_方向放电与读出"),
               ("reports/assets/paper_trajectory", "补图S1_出发返程与搜索"),
               (f"{results}/figure1_neural_controls", "补图S2_神经方向对照"),
               (f"{results}/figure2_return_robustness", "补图S3_返程执行误差"),
               (f"{results}/figure3_budget_tradeoff", "补图S4_搜索预算与代价")]
    required = [f"reports/{PAPER}", "docs/paper_figures.md", "docs/paper_supplement.md",
                "docs/final_delivery.md", f"{results}/robustness_summary.csv"]
    required += [f"{stem}.{suffix}" for stem, _ in figures for suffix in ("png", "pdf")]
    for name in required:
        if name not in archive.namelist():
            raise ValueError(f"Not present in revision {revision}: {name}")
    for entry in archive.infolist():
        path = Path(entry.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Invalid archive path: {entry.filename}")
    output.mkdir(parents=True, exist_ok=False)

    # Keep one paper in the delivery; the reproducibility archive holds code
    # and data, without duplicate reports or obsolete demonstration media.
    excluded = []
    source_files = 0
    with zipfile.ZipFile(output / "04_代码与数据.zip", "w", zipfile.ZIP_DEFLATED) as source:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            path = Path(entry.filename)
            report_asset_needed = entry.filename == "reports/assets/paper_direction_readout.png"
            if ((path.parts[0] == "reports" and not report_asset_needed)
                    or path.suffix.lower() in {".docx", ".gif"}
                    or path.name == "demo_final_frame.png"):
                excluded.append(entry.filename)
                continue
            data = archive.read(entry)
            if entry.filename == "README.md":
                readme = data.decode("utf-8")
                readme = readme.replace(f"](reports/{PAPER})", f"](../01_论文/{PAPER})")
                readme = readme.replace(
                    "reports/assets/paper_direction_readout.png",
                    "../02_论文插图/图1_方向放电与读出.png")
                readme = readme.replace(
                    "reports/assets/paper_trajectory.png",
                    "../02_论文插图/补图S1_出发返程与搜索.png")
                data = readme.encode("utf-8")
            source.writestr(f"代码与数据/{entry.filename}", data)
            source_files += 1

    def copy(relative, destination):
        target = output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(relative))

    copy(f"reports/{PAPER}", f"01_论文/{PAPER}")
    for source_stem, destination_stem in figures:
        for suffix in ["png", "pdf"]:
            copy(f"{source_stem}.{suffix}", f"02_论文插图/{destination_stem}.{suffix}")
    copy("docs/paper_figures.md", "02_论文插图/图注与插图说明.md")
    copy("docs/paper_supplement.md", "03_补充材料/论文补充材料.md")
    copy("docs/final_delivery.md", "00_阅读说明.md")

    files = sorted(p for p in output.rglob("*") if p.is_file())
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "https://github.com/yinyiqing/fly-brain-navigation",
        "source_revision": object_id,
        "source_object_type": kind,
        "source_tree": tree_id,
        "presentation": "Static paper figures in PNG and PDF; no HTML entry point",
        "note": "Pinned code/data archive; the figure required to rebuild the paper is retained. Word reports, other report figures and old demonstration media are excluded. README links point to the separately delivered paper and figures. No Git history, environments or downloaded raw datasets. Hashes exclude this manifest.",
        "source_files_in_archive": source_files,
        "source_exclusions": excluded,
        "files": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in files},
    }
    (output / "03_补充材料/版本与文件校验.json").write_text(
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
