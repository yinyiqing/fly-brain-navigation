#!/usr/bin/env python3
"""Small FlyWire CX readout experiment with an explicit external path integrator.

No biological compass phases or intrinsic path-integration ability are assumed.
The return leg is a single commanded turn and straight walk with exact actuation.
"""

import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def wrap(angle):
    return (np.asarray(angle) + np.pi) % (2 * np.pi) - np.pi


def route_arrays(config):
    route = config["route"]
    n = route["samples_per_segment"]
    headings = np.repeat(np.deg2rad(route["headings_deg"]), n)
    distances = np.repeat(np.asarray(route["lengths"], dtype=float) / n, n)
    return headings, distances


def integrate(headings, distances):
    vectors = np.column_stack((np.cos(headings), np.sin(headings))) * distances[:, None]
    return np.vstack((np.zeros(2), np.cumsum(vectors, axis=0)))


def observe_turns(true_headings, sigma_deg, seed):
    # Noise is added to each incremental rotation, then accumulates as yaw drift.
    turns = wrap(np.diff(np.r_[0.0, true_headings]))
    noise = np.random.default_rng(seed).normal(size=len(turns)) * np.deg2rad(sigma_deg)
    return turns + noise


def home_command(estimated_path, estimated_heading):
    # Agent-side function: receives estimates only, never the true home vector.
    vector = -estimated_path[-1]
    distance = float(np.linalg.norm(vector))
    if distance < 1e-12:
        return 0.0, 0.0
    turn = float(wrap(np.arctan2(vector[1], vector[0]) - estimated_heading))
    return turn, distance


def evaluate_return(true_path, true_last_heading, decoded_headings, distances, radius):
    estimate = integrate(decoded_headings, distances)
    turn, distance = home_command(estimate, decoded_headings[-1])
    # Environment-side execution: perfect actuation for this bounded first task.
    actual_return_heading = true_last_heading + turn
    end = true_path[-1] + distance * np.array([np.cos(actual_return_heading), np.sin(actual_return_heading)])
    back = np.linspace(true_path[-1], end, 21)
    error = float(np.linalg.norm(end))
    return {
        "endpoint_error": error, "success": error <= radius,
        "return_distance": distance, "return_turn_deg": float(np.rad2deg(turn)),
        "endpoint_x": float(end[0]), "endpoint_y": float(end[1]),
    }, estimate, back


def fit_readout(features, headings, alpha):
    mean = features.mean(axis=0)
    scale = np.maximum(features.std(axis=0), 1.0)
    x = (features - mean) / scale
    targets = np.column_stack((np.cos(headings), np.sin(headings)))
    offset = targets.mean(axis=0)
    weights = np.linalg.solve(x.T @ x + alpha * np.eye(x.shape[1]), x.T @ (targets - offset))
    return {"mean": mean, "scale": scale, "weights": weights, "offset": offset}


def decode(features, readout):
    xy = ((features - readout["mean"]) / readout["scale"]) @ readout["weights"] + readout["offset"]
    return np.arctan2(xy[..., 1], xy[..., 0])


def motion_average(headings, measured_turns):
    """Causal circular mean after transporting past readouts by observed turns.

    This is external readout processing, not neural memory. Neither true
    headings, positions nor future observations enter this function.
    """
    headings = np.asarray(headings, dtype=float)
    measured_turns = np.asarray(measured_turns, dtype=float)
    if headings.ndim != 1 or headings.shape != measured_turns.shape:
        raise ValueError("Headings and measured turns must be matching 1-D arrays")
    result = np.empty_like(headings)
    accumulated = 0j
    for step, (heading, turn) in enumerate(zip(headings, measured_turns)):
        accumulated = accumulated * np.exp(1j * turn) + np.exp(1j * heading)
        # Opposed readings have no defined circular mean; retain the current
        # neural reading rather than substituting a geometric/true direction.
        result[step] = heading if abs(accumulated) < 1e-12 else np.angle(accumulated)
    return wrap(result)


class CXEncoder:
    """Artificial EPG rate code -> real signed CX connections -> non-EPG counts."""

    def __init__(self, config, output):
        import brian2 as b2
        import pyarrow as pa
        from smoke_simulation import prepare_inputs
        self.b2, self.config = b2, config
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
        b2.start_scope()
        b2.defaultclock.dt = 0.1 * b2.ms
        b2.prefs.codegen.target = "cython"
        cache = ROOT / ".cache/brian2"
        cache.mkdir(parents=True, exist_ok=True)
        b2.prefs.codegen.runtime.cython.cache_dir = str(cache)
        self.path_comp, self.path_con, neurons, edges, _ = prepare_inputs("cx", output)
        with (ROOT / "data/raw/flywire_783/neuron_annotations_v2.1.0.tsv").open() as stream:
            ann = {int(row["root_id"]): row for row in csv.DictReader(stream, delimiter="\t")}
        self.inputs = np.array([i for i, root in enumerate(neurons.index)
                                if ann[int(root)]["hemibrain_type"] == "EPG"], dtype=int)
        if len(self.inputs) < 8:
            raise ValueError("Insufficient annotated EPG neurons")
        # These are synthetic preferred directions, not anatomical wedge labels.
        self.phases = 2 * np.pi * np.arange(len(self.inputs)) / len(self.inputs)
        connections = pd.read_parquet(self.path_con)
        outgoing = connections[connections.Presynaptic_Index.isin(self.inputs)
                               & ~connections.Postsynaptic_Index.isin(self.inputs)].copy()
        outgoing["absolute_weight"] = outgoing["Excitatory x Connectivity"].abs()
        scores = outgoing.groupby("Postsynaptic_Index")["absolute_weight"].sum()
        # Structural selection, performed before seeing any calibration responses.
        order = sorted(scores.index, key=lambda i: (-int(scores.loc[i]), int(i)))
        self.features = np.array(order[:config["feature_count"]], dtype=int)
        assert not np.intersect1d(self.inputs, self.features).size
        self.metadata = {
            "neurons": len(neurons), "connection_records": edges,
            "input_indices": self.inputs.tolist(),
            "input_ids": [str(int(neurons.index[i])) for i in self.inputs],
            "artificial_preferred_directions_deg": np.rad2deg(self.phases).tolist(),
            "feature_indices": self.features.tolist(),
            "feature_ids": [str(int(neurons.index[i])) for i in self.features],
            "feature_types": [ann[int(neurons.index[i])]["hemibrain_type"] for i in self.features],
            "feature_selection": "128 strongest absolute EPG-to-non-EPG connection sums; index breaks ties",
            "note": "Input phases follow upstream row order and have no biological compass interpretation.",
        }
        sys.path.insert(0, str(ROOT / "external/Drosophila_brain_model"))
        import model
        params = dict(model.default_params)
        self.neurons, self.synapses, self.monitor = model.create_model(self.path_comp, self.path_con, params)
        self.neurons.rfc[self.inputs] = 0 * b2.ms
        self.poisson = b2.PoissonGroup(len(self.inputs), rates=0 * b2.Hz, name="heading_input")
        stimulus = b2.Synapses(self.poisson, self.neurons, on_pre="v_post += stimulus_weight",
                              namespace={"stimulus_weight": params["w_syn"] * params["f_poi"]},
                              name="heading_stimulus")
        stimulus.connect(i=np.arange(len(self.inputs)), j=self.inputs)
        self.net = b2.Network(self.neurons, self.synapses, self.monitor, self.poisson, stimulus)
        self.net.store("rest")

    def response(self, angle, seed, disconnect=False):
        b2 = self.b2
        self.net.restore("rest")
        b2.seed(seed)
        c = self.config
        rates = c["input_min_hz"] + (c["input_max_hz"] - c["input_min_hz"]) * (1 + np.cos(angle - self.phases)) / 2
        self.poisson.rates = rates * b2.Hz
        if disconnect:
            self.synapses.w = 0 * b2.mV
        self.net.run(c["window_ms"] * b2.ms, namespace={})
        counts = np.asarray(self.monitor.count[:], dtype=np.int64)
        return counts[self.features].copy(), int(counts.sum())


def calibrate(encoder, config, output):
    n = config["training_directions"]
    grid = 2 * np.pi * np.arange(n) / n
    angles = np.tile(grid, config["training_repeats"])
    train = []
    for k, angle in enumerate(angles):
        train.append(encoder.response(angle, 4100 + k)[0])
        if (k + 1) % n == 0:
            print(f"Calibration {k + 1}/{len(angles)}", flush=True)
    train = np.asarray(train)
    readout = fit_readout(train, angles, config["ridge_alpha"])
    test_angles = grid + np.pi / n  # unseen directions, separate Poisson seeds
    test = np.array([encoder.response(angle, 9100 + k)[0] for k, angle in enumerate(test_angles)])
    predictions = decode(test, readout)
    errors = np.rad2deg(np.abs(wrap(predictions - test_angles)))
    # One independent intervention checks that downstream counts require the graph.
    detached, all_spikes = encoder.response(0.0, 11001, disconnect=True)
    np.savez_compressed(output / "readout.npz", **readout)
    np.savez_compressed(output / "calibration.npz", train_counts=train, train_angles=angles,
                        test_counts=test, test_angles=test_angles, test_predictions=predictions,
                        disconnected_counts=detached)
    report = {
        "train_samples": len(train), "heldout_samples": len(test),
        "heldout_mae_deg": float(errors.mean()), "heldout_median_deg": float(np.median(errors)),
        "heldout_max_deg": float(errors.max()), "predeclared_mae_limit_deg": config["heldout_mae_limit_deg"],
        "passed": bool(errors.mean() <= config["heldout_mae_limit_deg"]),
        "disconnected_feature_spikes": int(detached.sum()),
        "disconnected_total_spikes_including_inputs": all_spikes,
        "test_angle_offset_deg": 180 / n,
    }
    if detached.any():
        raise AssertionError("Disconnected non-input neurons unexpectedly fired")
    (output / "calibration_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print("CALIBRATION " + json.dumps(report), flush=True)
    return readout, report


def run(config, output, config_path=None):
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    # These checks bound our process; no system-wide resource settings change.
    available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))) * 1024
    if available < 3 * 1024**3:
        raise RuntimeError("Need 3 GiB available host memory for the bounded CX run")
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    upstream = ROOT / "external/Drosophila_brain_model"
    commit = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if commit != json.loads((ROOT / "upstream.lock.json").read_text())["commit"]:
        raise ValueError("Unexpected upstream commit")
    encoder = CXEncoder(config["neural"], output)
    (output / "neural_mapping.json").write_text(json.dumps(encoder.metadata, indent=2) + "\n")
    readout, calibration = calibrate(encoder, config["neural"], output)
    true_headings, distances = route_arrays(config)
    true_path = integrate(true_headings, distances)
    records, traces, observations, neural_counts = [], [], [], []
    middle_noise = config["turn_noise_std_deg"][1]
    for sigma in config["turn_noise_std_deg"]:
        for seed in config["trial_seeds"]:
            measured_turns = observe_turns(true_headings, sigma, seed)
            measured_headings = wrap(np.cumsum(measured_turns))
            methods = {"geometric": measured_headings}
            if calibration["passed"]:
                counts = np.array([encoder.response(theta, 20000 + seed * 100 + k)[0]
                                   for k, theta in enumerate(measured_headings)])
                methods["cx_readout"] = decode(counts, readout)
                if config.get("motion_compensated_average", False):
                    methods["cx_motion_average"] = motion_average(methods["cx_readout"], measured_turns)
                neural_counts.append(counts)
                if sigma == middle_noise:
                    # Counterfactual replay of the same outbound inputs with readout disabled.
                    methods["readout_off"] = decode(np.zeros_like(counts), readout)
                    if config.get("motion_compensated_average", False):
                        methods["motion_average_off"] = motion_average(methods["readout_off"], measured_turns)
            for k, (turn, angle) in enumerate(zip(measured_turns, measured_headings)):
                observations.append({"noise_deg": sigma, "seed": seed, "step": k,
                                     "measured_turn_rad": float(turn), "estimated_yaw_rad": float(angle),
                                     "distance": float(distances[k])})
            for method, headings in methods.items():
                metrics, estimate, back = evaluate_return(true_path, true_headings[-1], headings,
                                                          distances, config["success_radius"])
                metrics.update(method=method, noise_deg=sigma, seed=seed,
                               heading_mae_deg=float(np.rad2deg(np.abs(wrap(headings - true_headings))).mean()))
                records.append(metrics)
                for phase, points in [("outbound_true", true_path), ("outbound_estimated", estimate), ("return_true", back)]:
                    for k, xy in enumerate(points):
                        traces.append({"method": method, "noise_deg": sigma, "seed": seed,
                                       "phase": phase, "step": k, "x": float(xy[0]), "y": float(xy[1])})
            print(f"Completed noise={sigma} deg, seed={seed}", flush=True)
    metrics = pd.DataFrame(records)
    metrics.to_csv(output / "metrics.csv", index=False)
    pd.DataFrame(traces).to_csv(output / "trajectories.csv", index=False)
    pd.DataFrame(observations).to_csv(output / "observations.csv", index=False)
    np.savez_compressed(output / "navigation_counts.npz", counts=np.array(neural_counts))
    summary = metrics.groupby(["method", "noise_deg"], sort=False).agg(
        mean_error=("endpoint_error", "mean"), std_error=("endpoint_error", "std"),
        min_error=("endpoint_error", "min"), max_error=("endpoint_error", "max"),
        successes=("success", "sum"), trials=("success", "size"),
    ).reset_index()
    summary.to_csv(output / "summary.csv", index=False)
    zero = metrics[(metrics.method == "geometric") & (metrics.noise_deg == 0)]
    assert len(zero) and float(zero.endpoint_error.max()) < 1e-9, "Noiseless geometry must return exactly"
    assert np.isfinite(metrics.select_dtypes(include=[np.number]).to_numpy()).all()
    source_files = [Path(__file__), ROOT / "scripts/smoke_simulation.py"]
    if config_path is not None:
        source_files.append(config_path.resolve())
    source_hashes = {
        str(q.relative_to(ROOT) if q.is_relative_to(ROOT) else q):
            hashlib.sha256(q.read_bytes()).hexdigest()
        for q in source_files
    }
    manifest = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(), "upstream_commit": commit,
        "source_sha256": source_hashes, "python": sys.version,
        "saved_config_sha256": hashlib.sha256((output / "config.json").read_bytes()).hexdigest(),
        "neural_gate_passed": calibration["passed"], "calibration": calibration,
        "trial_rows": len(metrics), "wall_seconds": time.perf_counter() - started,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "geometry_sanity_passed": True,
        "limitations": ["Artificial EPG direction labels; no recovered biological compass phases.",
                        "Each neural window resets to rest; no neural memory or intrinsic path integration.",
                        "External code integrates noisy turns and positions; return actuation is exact.",
                        f"One route, {len(config['trial_seeds'])} seeds per noise; descriptive coursework results only.",
                        "CX induced subgraph drops connections outside the annotated CX set."],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(summary.to_string(index=False), flush=True)
    print(f"RESULTS {output}\nWALL_SECONDS {manifest['wall_seconds']:.2f}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/homing.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or ROOT / "outputs/homing" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run(json.loads(args.config.read_text()), destination, args.config)
