"""Download eyemap CSVs from the public eyemap archive into params/eyemaps/.

Source: https://artxz.github.io/eyemap-archive/ (Reiser Lab, Janelia Research
Campus). Each dataset/hemisphere CSV has columns p,q,x,y,z[,theta,phi,rootid]
and is directly usable as the `eyemap_path` argument to
`connectome_interpreter.hex_heatmap()` and `plot_mollweide_projection()`.

Usage:
    python src/setup_data/download_eyemaps.py --list
    python src/setup_data/download_eyemaps.py --dataset eyemap_mcns_f20240701 --hemisphere both
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from dotenv import find_dotenv
from tqdm import tqdm

MANIFEST_URL = "https://artxz.github.io/eyemap-archive/manifest.json"
DEFAULT_OUT_DIR = Path(find_dotenv()).parent / "params" / "eyemaps"
DEFAULT_DATASETS = ("eyemap_mcns_f20240701",)
HEMISPHERES = ("left", "right")


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
    """Download one dataset/hemisphere eyemap CSV, skipping it if already present.

    Args:
        entry: One dataset's manifest entry (from manifest["datasets"]).
        hemisphere: "left" or "right".
        out_dir: Directory to download into; the file is written to
            `out_dir/<dataset_id>/<hemisphere>.csv`.
        manifest_url: URL the manifest was fetched from, used to resolve the
            CSV's relative link.
        force: Re-download even if the destination file already exists.

    Returns:
        Path to the downloaded (or already-present) CSV file.
    """
    if hemisphere not in entry["hemispheres"]:
        raise ValueError(
            f"Dataset {entry['id']!r} has no {hemisphere!r} hemisphere. "
            f"Available: {sorted(entry['hemispheres'])}"
        )

    dest = out_dir / entry["id"] / f"{hemisphere}.csv"
    if dest.exists() and not force:
        return dest

    csv_url = urljoin(manifest_url, entry["hemispheres"][hemisphere]["files"]["csv"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(csv_url, dest)
    return dest


def main() -> None:
    """Parse CLI args and download the requested eyemap CSVs from the archive."""
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
        tqdm.write(f"{dataset_id}/{hemisphere}.csv -> {dest}")


if __name__ == "__main__":
    main()
