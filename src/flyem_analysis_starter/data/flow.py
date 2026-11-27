"""Information-flow layers (hitting times) and lateral-flow matrices.

Works for any dataset. `fetch_instance_flow` gives each neuron the number of
steps information takes to reach it from the eye's input neurons; the
`data.build` flow step calls it. The lateral-flow helpers below are used by the
effective-connectivity build (`local/s3_effconn.py`, not yet in the package).

Adapted from reiserlab/visualpathways, `src/setup_data/flow.py`. Not part of
the stable API.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

# Input neurons of the right eye that seed the flow. The left-eye seeds swap
# the side suffix; seeds missing from a dataset are skipped by
# `find_instance_flow` (FlyWire has no R7d_L/R8d_L).
R_FLOW_SEEDS = ["L1_R", "L2_R", "L3_R", "R7_R", "R8_R", "R7d_R", "R8d_R", "HBeyelet_R"]
L_FLOW_SEEDS = [s[:-2] + "_L" for s in R_FLOW_SEEDS]


def flow_seeds(side: str) -> list[str]:
    """Return the seed instances for flow from the right (`"r"`) or left (`"l"`) eye."""
    if side not in ("r", "l"):
        raise ValueError(f"side must be 'r' or 'l', got {side!r}")
    return list(R_FLOW_SEEDS if side == "r" else L_FLOW_SEEDS)


def flow_file_names(prefix: str, steps: int, thre: float) -> tuple[str, str]:
    """Return the per-neuron and per-instance hitting-time file names.

    Args:
        prefix: Everything before the step count, e.g. `malecns_v1.0_r_flow_`.
        steps: Number of flow steps.
        thre: Flow threshold.

    Returns:
        `(per_neuron, per_group)` file names, as `find_instance_flow` writes them.
    """
    stem = f"{prefix}{steps}step_{thre}thre_hit"
    return f"{stem}.csv", f"{stem}_per_group.csv"


def fetch_instance_flow(
    inprop: sp.csc_matrix,
    idx_to_instance: dict[int, str],
    seed_groups: list[str],
    data_dir: Path,
    save_prefix: str,
    steps: int = 20,
    thre: float = 0.1,
    method: str | None = None,
) -> pd.DataFrame:
    """Compute per-neuron hitting times and write them as two CSV files.

    Runs `connectome_interpreter.find_instance_flow`, which writes
    `{save_prefix}{steps}step_{thre}thre_hit.csv` (per neuron: `idx`,
    `hitting_time`, `instance`) and `..._per_group.csv` (per instance) into
    `data_dir`. Its `cell_group` column is renamed to `instance` in both.

    Takes about 5 minutes for the male CNS on a laptop with the batched navis
    model (navis-org/navis#202); the per-node model of navis 1.11 took 3 hours.

    Args:
        inprop: Input-fraction matrix (see `data.load_inprop`).
        idx_to_instance: Matrix index to instance name, from `meta`.
        seed_groups: Instances the flow starts from (see `flow_seeds`).
        data_dir: Folder to write the two files into.
        save_prefix: File-name prefix, e.g. `malecns_v1.0_r_flow_`.
        steps: Number of flow steps.
        thre: Flow threshold.
        method: navis `BayesianTraversalModel` math, `"legacy"` or
            `"conditioned"` (see `config.FLOW_METHOD`); None uses navis' default.

    Returns:
        The per-neuron table.
    """
    from connectome_interpreter import find_instance_flow

    find_instance_flow(
        inprop,
        idx_to_instance,
        flow_seed_groups=seed_groups,
        file_path=str(data_dir),
        save_prefix=save_prefix,
        flow_steps=steps,
        flow_thre=thre,
        method=method,
    )
    per_neuron, per_group = flow_file_names(save_prefix, steps, thre)
    out = Path(data_dir) / per_neuron
    df = pd.read_csv(out).rename(columns={"cell_group": "instance"})
    df.to_csv(out, index=False)
    out_group = Path(data_dir) / per_group
    if out_group.exists():
        pd.read_csv(out_group).rename(columns={"cell_group": "instance"}).to_csv(
            out_group, index=False
        )
    return df


# === Lateral flow (used by the effective-connectivity build) ===


def trim_inprop_by_flow(
    inprop: sp.csc_matrix,
    idx_to_instance: dict[int, str],
    flow_type_df: pd.DataFrame,
    flow_diff_min: float = 0.0,
    flow_diff_max: float = 20.0,
) -> sp.csc_matrix:
    """Keep the edges whose post-minus-pre hitting time lies in `(min, max)`.

    Per-instance hitting times come from `flow_type_df` (`instance`,
    `hitting_time`). Edges whose pre or post neuron has no hitting time are
    dropped.

    Args:
        inprop: Input-fraction matrix.
        idx_to_instance: Matrix index to instance name.
        flow_type_df: Per-instance hitting times.
        flow_diff_min: Lower bound (exclusive) on the hitting-time difference.
        flow_diff_max: Upper bound (exclusive).

    Returns:
        The trimmed matrix, same shape as `inprop`.
    """
    hit_map = dict(zip(flow_type_df["instance"], flow_type_df["hitting_time"]))
    hit_by_idx = np.full(inprop.shape[0], np.nan, dtype=np.float64)
    for i, instance in idx_to_instance.items():
        h = hit_map.get(instance)
        if h is not None:
            hit_by_idx[i] = h

    coo = inprop.tocoo()
    diff = hit_by_idx[coo.col] - hit_by_idx[coo.row]
    mask = (diff > flow_diff_min) & (diff < flow_diff_max)
    return sp.csc_matrix(
        (coo.data[mask], (coo.row[mask], coo.col[mask])), shape=inprop.shape
    )


def save_lat_flow_0(
    trimmed_inprop: sp.csc_matrix,
    data_dir: Path,
    save_prefix: str,
    output_threshold: float = 1e-6,
) -> None:
    """Write `{save_prefix}0.npz`, dropping values with `|x| <= output_threshold`.

    The threshold makes the stored matrix match `compress_paths` step 0 exactly.
    """
    m = sp.csc_matrix(trimmed_inprop, copy=True)
    m.data[np.abs(m.data) <= output_threshold] = 0
    m.eliminate_zeros()
    sp.save_npz(Path(data_dir) / f"{save_prefix}0.npz", m)


def compute_lat_flow_sum(
    trimmed_inprop: sp.csc_matrix,
    step_number: int = 10,
    output_threshold: float = 1e-6,
    chunk_size: int = 5000,
) -> sp.csc_matrix:
    """Return `A + A^2 + ... + A^step_number` for `A = trimmed_inprop`.

    Wraps `compress_paths(save_to_disk=False)` and `add_first_n_matrices`, using
    a GPU if available. Keep `chunk_size * n_cols < 2**31` (the limit of
    `torch.nonzero`); on 8 A100 GPUs the full run takes about 15 minutes.
    """
    from connectome_interpreter import add_first_n_matrices, compress_paths

    steps = compress_paths(
        trimmed_inprop,
        step_number=step_number,
        output_threshold=output_threshold,
        chunkSize=chunk_size,
        save_to_disk=False,
        return_results=True,
    )
    return sp.csc_matrix(add_first_n_matrices(steps, len(steps)))


def save_lat_flow_sum(summed: sp.csc_matrix, data_dir: Path, save_prefix: str) -> None:
    """Write `{save_prefix}sum.npz`."""
    sp.save_npz(Path(data_dir) / f"{save_prefix}sum.npz", sp.csc_matrix(summed))
