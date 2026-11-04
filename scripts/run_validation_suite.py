#!/usr/bin/env python3
"""Small, fixed neural-label controls and paired return-actuation validation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_homing import ROOT, decode, fit_readout, home_command, integrate, motion_average, route_arrays, wrap
from run_search_homing import execute_return, return_actions, summarize
import numpy as np
import pandas as pd


def shuffled_labels(angles, seed):
    """Consistently permute training labels; spike features and test times stay intact."""
    unique, inverse = np.unique(np.asarray(angles, dtype=float), return_inverse=True)
    permutation = np.random.default_rng(seed).permutation(len(unique))
    return unique[permutation][inverse], unique, unique[permutation]


def execution_errors(base_seed, route_index, trial_seed, sigma_deg, count):
    """Shared standardized draws per route/trial, independent of method and budget."""
    if sigma_deg < 0 or not np.isfinite(sigma_deg):
        raise ValueError("Execution-noise standard deviation must be finite and nonnegative")
    rng = np.random.default_rng(np.random.SeedSequence([base_seed, route_index, trial_seed]))
    return rng.normal(size=count) * np.deg2rad(sigma_deg)


def source_setup(config):
    source = ROOT / config["source_results"]
    source_config = json.loads((source / "config.json").read_text())
    return source, source_config


def ablation_tables(config):
    source, settings = source_setup(config)
    first_raw = source / "raw" / settings["routes"][0]["name"]
    with np.load(first_raw / "calibration.npz") as file:
        calibration = {key: file[key] for key in file.files}
    with np.load(first_raw / "readout.npz") as file:
        normal = {key: file[key] for key in file.files}
    neural = json.loads((first_raw / "config.json").read_text())["neural"]
    models = [("cx_normal", 0, normal), ("readout_off", 0, normal)]
    mapping_rows = []
    for seed in config["label_shuffle_seeds"]:
        labels, original, shuffled = shuffled_labels(calibration["train_angles"], seed)
        model = fit_readout(calibration["train_counts"], labels, neural["ridge_alpha"])
        models.append(("cx_shuffled_labels", seed, model))
        mapping_rows.extend({"shuffle_seed": seed, "input_deg": np.rad2deg(a), "training_label_deg": np.rad2deg(b)}
                            for a, b in zip(original, shuffled))
    decoder_rows = []
    for method, variant, model in models:
        features = calibration["test_counts"]
        predicted = decode(np.zeros_like(features) if method == "readout_off" else features, model)
        errors = np.rad2deg(np.abs(wrap(predicted - calibration["test_angles"])))
        decoder_rows.append({"method": method, "variant": variant, "heldout_mae_deg": errors.mean(),
                             "heldout_max_deg": errors.max(), "heldout_directions": len(errors)})
    rows = []
    for route in settings["routes"]:
        raw = source / "raw" / route["name"]
        current_config = json.loads((raw / "config.json").read_text())
        with np.load(raw / "calibration.npz") as current:
            for key in calibration:
                np.testing.assert_array_equal(current[key], calibration[key])
        with np.load(raw / "readout.npz") as current:
            for key in normal:
                np.testing.assert_array_equal(current[key], normal[key])
        truth, distances = route_arrays(current_config)
        true_path = integrate(truth, distances)
        observations = pd.read_csv(raw / "observations.csv")
        with np.load(raw / "navigation_counts.npz") as file:
            counts = file["counts"]
        index = 0
        for sigma in current_config["turn_noise_std_deg"]:
            for seed in current_config["trial_seeds"]:
                obs = observations[(observations.noise_deg == sigma) & (observations.seed == seed)].sort_values("step")
                turns = obs.measured_turn_rad.to_numpy()
                measured = obs.estimated_yaw_rad.to_numpy()
                activity = counts[index]
                index += 1
                methods = [("geometric", 0, measured)]
                for method, variant, model in models:
                    inputs = np.zeros_like(activity) if method == "readout_off" else activity
                    headings = motion_average(decode(inputs, model), turns)
                    methods.append((method, variant, headings))
                for method, variant, headings in methods:
                    turn, distance = home_command(integrate(headings, distances), headings[-1])
                    for budget in [0, settings["search_distance_budget"]]:
                        actions = return_actions(turn, distance, settings["search_spacing"], budget)
                        result, _ = execute_return(true_path[-1], truth[-1], actions, settings["success_radius"])
                        rows.append({"route": route["name"], "noise_deg": sigma, "seed": seed,
                                     "method": method, "variant": variant, "budget": budget,
                                     "heading_mae_deg": np.rad2deg(np.abs(wrap(headings - truth))).mean(), **result})
    metrics = pd.DataFrame(rows)
    # Compare each unchanged branch to the previously saved complete experiment.
    old = pd.read_csv(source / "metrics.csv")
    for method, prefix in [("cx_normal", "cx"), ("geometric", "geometric"), ("readout_off", "readout_off")]:
        for budget, suffix in [(0, "direct"), (settings["search_distance_budget"], "search")]:
            expected = old[old.method == prefix + "_" + suffix].set_index(["route", "noise_deg", "seed"])
            actual = metrics[(metrics.method == method) & (metrics.budget == budget)].set_index(["route", "noise_deg", "seed"])
            for key, row in expected.iterrows():
                assert bool(actual.loc[key, "success"]) == bool(row.success)
                np.testing.assert_allclose(actual.loc[key, ["endpoint_error", "return_distance"]].to_numpy(dtype=float),
                                           [row.endpoint_error, row.return_distance], atol=1e-10, rtol=1e-10)
    return {"ablation_metrics.csv": metrics,
            "ablation_by_variant.csv": summarize(metrics, ["method", "variant", "noise_deg", "budget"]),
            "decoder_controls.csv": pd.DataFrame(decoder_rows),
            "label_permutations.csv": pd.DataFrame(mapping_rows)}


def historical_budget_table(config):
    source, _ = source_setup(config)
    old = pd.read_csv(source / "metrics.csv")
    old = old[old.method == "cx_search"]
    rows = []
    for budget in config["historical_budgets"]:
        for sigma, trials in old.groupby("noise_deg", sort=False):
            success = trials.success & (trials.search_distance <= budget + 1e-9)
            distance = trials.return_distance - trials.search_distance + np.minimum(trials.search_distance, budget)
            rows.append({"analysis": "retrospective", "noise_deg": sigma, "budget": budget,
                         "successes": int(success.sum()), "trials": len(trials),
                         "success_rate": success.mean(), "mean_return_distance": distance.mean()})
    return pd.DataFrame(rows)


def robustness_tables(output, config):
    _, settings = source_setup(config)
    rows, traces = [], []
    max_budget = max(config["search_budgets"])
    action_count = len(list(return_actions(0, 0, settings["search_spacing"], max_budget)))
    for route_index, route in enumerate(settings["routes"]):
        raw = output / "raw" / route["name"]
        current_config = json.loads((raw / "config.json").read_text())
        if current_config["trial_seeds"] != config["trial_seeds"]:
            raise AssertionError("Unexpected validation seeds")
        headings, distances = route_arrays(current_config)
        true_path = integrate(headings, distances)
        metrics = pd.read_csv(raw / "metrics.csv")
        for trial in metrics.itertuples(index=False):
            if trial.method not in ["geometric", "cx_motion_average"]:
                continue
            method = "cx" if trial.method == "cx_motion_average" else "geometric"
            for sigma in config["execution_noise_deg"]:
                errors = execution_errors(config["execution_seed"], route_index, trial.seed, sigma, action_count)
                for budget in config["search_budgets"]:
                    actions = return_actions(np.deg2rad(trial.return_turn_deg), trial.return_distance,
                                             settings["search_spacing"], budget)
                    result, points = execute_return(true_path[-1], headings[-1], actions,
                                                    settings["success_radius"], turn_errors=errors)
                    keys = {"route": route["name"], "noise_deg": trial.noise_deg, "seed": trial.seed,
                            "method": method, "execution_noise_deg": sigma, "budget": budget}
                    rows.append({**keys, **result})
                    if (route["name"] == config["demo_route"] and trial.seed == config["demo_seed"]
                            and method == "cx" and sigma == config["demo_execution_noise_deg"] and budget == max_budget):
                        all_points = [("outbound", *xy) for xy in true_path] + points[1:]
                        for step, (phase, x, y) in enumerate(all_points):
                            traces.append({**keys, "phase": phase, "step": step, "x": x, "y": y})
    metrics = pd.DataFrame(rows)
    paired = []
    for (method, noise, budget), group in metrics.groupby(["method", "noise_deg", "budget"], sort=False):
        exact = group[group.execution_noise_deg == 0].set_index(["route", "seed"])
        noisy = group[group.execution_noise_deg == config["demo_execution_noise_deg"]].set_index(["route", "seed"]).loc[exact.index]
        paired.append({"method": method, "noise_deg": noise, "budget": budget,
                       "trials": len(exact), "lost_successes": int((exact.success & ~noisy.success).sum()),
                       "gained_successes": int((~exact.success & noisy.success).sum()),
                       "mean_extra_return_distance": (noisy.return_distance - exact.return_distance).mean()})
    return {"robustness_metrics.csv": metrics,
            "robustness_summary.csv": summarize(metrics, ["method", "noise_deg", "execution_noise_deg", "budget"]),
            "robustness_by_route.csv": summarize(metrics, ["route", "method", "noise_deg", "execution_noise_deg", "budget"]),
            "paired_execution_effects.csv": pd.DataFrame(paired),
            "demo_trajectories.csv": pd.DataFrame(traces)}


def evaluate(output, config):
    tables = ablation_tables(config)
    tables.update(robustness_tables(output, config))
    tables["budget_historical.csv"] = historical_budget_table(config)
    for name in ["ablation_metrics.csv", "robustness_metrics.csv"]:
        table = tables[name]
        assert np.isfinite(table.select_dtypes(include=[np.number]).to_numpy()).all()
        assert (table.search_distance <= table.budget + 1e-9).all()
        assert (table.loc[table.success, "endpoint_error"] <= 1 + 1e-9).all()
    return tables


def verify(output):
    config = json.loads((output / "config.json").read_text())
    tables = evaluate(output, config)
    for name, actual in tables.items():
        pd.testing.assert_frame_equal(pd.read_csv(output / name), actual,
                                      check_exact=False, atol=1e-10, rtol=1e-10)
    manifest = json.loads((output / "manifest.json").read_text())
    for name, digest in manifest["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise AssertionError(f"Source changed: {name}")
    record = {"passed": True, "tables_compared": len(tables),
              "ablation_rows": len(tables["ablation_metrics.csv"]),
              "robustness_rows": len(tables["robustness_metrics.csv"]),
              "old_normal_geometry_and_off_results_match": True,
              "absolute_tolerance": 1e-10, "relative_tolerance": 1e-10,
              "scope": "Independent-process control replay from saved spikes and commands; no neural rerun"}
    (output / "reproducibility.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


def run(config_path, output):
    started = time.perf_counter()
    config = json.loads(config_path.read_text())
    source, settings = source_setup(config)
    if set(config["trial_seeds"]) & set(settings["trial_seeds"]):
        raise ValueError("Validation seeds must be new")
    baseline_path = ROOT / settings["baseline_config"]
    baseline = json.loads(baseline_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    for route in settings["routes"]:
        expanded = {**baseline, "route": route["route"], "trial_seeds": config["trial_seeds"],
                    "turn_noise_std_deg": settings["turn_noise_std_deg"], "success_radius": settings["success_radius"]}
        path = output / (route["name"] + "_input.json")
        path.write_text(json.dumps(expanded, indent=2) + "\n")
        print(f"New neural validation trials: {route['name']}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts/run_homing.py"), "--config", str(path),
                        "--output", str(output / "raw" / route["name"])], check=True, cwd=ROOT)
    tables = evaluate(output, config)
    for name, table in tables.items():
        table.to_csv(output / name, index=False)
    files = [Path(__file__), ROOT / "scripts/run_search_homing.py", ROOT / "scripts/run_homing.py",
             ROOT / "docs/validation_plan.md", config_path, baseline_path]
    files.extend(path for path in source.rglob('*') if path.is_file()
                 and path.suffix in {".csv", ".npz", ".json"})
    manifest = {"completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "wall_seconds": time.perf_counter() - started,
                "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
                "new_neural_trials": len(settings["routes"]) * len(config["trial_seeds"]) * len(settings["turn_noise_std_deg"]),
                "ablation_rows": len(tables["ablation_metrics.csv"]),
                "robustness_rows": len(tables["robustness_metrics.csv"]),
                "limitations": ["Label controls test correspondence, not connectome-specific superiority.",
                                "Execution noise affects turns only; distances and goal detection remain ideal.",
                                "Routes share ten seed values; route-seed combinations are not independent seeds.",
                                "Five label permutations are controls, not extra independent navigation trials.",
                                "Motion integration and search remain external; no intrinsic neural memory."]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    summary = tables["robustness_summary.csv"]
    print(summary[(summary.method == "cx") & (summary.budget == max(config["search_budgets"]))].to_string(index=False), flush=True)
    print(tables["decoder_controls.csv"].to_string(index=False), flush=True)
    print(f"RESULTS {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/homing_validation.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.verify.resolve())
    else:
        destination = args.output or ROOT / "outputs/homing" / datetime.now(timezone.utc).strftime("validation-%Y%m%dT%H%M%SZ")
        run(args.config.resolve(), destination.resolve())
