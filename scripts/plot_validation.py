#!/usr/bin/env python3
"""Render validation figures and a fixed-seed animation from saved results."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Circle
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"cx": "#33866b", "geometric": "#367fa0", "shuffle": "#8a69aa", "off": "#969da4"}


def save_figure(fig, output, name):
    for suffix in ["png", "pdf"]:
        fig.savefig(output / f"{name}.{suffix}", dpi=170, bbox_inches="tight")
    plt.close(fig)


def neural_figure(output, config):
    source = ROOT / config["source_results"]
    controls = pd.read_csv(output / "decoder_controls.csv")
    ablations = pd.read_csv(output / "ablation_by_variant.csv")
    with np.load(source / "raw/original/calibration.npz") as data:
        counts = data["test_counts"].astype(float)
    normalized = counts / np.maximum(counts.max(axis=0), 1)
    fig, axes = plt.subplots(1, 3, figsize=(14.7, 4.4), gridspec_kw={"width_ratios": [1.1, 1, 1.15]})
    im = axes[0].imshow(normalized.T, aspect="auto", origin="lower", cmap="viridis",
                        extent=[0, 360, 0, counts.shape[1]], vmin=0, vmax=1)
    axes[0].set(xlabel="Artificial input direction (degrees)", ylabel="Readout neuron index",
                title="Held-out neural responses", xticks=[0, 90, 180, 270, 360])
    fig.colorbar(im, ax=axes[0], label="Counts / per-neuron maximum", fraction=.05, pad=.03)
    methods = ["cx_normal", "cx_shuffled_labels", "readout_off"]
    colors = [COLORS["cx"], COLORS["shuffle"], COLORS["off"]]
    for index, (method, color) in enumerate(zip(methods, colors)):
        values = controls[controls.method == method].heldout_mae_deg.to_numpy()
        axes[1].bar(index, values.mean(), width=.62, color=color, alpha=.75)
        axes[1].scatter(index + np.linspace(-.15, .15, len(values)), values, s=24, color="#333d46", zorder=3)
        axes[1].text(index, values.max() + 4, f"{values.mean():.1f}°", ha="center", fontsize=10)
    axes[1].set(xticks=range(3), xticklabels=["Normal", "Shuffled\nlabels", "Readout\noff"],
                ylabel="Mean absolute direction error (degrees)", ylim=(0, 135),
                title="16 held-out directions")
    for index, (method, color) in enumerate(zip(["geometric"] + methods, [COLORS["geometric"]] + colors)):
        group = ablations[(ablations.method == method) & (ablations.noise_deg == 5) & (ablations.budget == 72)]
        values = group.success_rate.to_numpy()
        axes[2].bar(index, values.mean(), width=.62, color=color, alpha=.75)
        axes[2].scatter(index + np.linspace(-.15, .15, len(values)), values, s=24, color="#333d46", zorder=3)
        label = f"{group.successes.mean():g}/15" if len(group) == 1 else f"mean\n{group.successes.mean():.1f}/15"
        axes[2].text(index, values.max() + .035, label, ha="center", fontsize=9)
    axes[2].set(xticks=range(4), xticklabels=["Geometry", "Normal", "Shuffled\nlabels", "Readout\noff"],
                ylabel="Fraction reaching home", ylim=(0, 1.2), title="5° observation noise, search budget 72")
    for ax in axes[1:]:
        ax.grid(axis="y", alpha=.16)
    fig.suptitle("Correct direction labels matter in this pipeline; this does not test connectome-specific superiority", fontsize=12)
    fig.text(.5, .015, "Shuffled-label dots: five fixed permutations, not extra independent navigation trials.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .93))
    save_figure(fig, output, "figure1_neural_controls")


def robustness_figure(output):
    data = pd.read_csv(output / "robustness_summary.csv")
    data = data[(data.method == "cx") & (data.budget == 72)]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7))
    x = np.arange(3)
    for sigma, shift, color in [(0, -.17, "#8bc1ae"), (2, .17, COLORS["cx"])]:
        group = data[data.execution_noise_deg == sigma].set_index("noise_deg").loc[[0, 5, 15]]
        label = f"Return turn error: {sigma}° SD"
        axes[0].bar(x + shift, group.success_rate, width=.3, color=color, label=label)
        axes[1].bar(x + shift, group.mean_return_distance, width=.3, color=color, label=label)
        for xpos, row in zip(x + shift, group.itertuples()):
            axes[0].text(xpos, row.success_rate + .025, f"{row.successes}/{row.trials}", ha="center", fontsize=9)
            axes[1].text(xpos, row.mean_return_distance + .8, f"{row.mean_return_distance:.1f}", ha="center", fontsize=9)
    axes[0].set(ylabel="Fraction reaching home", ylim=(0, 1.15), title="Success with the same search budget")
    axes[1].set(ylabel="Mean actual return distance", title="Cost includes failed trials")
    axes[1].set_ylim(0, data.mean_return_distance.max() * 1.2)
    for ax in axes:
        ax.set_xticks(x, ["0°", "5°", "15°"])
        ax.set_xlabel("Outbound incremental turn observation noise")
        ax.grid(axis="y", alpha=.16)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.suptitle("New validation: three routes × ten seeds | CX + search, budget 72", fontsize=12)
    fig.tight_layout(rect=(0, .11, 1, .94))
    save_figure(fig, output, "figure2_return_robustness")


def budget_figure(output):
    data = pd.read_csv(output / "robustness_summary.csv")
    data = data[data.method == "cx"]
    fig, axes = plt.subplots(1, 2, figsize=(11.7, 4.8))
    for noise, color in [(5, "#c47b2e"), (15, "#8167a4")]:
        for execution, style in [(0, "-"), (2, "--")]:
            group = data[(data.noise_deg == noise) & (data.execution_noise_deg == execution)].sort_values("budget")
            label = f"Observation {noise}°, return {execution}°"
            axes[0].plot(group.budget, group.success_rate, style, marker="o", color=color, lw=1.7, label=label)
            axes[1].plot(group.budget, group.mean_return_distance, style, marker="o", color=color, lw=1.7, label=label)
    axes[0].set(ylabel="Fraction reaching home", ylim=(0, 1.08), title="More search can recover missed homes")
    axes[1].set(ylabel="Mean actual return distance", title="Recovery costs extra movement")
    for ax in axes:
        ax.set_xlabel("Additional search distance budget")
        ax.set_xticks([0, 18, 36, 72])
        ax.grid(alpha=.16)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=9)
    fig.suptitle("Prospective budget check: 30 route-seed combinations per point", fontsize=12)
    fig.tight_layout(rect=(0, .16, 1, .94))
    save_figure(fig, output, "figure3_budget_tradeoff")


def demo_animation(output, config):
    data = pd.read_csv(output / "demo_trajectories.csv")
    metrics = pd.read_csv(output / "robustness_metrics.csv")
    metrics = metrics[(metrics.route == config["demo_route"]) & (metrics.seed == config["demo_seed"])
                      & (metrics.method == "cx") & (metrics.budget == max(config["search_budgets"]))
                      & (metrics.execution_noise_deg == config["demo_execution_noise_deg"])]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.8))
    states = []
    phase_names = {"outbound": "Outbound", "direct": "Direct return", "search": "Local search"}
    for ax, noise in zip(axes, [0, 5, 15]):
        trial = data[data.noise_deg == noise].sort_values("step")
        points = trial[["x", "y"]].to_numpy()
        cumulative = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        row = metrics[metrics.noise_deg == noise].iloc[0]
        outbound = trial[trial.phase == "outbound"]
        ax.plot(outbound.x, outbound.y, "--", color="#bac1c5", lw=1)
        ax.add_patch(Circle((0, 0), 1, color=COLORS["cx"], alpha=.13))
        ax.scatter([0], [0], marker="*", s=90, color="#34464d", zorder=4)
        low, high = points.min(axis=0), points.max(axis=0)
        center = (low + high) / 2
        span = max(high - low) + 3
        ax.set(xlim=(center[0] - span / 2, center[0] + span / 2),
               ylim=(center[1] - span / 2, center[1] + span / 2),
               xlabel="x (distance units)", ylabel="y (distance units)", title=f"Observation noise: {noise}°")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.13)
        line, = ax.plot([], [], color=COLORS["cx"], lw=1.8)
        marker, = ax.plot([], [], "o", color=COLORS["cx"], ms=5)
        status = ax.text(.03, .97, "", transform=ax.transAxes, va="top", fontsize=9,
                         bbox={"facecolor": "white", "alpha": .8, "edgecolor": "none", "pad": 2})
        states.append((points, cumulative, trial.phase.to_numpy(), bool(row.success), line, marker, status))
    fig.suptitle(f"CX homing + finite search | fixed seed {config['demo_seed']} | return turn error {config['demo_execution_noise_deg']}° SD", fontsize=12)
    fig.text(.5, .025, "Same travel distance per frame in all panels. Home radius = 1. No target coordinates enter the controller.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .16, 1, .93))

    def update(travelled):
        for points, cumulative, phases, success, line, marker, status in states:
            travelled_here = min(travelled, cumulative[-1])
            index = min(int(np.searchsorted(cumulative, travelled_here, side="right")), len(points) - 1)
            if index == 0:
                current = points[0]
            else:
                length = cumulative[index] - cumulative[index - 1]
                fraction = (travelled_here - cumulative[index - 1]) / max(length, 1e-12)
                current = points[index - 1] + fraction * (points[index] - points[index - 1])
            trail = np.vstack([points[:index], current])
            line.set_data(trail[:, 0], trail[:, 1])
            marker.set_data([current[0]], [current[1]])
            finished = travelled >= cumulative[-1] - 1e-9
            phase = ("Home reached" if success else "Budget exhausted") if finished else phase_names[phases[index]]
            marker.set_color("#b65151" if finished and not success else COLORS["cx"])
            status.set_text(f"{phase}\nTotal travel: {travelled_here:.1f}")
        return []

    maximum = max(state[1][-1] for state in states)
    frames = np.r_[np.linspace(0, maximum, 135), np.repeat(maximum, 15)]
    animation = FuncAnimation(fig, update, frames=frames, interval=80, blit=False)
    animation.save(output / "homing_demo.gif", writer=PillowWriter(fps=12), dpi=90)
    update(maximum)
    fig.savefig(output / "demo_final_frame.png", dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--animation", action="store_true")
    args = parser.parse_args()
    output = args.results.resolve()
    config = json.loads((output / "config.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    neural_figure(output, config)
    robustness_figure(output)
    budget_figure(output)
    if args.animation:
        demo_animation(output, config)
    print(f"Saved validation figures to {output}")


if __name__ == "__main__":
    main()
