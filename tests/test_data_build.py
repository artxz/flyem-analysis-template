"""Checks for the data build (`data.build`, `data.flywire`, `data.flow`).

neuPrint and connectome_interpreter are replaced by small fakes, so these tests
need no network, token or hours of compute.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from flyem_analysis_starter import config
from flyem_analysis_starter.data import build, flow, flywire, load, malecns, publish

FW = config.FLYWIRE_DATASET

# A 4-neuron FlyWire-like dataset: body IDs, edges and neuPrint properties.
_EDGES = pd.DataFrame(
    {
        "bodyId_pre": [30, 10, 10, 20, 40],
        "bodyId_post": [10, 20, 30, 30, 20],
        "weight": np.array([5, 3, 2, 7, 1], dtype=np.int32),
    }
)
_NEURONS = pd.DataFrame(
    {
        "bodyId": [10, 20, 30, 40],
        "cell_type": ["L1", "Mi1", "Tm1 (a)", "Dm3_indeterminate"],
        "nt": ["glutamate", "acetylcholine", "acetylcholine", "gaba"],
        "superclass": ["optic"] * 4,
        "subclass": [None] * 4,
        "class": [None] * 4,
        "dimorphism": [None] * 4,
        "side": ["left", "left", "center", "na"],
    }
)


def _writer(names: list[str], content: str = "x") -> Any:
    """Return a step `run` function that writes `names` into the temporary folder."""

    def run(tmp: Path, folder: Path) -> None:
        """Write each file with the given content."""
        for n in names:
            (tmp / n).write_text(content)

    return run


def test_run_step_records_and_skips(tmp_path, capsys):
    step = build.Step("a", outputs=("t_a.csv",), inputs=(), run=_writer(["t_a.csv"]))
    manifest = build.read_manifest(tmp_path, "t")
    assert build.run_step(step, tmp_path, manifest, force=False)
    entry = build.read_manifest(tmp_path, "t")["steps"]["a"]
    assert set(entry) == {"outputs", "inputs", "source", "finished", "seconds"}
    assert entry["outputs"]["t_a.csv"] == build._sha256(tmp_path / "t_a.csv")
    assert not list(tmp_path.glob(".tmp-*"))

    assert not build.run_step(step, tmp_path, manifest, force=False)
    assert "up to date" in capsys.readouterr().out
    assert build.run_step(step, tmp_path, manifest, force=True)

    (tmp_path / "t_a.csv").write_text("edited")  # output changed: rebuild
    assert build.run_step(step, tmp_path, manifest, force=False)


def test_run_step_reruns_when_input_changes(tmp_path):
    first = build.Step("a", ("t_a.csv",), (), _writer(["t_a.csv"]))
    second = build.Step("b", ("t_b.csv",), ("t_a.csv",), _writer(["t_b.csv"]))
    manifest = build.read_manifest(tmp_path, "t")
    build.run_step(first, tmp_path, manifest, force=False)
    build.run_step(second, tmp_path, manifest, force=False)
    assert not build.run_step(second, tmp_path, manifest, force=False)
    first_v2 = build.Step("a", ("t_a.csv",), (), _writer(["t_a.csv"], "new"))
    build.run_step(first_v2, tmp_path, manifest, force=True)
    assert build.run_step(second, tmp_path, manifest, force=False)


def test_failed_step_leaves_old_files_and_no_record(tmp_path):
    good = build.Step("a", ("t_a.csv",), (), _writer(["t_a.csv"], "old"))
    manifest = build.read_manifest(tmp_path, "t")
    build.run_step(good, tmp_path, manifest, force=False)

    def crash(tmp: Path, folder: Path) -> None:
        """Write a partial output, then fail."""
        (tmp / "t_a.csv").write_text("partial")
        raise RuntimeError("neuPrint went away")

    with pytest.raises(RuntimeError):
        build.run_step(
            build.Step("a", ("t_a.csv",), (), crash), tmp_path, manifest, True
        )
    assert (tmp_path / "t_a.csv").read_text() == "old"
    assert "a" not in build.read_manifest(tmp_path, "t")["steps"]
    assert not list(tmp_path.glob(".tmp-*"))

    incomplete = build.Step("a", ("t_a.csv", "t_b.csv"), (), _writer(["t_a.csv"]))
    with pytest.raises(FileNotFoundError, match="did not write"):
        build.run_step(incomplete, tmp_path, manifest, force=False)

    needs = build.Step("c", ("t_c.csv",), ("t_missing.csv",), _writer(["t_c.csv"]))
    with pytest.raises(FileNotFoundError, match="run the earlier steps"):
        build.run_step(needs, tmp_path, manifest, force=False)


def test_manifest_refuses_other_dataset(tmp_path):
    step = build.Step("a", ("t_a.csv",), (), _writer(["t_a.csv"]))
    build.run_step(step, tmp_path, build.read_manifest(tmp_path, "t"), force=False)
    with pytest.raises(ValueError, match="belongs to 't'"):
        build.read_manifest(tmp_path, "other")


def test_flywire_finalize_meta():
    nodes = sorted(_NEURONS.bodyId)
    meta = flywire.finalize_meta(_NEURONS.iloc[::-1], nodes)
    assert list(meta.columns) == flywire.META_COLUMNS
    assert meta.bodyId.tolist() == nodes
    assert meta.idx.tolist() == [0, 1, 2, 3]
    assert meta.instance.tolist() == ["L1_L", "Mi1_L", "Tm1_0", "Dm3_0"]
    assert meta.cell_type.tolist() == ["L1", "Mi1", "Tm1", "Dm3"]
    assert meta.side.tolist() == ["left", "left", "noside", "noside"]
    assert meta.sign.tolist() == [-1, 1, 1, -1]
    assert meta.coords.isna().all()


class _FakeClient:
    """Stands in for `neuprint.Client`, answering metadata queries from a table."""

    def __init__(self, neurons: pd.DataFrame) -> None:
        """Keep the table and count the queries."""
        self.neurons = neurons
        self.queries = 0

    def fetch_custom(self, cql: str) -> pd.DataFrame:
        """Return the rows whose body IDs appear in the query's ID list."""
        self.queries += 1
        ids = [int(x) for x in cql.split("[", 1)[1].split("]", 1)[0].split(",")]
        return self.neurons[self.neurons.bodyId.isin(ids)].reset_index(drop=True)


def test_fetch_neuron_table_batches_and_keeps_order():
    client = _FakeClient(_NEURONS)
    out = malecns.fetch_neuron_table(
        [40, 10, 99, 30, 20], client, "n.type as cell_type", batch_size=2
    )
    assert client.queries == 3
    assert out.bodyId.tolist() == [40, 10, 99, 30, 20]
    assert out.loc[out.bodyId == 99, "cell_type"].isna().all()


def test_fetch_typed_edges_chunks_drop_rois_and_sums(monkeypatch):
    # Per-ROI rows as fetch_adjacencies returns them, for presynaptic 1, 2, 3.
    rows = pd.DataFrame(
        [
            (1, 2, "ME(R)", 3), (1, 2, "LA(R)", 4), (1, 2, "NotPrimary", 1),
            (2, 3, "LA(L)", 5),  # lamina only: the pair disappears
            (3, 1, "LO(R)", 2), (3, 1, "ME(R)", 6),
        ],
        columns=["bodyId_pre", "bodyId_post", "roi", "weight"],
    )  # fmt: skip
    calls = []

    def fake_adjacencies(sources, targets, client):
        ids = list(sources.bodyId)
        calls.append(ids)
        return None, rows[rows.bodyId_pre.isin(ids)].reset_index(drop=True)

    class _Client:
        def fetch_custom(self, query):
            return pd.DataFrame({"bodyId": [3, 1, 2]})

    monkeypatch.setattr(malecns, "fetch_adjacencies", fake_adjacencies)
    out = malecns.fetch_typed_edges(_Client(), ["LA(R)", "LA(L)"], chunk_size=2)
    assert calls == [[1, 2], [3]]
    got = {(r.bodyId_pre, r.bodyId_post): r.weight for r in out.itertuples()}
    assert got == {(1, 2): 4, (3, 1): 8}
    assert out["weight"].dtype == np.int32


@pytest.fixture
def fake_neuprint(monkeypatch):
    """Make the FlyWire matrices step read the toy dataset instead of neuPrint."""
    from flyem_analysis_starter import neuprint_client

    client = _FakeClient(_NEURONS)
    monkeypatch.setattr(neuprint_client, "connect", lambda **kw: client)
    monkeypatch.setattr(flywire, "fetch_connectivity", lambda c: _EDGES.copy())
    return client


def test_flywire_matrices_step_end_to_end(fake_neuprint, tmp_path):
    out = tmp_path / "build"
    build.main(["--dataset", FW, "--steps", "matrices", "--out-dir", str(out)])
    meta = load.load_meta(FW, out)
    prop = load.load_prop(FW, out)
    assert meta.bodyId.tolist() == [10, 20, 30, 40]
    assert prop.shape == (4, 4)
    assert prop[2, 0] == 5 and prop[1, 2] == 7  # 30->10 and 20->30
    assert not (out / f"{FW}_inprop.npz").exists()  # derived, never hosted

    # Unchanged files: the step is skipped and a comparison with itself is clean.
    build.main(["--dataset", FW, "--steps", "matrices", "--out-dir", str(out)])
    assert build.compare(FW, out, out) == []

    files = publish._dataset_files(FW, out)
    assert [f.name for f in files] == list(build.matrix_files(FW))
    assert publish._build_source(out, files).startswith("flyem")


def test_compare_reports_differences(fake_neuprint, tmp_path):
    out = tmp_path / "build"
    build.main(["--dataset", FW, "--steps", "matrices", "--out-dir", str(out)])
    ref = tmp_path / "ref"
    ref.mkdir()
    meta = load.load_meta(FW, out)
    meta.loc[1, "nt"] = "gaba"
    meta.to_csv(ref / f"{FW}_meta.csv", index=False)
    prop = load.load_prop(FW, out).tolil()
    prop[0, 1] = 99
    sp.save_npz(ref / f"{FW}_prop.npz", sp.csc_matrix(prop))

    diffs = build.compare(FW, out, ref)
    assert any("column 'nt' differs in 1 rows" in d for d in diffs)
    assert any("prop: 1 entries differ" in d for d in diffs)
    with pytest.raises(SystemExit):
        build.main(
            ["--dataset", FW, "--compare-only", "--out-dir", str(out),
             "--reference", str(ref)]
        )  # fmt: skip


def test_flow_step_with_fake_connectome_interpreter(
    fake_neuprint, tmp_path, monkeypatch
):
    calls: dict[str, Any] = {}

    def find_instance_flow(inprop, idx_to_instance, flow_seed_groups, file_path,
                           save_prefix, flow_steps, flow_thre):  # fmt: skip
        """Record the call and write both tables with upstream's column name."""
        calls.update(seeds=flow_seed_groups, n=inprop.shape[0], prefix=save_prefix)
        per_neuron, per_group = flow.flow_file_names(save_prefix, flow_steps, flow_thre)
        names = list(idx_to_instance.values())
        pd.DataFrame(
            {"idx": list(idx_to_instance), "hitting_time": 1.0, "cell_group": names}
        ).to_csv(Path(file_path) / per_neuron, index=False)
        pd.DataFrame({"cell_group": names, "hitting_time": 1.0}).to_csv(
            Path(file_path) / per_group, index=False
        )

    fake = types.ModuleType("connectome_interpreter")
    fake.find_instance_flow = find_instance_flow  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "connectome_interpreter", fake)

    out = tmp_path / "build"
    build.main(["--dataset", FW, "--out-dir", str(out)])  # both steps
    side = config.FLYWIRE_SIDE_CHAR
    assert calls == {
        "seeds": flow.flow_seeds(side),
        "n": 4,
        "prefix": f"{FW}_{side}_flow_",
    }
    table = load.load_flow(FW, side=side, data_dir=out)
    assert list(table.columns) == ["idx", "hitting_time", "instance"]
    assert load.load_flow(FW, side=side, per_group=True, data_dir=out).shape == (4, 2)
    steps = build.read_manifest(out, FW)["steps"]
    assert set(steps["flow"]["inputs"]) == set(build.matrix_files(FW))


def test_publish_refuses_files_changed_after_build(fake_neuprint, tmp_path):
    out = tmp_path / "build"
    build.main(["--dataset", FW, "--steps", "matrices", "--out-dir", str(out)])
    files = publish._dataset_files(FW, out)
    files[0].write_text("hand edit")
    with pytest.raises(ValueError, match="changed since build-data"):
        publish._build_source(out, files)
    extra = out / f"{FW}_extra.csv"
    extra.write_text("x")
    with pytest.raises(ValueError, match="not made by build-data"):
        publish._build_source(out, [extra])
    assert publish._build_source(tmp_path, files) is None  # no manifest there


def test_build_never_writes_into_data_dir():
    with pytest.raises(SystemExit, match="never writes into DATA_DIR"):
        build.main(["--dataset", FW, "--out-dir", str(config.DATA_DIR)])


def test_build_registry_and_file_names():
    assert set(build.FLOW_SIDE) == set(config.DATASETS)
    assert set(build._MATRIX_BUILDERS) == set(config.DATASETS)
    assert config.FLYWIRE_SIDE_CHAR == "l"  # visualpathways' FlyWire flow side
    # The name the existing male CNS flow file has, and load_flow reads.
    assert build.flow_files("malecns_v1.0", "r") == (
        "malecns_v1.0_r_flow_20step_0.1thre_hit.csv",
        "malecns_v1.0_r_flow_20step_0.1thre_hit_per_group.csv",
    )
    assert flow.flow_seeds("l")[0] == "L1_L"
    with pytest.raises(ValueError):
        flow.flow_seeds("x")
