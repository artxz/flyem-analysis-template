"""Download eyemap XLSX files from the public eyemap archive into params/eyemaps/.

Source: https://artxz.github.io/eyemap-archive/ (Reiser Lab, Janelia Research
Campus). Each dataset/hemisphere XLSX has columns p,q,x,y,z[,theta,phi,rootid]
plus hex1,hex2. Files land as `<dataset>/right.xlsx` and `<dataset>/left.xlsx`,
which is the layout `connectome_interpreter.hex_heatmap()` and
`plot_mollweide_projection()` expect from their `eyemap_dir` argument -- they pick
a file by `which_eye`. Hemispheres the archive publishes only in another format
are converted, so the directory always holds XLSX.

Each file also gets two columns appended here: `hex1b`/`hex2b`, the same lattice
sites re-encoded into a **binocular** frame in which the two eyes occupy disjoint
blocks (see `add_binocular_hex()`). Both hemispheres are numbered in the same
`hex1`/`hex2` frame, so drawing them together collapses a left and a right column
onto one hexagon; `hex1b`/`hex2b` fix that without disturbing anything that reads
`hex1`/`hex2`. `which_eye='both'` reads the new pair, one eye reads the old.

Usage:
    python src/setup_data/download_eyemaps.py --list
    python src/setup_data/download_eyemaps.py --dataset eyemap_mcns_f20240701 --hemisphere both
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from dotenv import find_dotenv
from tqdm import tqdm

MANIFEST_URL = "https://artxz.github.io/eyemap-archive/manifest.json"
DEFAULT_OUT_DIR = Path(find_dotenv()).parent / "params" / "eyemaps"
DEFAULT_DATASETS = ("eyemap_mcns_f20240701",)
HEMISPHERES = ("left", "right")

# Archive formats we can turn into an eyemap XLSX, in order of preference.
DOWNLOAD_FORMATS = ("xlsx", "csv")

BINOCULAR_HEX_COLS = ("hex1b", "hex2b")
COORDS2_X_OFFSET = 20  # half-gap between the two eyes, in hex-column units


def fetch_manifest(manifest_url: str = MANIFEST_URL) -> dict:
    """Fetch and parse the eyemap archive's dataset manifest.

    Args:
        manifest_url: URL of the archive's manifest.json.

    Returns:
        The manifest as a dict with a top-level "datasets" list.
    """
    with urllib.request.urlopen(manifest_url) as response:
        return json.load(response)


def list_datasets(manifest: dict) -> None:
    """Print each dataset's id, title, and available hemispheres to stdout.

    Args:
        manifest: Manifest dict as returned by `fetch_manifest()`.
    """
    for entry in manifest["datasets"]:
        sides = ", ".join(entry["hemispheres"])
        print(f"{entry['id']}: {entry['title']} [{sides}]")


def download_eyemap(
    entry: dict,
    hemisphere: str,
    out_dir: Path,
    manifest_url: str = MANIFEST_URL,
    force: bool = False,
) -> Path:
    """Download one dataset/hemisphere eyemap as XLSX, skipping it if present.

    The archive publishes each hemisphere in several formats. XLSX is taken
    whenever it is offered; otherwise the first available of `DOWNLOAD_FORMATS`
    is fetched and converted, so a dataset directory always ends up holding
    `right.xlsx`/`left.xlsx` -- the layout the plotters' `eyemap_dir` expects.

    Args:
        entry: One dataset's manifest entry (from manifest["datasets"]).
        hemisphere: "left" or "right".
        out_dir: Directory to download into; the file is written to
            `out_dir/<dataset_id>/<hemisphere>.xlsx`.
        manifest_url: URL the manifest was fetched from, used to resolve the
            file's relative link.
        force: Re-download even if the destination file already exists.

    Returns:
        Path to the downloaded (or already-present) XLSX file.
    """
    if hemisphere not in entry["hemispheres"]:
        raise ValueError(
            f"Dataset {entry['id']!r} has no {hemisphere!r} hemisphere. "
            f"Available: {sorted(entry['hemispheres'])}"
        )

    dest = out_dir / entry["id"] / f"{hemisphere}.xlsx"
    if dest.exists() and not force:
        return dest

    available = entry["hemispheres"][hemisphere]["files"]
    fmt = next((f for f in DOWNLOAD_FORMATS if f in available), None)
    if fmt is None:
        raise ValueError(
            f"Dataset {entry['id']!r} {hemisphere!r} is published in none of "
            f"{DOWNLOAD_FORMATS} (only {sorted(available)}), so it cannot be "
            "turned into an eyemap XLSX."
        )

    url = urljoin(manifest_url, available[fmt])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "xlsx":
        urllib.request.urlretrieve(url, dest)
        return dest

    # No XLSX for this hemisphere: fetch what there is and convert it, so the
    # directory layout stays uniform.
    with urllib.request.urlopen(url) as response:
        pd.read_csv(io.BytesIO(response.read())).to_excel(dest, index=False)
    return dest


def coords2_x(x, side) -> pd.Series:
    """Shift and mirror `x` (= hex2 - hex1) into the two-eye `coords2` frame.

    The right eye moves to positive x (`x + COORDS2_X_OFFSET`); the left eye is
    shifted and then mirrored to negative x, so the eyes no longer overlap and
    both frontal fields face the mid-line (x grows posteriorly in both eyes).
    Mirroring x is equivalent to swapping hex1/hex2, so `(x + y)` stays even and
    the encoding stays invertible for `plot_mollweide_projection()`.

    This is the one definition of the two-eye frame: `hex_b_from_hex()` uses it
    for the eyemap's `hex1b`/`hex2b` columns and the malecns setup module uses it
    for the neuron table's `coords2` column, so the two cannot drift apart.

    Args:
        x: Single-eye x coordinates (`hex2 - hex1`), scalar or array-like.
        side: "r"/"l" (or "right"/"left", any case), either a scalar applying to
            every row or an array-like aligned with `x`. Anything else --
            notably "noside" -- yields <NA>.

    Returns:
        `Int64` Series of two-eye x coordinates, with a reset index.
    """
    x = pd.Series(x).reset_index(drop=True).astype("Int64")
    if isinstance(side, str):
        letter = pd.Series(side, index=x.index, dtype="object")
    else:
        letter = pd.Series(side, dtype="object").reset_index(drop=True)
    letter = letter.astype("string").str[:1].str.lower()

    shifted = x + COORDS2_X_OFFSET
    out = pd.Series(pd.NA, index=x.index, dtype="Int64")
    is_right = (letter == "r").fillna(False).to_numpy(dtype=bool)
    is_left = (letter == "l").fillna(False).to_numpy(dtype=bool)
    out[is_right] = shifted[is_right]
    out[is_left] = -shifted[is_left]
    return out


def hex_b_from_hex(hex1, hex2, side) -> tuple[pd.Series, pd.Series]:
    """Re-encode per-eye hex ids into the binocular frame `(hex1b, hex2b)`.

    Applies `coords2_x()` to `x = hex2 - hex1`, leaves `y = hex2 + hex1` alone,
    and converts back. Mirroring x is equivalent to swapping hex1/hex2, so
    `(x + y)` parity -- and therefore lattice membership -- is preserved, and the
    encoding is invertible: `plot_mollweide_projection()` recovers the ids from
    a `'x,y'` index and merges on them.

    Args:
        hex1: Per-eye hex1 ids, array-like.
        hex2: Per-eye hex2 ids, array-like.
        side: "r"/"l" (or "right"/"left", any case), either a scalar applying to
            every row or an array-like aligned with `hex1`/`hex2`.

    Returns:
        `(hex1b, hex2b)` as `Int64` Series with reset indices, <NA> wherever
        `coords2_x()` could not place the row on an eye.
    """
    hex1 = pd.Series(hex1).reset_index(drop=True).astype("Int64")
    hex2 = pd.Series(hex2).reset_index(drop=True).astype("Int64")
    x_b = coords2_x(hex2 - hex1, side)
    y = hex2 + hex1
    # x_b and y always share parity, so both halves divide exactly.
    return (y - x_b) // 2, (y + x_b) // 2


def add_binocular_hex(eyemap_file: Path, hemisphere: str, force: bool = False) -> bool:
    """Append `hex1b`/`hex2b` to one hemisphere's eyemap file, rewriting it.

    `hex1`/`hex2` and everything else -- including the archive's own `p`/`q`
    numbering and the viewing direction `x,y,z` -- are left untouched, so this is
    additive: existing callers reading `hex1`/`hex2` see no change, while callers
    wanting both eyes in one figure read `hex1b`/`hex2b` from both hemisphere
    files instead.

    Args:
        eyemap_file: Path to a hemisphere's `.xlsx`, as written by
            `download_eyemap()`.
        hemisphere: Which eye this file covers, "left" or "right".
        force: Recompute the columns even when they are already present.

    Returns:
        True if the file was rewritten, False if it already had the columns and
        `force` was not set.
    """
    eyemap_file = Path(eyemap_file)
    eyemap = pd.read_excel(eyemap_file)
    if not force and set(BINOCULAR_HEX_COLS) <= set(eyemap.columns):
        return False

    hex1b, hex2b = hex_b_from_hex(eyemap["hex1"], eyemap["hex2"], hemisphere)
    if hex1b.isna().any() or hex2b.isna().any():
        raise ValueError(
            f"{eyemap_file.name}: hemisphere {hemisphere!r} is not recognised as "
            "an eye, so hex1b/hex2b cannot be computed. Expected 'left' or 'right'."
        )

    hex1b_col, hex2b_col = BINOCULAR_HEX_COLS
    eyemap[hex1b_col] = hex1b.astype("int64").to_numpy()
    eyemap[hex2b_col] = hex2b.astype("int64").to_numpy()
    eyemap.to_excel(eyemap_file, index=False)
    return True


def main() -> None:
    """Parse CLI args and download the requested eyemap XLSX files from the archive."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset",
        nargs="+",
        default=list(DEFAULT_DATASETS),
        help="Dataset id(s) to download (see --list). Default: %(default)s",
    )
    parser.add_argument(
        "--hemisphere",
        choices=("left", "right", "both"),
        default="both",
        help="Which hemisphere(s) to download. Default: %(default)s",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory to download into. Default: %(default)s",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if the file exists."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available datasets and exit without downloading.",
    )
    args = parser.parse_args()

    manifest = fetch_manifest()
    if args.list:
        list_datasets(manifest)
        return

    entries_by_id = {entry["id"]: entry for entry in manifest["datasets"]}
    unknown = set(args.dataset) - entries_by_id.keys()
    if unknown:
        raise ValueError(
            f"Unknown dataset(s) {sorted(unknown)}. Run with --list to see options."
        )

    hemispheres = HEMISPHERES if args.hemisphere == "both" else (args.hemisphere,)
    jobs = [
        (dataset_id, hemisphere)
        for dataset_id in args.dataset
        for hemisphere in hemispheres
    ]
    for dataset_id, hemisphere in tqdm(jobs, desc="Downloading eyemaps"):
        dest = download_eyemap(
            entries_by_id[dataset_id], hemisphere, args.out_dir, force=args.force
        )
        # Add the binocular columns now, so nothing has to derive them later.
        rewritten = add_binocular_hex(dest, hemisphere, force=args.force)
        cols = "/".join(BINOCULAR_HEX_COLS)
        note = f"+{cols}" if rewritten else f"{cols} already present"
        tqdm.write(f"{dataset_id}/{hemisphere}.xlsx -> {dest}  ({note})")


if __name__ == "__main__":
    main()
