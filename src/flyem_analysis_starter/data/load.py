"""Load the prebuilt neuron tables and connectivity matrices.

Every loader reads from `config.DATA_DIR` unless given `data_dir=`. File names
start with the dataset tag from `config.DATASETS`, e.g. `malecns_v1.0_meta.csv`.

- `meta`: one row per neuron. Row `idx` is that neuron's row and column in the
  matrices.
- `prop`: raw synapse counts, presynaptic neurons in rows, postsynaptic in
  columns (int32, CSC).
- `inprop`: `prop` with each column divided by its sum, i.e. the fraction of a
  neuron's input that comes from each partner (float32, CSC).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from .. import config

__all__ = ["data_file", "load_meta", "load_prop", "load_inprop", "load_flow"]


def data_file(name: str, data_dir: Path | str | None = None) -> Path:
    """Return the path of a downloaded data file, raising if it is missing.

    Args:
        name: File name, e.g. `malecns_v1.0_meta.csv`.
        data_dir: Folder to look in. Defaults to `config.DATA_DIR`.

    Returns:
        Path to the existing file.

    Raises:
        FileNotFoundError: The file is not there; the message says how to get it.
    """
    folder = Path(data_dir) if data_dir is not None else config.DATA_DIR
    path = folder / name
    if not path.is_file():
        raise FileNotFoundError(
            f"{name} not found in {folder}. Download the data with "
            "`pixi run fetch-data` in the project folder, or "
            "`flyem_analysis_starter.data.fetch_data()` from Python."
        )
    return path


def load_meta(
    dataset: str = config.DEFAULT_DATASET, data_dir: Path | str | None = None
) -> pd.DataFrame:
    """Load the neuron table for a dataset.

    Args:
        dataset: Registry tag, e.g. `malecns_v1.0`.
        data_dir: Folder holding the data. Defaults to `config.DATA_DIR`.

    Returns:
        One row per neuron, with `bodyId`, `instance`, `cell_type`, `nt`,
        `sign`, `side`, `idx` and, for optic-lobe neurons, `coords`/`coords2`.
    """
    return pd.read_csv(data_file(f"{dataset}_meta.csv", data_dir))


def load_prop(
    dataset: str = config.DEFAULT_DATASET, data_dir: Path | str | None = None
) -> sp.csc_matrix:
    """Load the synapse-count matrix (presynaptic rows, postsynaptic columns).

    Args:
        dataset: Registry tag, e.g. `malecns_v1.0`.
        data_dir: Folder holding the data. Defaults to `config.DATA_DIR`.

    Returns:
        Square CSC matrix of synapse counts, indexed by `meta.idx`.
    """
    return sp.csc_matrix(sp.load_npz(data_file(f"{dataset}_prop.npz", data_dir)))


def _inprop_from_prop(prop: sp.spmatrix) -> sp.csc_matrix:
    """Divide each column of `prop` by its sum, giving float32 input fractions.

    Each entry is divided in float64 and then rounded to float32, exactly as
    `data.malecns.build_sparse_matrices` does, so the two give identical
    matrices. Columns that sum to zero (neurons with no input) stay zero.
    """
    prop = sp.csc_matrix(prop)
    prop.sum_duplicates()
    colsum = np.asarray(prop.sum(axis=0), dtype=np.float64).ravel()
    col_of_entry = np.repeat(np.arange(prop.shape[1]), np.diff(prop.indptr))
    denom = colsum[col_of_entry]
    values = np.divide(
        prop.data.astype(np.float64),
        denom,
        out=np.zeros(len(denom), dtype=np.float64),
        where=denom > 0,
    )
    inprop = sp.csc_matrix(
        (values.astype(np.float32), prop.indices.copy(), prop.indptr.copy()),
        shape=prop.shape,
    )
    check = np.asarray(inprop.sum(axis=0)).ravel()[colsum > 0]
    if not np.allclose(check, 1, atol=1e-5):
        raise ValueError("inprop columns do not sum to 1; is prop corrupted?")
    return inprop


def load_inprop(
    dataset: str = config.DEFAULT_DATASET, data_dir: Path | str | None = None
) -> sp.csc_matrix:
    """Load the input-fraction matrix, derived from `prop` on the fly.

    Entry `[i, j]` is the fraction of neuron `j`'s input synapses that come from
    neuron `i`, so every non-empty column sums to 1.

    Args:
        dataset: Registry tag, e.g. `malecns_v1.0`.
        data_dir: Folder holding the data. Defaults to `config.DATA_DIR`.

    Returns:
        Square float32 CSC matrix, indexed by `meta.idx`.
    """
    return _inprop_from_prop(load_prop(dataset, data_dir))


def load_flow(
    dataset: str = config.DEFAULT_DATASET,
    side: str = config.SIDE_CHAR,
    per_group: bool = False,
    data_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Load the information-flow layers (hitting times) seeded from one eye.

    Built with `connectome_interpreter.find_instance_flow` using
    `config.N_FLOW` steps and threshold `config.HIT_THRE`.

    Args:
        dataset: Registry tag, e.g. `malecns_v1.0`.
        side: Eye the flow was seeded from, `"r"` or `"l"`.
        per_group: Load the per-instance medians instead of per-neuron values.
        data_dir: Folder holding the data. Defaults to `config.DATA_DIR`.

    Returns:
        The table as written by `find_instance_flow` (columns include `idx` and
        `hitting_time` per neuron, or the instance per group).
    """
    suffix = "_per_group" if per_group else ""
    name = (
        f"{dataset}_{side}_flow_{config.N_FLOW}step_{config.HIT_THRE}thre_hit"
        f"{suffix}.csv"
    )
    return pd.read_csv(data_file(name, data_dir))
