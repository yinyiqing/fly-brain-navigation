#!/usr/bin/env python3
"""Plot saved held-out spike counts and direction predictions for the paper.

The heatmap keeps all 128 neurons in their saved structural-selection order.
Each column is one 250 ms held-out response; no smoothing or neuron selection
is applied. This script reads existing results and does not run Brian2.
"""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "examples/search-20261104/raw/original"
    with np.load(source / "calibration.npz") as saved:
        counts = saved["test_counts"].copy()
        angles = saved["test_angles"].copy()
        predictions = saved["test_predictions"].copy()
    with np.load(source / "readout.npz") as model:
        components = ((counts - model["mean"]) / model["scale"]) @ model["weights"] + model["offset"]
    np.testing.assert_allclose(np.arctan2(components[:, 1], components[:, 0]), predictions,
                               rtol=1e-12, atol=1e-12)
    assert counts.shape == (16, 128) and np.isfinite(counts).all()
    input_deg = np.rad2deg(angles) % 360
    predicted_deg = np.rad2deg(predictions) % 360
    errors = np.rad2deg(np.abs((predictions - angles + np.pi) % (2 * np.pi) - np.pi))
    summary = json.loads((source / "calibration_summary.json").read_text())
    np.testing.assert_allclose(errors.mean(), summary["heldout_mae_deg"], rtol=1e-12)
    np.testing.assert_allclose(input_deg, np.arange(16) * 22.5 + 11.25)

    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = ["Droid Sans Fallback", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                  "Noto Sans CJK JP", "Songti SC", "PingFang SC"]
    cjk = next((font for font in candidates if font in available), None)
    if cjk is None:
        raise RuntimeError("A CJK font such as Noto Sans CJK is required for the Chinese figure")
    plt.rcParams.update({"font.family": ["DejaVu Sans", cjk], "font.size": 9,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig = plt.figure(figsize=(6.4, 2.65))
    grid = fig.add_gridspec(1, 4, width_ratios=[1, .045, .22, 1],
                           left=.085, right=.975, bottom=.20, top=.87, wspace=.13)
    heat = fig.add_subplot(grid[0, 0])
    color_axis = fig.add_subplot(grid[0, 1])
    scatter = fig.add_subplot(grid[0, 3])
    # The 22.5-degree bins are centred on the actual test angles.
    cells = heat.pcolormesh(np.linspace(0, 360, 17), np.arange(129) + .5,
                           counts.T, shading="flat", cmap="viridis", vmin=0,
                           vmax=10 * np.ceil(counts.max() / 10), rasterized=False)
    heat.set(xlim=(0, 360), ylim=(128.5, .5), xticks=[0, 90, 180, 270, 360],
             yticks=[1, 32, 64, 96, 128], xlabel="输入方向（°）", ylabel="读出神经元序号",
             title="(a) 下游放电响应")
    colorbar = fig.colorbar(cells, cax=color_axis)
    colorbar.solids.set_rasterized(False)
    colorbar.ax.set_title("次数", pad=6, fontsize=8)
    colorbar.ax.tick_params(labelsize=8)
    scatter.plot([0, 360], [0, 360], linestyle="--", lw=1, color="#8c949a", label="输入与读出一致")
    scatter.scatter(input_deg, predicted_deg, s=18, facecolor="#246a9a",
                    edgecolor="white", linewidth=.35, zorder=3, label="未见方向")
    scatter.set(xlim=(0, 360), ylim=(0, 360), xticks=[0, 90, 180, 270, 360],
                yticks=[0, 90, 180, 270, 360], xlabel="输入方向（°）", ylabel="读出方向（°）",
                title="(b) 方向读出结果")
    scatter.text(.04, .95, f"平均误差 {errors.mean():.2f}°", transform=scatter.transAxes,
                 va="top", fontsize=9)
    scatter.legend(loc="lower right", fontsize=7.8, frameon=False, handlelength=1.6)
    scatter.grid(alpha=.15, lw=.5)
    output = ROOT / "reports/assets/paper_direction_readout"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix(".png"), dpi=400)
    # Tiny same-colour overlaps prevent PDF viewers from drawing white seams
    # between adjacent vector cells. The saved counts and PNG are unchanged.
    cells.set_edgecolor("face")
    cells.set_linewidth(.15)
    colorbar.solids.set_edgecolor("face")
    colorbar.solids.set_linewidth(.1)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)
    record = {
        "source": str((source / "calibration.npz").relative_to(ROOT)),
        "source_sha256": hashlib.sha256((source / "calibration.npz").read_bytes()).hexdigest(),
        "test_directions": len(angles), "feature_neurons": counts.shape[1], "window_ms": 250,
        "heatmap": "All saved held-out spike counts in original feature order; linear scale; no smoothing",
        "input_degrees": input_deg.tolist(), "predicted_degrees": predicted_deg.tolist(),
        "absolute_circular_errors_degrees": errors.tolist(),
        "heldout_mae_deg": float(errors.mean()), "heldout_max_deg": float(errors.max()),
        "saved_readout_predictions_verified": True, "new_experiment_run": False,
        "png_dpi": 400, "figure_size_inches": [6.4, 2.65],
        "sha256": {suffix: hashlib.sha256(output.with_suffix('.' + suffix).read_bytes()).hexdigest()
                   for suffix in ["png", "pdf"]},
    }
    (ROOT / "data/metadata/paper_readout_figure.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {output.name}.png/.pdf; 16 held-out predictions verified; MAE={errors.mean():.2f} degrees")


if __name__ == "__main__":
    main()
