"""Read the pre-built ROI background assets written by `plotting.make_roi_assets`.

Loaders only -- nothing here touches the network or recomputes geometry, so a
plot that draws the brain boundary costs milliseconds instead of the ~630 s
`navis.plot2d(volume_outlines=True)` spends unioning the 3 M-face shell.

Regions are `brain` (central brain + both optic lobes) and `cb` (central brain
only); views are `xy` (anterior), `xz` (dorsal) and `zy` (lateral). Everything
is in the 8 nm-voxel frame the plotters use. The files ship inside the package
(`params/rois`); maintainers regenerate them with
`python -m flyem_analysis_starter.plotting.make_roi_assets`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    import navis
from ..config import params_path

__all__ = [
    "REGIONS",
    "VIEWS",
    "get_manifest",
    "get_mesh",
    "get_outline",
    "get_outline_rings",
    "get_volume",
    "view_key",
]

ROI_DIR = params_path("rois")
MESH_DIR = ROI_DIR / "roi_meshes"
OUTLINE_DIR = ROI_DIR / "roi_outlines"
MANIFEST_FN = ROI_DIR / "roi_assets_manifest.json"

REGIONS = ("brain", "cb")
VIEWS = ("xy", "xz", "zy")

# Which stored view a `navis.plot2d`-style view tuple maps onto. The stored
# rings are unsigned, so ('x', '-y') and ('x', 'y') share one file and the sign
# is left to the inverted matplotlib axis. Axis *order* does matter, though --
# column 0 of a ring is the first axis of the key -- so a transposed view such
# as ('y', '-x') is deliberately absent and the caller falls back instead of
# drawing the rings sideways.
_VIEW_BY_AXES = {
    ("x", "y"): "xy",
    ("x", "z"): "xz",
    ("z", "y"): "zy",
}


def view_key(view: tuple[str, ...] | str) -> str | None:
    """Map a navis view tuple such as ('x', '-y') to a stored view key, or None.

    Args:
        view: a view key (`'xy'`), or the axis pair navis takes, signs optional.
            The pair is matched in order: `('x', '-y')` is `xy`, but the
            transposed `('y', '-x')` has no stored ring and gives None.

    Returns:
        The key into the stored outlines, or None when no outline was built for
        that projection (a transposed or oblique view, say) and the caller must
        fall back.
    """
    if isinstance(view, str):
        return view if view in VIEWS else None
    axes = tuple(s.lstrip("-") for s in view[:2])
    return _VIEW_BY_AXES.get(axes)


@lru_cache(maxsize=None)
def get_outline(region: str = "brain", view: str = "xy") -> tuple[pd.DataFrame, ...]:
    """Load the silhouette rings for a region and view, exterior ring first.

    Args:
        region: one of `REGIONS`.
        view: one of `VIEWS`.

    Returns:
        One `x1,y1` DataFrame per ring: index 0 is the exterior, later entries
        are holes (the esophageal foramen for `cb`/`xy`). The tuple is shaped
        like upstream visualpathways' `outlines_bkgd`, so it can be passed
        straight to `utils.projection_plots` helpers.

    Raises:
        FileNotFoundError: if the assets have not been generated yet.
    """
    files = sorted(OUTLINE_DIR.glob(f"outline_{region}_{view}_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No outline for region={region!r} view={view!r} in {OUTLINE_DIR}. "
            "Rebuild with `python -m flyem_analysis_starter.plotting.make_roi_assets`."
        )
    return tuple(pd.read_csv(fn) for fn in files)


def get_outline_rings(region: str = "brain", view: str = "xy") -> list[np.ndarray]:
    """Same rings as `get_outline`, as (n, 2) arrays ready for `ax.plot`."""
    return [df[["x1", "y1"]].to_numpy() for df in get_outline(region, view)]


@lru_cache(maxsize=None)
def get_mesh(region: str = "brain") -> tuple[np.ndarray, np.ndarray]:
    """Load the decimated shell mesh for a region as a (vertices, faces) pair.

    Raises:
        FileNotFoundError: if the assets have not been generated yet.
    """
    fn = MESH_DIR / f"{region}_shell.npz"
    if not fn.is_file():
        raise FileNotFoundError(
            f"{fn} missing. Rebuild with "
            "`python -m flyem_analysis_starter.plotting.make_roi_assets`."
        )
    with np.load(fn) as npz:
        return npz["vertices"].astype(float), npz["faces"].astype(int)


def get_volume(
    region: str = "brain", color: tuple[float, ...] = (1, 1, 1, 0.2)
) -> navis.Volume:
    """Load the decimated shell mesh as a coloured `navis.Volume`."""
    import navis

    verts, faces = get_mesh(region)
    vol = navis.Volume(vertices=verts, faces=faces)
    vol.color = color
    return vol


def get_manifest() -> dict:
    """Read the provenance manifest for the generated assets."""
    return json.loads(MANIFEST_FN.read_text())
