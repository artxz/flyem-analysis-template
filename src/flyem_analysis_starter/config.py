"""Paths, dataset registry and shared constants for flyem_analysis_starter.

This is the only module that decides where files live. Everything else asks it.

- `PROJECT_ROOT`: the repository folder when the package runs from an editable
  clone, otherwise `None`. The library never reads from it; only tools that write
  into the source tree (`plotting.make_roi_assets`) need it.
- `DATA_DIR`: downloaded data (meta, prop, flow layers, extra eyemaps).
  `<repo>/cache/data` in a clone, otherwise the per-user data folder. Override
  with `FLYEM_DATA_DIR`.
- `CACHE_DIR`: rebuildable caches (synapses, skeletons, meshes, ROI meshes, the
  brain shell, build outputs). `<repo>/cache` in a clone, otherwise the per-user
  cache folder. Override with `FLYEM_CACHE_DIR`.
- `params_path()`: read-only lookup tables shipped inside the package.

On import, a `.env` file is read if present: `<repo>/.env` in a clone, otherwise
`./.env` in the current directory. Values already set in the environment win.
The file is only for secrets (the neuPrint token) and the overrides above; a
missing file is fine.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_cache_dir, user_data_dir

__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "CACHE_DIR",
    "MODEL_COMPARISON_DIR",
    "params_path",
    "Dataset",
    "DATASETS",
    "DEFAULT_DATASET",
    "FLYWIRE_DATASET",
    "dataset_tag",
    "SIDE_CHAR",
    "FLYWIRE_SIDE_CHAR",
    "HIT_THRE",
    "N_FLOW",
    "SEGMENTATION_SOURCE",
    "SHELL_SOURCE",
]

_DIST_NAME = "flyem-analysis-starter"
_PACKAGE_DIR = Path(__file__).resolve().parent


def _find_project_root(package_dir: Path) -> Path | None:
    """Return the repository folder if the package sits in an editable clone.

    A clone is recognised when the package lives in a `src/` folder next to a
    `pyproject.toml` whose `[project].name` is this distribution. This never
    uses `.env` or `PIXI_PROJECT_ROOT`, which may point at another project.

    Args:
        package_dir: Folder holding this package's `__init__.py`.

    Returns:
        The repository folder, or `None` for a regular install.
    """
    src_dir = package_dir.parent
    if src_dir.name != "src":
        return None
    pyproject = src_dir.parent / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        name = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"]
    except (KeyError, tomllib.TOMLDecodeError, OSError):
        return None
    return src_dir.parent if name == _DIST_NAME else None


def _resolve_dirs(
    project_root: Path | None, environ: os._Environ[str] | dict[str, str]
) -> tuple[Path, Path]:
    """Work out `(DATA_DIR, CACHE_DIR)` from the clone location and overrides.

    Args:
        project_root: Repository folder, or `None` for a regular install.
        environ: Environment to read `FLYEM_DATA_DIR` / `FLYEM_CACHE_DIR` from.

    Returns:
        The data and cache folders as absolute paths (not created).
    """
    if project_root is not None:
        cache_default = project_root / "cache"
        data_default = cache_default / "data"
    else:
        cache_default = Path(user_cache_dir(_DIST_NAME, appauthor=False))
        data_default = Path(user_data_dir(_DIST_NAME, appauthor=False))
    data_dir = Path(environ.get("FLYEM_DATA_DIR") or data_default).expanduser()
    cache_dir = Path(environ.get("FLYEM_CACHE_DIR") or cache_default).expanduser()
    return data_dir.resolve(), cache_dir.resolve()


PROJECT_ROOT: Path | None = _find_project_root(_PACKAGE_DIR)

# Secrets and overrides only. override=False: the real environment wins.
load_dotenv((PROJECT_ROOT or Path.cwd()) / ".env", override=False)

DATA_DIR, CACHE_DIR = _resolve_dirs(PROJECT_ROOT, os.environ)
MODEL_COMPARISON_DIR = CACHE_DIR / "model_comparison"


def params_path(*parts: str) -> Path:
    """Return the path of a lookup file shipped in the package's `params/` folder.

    The files are read-only package data (ROI outlines, column pins, the bundled
    eyemap, the data manifest). Nothing at runtime should write there.

    Args:
        *parts: Path components below `params/`, e.g. `"rois", "roi_meshes"`.

    Returns:
        Absolute path to the file or folder. It is not checked for existence.

    Raises:
        RuntimeError: The package is installed inside a zip file rather than as
            files on disk, which the loaders do not support.
    """
    root = files("flyem_analysis_starter").joinpath("params")
    if not isinstance(root, Path):
        raise RuntimeError(
            f"flyem_analysis_starter must be installed as files on disk, not {root!r}."
        )
    return root.joinpath(*parts)


# === Dataset registry ===


@dataclass(frozen=True)
class Dataset:
    """A neuPrint dataset and the tag used to name its files.

    Attributes:
        tag: File-name prefix and cache key, e.g. `malecns_v1.0`. Safe on every
            operating system (no `:`).
        server: neuPrint server URL.
        name: Dataset name on that server, e.g. `male-cns:v1.0`.
    """

    tag: str
    server: str
    name: str


DATASETS: dict[str, Dataset] = {
    d.tag: d
    for d in (
        Dataset("malecns_v1.0", "https://neuprint.janelia.org", "male-cns:v1.0"),
        Dataset(
            "flywire-fafb-v783b",
            "https://neuprint-cns.janelia.org",
            "flywire-fafb:v783b",
        ),
    )
}
DEFAULT_DATASET = "malecns_v1.0"
FLYWIRE_DATASET = "flywire-fafb-v783b"


def _normalise_server(url: str) -> str:
    """Strip the scheme and trailing slash so server URLs compare equal."""
    return url.split("://", 1)[-1].rstrip("/").lower()


def dataset_tag(dataset_name: str, server: str | None = None) -> str:
    """Return the registry tag for a neuPrint dataset name, for file and cache names.

    Args:
        dataset_name: Dataset name as neuPrint reports it (`client.dataset`),
            e.g. `male-cns:v1.0`. A registry tag is accepted too and returned
            unchanged.
        server: Server URL, used to tell apart datasets of the same name on
            different servers. Optional.

    Returns:
        The registry tag (e.g. `malecns_v1.0`). A dataset missing from the
        registry gets its name with `:` and path separators replaced by `_`, so
        the result is always a valid folder name on Windows.
    """
    if dataset_name in DATASETS:
        return dataset_name
    for ds in DATASETS.values():
        same_server = server is None or _normalise_server(server) == _normalise_server(
            ds.server
        )
        if ds.name == dataset_name and same_server:
            return ds.tag
    return "".join("_" if c in ':/\\<>"|?*' else c for c in dataset_name)


# === Build constants (data/build, flow layers) ===

SIDE_CHAR = "r"  # optic lobe the male CNS flow layers are built for
FLYWIRE_SIDE_CHAR = "r"  # same for FlyWire/FAFB
HIT_THRE = 0.1  # hitting-time threshold for flow layers
N_FLOW = 20  # number of flow steps


# === Plotting sources (neuron meshes and the brain shell) ===

SEGMENTATION_SOURCE = os.environ.get(
    "SEGMENTATION_SOURCE", "precomputed://gs://flyem-male-cns/v1.0/segmentation"
)
SHELL_SOURCE = os.environ.get(
    "SHELL_SOURCE", "gs://flyem-optic-lobe/rois/fullbrain-major-shells/"
)
