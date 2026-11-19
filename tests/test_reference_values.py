"""Reference values recorded before the notebooks' outputs were stripped (plan Phase 0).

They pin down what the data and the analysis code produce today, so the Phase 1
restructuring can be checked against them. Where each value comes from:

- ``pathways.ipynb`` output (executed 2026-09-04): meta row count, number of
  right-side input / LC10a neurons, unsigned 1-3 hop effective weights onto LC10a_R.
- ``paper_figs_visual_pathways_layers.ipynb`` output (2026-09-21): ``main_groups``
  counts and the number of right optic-lobe cell types with a flow layer.
- ``paper_figs_optic_lobe.ipynb`` output (2026-09-21): MeTu and LPLC4_R neuron counts
  (neuPrint).
- Measured from ``cache/data`` on 2026-11-19 with the code at that date (no notebook
  printed them): ``prop`` shape / nnz / dtype and the signed effective weights.

The tests deliberately read files directly instead of importing ``src/`` modules, so
they keep working while the package is renamed.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("FLYEM_DATA_DIR", PROJECT_ROOT / "cache" / "data"))
DATASET = "malecns_v1.0"

INPUT_TYPES = ["L1", "L2", "L3", "R8", "R8d", "R7", "R7d", "HBeyelet"]
OUTPUT_TYPE = "LC10a"

# pathways.ipynb, "Barcode plot" section: nr_hops_max=3, direct_thre=0, signed=False,
# grouped by instance with combining_method='mean'. Printed to 6 decimals.
LC10A_EFFECTIVE_WEIGHTS = {
    "L1_R": 0.010196,
    "L2_R": 0.012318,
    "L3_R": 0.016928,
    "R8_R": 0.004849,
    "R8d_R": 0.000036,
    "R7_R": 0.004985,
    "R7d_R": 0.000055,
    "HBeyelet_R": 0.000014,
}

# Same computation with signed=True (signs as in pathways.ipynb); measured 2026-11-19.
# exc + inh equals the unsigned weights above.
LC10A_SIGNED_EXC = {
    "L1_R": 0.00835551065,
    "L2_R": 0.00943708117,
    "L3_R": 0.00964810443,
    "R8_R": 0.00320651563,
    "R8d_R": 2.58698483e-05,
    "R7_R": 0.00310784008,
    "R7d_R": 3.632266e-05,
    "HBeyelet_R": 2.49443914e-06,
}
LC10A_SIGNED_INH = {
    "L1_R": 0.00184079076,
    "L2_R": 0.00288043982,
    "L3_R": 0.00727948474,
    "R8_R": 0.00164297356,
    "R8d_R": 9.97761244e-06,
    "R7_R": 0.00187673875,
    "R7d_R": 1.91340933e-05,
    "HBeyelet_R": 1.16269869e-05,
}

# cache/data/malecns_v1.0_prop.npz, measured 2026-11-19 (integer synapse counts, CSC).
PROP_NNZ = 25_099_814
PROP_DTYPE = np.int32


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"{path.name} not found in {path.parent}; run `pixi run fetch-data`")
    return path


@pytest.fixture(scope="module")
def meta() -> pd.DataFrame:
    path = _require(DATA_DIR / f"{DATASET}_meta.csv")
    return pd.read_csv(path, index_col=0).reset_index()


@pytest.fixture(scope="module")
def prop() -> sp.csc_matrix:
    return sp.load_npz(_require(DATA_DIR / f"{DATASET}_prop.npz"))


@pytest.fixture(scope="module")
def inprop(prop) -> sp.csc_matrix:
    """Input-normalized weights, as in the notebooks (column sums of 1)."""
    total_post = np.asarray(prop.sum(axis=0)).ravel().astype(float)
    inv = np.divide(1.0, total_post, out=np.zeros_like(total_post), where=total_post != 0)
    return prop.multiply(inv).tocsc().astype(np.float32)


@pytest.mark.data
def test_meta_rows(meta):
    assert len(meta) == 162084
    assert meta.idx.is_unique


@pytest.mark.data
def test_prop_matrix(prop, meta):
    assert prop.shape == (162084, 162084)
    assert prop.nnz == PROP_NNZ
    assert prop.dtype == PROP_DTYPE
    assert meta.idx.max() < prop.shape[0]


@pytest.mark.data
def test_inprop_columns_sum_to_one(inprop):
    colsum = np.asarray(inprop.sum(axis=0)).ravel()
    assert np.allclose(colsum[colsum > 0], 1, atol=1e-5)


@pytest.mark.data
def test_main_groups_counts(meta):
    seed_types = ["L1", "L2", "L3", "R7", "R8", "R7d", "R8d", "HBeyelet"]
    group_of_superclass = {
        "ol_intrinsic": "VIN",
        "visual_projection": "VPN",
        "visual_centrifugal": "VCN",
    }
    groups = meta.superclass.map(group_of_superclass).fillna("other")
    groups[meta.cell_type.isin(seed_types)] = "visual input"
    assert groups.value_counts().to_dict() == {
        "VIN": 83985,
        "other": 59756,
        "VPN": 9200,
        "visual input": 8581,
        "VCN": 562,
    }


@pytest.mark.data
def test_flow_layers_right_ol_types(meta):
    path = _require(DATA_DIR / f"{DATASET}_r_flow_20step_0.1thre_hit.csv")
    flow = pd.read_csv(path).rename(columns={"cell_group": "instance"})
    assert len(flow) == 162084
    group_of_superclass = {
        "ol_intrinsic": "VIN",
        "visual_projection": "VPN",
        "visual_centrifugal": "VCN",
    }
    groups = meta.superclass.map(group_of_superclass).fillna("other")
    groups[meta.cell_type.isin(INPUT_TYPES)] = "visual input"
    flow = flow.merge(meta.assign(main_groups=groups)[["idx", "main_groups"]], on="idx")
    ol = flow[
        flow.instance.str.endswith("_R")
        & (flow.main_groups != "other")
        & (flow.instance != "R1-R6_R")
    ]
    assert ol.instance.nunique() == 719


def _effective_weights_onto(meta, inprop, signed: bool) -> tuple[pd.Series, pd.Series]:
    """Sum 1-3 hop effective weights from INPUT_TYPES onto OUTPUT_TYPE (right side)."""
    ci = pytest.importorskip("connectome_interpreter")
    right = meta.side == "right"
    inidx = meta.idx[meta.cell_type.isin(INPUT_TYPES) & right]
    outidx = meta.idx[(meta.cell_type == OUTPUT_TYPE) & right]
    assert len(inidx) == 4317
    assert len(outidx) == 140

    idx_to_instance = dict(zip(meta.idx, meta.instance))
    # signs as in pathways.ipynb: ACh and "other" excitatory, GABA/Glu inhibitory, L1 +1
    sign = meta.nt.map({"glutamate": -1, "gaba": -1}).fillna(1).astype(int)
    sign[meta.cell_type == "L1"] = 1
    idx_to_sign = dict(zip(meta.idx, sign))

    target = f"{OUTPUT_TYPE}_R"
    exc = pd.Series(0.0, index=list(LC10A_EFFECTIVE_WEIGHTS))
    inh = exc.copy()
    for n_hop in range(1, 4):
        paths = ci.find_paths_of_length(inprop, inidx, outidx, n_hop)
        if paths is None or paths.empty:
            continue
        paths = ci.filter_paths(paths, 0.0)
        if paths is None or paths.empty:
            continue
        if signed:
            e, i = ci.signed_effective_conn_from_paths(paths, wide=False, idx_to_nt=idx_to_sign)
        else:
            e = ci.effective_conn_from_paths(paths, wide=False)
            i = e.iloc[:0]
        for frame, acc in ((e, exc), (i, inh)):
            if frame.empty:
                continue
            grouped = ci.group_paths(frame, idx_to_instance, idx_to_instance, combining_method="mean")
            w = grouped[grouped.post == target].set_index("pre").weight
            acc[:] = acc.add(w, fill_value=0).reindex(acc.index, fill_value=0)
    return exc, inh


@pytest.mark.data
def test_lc10a_effective_weights_unsigned(meta, inprop):
    exc, inh = _effective_weights_onto(meta, inprop, signed=False)
    expected = pd.Series(LC10A_EFFECTIVE_WEIGHTS)
    np.testing.assert_allclose(exc[expected.index], expected, rtol=1e-3, atol=1e-6)
    assert (inh == 0).all()


@pytest.mark.data
def test_lc10a_effective_weights_signed(meta, inprop):
    exc, inh = _effective_weights_onto(meta, inprop, signed=True)
    np.testing.assert_allclose(exc, pd.Series(LC10A_SIGNED_EXC), rtol=1e-4, atol=1e-8)
    np.testing.assert_allclose(inh, pd.Series(LC10A_SIGNED_INH), rtol=1e-4, atol=1e-8)


@pytest.mark.neuprint
def test_optic_lobe_gallery_counts():
    neuprint = pytest.importorskip("neuprint")
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    if not os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS"):
        pytest.skip("no neuPrint token (NEUPRINT_APPLICATION_CREDENTIALS)")
    client = neuprint.Client("https://neuprint.janelia.org", dataset="male-cns:v1.0")
    nc = neuprint.NeuronCriteria

    metu_types = ["MeTu1", "MeTu2a", "MeTu2b", "MeTu3a", "MeTu3b", "MeTu3c"]
    metu, _ = neuprint.fetch_neurons(nc(type=metu_types), client=client)
    metu = metu[metu.instance.str.endswith("_R")]
    assert metu.groupby("type").size().to_dict() == {
        "MeTu1": 124,
        "MeTu2a": 36,
        "MeTu2b": 16,
        "MeTu3a": 22,
        "MeTu3b": 38,
        "MeTu3c": 91,
    }

    lplc4, _ = neuprint.fetch_neurons(nc(type="LPLC4"), client=client)
    assert lplc4.instance.str.endswith("_R").sum() == 49
