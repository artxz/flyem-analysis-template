"""Helper for subpackages that import their submodules on first use."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


def lazy_getattr(
    package: str, names: dict[str, str], all_names: list[str]
) -> tuple[Callable[[str], Any], Callable[[], list[str]]]:
    """Build `__getattr__` and `__dir__` for a package with lazy submodules.

    Args:
        package: The package's `__name__`.
        names: Public name -> submodule that defines it, relative to `package`
            (`"load"`, or `"..data.malecns"` for a sibling package). A name
            that equals its submodule's name returns the module itself.
        all_names: The package's `__all__`.

    Returns:
        The `(__getattr__, __dir__)` pair to assign at module level.
    """

    def __getattr__(name: str) -> Any:
        """Import the submodule defining `name` and return the attribute."""
        if name not in names:
            raise AttributeError(f"module {package!r} has no attribute {name!r}")
        target = names[name]
        relative = target if target.startswith(".") else f".{target}"
        module = importlib.import_module(relative, package)
        return module if target == name else getattr(module, name)

    def __dir__() -> list[str]:
        """List the public names, including those not yet imported."""
        return sorted(all_names)

    return __getattr__, __dir__
