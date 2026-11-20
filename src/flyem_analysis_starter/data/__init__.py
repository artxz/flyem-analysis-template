"""Load the prebuilt neuron tables and connectivity matrices.

See `flyem_analysis_starter.data.load` for what `meta`, `prop` and `inprop`
contain. The build code that makes these files from neuPrint lives in
`data.malecns` and is not part of the stable API.
"""

from __future__ import annotations

from .._lazy import lazy_getattr

__all__ = [
    "data_file",
    "fetch_data",
    "hosted_datasets",
    "load_flow",
    "load_inprop",
    "load_meta",
    "load_prop",
]

_TARGETS = dict.fromkeys(__all__, "load") | {
    "fetch_data": "fetch",
    "hosted_datasets": "fetch",
}

__getattr__, __dir__ = lazy_getattr(__name__, _TARGETS, __all__)
