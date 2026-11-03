#!/usr/bin/env python3
"""Run one bounded upstream trial, on the real CX subgraph or full v783 graph.

This checks runtime compatibility and spike I/O, not navigation or biology.
"""

import argparse
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "external/Drosophila_brain_model"


def available_memory():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def prepare_inputs(scope, workdir):
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    original_comp = UPSTREAM / "Completeness_783.csv"
    original_con = UPSTREAM / "Connectivity_783.parquet"
    comp = pd.read_csv(original_comp, index_col=0)
    if comp.index.dtype.kind not in "iu" or not comp.index.is_unique:
        raise ValueError("Expected unique integer FlyWire IDs")
    with (ROOT / "data/raw/flywire_783/neuron_annotations_v2.1.0.tsv").open() as stream:
        cx = {
            int(row["root_id"]): row
            for row in csv.DictReader(stream, delimiter="\t")
            if row["cell_class"] == "CX"
        }
    cx_ids = [int(i) for i in comp.index if int(i) in cx]
    if not cx_ids:
        raise ValueError("No annotated CX neurons in the upstream model")
    # An artificial single-neuron probe. No claim about natural sensory input.
    epg = [i for i in cx_ids if cx[i]["hemibrain_type"] == "EPG"]
    stim_id = epg[0] if epg else cx_ids[0]
    probe = {
        "flywire_id": str(stim_id),
        "cell_type": cx[stim_id]["cell_type"],
        "hemibrain_type": cx[stim_id]["hemibrain_type"],
        "selection": "first EPG in upstream row order, otherwise first CX neuron",
    }
    if scope == "full":
        return original_comp, original_con, comp, pq.ParquetFile(original_con).metadata.num_rows, probe

    keep = np.array([int(i) in cx for i in comp.index], dtype=bool)
    remap = np.full(len(comp), -1, dtype=np.int64)
    remap[keep] = np.arange(int(keep.sum()), dtype=np.int64)
    selected = comp.loc[keep]
    path_comp = workdir / "Completeness_CX_783.csv"
    path_con = workdir / "Connectivity_CX_783.parquet"
    selected.to_csv(path_comp)
    columns = ["Presynaptic_ID", "Postsynaptic_ID", "Presynaptic_Index",
               "Postsynaptic_Index", "Connectivity", "Excitatory",
               "Excitatory x Connectivity"]
    source = pq.ParquetFile(original_con)
    schema = pa.schema([source.schema_arrow.field(c) for c in columns])
    edges = 0
    with pq.ParquetWriter(path_con, schema, compression="snappy") as writer:
        for batch in source.iter_batches(batch_size=131072, columns=columns, use_threads=False):
            table = pa.Table.from_batches([batch]).replace_schema_metadata(None)
            pre = remap[table["Presynaptic_Index"].to_numpy()]
            post = remap[table["Postsynaptic_Index"].to_numpy()]
            mask = (pre >= 0) & (post >= 0)
            if not mask.any():
                continue
            small = table.filter(pa.array(mask))
            for name, mapped in [("Presynaptic_Index", pre[mask]), ("Postsynaptic_Index", post[mask])]:
                small = small.set_column(small.schema.get_field_index(name), name, pa.array(mapped))
            ids = selected.index.to_numpy(dtype=np.int64)
            if not np.array_equal(ids[pre[mask]], small["Presynaptic_ID"].to_numpy()):
                raise ValueError("Presynaptic ID/index mismatch after remapping")
            if not np.array_equal(ids[post[mask]], small["Postsynaptic_ID"].to_numpy()):
                raise ValueError("Postsynaptic ID/index mismatch after remapping")
            writer.write_table(small)
            edges += small.num_rows
    if not edges:
        raise ValueError("CX induced subgraph has no edges")
    return path_comp, path_con, selected, edges, probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["cx", "full"], default="cx")
    parser.add_argument("--duration-ms", type=float, default=100)
    parser.add_argument("--seed", type=int, default=20261103)
    args = parser.parse_args()
    if not 0 < args.duration_ms <= 1000:
        parser.error("Smoke-test duration must be in (0, 1000] ms")

    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    workdir = ROOT / "outputs/smoke" / (args.scope + "-" + stamp)
    workdir.mkdir(parents=True)
    available = available_memory()
    limit = (4 if args.scope == "full" else 2) * 1024**3
    report = {
        "status": "running", "scope": args.scope,
        "started_at_utc": stamp, "output_directory": str(workdir.relative_to(ROOT)),
        "available_memory_before_bytes": available,
        "address_space_limit_bytes": limit,
        "duration_ms": args.duration_ms, "seed": args.seed,
        "n_run": 1, "n_proc": 1, "python": sys.version,
        "limitation": "Runtime smoke test only; no homing task or functional circuit validation. "
                      "CX scope drops every connection to a neuron outside the annotated CX set.",
    }
    try:
        # Bound this process only. Keep at least 1 GiB free at launch.
        if available < limit + 1024**3:
            raise RuntimeError("Insufficient available host memory for this bounded smoke test")
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ[key] = "1"
        import brian2 as b2
        import numpy as np
        import pandas as pd
        import pyarrow as pa
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
        b2.prefs.codegen.target = "cython"
        cache = ROOT / ".cache/brian2"
        cache.mkdir(parents=True, exist_ok=True)
        b2.prefs.codegen.runtime.cython.cache_dir = str(cache)
        b2.seed(args.seed)
        sys.path.insert(0, str(UPSTREAM))
        import model as upstream

        commit = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        if commit != lock["commit"]:
            raise ValueError("Upstream commit differs from upstream.lock.json")
        report["upstream_commit"] = commit
        report["packages"] = {name: importlib.metadata.version(name) for name in
                              ["brian2", "numpy", "pandas", "pyarrow", "Cython", "joblib", "sympy"]}
        report["codegen_target"] = "cython"
        path_comp, path_con, neurons, edges, probe = prepare_inputs(args.scope, workdir)
        report.update(neurons=len(neurons), connection_records=edges, probe=probe)
        report["input_files"] = [str(p.relative_to(ROOT)) for p in [path_comp, path_con]]
        report["preparation_wall_seconds"] = time.perf_counter() - started
        print(json.dumps({k: report[k] for k in ["scope", "neurons", "connection_records", "probe"]}), flush=True)
        params = dict(upstream.default_params)
        params.update(t_run=args.duration_ms * b2.ms, n_run=1)
        trial_start = time.perf_counter()
        upstream.run_exp(
            exp_name="probe", neu_exc=[int(probe["flywire_id"])], path_res=workdir,
            path_comp=path_comp, path_con=path_con, params=params, n_proc=1,
        )
        report["experiment_wall_seconds"] = time.perf_counter() - trial_start
        spikes = pd.read_parquet(workdir / "probe.parquet")
        if spikes.empty or not np.isfinite(spikes["t"]).all():
            raise ValueError("Expected finite nonempty spike output")
        if set(spikes["trial"]) != {0} or not spikes["flywire_id"].isin(neurons.index).all():
            raise ValueError("Invalid output trial or neuron ID")
        if not ((spikes["t"] >= 0) & (spikes["t"] < args.duration_ms / 1000)).all():
            raise ValueError("Spike time is outside the simulation interval")
        input_spikes = int((spikes["flywire_id"] == int(probe["flywire_id"])).sum())
        if not input_spikes:
            raise ValueError("Stimulated neuron did not fire in this smoke test")
        report.update(status="passed", spike_count=len(spikes),
                      active_neurons=int(spikes["flywire_id"].nunique()),
                      stimulated_neuron_spikes=input_spikes,
                      other_neuron_spikes=len(spikes) - input_spikes)
    except BaseException as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(total_wall_seconds=time.perf_counter() - started,
                      max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        (workdir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
