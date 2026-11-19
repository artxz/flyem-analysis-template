"""Package-level checks for flyem_analysis_starter (plan Phase 1).

Most tests run Python in a subprocess from a temporary folder, so they see the
package the way a notebook or another project would, with no `.env` unless the
test writes one.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

import flyem_analysis_starter
from flyem_analysis_starter import config

REPO = Path(__file__).resolve().parents[1]
PKG = "flyem_analysis_starter"
PUBLIC_API_FILE = REPO / "tests" / "public_api.txt"

# Variables that would leak the developer's own setup into a "fresh" subprocess.
_ENV_TO_DROP = ("FLYEM_DATA_DIR", "FLYEM_CACHE_DIR", "NEUPRINT_")

# Prepended to subprocess code to simulate a clone without `.env`: config's
# `load_dotenv` call becomes a no-op even though the developer's `.env` exists.
_NO_DOTENV = "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"


def _clean_env(**extra: str) -> dict[str, str]:
    """Return a copy of the environment without neuPrint or FLYEM_* variables."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_ENV_TO_DROP)}
    env.update(extra)
    return env


def _run(code: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    """Run `code` in a fresh interpreter and return its stdout, failing on errors."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env if env is not None else _clean_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return result.stdout


def _all_modules() -> list[str]:
    """List every module in the package, subpackages included."""
    names = [PKG]
    for info in pkgutil.walk_packages(flyem_analysis_starter.__path__, f"{PKG}."):
        names.append(info.name)
    return sorted(names)


# === Imports ===


def test_every_module_imports_without_dotenv_or_token(tmp_path: Path) -> None:
    """Importing needs no `.env`, token or network; connecting fails with a hint."""
    modules = _all_modules()
    assert f"{PKG}.plotting.plotter" in modules
    code = _NO_DOTENV + "\n".join(
        [
            "import importlib",
            f"for m in {modules!r}:",
            "    importlib.import_module(m)",
            f"from {PKG}.neuprint_client import NeuprintConnectionError, get_client",
            "try:",
            "    get_client()",
            "except NeuprintConnectionError as err:",
            "    assert 'NEUPRINT_APPLICATION_CREDENTIALS' in str(err), err",
            "    assert '.env' in str(err), err",
            "else:",
            "    raise AssertionError('get_client() connected without a token')",
            "print('ok')",
        ]
    )
    assert _run(code, tmp_path).strip().endswith("ok")


def test_import_works_from_another_directory(tmp_path: Path) -> None:
    """The package imports from any working directory, with no sys.path edits."""
    out = _run(
        f"import {PKG} as p; print(p.__file__); print(p.config.PROJECT_ROOT)",
        tmp_path,
    )
    file_line, root_line = out.strip().splitlines()
    assert Path(file_line).is_relative_to(REPO / "src")
    assert Path(root_line) == REPO


def test_notebooks_do_not_use_old_imports() -> None:
    """No notebook .py pair imports the old `utils` / `setup_data` packages."""
    pattern = re.compile(r"^\s*#?\s*(from|import)\s+(utils|setup_data)\b", re.M)
    pairs = [
        p
        for folder in ("tutorials", "examples")
        for p in (REPO / folder).glob("**/*.py")
    ]
    assert pairs, "no notebook .py pairs found"
    offenders = [
        str(p.relative_to(REPO)) for p in pairs if pattern.search(p.read_text("utf-8"))
    ]
    assert not offenders


# === Paths ===


def test_clone_paths() -> None:
    """In this clone, PROJECT_ROOT is the repo and params come from the package."""
    assert config.PROJECT_ROOT == REPO
    assert config.params_path().is_relative_to(REPO / "src" / PKG)
    assert config.params_path("rois", "roi_assets_manifest.json").is_file()


def test_resolve_dirs_defaults_and_overrides(tmp_path: Path) -> None:
    """Clone defaults sit under <repo>/cache; FLYEM_* variables override them."""
    data_dir, cache_dir = config._resolve_dirs(REPO, {})
    assert (data_dir, cache_dir) == (REPO / "cache" / "data", REPO / "cache")
    env = {
        "FLYEM_DATA_DIR": str(tmp_path / "d"),
        "FLYEM_CACHE_DIR": str(tmp_path / "c"),
    }
    assert config._resolve_dirs(REPO, env) == (tmp_path / "d", tmp_path / "c")


def test_dotenv_file_sets_data_and_cache_dirs(tmp_path: Path) -> None:
    """FLYEM_DATA_DIR / FLYEM_CACHE_DIR in a `.env` file change DATA_DIR / CACHE_DIR."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"FLYEM_DATA_DIR={tmp_path / 'mydata'}\n"
        f"FLYEM_CACHE_DIR={tmp_path / 'mycache'}\n"
    )
    # Point config's load_dotenv at the temporary file instead of the repo's .env.
    code = (
        "import dotenv\n"
        "_orig = dotenv.load_dotenv\n"
        f"dotenv.load_dotenv = lambda *a, **k: _orig({str(env_file)!r})\n"
        f"from {PKG} import config\n"
        "print(config.DATA_DIR); print(config.CACHE_DIR)\n"
    )
    data_line, cache_line = _run(code, tmp_path).strip().splitlines()
    assert Path(data_line) == (tmp_path / "mydata").resolve()
    assert Path(cache_line) == (tmp_path / "mycache").resolve()


@pytest.mark.parametrize(
    ("name", "server", "tag"),
    [
        ("male-cns:v1.0", None, "malecns_v1.0"),
        ("male-cns:v1.0", "https://neuprint.janelia.org/", "malecns_v1.0"),
        ("flywire-fafb:v783b", "neuprint-cns.janelia.org", "flywire-fafb-v783b"),
        ("malecns_v1.0", None, "malecns_v1.0"),
        ("optic-lobe:v1.1", None, "optic-lobe_v1.1"),
    ],
)
def test_dataset_tag(name: str, server: str | None, tag: str) -> None:
    """neuPrint dataset names map to registry tags, and never keep a colon."""
    assert config.dataset_tag(name, server) == tag


def test_cache_paths_have_no_colon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-dataset cache folders use the registry tag, not `male-cns:v1.0`."""
    import neuprint

    from flyem_analysis_starter.plotting import plotter

    class FakeClient:
        server = "https://neuprint.janelia.org"
        dataset = "male-cns:v1.0"

    for kind in ("synapses", "skeletons", "meshes", "rois"):
        # Without a default client: the dataset connect() would pick.
        rel = plotter._dataset_cache_dir(kind).relative_to(config.CACHE_DIR)
        assert ":" not in str(rel)
    monkeypatch.setattr(neuprint, "default_client", lambda: FakeClient())
    for kind in ("synapses", "skeletons", "meshes", "rois"):
        path = plotter._dataset_cache_dir(kind)
        assert path == config.CACHE_DIR / kind / "malecns_v1.0"
    for name in ("DATA_DIR", "CACHE_DIR", "MODEL_COMPARISON_DIR"):
        path = getattr(config, name)
        assert ":" not in str(path)[len(path.anchor) :]


# === Built wheel and a regular (non-editable) install ===


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the package wheel once for this module's tests."""
    out = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(REPO),
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(out),
            "-q",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    (whl,) = out.glob("flyem_analysis_starter-*.whl")
    return whl


def test_wheel_contains_package_data(wheel: Path) -> None:
    """The wheel ships the ROI assets and the data manifest."""
    names = set(zipfile.ZipFile(wheel).namelist())
    for needed in (
        f"{PKG}/params/rois/roi_meshes/brain_shell.npz",
        f"{PKG}/params/data_manifest.json",
        f"{PKG}/params/eyemaps/eyemap_mcns_f20240701/right.xlsx",
    ):
        assert needed in names


def test_installed_wheel_outside_repo(wheel: Path, tmp_path: Path) -> None:
    """Installed normally, the package reads its params and uses per-user folders."""
    site = tmp_path / "site"
    work = tmp_path / "work"
    work.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "-q",
            "--target",
            str(site),
            str(wheel),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    env = _clean_env(PYTHONPATH=str(site))
    code = (
        f"import {PKG} as p\n"
        "from platformdirs import user_data_dir, user_cache_dir\n"
        "from pathlib import Path\n"
        f"from {PKG}.plotting import roi_assets\n"
        f"from {PKG}.eyemap import eyemap_dir\n"
        "c = p.config\n"
        "print(p.__file__)\n"
        "assert c.PROJECT_ROOT is None, c.PROJECT_ROOT\n"
        f"name = {config._DIST_NAME!r}\n"
        "assert c.DATA_DIR == Path(user_data_dir(name, appauthor=False)).resolve()\n"
        "assert c.CACHE_DIR == Path(user_cache_dir(name, appauthor=False)).resolve()\n"
        "assert roi_assets.get_outline_rings('brain', 'xy')[0].shape[1] == 2\n"
        "assert (eyemap_dir() / 'right.xlsx').is_file()\n"
        "print('ok')\n"
    )
    out = _run(code, work, env).strip().splitlines()
    assert Path(out[0]).is_relative_to(site), (
        "imported the editable copy, not the wheel"
    )
    assert out[-1] == "ok"

    # An installed copy reads ./.env from the working directory.
    (work / ".env").write_text(f"FLYEM_DATA_DIR={tmp_path / 'elsewhere'}\n")
    out = _run(f"from {PKG} import config; print(config.DATA_DIR)", work, env)
    assert Path(out.strip()) == (tmp_path / "elsewhere").resolve()


# === Data ===


def test_load_inprop_matches_build(tmp_path: Path) -> None:
    """load_inprop() equals the inprop build_sparse_matrices() writes (CSC, float32)."""
    from flyem_analysis_starter.data import load_inprop
    from flyem_analysis_starter.data.malecns import build_sparse_matrices

    edges = pd.DataFrame(
        {
            "bodyId_pre": [10, 10, 20, 30, 30, 40],
            "bodyId_post": [20, 30, 30, 10, 20, 20],
            "weight": [3, 7, 1, 5, 2, 9],
        }
    )
    nodes = [10, 20, 30, 40]  # 40 has no inputs: its column stays empty
    prop, inprop = build_sparse_matrices(edges, nodes)
    sp.save_npz(tmp_path / "toy_prop.npz", prop)

    loaded = load_inprop("toy", data_dir=tmp_path)
    assert loaded.format == "csc" and loaded.dtype == np.float32
    assert loaded.shape == inprop.shape
    assert (loaded != inprop).nnz == 0


def test_missing_data_file_says_how_to_fetch(tmp_path: Path) -> None:
    """A missing file names both ways of downloading the data."""
    from flyem_analysis_starter.data import load_meta

    with pytest.raises(FileNotFoundError, match="pixi run fetch-data") as err:
        load_meta("malecns_v1.0", data_dir=tmp_path)
    assert "fetch_data()" in str(err.value)


@pytest.mark.data
def test_add_coords2_reproduces_cached_column() -> None:
    """add_coords2 on meta without coords2 rebuilds the cached column exactly."""
    from flyem_analysis_starter.data import load_meta
    from flyem_analysis_starter.eyemap import add_coords2

    meta = load_meta()
    rebuilt = add_coords2(meta.drop(columns="coords2"))
    pd.testing.assert_series_equal(
        rebuilt["coords2"].fillna("").astype(str),
        meta["coords2"].fillna("").astype(str),
    )


# === Public API ===


def _public_api() -> dict[str, set[str]]:
    """Read tests/public_api.txt as {module: names}."""
    api: dict[str, set[str]] = {}
    for line in PUBLIC_API_FILE.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            module, name = (s.strip() for s in line.split(":", 1))
            api.setdefault(module, set()).add(name)
    return api


def test_public_api_matches_list() -> None:
    """Each module's __all__ equals tests/public_api.txt, and every name resolves.

    Changing the public API on purpose means updating that file and CHANGELOG.md.
    """
    for module_name, names in _public_api().items():
        module = importlib.import_module(module_name)
        assert set(module.__all__) == names, module_name
        for name in names:
            getattr(module, name)


def test_public_functions_are_documented() -> None:
    """Every public function and class has a docstring and annotated parameters."""
    import inspect

    missing = []
    for module_name, names in _public_api().items():
        module = importlib.import_module(module_name)
        for name in names:
            obj = getattr(module, name)
            if not (inspect.isfunction(obj) or inspect.isclass(obj)):
                continue
            if not inspect.getdoc(obj):
                missing.append(f"{module_name}.{name}: no docstring")
            if inspect.isfunction(obj):
                params = inspect.signature(obj).parameters.values()
                bare = [
                    p.name for p in params if p.annotation is inspect.Parameter.empty
                ]
                if bare:
                    missing.append(f"{module_name}.{name}: no type hints on {bare}")
    assert not missing, "\n".join(missing)
