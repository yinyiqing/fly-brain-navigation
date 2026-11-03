#!/usr/bin/env python3
"""Make the two coursework figures from saved results; never rerun a simulation."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np
import pandas as pd

COLORS = {"geometric": "#2878a0", "cx_readout": "#d87828", "readout_off": "#b64c68"}
LABELS = {"geometric": "Geometric integration", "cx_readout": "CX readout + integration", "readout_off": "Readout disabled"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    p = args.results
    config = json.loads((p / "config.json").read_text())
    metrics = pd.read_csv(p / "metrics.csv")
    traces = pd.read_csv(p / "trajectories.csv")
    calibration = json.loads((p / "calibration_summary.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "savefig.dpi": 180})
    seed = config["trial_seeds"][0]
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.3), sharex=True, sharey=True)
    for ax, sigma in zip(axes, config["turn_noise_std_deg"]):
        sub = traces[(traces.seed == seed) & (traces.noise_deg == sigma)]
        out = sub[(sub.method == "geometric") & (sub.phase == "outbound_true")]
        ax.plot(out.x, out.y, "--", color="#7b858c", lw=1.8, label="Outbound route")
        ax.scatter([0], [0], marker="*", s=100, color="#34464d", zorder=5, label="Home")
        ax.scatter([out.x.iloc[-1]], [out.y.iloc[-1]], marker="s", s=32, color="#687b61", zorder=5)
        ax.add_patch(Circle((0, 0), config["success_radius"], fill=False, color="#8b9a90", ls=":"))
        for method in ["geometric", "cx_readout", "readout_off"]:
            back = sub[(sub.method == method) & (sub.phase == "return_true")]
            if back.empty:
                continue
            ax.plot(back.x, back.y, color=COLORS[method], lw=2, alpha=.9, label=LABELS[method])
            ax.scatter([back.x.iloc[-1]], [back.y.iloc[-1]], color=COLORS[method], s=38, zorder=6)
        ax.set_title(f"Turn noise: {sigma}\N{DEGREE SIGN}")
        ax.set_xlabel("x (arbitrary distance units)")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.16)
    axes[0].set_ylabel("y (arbitrary distance units)")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(.5, -.015))
    fig.suptitle(f"One outbound route, one straight return  |  representative seed {seed}", y=.98)
    fig.tight_layout(rect=(0, .16, 1, .95))
    for suffix in ["png", "pdf"]:
        fig.savefig(p / f"figure1_trajectories.{suffix}", bbox_inches="tight")
    plt.close(fig)

    fig, (ax, decoder_ax) = plt.subplots(1, 2, figsize=(11.8, 4.2), gridspec_kw={"width_ratios": [1.25, 1]})
    for method, shift in [("geometric", -.28), ("cx_readout", .28)]:
        sub = metrics[metrics.method == method]
        if sub.empty:
            continue
        grouped = sub.groupby("noise_deg").endpoint_error
        means, stds = grouped.mean(), grouped.std()
        ax.errorbar(means.index + shift, means.values, yerr=stds.values, color=COLORS[method],
                    marker="o", capsize=4, lw=1.7, label=LABELS[method])
        for sigma, group in sub.groupby("noise_deg"):
            jitter = np.linspace(-.13, .13, len(group))
            ax.scatter(sigma + shift + jitter, group.endpoint_error, s=20, color=COLORS[method], alpha=.5)
    off = metrics[metrics.method == "readout_off"]
    if len(off):
        ax.scatter(off.noise_deg.iloc[0], off.endpoint_error.mean(), marker="X", color=COLORS["readout_off"],
                   s=75, label=LABELS["readout_off"], zorder=5)
    ax.axhline(config["success_radius"], color="#8b9a90", ls=":", lw=1.3, label="Success radius")
    ax.set_xticks(config["turn_noise_std_deg"])
    ax.set_xlabel("Std. dev. of incremental turn noise (degrees)")
    ax.set_ylabel("Final distance to home (arbitrary units)")
    ax.set_ylim(bottom=-.4)
    ax.set_title("Homing error: mean ± sample SD, n = 3")
    ax.legend(fontsize=8.2, frameon=False, loc="upper left")
    ax.grid(alpha=.16)
    data = np.load(p / "calibration.npz")
    true = data["test_angles"]
    difference = (data["test_predictions"] - true + np.pi) % (2 * np.pi) - np.pi
    decoder_ax.plot([0, 360], [0, 360], "--", color="#a0a8ad", lw=1.2)
    decoder_ax.scatter(np.rad2deg(true), np.rad2deg(true + difference), color=COLORS["cx_readout"], s=32)
    decoder_ax.set(xlabel="Held-out artificial input direction (degrees)", ylabel="Decoded direction (degrees)",
                   xlim=(-5, 365), ylim=(-5, 365), xticks=[0, 90, 180, 270, 360], yticks=[0, 90, 180, 270, 360])
    decoder_ax.set_aspect("equal", adjustable="box")
    decoder_ax.set_title(f"Neural readout: MAE {calibration['heldout_mae_deg']:.2f}° (n = 16)")
    decoder_ax.grid(alpha=.16)
    fig.tight_layout()
    for suffix in ["png", "pdf"]:
        fig.savefig(p / f"figure2_errors.{suffix}", bbox_inches="tight")
    plt.close(fig)
    print(f"Saved two figures as PNG and PDF to {p}")


if __name__ == "__main__":
    main()
