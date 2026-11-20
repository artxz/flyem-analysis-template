"""Download the prebuilt data files listed in the package's data manifest.

The manifest (`params/data_manifest.json`, shipped inside the package) records,
for every hosted file, its release tag, download URLs, size and SHA-256 hash.
Each package version therefore pins the exact data it was tested with.

Run from a clone with `pixi run fetch-data` (add `--dataset flywire-fafb-v783b`
or `--all`), or call `fetch_data()` from Python in any install.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tqdm.auto import tqdm

from .. import config

__all__ = ["fetch_data", "hosted_datasets"]

_MANIFEST_NAME = "data_manifest.json"
_CHUNK = 1 << 20  # 1 MiB
_TIMEOUT_S = 60


def _load_manifest() -> dict[str, Any]:
    """Read the data manifest shipped with the package."""
    with open(config.params_path(_MANIFEST_NAME), encoding="utf-8") as f:
        manifest: dict[str, Any] = json.load(f)
    if manifest.get("schema_version") != 1:
        raise ValueError(
            f"Unsupported data manifest schema {manifest.get('schema_version')!r}"
        )
    return manifest


def _entries_for(manifest: dict[str, Any], dataset: str) -> list[dict[str, Any]]:
    """Return the manifest entries for one dataset, raising if there are none."""
    entries = [e for e in manifest["files"] if e["dataset"] == dataset]
    if not entries:
        known = sorted({e["dataset"] for e in manifest["files"]})
        raise ValueError(
            f"No hosted data for dataset {dataset!r}. Hosted datasets: "
            f"{', '.join(known) or 'none yet'}."
        )
    return entries


def hosted_datasets() -> list[str]:
    """List the dataset tags that `fetch_data()` can download.

    Returns:
        Registry tags (see `config.DATASETS`) with at least one hosted file.
    """
    return sorted({e["dataset"] for e in _load_manifest()["files"]})


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _matches(path: Path, entry: dict[str, Any]) -> bool:
    """Say whether a local file has the size and hash recorded in the manifest."""
    size_ok: bool = path.stat().st_size == entry["size"]
    return size_ok and _sha256(path) == str(entry["sha256"])


def _download(url: str, dest: Path, size: int, progress: bool) -> None:
    """Stream `url` into `dest`, showing a progress bar sized from the manifest."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "flyem-analysis-starter"}
    )
    with (
        urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response,
        open(dest, "wb") as out,
        tqdm(
            total=size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=dest.name.removesuffix(".part"),
            disable=not progress,
            leave=False,
        ) as bar,
    ):
        for block in iter(lambda: response.read(_CHUNK), b""):
            out.write(block)
            bar.update(len(block))


def _fetch_entry(entry: dict[str, Any], folder: Path, progress: bool) -> Path:
    """Make sure one manifest file is present and verified in `folder`."""
    name = str(entry["name"])
    path = folder / name
    if path.is_file():
        if _matches(path, entry):
            print(f"{name}: up to date")
            return path
        print(f"{name}: differs from the hosted copy, downloading it again")

    part = folder / f"{name}.part"
    errors: list[str] = []
    for url in entry["urls"]:
        try:
            _download(url, part, entry["size"], progress)
        except (urllib.error.URLError, OSError) as exc:
            errors.append(f"{url}: {exc}")
            continue
        if _matches(part, entry):
            break
        errors.append(f"{url}: downloaded file has the wrong size or SHA-256")
    else:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download {name}:\n  " + "\n  ".join(errors))

    try:
        os.replace(part, path)
    except PermissionError as exc:
        raise PermissionError(
            f"Could not replace {path}; another program has it open. Close "
            f"notebooks or kernels using {folder} and rerun."
        ) from exc
    print(f"{name}: downloaded ({entry['size'] / 2**20:.1f} MiB)")
    return path


def _fetch_entries(
    entries: Sequence[dict[str, Any]], folder: Path, progress: bool = True
) -> list[Path]:
    """Download and verify every entry into `folder`, returning the file paths."""
    folder.mkdir(parents=True, exist_ok=True)
    return [_fetch_entry(entry, folder, progress) for entry in entries]


def fetch_data(
    dataset: str = config.DEFAULT_DATASET,
    data_dir: Path | str | None = None,
    progress: bool = True,
) -> list[Path]:
    """Download a dataset's prebuilt files and verify their SHA-256 hashes.

    Files already present with the right hash are left alone, so rerunning is
    cheap. A file whose hash differs is downloaded again (and the message says
    so). Each download goes to `<name>.part` first and replaces the old file
    only once its hash checks out.

    Args:
        dataset: Registry tag, e.g. `malecns_v1.0` or `flywire-fafb-v783b`. See
            `hosted_datasets()` for what is available.
        data_dir: Folder to download into. Defaults to `config.DATA_DIR`
            (`cache/data` in a clone).
        progress: Show a progress bar per file.

    Returns:
        Paths of the dataset's files, all verified.

    Raises:
        ValueError: The manifest has no files for `dataset`.
        RuntimeError: Every URL for a file failed or gave the wrong hash.
        PermissionError: An existing file could not be replaced because it is
            open elsewhere (common on Windows).
    """
    entries = _entries_for(_load_manifest(), dataset)
    folder = Path(data_dir) if data_dir is not None else config.DATA_DIR
    return _fetch_entries(entries, folder, progress)


def main(argv: Sequence[str] | None = None) -> None:
    """Command-line entry point behind `pixi run fetch-data`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dataset",
        default=config.DEFAULT_DATASET,
        help="registry tag to download (default: %(default)s)",
    )
    group.add_argument(
        "--all", action="store_true", help="download every hosted dataset"
    )
    parser.add_argument(
        "--data-dir", type=Path, default=None, help="default: config.DATA_DIR"
    )
    args = parser.parse_args(argv)

    datasets = hosted_datasets() if args.all else [args.dataset]
    folder = args.data_dir if args.data_dir is not None else config.DATA_DIR
    print(f"Data folder: {folder}")
    try:
        for dataset in datasets:
            fetch_data(dataset, folder)
    except (ValueError, RuntimeError, PermissionError) as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
