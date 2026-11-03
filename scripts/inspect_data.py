#!/usr/bin/env python3
"""Validate FlyWire IDs, annotations and connectivity in bounded-size batches."""

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/flywire_783"


def main():
    roots = np.load(RAW / "proofread_root_ids_783.npy", allow_pickle=False)
    assert roots.ndim == 1 and roots.dtype.kind in "iu", "Root IDs must be integers"
    root_set = {int(value) for value in roots}
    assert len(root_set) == len(roots), "Duplicate proofread neuron IDs"
    annotation_ids = set()
    classes, transmitters = Counter(), Counter()
    annotation_rows = 0
    duplicate_annotations = 0
    with (RAW / "neuron_annotations_v2.1.0.tsv").open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        annotation_columns = reader.fieldnames
        assert "root_id" in annotation_columns
        for row in reader:
            root = int(row["root_id"])
            duplicate_annotations += root in annotation_ids
            annotation_ids.add(root)
            annotation_rows += 1
            classes[row.get("cell_class") or "unannotated"] += 1
            transmitters[row.get("top_nt") or "unannotated"] += 1
    assert not duplicate_annotations, "Duplicate annotation root IDs"

    totals = {"connection_rows_by_neuropil": 0, "synapse_count_sum": 0,
              "unknown_presynaptic_ids_rows": 0, "unknown_postsynaptic_ids_rows": 0,
              "self_connection_rows": 0, "nonpositive_synapse_count_rows": 0,
              "null_id_or_count_rows": 0}
    sample = []
    path = RAW / "proofread_connections_783.feather"
    with pa.memory_map(str(path), "r") as source:
        reader = pa.ipc.open_file(source)
        schema = reader.schema
        for name in ("pre_pt_root_id", "post_pt_root_id", "syn_count"):
            assert name in schema.names and pa.types.is_integer(schema.field(name).type), name
        assert "neuropil" in schema.names
        ids = pa.array(roots).cast(schema.field("pre_pt_root_id").type)
        batches = reader.num_record_batches
        for index in range(batches):
            batch = reader.get_batch(index)
            pre = batch.column(schema.get_field_index("pre_pt_root_id"))
            post = batch.column(schema.get_field_index("post_pt_root_id"))
            counts = batch.column(schema.get_field_index("syn_count"))
            totals["connection_rows_by_neuropil"] += batch.num_rows
            totals["synapse_count_sum"] += pc.sum(counts.cast(pa.int64())).as_py() or 0
            totals["unknown_presynaptic_ids_rows"] += pc.sum(pc.invert(pc.is_in(pre, value_set=ids))).as_py() or 0
            totals["unknown_postsynaptic_ids_rows"] += pc.sum(pc.invert(pc.is_in(post, value_set=ids))).as_py() or 0
            totals["self_connection_rows"] += pc.sum(pc.equal(pre, post)).as_py() or 0
            totals["nonpositive_synapse_count_rows"] += pc.sum(pc.less_equal(counts, 0)).as_py() or 0
            totals["null_id_or_count_rows"] += pc.sum(pc.or_(pc.or_(pc.is_null(pre), pc.is_null(post)), pc.is_null(counts))).as_py() or 0
            if not sample:
                sample = batch.slice(0, 3).to_pylist()
            if (index + 1) % 50 == 0 or index + 1 == batches:
                print("Checked batch %d/%d" % (index + 1, batches), flush=True)
    errors = {k: v for k, v in totals.items() if (k.startswith("unknown_") or k.startswith("nonpositive_") or k.startswith("null_")) and v}
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "FlyWire FAFB materialization 783", "annotation_release": "v2.1.0",
        "proofread_neurons": len(roots), "annotation_rows": annotation_rows,
        "duplicate_annotation_ids": duplicate_annotations,
        "proofread_ids_without_annotations": len(root_set - annotation_ids),
        "annotation_ids_outside_proofread_set": len(annotation_ids - root_set),
        "connectivity": totals,
        "connectivity_schema": {f.name: str(f.type) for f in schema},
        "record_batches": batches, "sample_connection_rows": sample,
        "annotation_columns": annotation_columns,
        "cell_class_counts": dict(classes.most_common()),
        "predicted_neurotransmitter_counts": dict(transmitters.most_common()),
        "structural_validation_passed": not errors,
        "note": "Rows are neuron-pair by neuropil aggregates, not individual synapses."
    }
    output = ROOT / "data/metadata/data_inventory.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"proofread_neurons": len(roots), "annotation_rows": annotation_rows,
                      "connectivity": totals, "structural_validation_passed": not errors}, indent=2))
    if errors:
        raise ValueError("Connectivity validation failed: %s" % errors)


if __name__ == "__main__":
    main()
