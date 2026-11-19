"""Starter tooling for FlyEM connectome analysis.

Subpackages are imported on first use, so `import flyem_analysis_starter` is fast
and needs neither a network connection nor a neuPrint token:

- `config`: where data, caches and lookup tables live; the dataset registry.
- `neuprint_client`: lazy neuPrint connection (`connect`, `get_client`).
- `data`: load `meta`, `prop`, `inprop` and flow layers.
- `eyemap`: eye maps and hex-lattice coordinates (`coords`, `coords2`).
- `plotting`: neurons over brain outlines, figure saving.
"""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version
from types import ModuleType

from . import config

try:
    __version__ = version("flyem-analysis-starter")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "config", "data", "eyemap", "neuprint_client", "plotting"]

_SUBMODULES = {"data", "eyemap", "neuprint_client", "plotting"}


def __getattr__(name: str) -> ModuleType:
    """Import a subpackage on first access."""
    if name in _SUBMODULES:
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the public names, including subpackages not yet imported."""
    return sorted(set(globals()) | set(__all__))
