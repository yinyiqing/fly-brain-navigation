#!/usr/bin/env python3
"""Compare the predeclared 250 ms and 1000 ms experiments from saved results."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def read_pair(short_dir, long_dir):
    short_config = json.loads((short_dir / "config.json").read_text())
    long_config = json.loads((long_dir / "config.json").read_text())
    assert short_config["neural"].pop("window_ms") == 250
    assert long_config["neural"].pop("window_ms") == 1000
    assert short_config == long_config, "Other experimental settings changed"
    pd.testing.assert_frame_equal(pd.read_csv(short_dir / "observations.csv"),
                                  pd.read_csv(long_dir / "observations.csv"), check_exact=True)
    short = pd.read_csv(short_dir / "metrics.csv")
    long = pd.read_csv(long_dir / "metrics.csv")
    pd.testing.assert_frame_equal(short[short.method == "geometric"].reset_index(drop=True),
                                  long[long.method == "geometric"].reset_index(drop=True), check_exact=True)
    for frame in [short, long]:
        neural = frame[frame.method == "cx_readout"]
        assert len(neural) == len(short_config["turn_noise_std_deg"]) * len(short_config["trial_seeds"])
        assert not neural.duplicated(["noise_deg", "seed"]).any()
    return short_config, short, long


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "examples/coursework-20261103")
    parser.add_argument("--candidate", type=Path, default=ROOT / "examples/window1000-20261104")
    parser.add_argument("--confirm-baseline", type=Path, default=ROOT / "examples/confirm250-20261104")
    parser.add_argument("--confirm-candidate", type=Path, default=ROOT / "examples/confirm1000-20261104")
    parser.add_argument("--output", type=Path, default=ROOT / "examples/window-comparison-20261104")
    args = parser.parse_args()
    pairs = [("original_seeds", args.baseline, args.candidate),
             ("new_seeds", args.confirm_baseline, args.confirm_candidate)]
    rows, evidence, seeds_seen = [], {}, set()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 180})
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.7), sharey=True)
    for ax, (group, short_dir, long_dir) in zip(axes, pairs):
        config, short, long = read_pair(short_dir, long_dir)
        seeds = set(config["trial_seeds"])
        assert not seeds & seeds_seen, "Confirmation seeds must be new"
        seeds_seen |= seeds
        short_summary = pd.read_csv(short_dir / "summary.csv").set_index(["method", "noise_deg"])
        long_summary = pd.read_csv(long_dir / "summary.csv").set_index(["method", "noise_deg"])
        for noise in config["turn_noise_std_deg"]:
            before = short_summary.loc[("cx_readout", noise)]
            after = long_summary.loc[("cx_readout", noise)]
            geometry = short_summary.loc[("geometric", noise)]
            paired = short[short.method == "cx_readout"].merge(
                long[long.method == "cx_readout"], on=["noise_deg", "seed"], suffixes=("_short", "_long"))
            paired = paired[paired.noise_deg == noise]
            rows.append({"group": group, "noise_deg": noise, "trials": int(before.trials),
                         "geometric_mean_error": float(geometry.mean_error),
                         "geometric_successes": int(geometry.successes),
                         "short_mean_error": float(before.mean_error),
                         "short_std_error": float(before.std_error), "short_successes": int(before.successes),
                         "long_mean_error": float(after.mean_error),
                         "long_std_error": float(after.std_error), "long_successes": int(after.successes),
                         "paired_error_reductions": int((paired.endpoint_error_long < paired.endpoint_error_short).sum())})
        for frame, method, label, shift, color in [
                (short, "geometric", "Geometric integration", -.45, "#526977"),
                (short, "cx_readout", "CX window 250 ms", 0, "#cc803a"),
                (long, "cx_readout", "CX window 1000 ms", .45, "#297da3")]:
            grouped = frame[frame.method == method].groupby("noise_deg").endpoint_error
            mean, sd = grouped.mean(), grouped.std()
            ax.errorbar(mean.index + shift, mean.values, yerr=sd.values,
                        marker="o", capsize=3, linewidth=1.6, color=color, label=label)
            for noise, values in grouped:
                ax.scatter(noise + shift + np.linspace(-.1, .1, len(values)), values,
                           color=color, alpha=.45, s=18)
        ax.axhline(config["success_radius"], color="#718a6c", linestyle=":", label="Success radius = 1")
        label = "Original seeds" if group == "original_seeds" else "New seeds for confirmation"
        ax.set_title(f"{label}: {', '.join(map(str, config['trial_seeds']))}")
        ax.set_xlabel("Incremental turn noise SD (degrees)")
        ax.set_xticks(config["turn_noise_std_deg"])
        ax.set_ylim(bottom=-.5)
        ax.grid(alpha=.15)
        evidence[group] = {"seeds": config["trial_seeds"], "observations_identical": True,
                           "geometric_results_identical": True, "only_window_differs": True}
        for name, directory in [("short", short_dir), ("long", long_dir)]:
            manifest = json.loads((directory / "manifest.json").read_text())
            evidence[group][name] = {
                "results_directory": directory.name,
                "heldout_mae_deg": manifest["calibration"]["heldout_mae_deg"],
                "wall_seconds": manifest["wall_seconds"], "max_rss_kib": manifest["max_rss_kib"],
                "sha256": {file: hashlib.sha256((directory / file).read_bytes()).hexdigest()
                           for file in ["config.json", "metrics.csv", "observations.csv", "calibration.npz"]}}
    axes[0].set_ylabel("Final distance to home (arbitrary units)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle("Longer neural observation window | mean ± sample SD, n = 3 per panel", y=.99)
    fig.tight_layout(rect=(0, .075, 1, .96))
    args.output.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(rows)
    comparison.to_csv(args.output / "window_comparison.csv", index=False)
    evidence["limitations"] = [
        "One fixed route; descriptive comparisons only.",
        "Primary seeds were inspected before this change; confirmation uses separate navigation seeds.",
        "Calibration and held-out direction seeds are shared across the two seed groups, not new tests.",
        "Longer simulated observations cost more time; external integration and ideal actuation remain."]
    (args.output / "comparison.json").write_text(json.dumps(evidence, indent=2) + "\n")
    for suffix in ["png", "pdf"]:
        fig.savefig(args.output / f"window_comparison.{suffix}", bbox_inches="tight")
    plt.close(fig)
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
