"""Build a dataset's data files from neuPrint (maintainer tool).

Usage, from a clone with a neuPrint token in `.env`:

    pixi run build-data --dataset malecns_v1.0 --steps matrices
    pixi run build-data --dataset malecns_v1.0 --steps flow
    pixi run build-data --dataset malecns_v1.0 --compare-only

Steps, in order:

- `matrices`: the neuron table (`<tag>_meta.csv`) and the synapse-count matrix
  (`<tag>_prop.npz`), queried from neuPrint. Needs a token; takes minutes.
- `flow`: information-flow layers seeded from one eye
  (`<tag>_<side>_flow_20step_0.1thre_hit.csv` and `..._per_group.csv`), computed
  from the matrices. About 3 hours on one core; run it as a cluster job.

Files go to `config.CACHE_DIR / "build" / <tag>`, never to `config.DATA_DIR`, so
the downloaded copies are not overwritten. Each step writes into a temporary
folder, and its files are moved into place only once the step has succeeded.
`build_manifest.json` records, per step, the SHA-256 of its outputs and inputs
and the code version. A step is skipped when that record is complete and every
hash still matches, unless `--force`.

`--compare` (or `--compare-only`) checks the built files against the copies in
`config.DATA_DIR` (or `--reference`). `pixi run publish-data --data-dir <build
folder>` then uploads them. Not part of the stable API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import config
from . import flow, load
from .fetch import _sha256

BUILD_MANIFEST = "build_manifest.json"
STEPS = ("matrices", "flow")

# Eye the flow layers are seeded from, per dataset.
FLOW_SIDE = {
    "malecns_v1.0": config.SIDE_CHAR,
    "flywire-fafb-v783b": config.FLYWIRE_SIDE_CHAR,
}


@dataclass(frozen=True)
class Step:
    """One build step: the files it reads and writes, and how to make them.

    Attributes:
        name: Step name, one of `STEPS`.
        outputs: File names the step must produce.
        inputs: File names (outputs of earlier steps) it reads from the build
            folder. A change to any of them makes the step run again.
        run: Called as `run(tmp_dir, build_dir)`; writes `outputs` into
            `tmp_dir`.
    """

    name: str
    outputs: tuple[str, ...]
    inputs: tuple[str, ...]
    run: Callable[[Path, Path], None]


def build_dir(dataset: str) -> Path:
    """Return the default build folder for a dataset tag."""
    return config.CACHE_DIR / "build" / dataset


def code_version() -> str:
    """Describe the code doing the build, for the build manifest.

    Returns:
        `flyem_analysis_starter.data.build at <commit>` in a clone, with
        ` plus uncommitted changes` if tracked files differ from that commit;
        otherwise the installed package version.
    """
    root = config.PROJECT_ROOT
    if root is not None:
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root, capture_output=True, text=True, check=True,
            ).stdout.strip()  # fmt: skip
            dirty = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=root, capture_output=True, text=True, check=True,
            ).stdout.strip()  # fmt: skip
        except (OSError, subprocess.CalledProcessError):
            pass
        else:
            suffix = " plus uncommitted changes" if dirty else ""
            return f"flyem_analysis_starter.data.build at {commit}{suffix}"
    try:
        return f"flyem-analysis-starter {version('flyem-analysis-starter')}"
    except PackageNotFoundError:
        return "flyem-analysis-starter (unknown version)"


# === Build manifest ===


def read_manifest(folder: Path, dataset: str) -> dict[str, Any]:
    """Read a build folder's manifest, or start an empty one.

    Raises:
        ValueError: The folder holds a build of a different dataset.
    """
    path = folder / BUILD_MANIFEST
    if not path.is_file():
        return {"schema_version": 1, "dataset": dataset, "steps": {}}
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("dataset") != dataset:
        raise ValueError(
            f"{path} belongs to {manifest.get('dataset')!r}, not {dataset!r}"
        )
    return manifest


def _write_manifest(folder: Path, manifest: dict[str, Any]) -> None:
    """Write the manifest via a temporary file, so it is never half-written."""
    part = folder / f"{BUILD_MANIFEST}.part"
    part.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(part, folder / BUILD_MANIFEST)


def _hashes(folder: Path, names: Sequence[str]) -> dict[str, str | None]:
    """Return the SHA-256 of each named file in `folder`, or None if missing."""
    return {n: _sha256(folder / n) if (folder / n).is_file() else None for n in names}


def is_current(step: Step, folder: Path, manifest: dict[str, Any]) -> bool:
    """Say whether a step's recorded outputs and inputs still match the files."""
    entry = manifest["steps"].get(step.name)
    if entry is None:
        return False
    if set(entry.get("outputs", {})) != set(step.outputs):
        return False
    if _hashes(folder, step.outputs) != entry["outputs"]:
        return False
    return bool(_hashes(folder, step.inputs) == entry.get("inputs", {}))


def run_step(step: Step, folder: Path, manifest: dict[str, Any], force: bool) -> bool:
    """Run one step unless it is current, moving its files into `folder` on success.

    Args:
        step: The step to run.
        folder: Build folder (created if missing).
        manifest: Build manifest, updated and saved when the step finishes.
        force: Run even if the step is current.

    Returns:
        True if the step ran, False if it was skipped.

    Raises:
        FileNotFoundError: An input is missing, or the step did not write
            every output.
    """
    folder.mkdir(parents=True, exist_ok=True)
    if not force and is_current(step, folder, manifest):
        print(f"[{step.name}] up to date, skipped (use --force to rebuild)")
        return False
    missing = [n for n in step.inputs if not (folder / n).is_file()]
    if missing:
        raise FileNotFoundError(
            f"[{step.name}] needs {missing} in {folder}; run the earlier steps first"
        )
    inputs = _hashes(folder, step.inputs)

    # Forget the old record first: if the step dies while moving files, the
    # next run sees no record and rebuilds instead of trusting a mixed set.
    manifest["steps"].pop(step.name, None)
    _write_manifest(folder, manifest)

    tmp = folder / f".tmp-{step.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    t0 = time.monotonic()
    try:
        step.run(tmp, folder)
        not_written = [n for n in step.outputs if not (tmp / n).is_file()]
        if not_written:
            raise FileNotFoundError(f"[{step.name}] did not write {not_written}")
        for name in step.outputs:
            os.replace(tmp / name, folder / name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    manifest["steps"][step.name] = {
        "outputs": _hashes(folder, step.outputs),
        "inputs": inputs,
        "source": code_version(),
        "finished": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "seconds": round(time.monotonic() - t0),
    }
    _write_manifest(folder, manifest)
    print(f"[{step.name}] done in {time.monotonic() - t0:.0f} s")
    return True


# === Steps ===


def _check_tables(meta: pd.DataFrame, prop: Any, sorted_nodes: Sequence[int]) -> None:
    """Check that meta rows, matrix indices and body IDs line up."""
    n = len(sorted_nodes)
    if meta["bodyId"].tolist() != list(sorted_nodes):
        raise ValueError("meta rows are not in matrix order")
    if meta["idx"].tolist() != list(range(n)):
        raise ValueError("meta.idx is not 0..n-1")
    if prop.shape != (n, n):
        raise ValueError(f"prop has shape {prop.shape}, expected {(n, n)}")


def _build_malecns_matrices(dataset: str, tmp: Path, folder: Path) -> None:
    """Query the male CNS and write its meta and prop into `tmp`."""
    from .. import neuprint_client
    from . import malecns

    client = neuprint_client.connect(dataset=dataset, verbose=True)
    print("Fetching connectivity ...")
    conn_df = malecns.fetch_connectivity(client)
    fill_r, fill_l = malecns.load_r78_fill()
    conn_df = malecns.merge_r78_fill(conn_df, fill_r, fill_l)
    nodes = malecns.get_sorted_nodes(conn_df)
    print(f"edges: {len(conn_df):,}; neurons: {len(nodes):,}")

    print("Fetching neuron metadata ...")
    meta = malecns.fetch_neuron_metadata(nodes, client)
    meta = malecns.override_r78_metadata(meta, fill_r, fill_l)
    print("Placing optic-lobe neurons on the hex lattice ...")
    meta = malecns.add_column_coords(meta)
    meta = malecns.add_r78_dorsal_l3_coords(meta, client)
    meta = malecns.finalize_meta(meta, nodes)

    prop, _ = malecns.build_sparse_matrices(conn_df, nodes)
    _check_tables(meta, prop, nodes)
    malecns.save_outputs(meta, prop, tmp, dataset)
    print(f"meta: {meta.shape}; prop: {prop.shape}, nnz {prop.nnz:,}")


def _build_flywire_matrices(dataset: str, tmp: Path, folder: Path) -> None:
    """Query FlyWire on neuPrint and write its meta and prop into `tmp`."""
    from .. import neuprint_client
    from . import flywire, malecns

    client = neuprint_client.connect(dataset=dataset, verbose=True)
    print("Fetching connectivity ...")
    conn_df = flywire.fetch_connectivity(client)
    nodes = malecns.get_sorted_nodes(conn_df)
    print(f"edges: {len(conn_df):,}; neurons: {len(nodes):,}")

    print("Fetching neuron metadata ...")
    meta = flywire.fetch_neuron_metadata(nodes, client)
    meta = flywire.finalize_meta(meta, nodes)

    prop, _ = malecns.build_sparse_matrices(conn_df, nodes)
    _check_tables(meta, prop, nodes)
    malecns.save_outputs(meta, prop, tmp, dataset)
    print(f"meta: {meta.shape}; prop: {prop.shape}, nnz {prop.nnz:,}")


_MATRIX_BUILDERS = {
    "malecns_v1.0": _build_malecns_matrices,
    "flywire-fafb-v783b": _build_flywire_matrices,
}


def _build_flow(dataset: str, side: str, tmp: Path, folder: Path) -> None:
    """Compute the flow layers from the built matrices and write them into `tmp`."""
    meta = load.load_meta(dataset, folder)
    inprop = load.load_inprop(dataset, folder)
    print(
        f"Computing flow from the {side!r} eye over {inprop.shape[0]:,} neurons "
        f"({config.N_FLOW} steps, threshold {config.HIT_THRE}, "
        f"method {config.FLOW_METHOD!r}) ..."
    )
    flow.fetch_instance_flow(
        inprop,
        dict(zip(meta["idx"], meta["instance"])),
        flow.flow_seeds(side),
        tmp,
        f"{dataset}_{side}_flow_",
        steps=config.N_FLOW,
        thre=config.HIT_THRE,
        method=config.FLOW_METHOD,
    )


def matrix_files(dataset: str) -> tuple[str, str]:
    """Return the meta and prop file names for a dataset tag."""
    return f"{dataset}_meta.csv", f"{dataset}_prop.npz"


def flow_files(dataset: str, side: str) -> tuple[str, str]:
    """Return the per-neuron and per-instance flow file names."""
    return flow.flow_file_names(
        f"{dataset}_{side}_flow_", config.N_FLOW, config.HIT_THRE
    )


def steps_for(dataset: str) -> dict[str, Step]:
    """Return the build steps for a dataset tag, keyed by name, in order."""
    if dataset not in _MATRIX_BUILDERS:
        raise ValueError(f"No build defined for {dataset!r}")
    side = FLOW_SIDE[dataset]
    matrices = matrix_files(dataset)
    return {
        "matrices": Step(
            "matrices",
            outputs=matrices,
            inputs=(),
            run=functools.partial(_MATRIX_BUILDERS[dataset], dataset),
        ),
        "flow": Step(
            "flow",
            outputs=flow_files(dataset, side),
            inputs=matrices,
            run=functools.partial(_build_flow, dataset, side),
        ),
    }


# === Comparison with the reference (downloaded) files ===


def _compare_frames(
    label: str, built: pd.DataFrame, ref: pd.DataFrame, key: str, atol: float
) -> list[str]:
    """List the differences between two tables that should be identical."""
    diffs = []
    if list(built.columns) != list(ref.columns):
        extra = [c for c in built.columns if c not in ref.columns]
        lost = [c for c in ref.columns if c not in built.columns]
        shared_b = [c for c in built.columns if c in ref.columns]
        shared_r = [c for c in ref.columns if c in built.columns]
        diffs.append(
            f"{label}: columns differ (new {extra}, missing {lost}, "
            f"shared columns in the same order: {shared_b == shared_r})"
        )
    if len(built) != len(ref):
        diffs.append(f"{label}: {len(built):,} rows, reference {len(ref):,}")
    if built[key].tolist() != ref[key].tolist():
        new = len(set(built[key]) - set(ref[key]))
        gone = len(set(ref[key]) - set(built[key]))
        diffs.append(
            f"{label}: {key} values or order differ ({new:,} new, {gone:,} missing)"
        )
        return diffs  # rows do not line up, so per-column checks mean nothing
    for col in [c for c in built.columns if c in ref.columns and c != key]:
        a, b = built[col], ref[col]
        if pd.api.types.is_float_dtype(a) and pd.api.types.is_float_dtype(b):
            close = np.isclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=atol)
        else:
            close = (a.astype(str) == b.astype(str)).to_numpy()
        close |= (a.isna() & b.isna()).to_numpy()
        n_bad = int((~close).sum())
        if n_bad:
            i = int(np.flatnonzero(~close)[0])
            diffs.append(
                f"{label}: column {col!r} differs in {n_bad:,} rows (first: "
                f"{key}={built[key].iloc[i]}, built {a.iloc[i]!r}, "
                f"reference {b.iloc[i]!r})"
            )
    return diffs


def compare(dataset: str, built_dir: Path, ref_dir: Path) -> list[str]:
    """Compare the built files with reference copies and list every difference.

    Checks meta (columns, row order, every value, `coords2` included), prop
    (shape, number of non-zeros, every entry) and, where both folders have
    them, the flow tables (hitting times to within 1e-9).

    Args:
        dataset: Registry tag.
        built_dir: Build folder.
        ref_dir: Folder with the reference copies, usually `config.DATA_DIR`.

    Returns:
        One line per difference; empty when everything matches.
    """
    diffs: list[str] = []
    meta_name, prop_name = matrix_files(dataset)
    for name in (meta_name, prop_name):
        for folder in (built_dir, ref_dir):
            if not (folder / name).is_file():
                diffs.append(f"{name}: missing from {folder}")
    if diffs:
        return diffs

    meta_b = pd.read_csv(built_dir / meta_name, low_memory=False)
    meta_r = pd.read_csv(ref_dir / meta_name, low_memory=False)
    print(f"meta: built {meta_b.shape}, reference {meta_r.shape}")
    diffs += _compare_frames("meta", meta_b, meta_r, "bodyId", atol=0)

    prop_b = load.load_prop(dataset, built_dir)
    prop_r = load.load_prop(dataset, ref_dir)
    print(
        f"prop: built {prop_b.shape} nnz {prop_b.nnz:,}, "
        f"reference {prop_r.shape} nnz {prop_r.nnz:,}"
    )
    if prop_b.shape != prop_r.shape:
        diffs.append(f"prop: shape {prop_b.shape}, reference {prop_r.shape}")
    else:
        if prop_b.nnz != prop_r.nnz:
            diffs.append(f"prop: {prop_b.nnz:,} non-zeros, reference {prop_r.nnz:,}")
        delta = (prop_b.astype(np.int64) - prop_r.astype(np.int64)).tocsc()
        delta.eliminate_zeros()
        if delta.nnz:
            diffs.append(f"prop: {delta.nnz:,} entries differ")

    side = FLOW_SIDE[dataset]
    for name, key in zip(flow_files(dataset, side), ("idx", "instance")):
        b_path, r_path = built_dir / name, ref_dir / name
        if not (b_path.is_file() and r_path.is_file()):
            print(f"{name}: not in both folders, not compared")
            continue
        flow_b, flow_r = pd.read_csv(b_path), pd.read_csv(r_path)
        print(f"{name}: built {flow_b.shape}, reference {flow_r.shape}")
        diffs += _compare_frames(name, flow_b, flow_r, key, atol=1e-9)
    return diffs


# === Command line ===


def main(argv: Sequence[str] | None = None) -> None:
    """Command-line entry point behind `pixi run build-data`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, choices=sorted(_MATRIX_BUILDERS))
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=STEPS,
        default=list(STEPS),
        help="steps to run, in order (default: all)",
    )
    parser.add_argument("--force", action="store_true", help="rerun current steps")
    parser.add_argument(
        "--out-dir", type=Path, default=None, help="default: CACHE_DIR/build/<tag>"
    )
    parser.add_argument(
        "--compare", action="store_true", help="compare with --reference afterwards"
    )
    parser.add_argument(
        "--compare-only", action="store_true", help="compare without building"
    )
    parser.add_argument(
        "--reference", type=Path, default=config.DATA_DIR, help="default: DATA_DIR"
    )
    args = parser.parse_args(argv)

    folder = (args.out_dir or build_dir(args.dataset)).resolve()
    if folder == config.DATA_DIR.resolve():
        sys.exit("build-data never writes into DATA_DIR; choose another --out-dir.")
    print(f"Build folder: {folder}")

    if not args.compare_only:
        from ..neuprint_client import NeuprintConnectionError

        manifest = read_manifest(folder, args.dataset)
        steps = steps_for(args.dataset)
        try:
            for name in STEPS:
                if name in args.steps:
                    run_step(steps[name], folder, manifest, args.force)
        except (NeuprintConnectionError, FileNotFoundError) as exc:
            sys.exit(f"error: {exc}")

    if args.compare or args.compare_only:
        print(f"Comparing with {args.reference} ...")
        diffs = compare(args.dataset, folder, args.reference)
        if diffs:
            print(f"{len(diffs)} difference(s):")
            for line in diffs:
                print(f"  - {line}")
            sys.exit(1)
        print("Built files match the reference.")


if __name__ == "__main__":
    main()
