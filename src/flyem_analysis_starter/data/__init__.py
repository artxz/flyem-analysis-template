"""Load the prebuilt neuron tables and connectivity matrices.

See `flyem_analysis_starter.data.load` for what `meta`, `prop` and `inprop`
contain. The build code that makes these files from neuPrint lives in
`data.malecns` and is not part of the stable API.
"""

from __future__ import annotations

from .._lazy import lazy_getattr

__all__ = ["data_file", "load_meta", "load_prop", "load_inprop", "load_flow"]

__getattr__, __dir__ = lazy_getattr(__name__, dict.fromkeys(__all__, "load"), __all__)
