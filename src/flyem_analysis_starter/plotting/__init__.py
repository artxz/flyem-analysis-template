"""Plot neurons (skeletons, meshes, synapses) over brain outlines.

Fetched skeletons, meshes, synapses and ROIs are cached under
`config.CACHE_DIR`, one folder per dataset. Brain outlines come from the
pre-built assets in the package (`plotting.roi_assets`), so drawing them takes
milliseconds and needs no network.
"""

from __future__ import annotations

from .._lazy import lazy_getattr

__all__ = [
    "CNS_RANGE_X",
    "CNS_RANGE_Y",
    "CNS_RANGE_Z",
    "NG_View",
    "get_mesh",
    "get_meshes",
    "get_outline_cns",
    "get_outline_rings_cns",
    "get_roi",
    "get_shell_cns",
    "get_skeleton",
    "get_skeletons",
    "get_synapses",
    "plot_2d_cns",
    "plot_3d_cns",
    "roi_assets",
    "save_figure",
    "show_figure",
]

_NAMES = {name: "plotter" for name in __all__}
_NAMES["NG_View"] = "ng_view"
_NAMES["roi_assets"] = "roi_assets"

__getattr__, __dir__ = lazy_getattr(__name__, _NAMES, __all__)
