"""Download and assemble the FlyWire (FAFB v783) neuron table and matrices.

The FlyWire counterpart of `data.malecns`, reading FlyWire's copy on neuPrint
(`flywire-fafb:v783b` on neuprint-cns.janelia.org; the male CNS token works
there too). Called by `data.build`. Compared with the male CNS build there is
no R7/R8 fill-in (that patches a male-CNS reconstruction gap) and no hex
coordinates (no FlyWire eyemap).

Dataset differences handled here (probed 2026-08-15):

- `instance` is empty on the server, so it is made from `cell_type` and side.
- The neurotransmitter prediction is `predictedNt` (no histamine class).
- `side` is a neuron property: `left`, `right`, `center` or `na`.
- The lamina regions of interest (ROIs) are `LA_L` / `LA_R`.
- Edge weights are not thresholded (minimum 1, like the male CNS, unlike the
  Codex export with at least 5 synapses).

Adapted from reiserlab/visualpathways, `src/setup_data/s1_flywirefafb_data.py`.
Not part of the stable API.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pandas as pd

from .malecns import NT_SIGN, SIDE_WORD, fetch_neuron_table, fetch_typed_edges

if TYPE_CHECKING:
    from neuprint import Client

META_COLUMNS = [
    "bodyId", "instance", "cell_type", "nt", "superclass", "subclass",
    "class", "dimorphism", "coords", "sign", "side", "idx",
]  # fmt: skip


def fetch_connectivity(client: Client) -> pd.DataFrame:
    """Download all typed-to-typed neuron adjacencies as a flat edge list.

    Lamina synapses (`LA_L`, `LA_R`) are dropped, as in the male CNS build, and
    the remaining per-ROI weights are summed per neuron pair (see
    `malecns.fetch_typed_edges`).

    Args:
        client: neuPrint client connected to the FlyWire dataset.

    Returns:
        Columns `bodyId_pre`, `bodyId_post`, `weight` (int32).
    """
    return fetch_typed_edges(client, ["LA_L", "LA_R"])


def fetch_neuron_metadata(body_ids: Sequence[int], client: Client) -> pd.DataFrame:
    """Fetch type, neurotransmitter, classes and side for each body ID.

    Args:
        body_ids: Neurons to look up, in the order the result should have.
        client: neuPrint client connected to the FlyWire dataset.

    Returns:
        One row per body ID with `cell_type`, `nt`, `superclass`, `subclass`,
        `class`, `dimorphism` and `side` (missing values where neuPrint has none).
    """
    return fetch_neuron_table(
        body_ids,
        client,
        "n.type as cell_type, n.predictedNt as nt, n.superclass as superclass, "
        "n.subclass as subclass, n.class as class, n.dimorphism as dimorphism, "
        "n.side as side",
    )


def finalize_meta(meta: pd.DataFrame, sorted_nodes: Sequence[int]) -> pd.DataFrame:
    """Add `sign`, `instance`, an empty `coords` and `idx`, and sort by `idx`.

    `side` values other than left/right become `noside`; `instance` is
    `cell_type` plus `_L`, `_R` or `_0`; `(...)` and `_indeterminate` are
    stripped from `instance` and `cell_type`, as in `malecns.finalize_meta`.

    Args:
        meta: Output of `fetch_neuron_metadata`.
        sorted_nodes: Body IDs in matrix order.

    Returns:
        The neuron table with the columns in `META_COLUMNS`.
    """
    out = meta.copy()
    out["sign"] = out["nt"].map(NT_SIGN)
    out["side"] = out["side"].where(out["side"].isin(["left", "right"]), "noside")
    out["instance"] = out["cell_type"] + "_" + out["side"].map(SIDE_WORD)
    for col in ("instance", "cell_type"):
        out[col] = (
            out[col]
            .str.replace(r"\s*\(.*?\)", "", regex=True)
            .str.replace(r"_indeterminate", "", regex=True)
        )
    out["coords"] = pd.NA
    nodes_to_idx = {n: i for i, n in enumerate(sorted_nodes)}
    out["idx"] = out["bodyId"].map(nodes_to_idx)
    out = out.sort_values("idx").reset_index(drop=True)
    return out[META_COLUMNS]
