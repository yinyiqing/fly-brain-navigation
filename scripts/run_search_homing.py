#!/usr/bin/env python3
"""Test bounded external search after CX-guided homing, with goal-contact stopping."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_homing import ROOT, integrate, route_arrays, wrap
import numpy as np
import pandas as pd


def return_actions(turn, distance, spacing, search_budget):
    """Agent-side plan: estimated command and fixed parameters only, no true pose."""
    if not np.isfinite([turn, distance, spacing, search_budget]).all():
        raise ValueError("Return parameters must be finite")
    if distance < 0 or spacing <= 0 or search_budget < 0:
        raise ValueError("Invalid distance, spacing or search budget")
    yield float(turn), float(distance), "direct"
    remaining, leg = float(search_budget), 0
    while remaining > 1e-10:
        length = min(spacing * (leg // 2 + 1), remaining)
        yield np.pi / 2, length, "search"
        remaining -= length
        leg += 1


def contact_distance(position, heading, distance, radius):
    """Environment-side first intersection with the home disk along a segment."""
    position = np.asarray(position, dtype=float)
    c = float(position @ position - radius**2)
    if c <= 0:
        return 0.0
    direction = np.array([np.cos(heading), np.sin(heading)])
    projection = float(position @ direction)
    discriminant = projection**2 - c
    if discriminant < -1e-12:
        return None
    entry = -projection - np.sqrt(max(0.0, discriminant))
    if entry < -1e-12 or entry > distance + 1e-12:
        return None
    return float(np.clip(entry, 0.0, distance))


def execute_return(position, heading, actions, radius):
    """Environment executes the plan; contact terminates every method equally.

    No direction, distance or position observation is sent back to the plan.
    Return actuation is exact, as in the original coursework experiment.
    """
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError("Success radius must be positive and finite")
    position = np.asarray(position, dtype=float).copy()
    points = [("direct", *position)]
    travelled = search_distance = 0.0
    success = False
    stage = "budget_exhausted"
    for turn, requested, phase in actions:
        heading = float(wrap(heading + turn))
        contact = contact_distance(position, heading, requested, radius)
        actual = requested if contact is None else contact
        end = position + actual * np.array([np.cos(heading), np.sin(heading)])
        count = max(1, int(np.ceil(actual / 0.25)))
        points.extend((phase, *xy) for xy in np.linspace(position, end, count + 1)[1:])
        position = end
        travelled += actual
        if phase == "search":
            search_distance += actual
        if contact is not None:
            success, stage = True, phase
            break
    return {
        "success": success,
        "endpoint_error": float(np.linalg.norm(position)),
        "return_distance": travelled,
        "search_distance": search_distance,
        "termination_stage": stage,
        "endpoint_x": float(position[0]),
        "endpoint_y": float(position[1]),
    }, points


def evaluate_saved(output, config):
    records, traces = [], []
    names = {"geometric": "geometric", "cx_motion_average": "cx",
             "motion_average_off": "readout_off"}
    for route in config["routes"]:
        raw = output / "raw" / route["name"]
        source_config = json.loads((raw / "config.json").read_text())
        if source_config["success_radius"] != config["success_radius"]:
            raise ValueError("Success radius must match the source experiment")
        headings, distances = route_arrays(source_config)
        true_path = integrate(headings, distances)
        for trial in pd.read_csv(raw / "metrics.csv").itertuples(index=False):
            if trial.method not in names:
                continue
            for suffix, budget in [("direct", 0.0), ("search", config["search_distance_budget"])]:
                method = names[trial.method] + "_" + suffix
                actions = return_actions(np.deg2rad(trial.return_turn_deg), trial.return_distance,
                                         config["search_spacing"], budget)
                metrics, points = execute_return(true_path[-1], headings[-1], actions,
                                                config["success_radius"])
                keys = {"route": route["name"], "noise_deg": trial.noise_deg,
                        "seed": trial.seed, "method": method}
                records.append({**keys, **metrics, "initial_endpoint_error": trial.endpoint_error,
                                "initial_return_distance": trial.return_distance})
                for step, (phase, x, y) in enumerate(points):
                    traces.append({**keys, "phase": phase, "step": step, "x": x, "y": y})
    return pd.DataFrame(records), pd.DataFrame(traces)


def summarize(metrics, keys):
    return metrics.groupby(keys, sort=False).agg(
        successes=("success", "sum"), trials=("success", "size"),
        success_rate=("success", "mean"), mean_error=("endpoint_error", "mean"),
        mean_return_distance=("return_distance", "mean"),
        mean_search_distance=("search_distance", "mean"),
        max_search_distance=("search_distance", "max"),
    ).reset_index()


def plot_results(output, config, metrics, traces):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    colors = {"cx_direct": "#d87828", "cx_search": "#36865e", "geometric_search": "#2878a0"}
    labels = {"cx_direct": "CX: direct return", "cx_search": "CX: return + search",
              "geometric_search": "Geometry: return + search"}
    route = config["routes"][0]
    seed = config["trial_seeds"][0]
    headings, distances = route_arrays({"route": route["route"]})
    outbound = integrate(headings, distances)
    fig, axes = plt.subplots(1, len(config["turn_noise_std_deg"]), figsize=(13, 4.5))
    for ax, sigma in zip(np.atleast_1d(axes), config["turn_noise_std_deg"]):
        ax.plot(*outbound.T, "--", color="#9099a0", lw=1.4, label="Outbound route")
        ax.add_patch(Circle((0, 0), config["success_radius"], color="#36865e", alpha=.14))
        ax.scatter([0], [0], marker="*", s=100, color="#34464d", label="Home")
        for method in ["cx_search", "cx_direct"]:
            trial = traces[(traces.route == route["name"]) & (traces.seed == seed)
                           & (traces.noise_deg == sigma) & (traces.method == method)]
            ax.plot(trial.x, trial.y, color=colors[method], lw=1.5,
                    ls="--" if method == "cx_direct" else "-", label=labels[method])
            ax.scatter(trial.x.iloc[-1], trial.y.iloc[-1], s=30, color=colors[method])
        ax.set(title=f"Turn noise: {sigma}°", xlabel="x (distance units)", ylabel="y (distance units)")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.15)
    handles, legend = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend, loc="lower center", ncol=4, frameon=False)
    fig.suptitle(f"Fixed example: {route['name']}, seed {seed} | home radius = 1")
    fig.tight_layout(rect=(0, .10, 1, .94))
    for suffix in ["png", "pdf"]:
        fig.savefig(output / f"figure1_search_trajectories.{suffix}", dpi=170)
    plt.close(fig)

    summary = summarize(metrics, ["method", "noise_deg"])
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    x = np.arange(len(config["turn_noise_std_deg"]))
    for index, method in enumerate(colors):
        sub = summary[summary.method == method].set_index("noise_deg").loc[config["turn_noise_std_deg"]]
        offset = x + (index - 1) * .25
        axes[0].bar(offset, sub.success_rate, width=.23, color=colors[method], label=labels[method])
        for xpos, row in zip(offset, sub.itertuples()):
            axes[0].text(xpos, row.success_rate + .025, f"{row.successes}/{row.trials}", ha="center", fontsize=8)
        axes[1].bar(offset, sub.mean_return_distance, width=.23, color=colors[method], label=labels[method])
    axes[0].set(ylabel="Fraction reaching home", ylim=(0, 1.16), title="Same contact rule for every method")
    axes[1].set(ylabel="Mean return distance (all trials)", title="Extra travel is included, including failures")
    for ax in axes:
        ax.set_xticks(x, [f"{sigma}°" for sigma in config["turn_noise_std_deg"]])
        ax.set_xlabel("Incremental turn noise")
        ax.grid(axis="y", alpha=.15)
    handles, legend = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend, loc="lower center", ncol=3, frameon=False)
    fig.suptitle("Three routes × five new seeds per noise level")
    fig.tight_layout(rect=(0, .10, 1, .94))
    for suffix in ["png", "pdf"]:
        fig.savefig(output / f"figure2_search_results.{suffix}", dpi=170)
    plt.close(fig)


def replay(output):
    config = json.loads((output / "config.json").read_text())
    metrics, traces = evaluate_saved(output, config)
    for filename, actual in [("metrics.csv", metrics), ("trajectories.csv", traces)]:
        pd.testing.assert_frame_equal(pd.read_csv(output / filename), actual,
                                      check_exact=False, atol=1e-12, rtol=1e-12)
    record = {"passed": True, "scope": "Navigation replay from saved neural return commands; not a neural rerun",
              "absolute_tolerance": 1e-12, "relative_tolerance": 1e-12,
              "trial_rows": len(metrics), "trajectory_rows": len(traces)}
    (output / "reproducibility.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


def run(config_path, output):
    started = time.perf_counter()
    config = json.loads(config_path.read_text())
    baseline_path = ROOT / config["baseline_config"]
    baseline = json.loads(baseline_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    for route in config["routes"]:
        expanded = {**baseline, "route": route["route"], "trial_seeds": config["trial_seeds"],
                    "turn_noise_std_deg": config["turn_noise_std_deg"], "success_radius": config["success_radius"]}
        path = output / (route["name"] + "_input.json")
        path.write_text(json.dumps(expanded, indent=2) + "\n")
        print(f"Running neural trials for route: {route['name']}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts/run_homing.py"), "--config", str(path),
                        "--output", str(output / "raw" / route["name"])], check=True, cwd=ROOT)
    metrics, traces = evaluate_saved(output, config)
    if not np.isfinite(metrics.select_dtypes(include=[np.number])).all().all():
        raise AssertionError("Nonfinite navigation result")
    if metrics.search_distance.max() > config["search_distance_budget"] + 1e-9:
        raise AssertionError("Search budget exceeded")
    if (metrics.loc[metrics.success, "endpoint_error"] > config["success_radius"] + 1e-9).any():
        raise AssertionError("False goal-contact success")
    metrics.to_csv(output / "metrics.csv", index=False)
    traces.to_csv(output / "trajectories.csv", index=False)
    summary = summarize(metrics, ["method", "noise_deg"])
    summary.to_csv(output / "summary.csv", index=False)
    summarize(metrics, ["route", "method", "noise_deg"]).to_csv(output / "by_route.csv", index=False)
    selected = summary[summary.method == "cx_search"].set_index("noise_deg")
    checks = {"zero_noise_15_of_15": bool(selected.loc[0, "successes"] == 15),
              "low_noise_at_least_12_of_15": bool(selected.loc[5, "successes"] >= 12)}
    source_paths = [Path(__file__), ROOT / "scripts/run_homing.py", config_path, baseline_path,
                    ROOT / "docs/search_homing_plan.md"]
    manifest = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in source_paths},
        "wall_seconds": time.perf_counter() - started, "trial_rows": len(metrics),
        "predeclared_targets": checks,
        "limitations": ["Binary goal-contact termination is an added task assumption.",
                        "Search is an external controller, not learned neural behavior.",
                        "Return actuation is exact; no additional motion noise or obstacles.",
                        "Fifteen trials per noise level are a small descriptive course experiment."],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    plot_results(output, config, metrics, traces)
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(checks), flush=True)
    print(f"RESULTS {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/homing_search.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", type=Path, help="Verify saved navigation without rerunning Brian2")
    args = parser.parse_args()
    if args.replay:
        replay(args.replay.resolve())
    else:
        destination = args.output or ROOT / "outputs/homing" / datetime.now(timezone.utc).strftime("search-%Y%m%dT%H%M%SZ")
        run(args.config.resolve(), destination.resolve())
