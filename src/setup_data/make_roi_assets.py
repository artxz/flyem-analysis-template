"""Build the reusable ROI background assets: decimated shell meshes + 2-D outlines.

The `SHELL_SOURCE` precomputed volume (`fullbrain-major-shells`) holds three
segments in the 8 nm-voxel frame -- 1 = central brain, 2 and 3 = the two optic
lobes (there is no VNC segment). Downloaded at full resolution that is
1.53 M vertices / 3.06 M faces, which is why every plot that derives a boundary
from it on the fly is slow: `navis.plot2d(volume_outlines=True)` spends ~630 s
unioning the projected faces, and the `alphashape` route in
`plotter.get_outline_cns()` took ~80 min once.

This script pays that cost once, offline, and writes small files:

* `params/rois/roi_meshes/{region}_shell.npz` -- vertex-clustered mesh, plotted
  directly instead of the 3 M-face original.
* `params/rois/roi_outlines/outline_{region}_{view}_{i}.csv` -- the projected
  silhouette as rings of `x1,y1` points; `i=0` is the exterior and `i>=1` are
  holes (for the central brain in anterior view, the esophageal foramen). The
  one-ring-per-file layout with `x1,y1` columns is upstream visualpathways'
  format (`params/outline_cb_1.csv`, `outline_cb_2.csv`), so these files drop
  into `utils.projection_plots.plot_neuron_with_outlines()` and friends as an
  `outlines_bkgd` list, as well as into this repo's plotters.
* `params/rois/roi_assets_manifest.json` -- provenance for both of the above.
* `cache/cns_shell_cv/cns_shell.pickle` -- the full-resolution fused shell in
  the layout `plotter.get_shell_cns()` expects, so neither repo re-downloads it.

Outlines are silhouettes of the mesh itself (union of the projected triangles),
not alpha shapes of a point cloud: no alpha parameter to tune, and holes come
out as real polygon interiors. A hole is therefore the region where no tissue
lies at *any* depth, so the foramen ring is tighter than upstream's t-bar alpha
shape -- concentric with it, about a third of the area.

Usage:
    python src/setup_data/make_roi_assets.py
    python src/setup_data/make_roi_assets.py --regions cb --views xy --force
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import shapely
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
PROJECT_ROOT = Path(find_dotenv()).parent
ROI_DIR = PROJECT_ROOT / "params" / "rois"
MESH_DIR = ROI_DIR / "roi_meshes"
OUTLINE_DIR = ROI_DIR / "roi_outlines"
MANIFEST_FN = ROI_DIR / "roi_assets_manifest.json"
RAW_CACHE_DIR = PROJECT_ROOT / "cache" / "roi_meshes_raw"
SHELL_CACHE_FN = PROJECT_ROOT / "cache" / "cns_shell_cv" / "cns_shell.pickle"

# Segment ids in SHELL_SOURCE that make up each named region. `brain` is
# everything the source has; `cb` is the central brain alone, matching the
# extent of upstream's outline_cb_*.csv.
REGIONS: dict[str, tuple[int, ...]] = {
    "brain": (1, 2, 3),
    "cb": (1,),
}

# Projection planes, as the pair of vertex columns that become (x1, y1).
# `xy` is the anterior view used by `plot_2d_cns` / `plot_3d_cns`. Signs are not
# baked in: a '-y' view is an inverted matplotlib axis, not negated data.
VIEWS: dict[str, tuple[int, int]] = {
    "xy": (0, 1),
    "xz": (0, 2),
    "zy": (2, 1),
}

# All lengths below are in 8 nm voxels, the frame the plotters work in.
DEFAULT_MESH_GRID = 300.0  # vertex-clustering cell for the saved 3-D mesh
DEFAULT_OUTLINE_GRID = 400.0  # coarser: only the silhouette survives projection
DEFAULT_SIMPLIFY = 40.0  # Douglas-Peucker tolerance on the rings
DEFAULT_MIN_HOLE_AREA = 1e6  # drop pinholes left by decimation (foramen ~1.2e7)
DEFAULT_MIN_PART_AREA = 1e7  # drop detached specks of the projection

VOXEL_NM = 8


def fetch_shell(seg_ids: Sequence[int], *, force: bool = False):
    """Download the fused shell mesh for `seg_ids`, in voxels, with a disk cache.

    Args:
        seg_ids: segment ids in the `SHELL_SOURCE` precomputed volume.
        force: re-download even when the cache file exists.

    Returns:
        The CloudVolume mesh, vertices already converted from nm to 8 nm voxels.
    """
    import cloudvolume as cv  # slow import; only needed on a cold cache

    assert os.environ.get("SHELL_SOURCE"), (
        "Please set the `SHELL_SOURCE` variable in your environment."
    )
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fn = RAW_CACHE_DIR / f"shell_{'-'.join(str(s) for s in seg_ids)}.pickle"
    if fn.is_file() and not force:
        with fn.open("rb") as fh:
            return pickle.load(fh)
    vol = cv.CloudVolume(
        f"precomputed://{os.environ['SHELL_SOURCE']}", use_https=True, progress=False
    )
    mesh = vol.mesh.get(list(seg_ids))
    mesh.vertices = mesh.vertices / VOXEL_NM
    with fn.open("wb") as fh:
        pickle.dump(mesh, fh)
    return mesh


def cluster_decimate(
    verts: np.ndarray, faces: np.ndarray, grid: float
) -> tuple[np.ndarray, np.ndarray]:
    """Decimate a mesh by welding every vertex inside the same `grid`-sized cell.

    Vertex clustering rather than quadric decimation, because it needs nothing
    beyond numpy and the shell is a smooth blob where cluster artifacts do not
    show. Face winding is preserved; degenerate and duplicated faces are dropped.

    Args:
        verts: (n, 3) vertex coordinates.
        faces: (m, 3) triangle vertex indices.
        grid: cell size, same units as `verts`.

    Returns:
        The decimated `(vertices, faces)` pair.
    """
    keys = np.floor(np.asarray(verts, dtype=np.float64) / grid).astype(np.int64)
    _, inv, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    new_verts = (
        np.column_stack(
            [
                np.bincount(inv, weights=verts[:, d], minlength=counts.size)
                for d in range(3)
            ]
        )
        / counts[:, None]
    )

    new_faces = inv[np.asarray(faces)]
    keep = (
        (new_faces[:, 0] != new_faces[:, 1])
        & (new_faces[:, 1] != new_faces[:, 2])
        & (new_faces[:, 0] != new_faces[:, 2])
    )
    new_faces = new_faces[keep]
    # De-duplicate on the unordered vertex triple, but keep the original winding.
    _, first = np.unique(np.sort(new_faces, axis=1), axis=0, return_index=True)
    return new_verts, new_faces[np.sort(first)]


def project_silhouette(
    verts: np.ndarray, faces: np.ndarray, axes: tuple[int, int]
) -> shapely.Geometry:
    """Union the mesh triangles projected onto `axes` into a silhouette polygon."""
    tri = np.asarray(verts)[np.asarray(faces)][:, :, axes]
    return shapely.union_all(shapely.polygons(np.concatenate([tri, tri[:, :1]], 1)))


def polygon_rings(
    poly: shapely.Geometry,
    *,
    simplify_tol: float = DEFAULT_SIMPLIFY,
    min_hole_area: float = DEFAULT_MIN_HOLE_AREA,
    min_part_area: float = DEFAULT_MIN_PART_AREA,
) -> list[np.ndarray]:
    """Turn a silhouette polygon into a list of rings, exterior first.

    Args:
        poly: polygon or multipolygon from `project_silhouette`.
        simplify_tol: Douglas-Peucker tolerance, in voxels.
        min_hole_area: interiors smaller than this are decimation pinholes.
        min_part_area: disconnected parts smaller than this are dropped.

    Returns:
        Closed rings as (n, 2) arrays: every part's exterior, then its kept holes.
    """
    parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    parts = sorted((p for p in parts if p.area >= min_part_area), key=lambda p: -p.area)
    rings: list[np.ndarray] = []
    for part in parts:
        simple = shapely.simplify(part, simplify_tol)
        rings.append(np.asarray(simple.exterior.coords))
        holes = sorted(
            (h for h in simple.interiors if shapely.Polygon(h).area >= min_hole_area),
            key=lambda h: -shapely.Polygon(h).area,
        )
        rings.extend(np.asarray(h.coords) for h in holes)
    return rings


def write_outline_csvs(
    rings: Iterable[np.ndarray], region: str, view: str, *, out_dir: Path = OUTLINE_DIR
) -> list[Path]:
    """Write one `x1,y1` CSV per ring, numbered from 0 (the exterior)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, ring in enumerate(rings):
        fn = out_dir / f"outline_{region}_{view}_{i}.csv"
        pd.DataFrame(np.round(ring).astype(int), columns=["x1", "y1"]).to_csv(
            fn, index=False
        )
        written.append(fn)
    return written


def write_mesh_npz(
    verts: np.ndarray,
    faces: np.ndarray,
    region: str,
    *,
    out_dir: Path = MESH_DIR,
    **meta: object,
) -> Path:
    """Write a decimated mesh as a compressed npz of `vertices` and `faces`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{region}_shell.npz"
    np.savez_compressed(
        fn,
        vertices=np.asarray(verts, dtype=np.float32),
        faces=np.asarray(faces, dtype=np.int32),
        meta=json.dumps(meta),
    )
    return fn


def build_region(
    region: str,
    views: Sequence[str],
    *,
    mesh_grid: float = DEFAULT_MESH_GRID,
    outline_grid: float = DEFAULT_OUTLINE_GRID,
    simplify_tol: float = DEFAULT_SIMPLIFY,
    force: bool = False,
) -> dict[str, object]:
    """Build and write the mesh and per-view outlines for one region.

    Args:
        region: key of `REGIONS`.
        views: keys of `VIEWS` to project onto.
        mesh_grid: clustering cell for the saved 3-D mesh, in voxels.
        outline_grid: clustering cell used before projecting, in voxels.
        simplify_tol: Douglas-Peucker tolerance on the rings, in voxels.
        force: re-download the raw shell instead of using the cache.

    Returns:
        The manifest entry describing what was written.
    """
    seg_ids = REGIONS[region]
    mesh = fetch_shell(seg_ids, force=force)
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    print(f"[{region}] segments {seg_ids}: {len(verts)} verts / {len(faces)} faces")

    mesh_v, mesh_f = cluster_decimate(verts, faces, mesh_grid)
    mesh_fn = write_mesh_npz(
        mesh_v,
        mesh_f,
        region,
        segments=list(seg_ids),
        grid_voxels=mesh_grid,
        units="8 nm voxels",
    )
    size_mb = mesh_fn.stat().st_size / 1e6
    print(
        f"[{region}] mesh grid={mesh_grid:g} -> {len(mesh_v)} verts /"
        f" {len(mesh_f)} faces, {size_mb:.1f} MB -> {mesh_fn.name}"
    )

    out_v, out_f = cluster_decimate(verts, faces, outline_grid)
    outlines: dict[str, list[str]] = {}
    for view in views:
        rings = polygon_rings(
            project_silhouette(out_v, out_f, VIEWS[view]), simplify_tol=simplify_tol
        )
        files = write_outline_csvs(rings, region, view)
        outlines[view] = [fn.name for fn in files]
        sizes = ", ".join(f"{len(r)} pts" for r in rings)
        print(f"[{region}] outline {view}: {len(rings)} ring(s) ({sizes})")

    return {
        "segments": list(seg_ids),
        "n_vertices_full": int(len(verts)),
        "n_faces_full": int(len(faces)),
        "mesh": {
            "file": mesh_fn.name,
            "grid_voxels": mesh_grid,
            "n_vertices": int(len(mesh_v)),
            "n_faces": int(len(mesh_f)),
        },
        "outlines": {
            "grid_voxels": outline_grid,
            "simplify_voxels": simplify_tol,
            "files": outlines,
        },
    }


def warm_shell_cache(*, force: bool = False) -> Path | None:
    """Copy the full-resolution fused shell into the path `get_shell_cns()` reads."""
    if SHELL_CACHE_FN.is_file() and not force:
        return None
    mesh = fetch_shell(REGIONS["brain"])
    SHELL_CACHE_FN.parent.mkdir(parents=True, exist_ok=True)
    with SHELL_CACHE_FN.open("wb") as fh:
        pickle.dump(mesh, fh)
    return SHELL_CACHE_FN


def main() -> None:
    """Build every requested region's assets and refresh the manifest."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--regions", nargs="+", default=list(REGIONS), choices=list(REGIONS)
    )
    parser.add_argument("--views", nargs="+", default=list(VIEWS), choices=list(VIEWS))
    parser.add_argument("--mesh-grid", type=float, default=DEFAULT_MESH_GRID)
    parser.add_argument("--outline-grid", type=float, default=DEFAULT_OUTLINE_GRID)
    parser.add_argument("--simplify", type=float, default=DEFAULT_SIMPLIFY)
    parser.add_argument(
        "--force", action="store_true", help="re-download the raw shell meshes"
    )
    parser.add_argument(
        "--skip-shell-cache",
        action="store_true",
        help="do not write cache/cns_shell_cv/cns_shell.pickle",
    )
    args = parser.parse_args()

    # Merge into any existing manifest so a partial rebuild (one region, one
    # view) does not drop the entries it did not touch.
    previous = json.loads(MANIFEST_FN.read_text()) if MANIFEST_FN.is_file() else {}
    manifest = {
        "generated": date.today().isoformat(),
        "source": os.environ.get("SHELL_SOURCE", "$SHELL_SOURCE"),
        "units": f"{VOXEL_NM} nm voxels",
        "script": "src/setup_data/make_roi_assets.py",
        "regions": previous.get("regions", {}),
    }
    for region in args.regions:
        entry = build_region(
            region,
            args.views,
            mesh_grid=args.mesh_grid,
            outline_grid=args.outline_grid,
            simplify_tol=args.simplify,
            force=args.force,
        )
        kept = manifest["regions"].get(region, {}).get("outlines", {}).get("files", {})
        entry["outlines"]["files"] = {**kept, **entry["outlines"]["files"]}
        manifest["regions"][region] = entry

    if not args.skip_shell_cache:
        written = warm_shell_cache(force=args.force)
        print(f"shell cache: {written if written else 'already present'}")

    MANIFEST_FN.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest -> {MANIFEST_FN}")


if __name__ == "__main__":
    main()
