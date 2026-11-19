"""Eye maps and hex-lattice coordinates for optic-lobe neurons.

Both optic lobes share one `hex1`/`hex2` column numbering, so a left and a
right column have the same `coords`. `coords2` (and the eyemap's `hex1b`/`hex2b`)
move the two eyes into separate blocks so both fit in one hex plot.
"""

from __future__ import annotations

from .._lazy import lazy_getattr

__all__ = [
    "DEFAULT_EYEMAP",
    "add_binocular_hex",
    "add_coords2",
    "coords2_x",
    "download_eyemaps",
    "eyemap_dir",
    "hex_b_from_hex",
]

_NAMES = {name: "download" for name in __all__}
_NAMES["add_coords2"] = "..data.malecns"

__getattr__, __dir__ = lazy_getattr(__name__, _NAMES, __all__)
