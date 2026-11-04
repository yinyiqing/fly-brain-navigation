#!/usr/bin/env python3
"""Draw phase-labelled paper trajectories from the prespecified seed 701.

The CSV phase describes the segment ending at each row. Each new phase must
therefore include the preceding point to preserve its boundary and distance.
This script changes only visualization; it does not run or modify experiments.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PHASES = [
    ("outbound", "#2878ad", "--", "出发 A → B"),
    ("direct", "#d57722", "-", "返程 B → C"),
    ("search", "#8760a7", "-.", "搜索 C → 终点"),
]


def phase_points(trial, phase):
    indices = np.flatnonzero(trial.phase.to_numpy() == phase)
    if not len(indices) or not np.all(np.diff(indices) == 1):
        raise ValueError(f"Expected one continuous {phase} phase")
    return trial.iloc[max(0, indices[0] - 1):indices[-1] + 1][["x", "y"]].to_numpy()


def length(points):
    return np.linalg.norm(np.diff(points, axis=0), axis=1).sum()


def add_arrows(ax, points, color, fractions):
    cumulative = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    # Interpolate on the saved polyline. Arrow heads follow actual travel order.
    def location(distance):
        return np.array([np.interp(distance, cumulative, points[:, axis]) for axis in [0, 1]])
    for fraction in fractions:
        distance = cumulative[-1] * fraction
        tail, head = location(max(0, distance - .5)), location(min(cumulative[-1], distance + .5))
        ax.annotate("", xy=head, xytext=tail,
                    arrowprops={"arrowstyle": "-|>", "color": color,
                                "lw": 1.1, "mutation_scale": 10}, zorder=4)


def label(ax, text, point, position, ha="left"):
    ax.annotate(text, xy=point, xytext=position, fontsize=8, ha=ha,
                va="center", color="#26323b",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": .94, "pad": 1.4},
                arrowprops={"arrowstyle": "-", "lw": .6, "color": "#68737b"}, zorder=8)


def main():
    source = ROOT / "examples/validation-20261104"
    config = json.loads((source / "config.json").read_text())
    data = pd.read_csv(source / "demo_trajectories.csv")
    metrics = pd.read_csv(source / "robustness_metrics.csv")
    available = {font.name for font in font_manager.fontManager.ttflist}
    # Prefer TrueType CJK outlines for portable PDF font embedding.
    candidates = ["Droid Sans Fallback", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans CJK JP", "PingFang SC"]
    font = next((name for name in candidates if name in available), None)
    if font is None:
        raise RuntimeError("Install a CJK font such as Noto Sans CJK before drawing Chinese paper figures")
    plt.rcParams.update({"font.family": ["DejaVu Sans", font], "font.size": 8.5,
                         "pdf.fonttype": 42, "ps.fonttype": 42,
                         "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(5.8, 3.6))
    fig.subplots_adjust(left=.085, right=.98, bottom=.29, top=.90, wspace=.27)
    for panel, ax, noise in zip(["a", "b"], axes, [5, 15]):
        trial = data[data.noise_deg == noise].sort_values("step").reset_index(drop=True)
        for column, expected in [("route", config["demo_route"]), ("seed", config["demo_seed"]),
                                 ("method", "cx"), ("execution_noise_deg", config["demo_execution_noise_deg"]),
                                 ("budget", max(config["search_budgets"]))]:
            if trial.empty or not (trial[column] == expected).all():
                raise ValueError(f"Unexpected demo {column}")
        selected = metrics[(metrics.noise_deg == noise) & (metrics.route == config["demo_route"])
                           & (metrics.seed == config["demo_seed"]) & (metrics.method == "cx")
                           & (metrics.execution_noise_deg == config["demo_execution_noise_deg"])
                           & (metrics.budget == max(config["search_budgets"]))]
        if len(selected) != 1:
            raise ValueError("Expected one saved outcome per panel")
        outcome = selected.iloc[0]
        paths = {phase: phase_points(trial, phase) for phase, *_ in PHASES}
        assert np.allclose(paths["outbound"][-1], paths["direct"][0])
        assert np.allclose(paths["direct"][-1], paths["search"][0])
        assert np.isclose(length(paths["outbound"]), 18.)
        assert np.isclose(length(paths["search"]), outcome.search_distance)
        assert np.isclose(length(paths["direct"]) + length(paths["search"]), outcome.return_distance)
        endpoint = paths["search"][-1]
        assert np.allclose(endpoint, [outcome.endpoint_x, outcome.endpoint_y])
        assert bool(np.linalg.norm(endpoint) <= 1 + 1e-9) == bool(outcome.success)
        ax.add_patch(Circle((0, 0), 1, facecolor="#e3eee6", edgecolor="#91a99a", lw=.6, zorder=1))
        for phase, color, style, _ in PHASES:
            points = paths[phase]
            ax.plot(points[:, 0], points[:, 1], linestyle=style, color=color,
                    lw=1.35 if phase != "outbound" else 1.15, zorder=2)
            add_arrows(ax, points, color, [.18, .63] if phase != "direct" else [.5])
        start_return = paths["direct"][0]
        start_search = paths["search"][0]
        ax.scatter([0], [0], marker="*", s=75, color="#243b36", zorder=6)
        ax.scatter(*start_return, marker="D", s=27, facecolor="white", edgecolor="#26323b", zorder=6)
        ax.scatter(*start_search, marker="s", s=27, facecolor="white", edgecolor="#26323b", zorder=6)
        ax.scatter(*endpoint, marker="o" if bool(outcome.success) else "X", s=32,
                   color="#24704a" if bool(outcome.success) else "#bd4848", zorder=7)
        label(ax, "A 家 / 出发点", (0, 0), (1.0, -1.35))
        label(ax, "B 开始返程", start_return, (9.3, 10.6), ha="right")
        if noise == 5:
            label(ax, "C 开始搜索", start_search, (-5.9, 5.5))
            label(ax, "到达", endpoint, (-5.9, -.9))
        else:
            label(ax, "C 开始搜索", start_search, (-5.9, 14.0))
            label(ax, "未到达", endpoint, (-5.9, -.9))
        ax.set(xlim=(-6.5, 10), ylim=(-2.3, 15), xlabel="x（距离单位）", ylabel="y（距离单位）",
               xticks=[-5, 0, 5, 10], yticks=[0, 5, 10, 15],
               title=f"({panel}) {noise}° 观测噪声：" + ("成功" if outcome.success else "失败"))
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.14, lw=.5)
    handles = [Line2D([0], [0], color=color, linestyle=style, lw=1.5, label=text)
               for _, color, style, text in PHASES]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .065),
               ncol=3, frameon=False, handlelength=2.2, columnspacing=1.3, fontsize=8)
    fig.text(.5, .025, "无障碍物；浅色圆为到达范围（半径 1）；箭头表示行进方向", ha="center", fontsize=8)
    destination = ROOT / "reports/assets/paper_trajectory"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination.with_suffix(".png"), dpi=400)
    fig.savefig(destination.with_suffix(".pdf"))
    plt.close(fig)
    print(f"Saved PNG/PDF: {destination}; phase boundaries and travel distances match saved metrics")


if __name__ == "__main__":
    main()
