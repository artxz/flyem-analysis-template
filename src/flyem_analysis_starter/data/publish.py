"""Publish a dataset's prebuilt files as a GitHub data release (maintainer only).

Usage, from a clone with the GitHub command-line tool (`gh`) logged in:

    pixi run publish-data --dataset malecns_v1.0 --tag data-malecns_v1.0-r1

It hashes every `<dataset>_*` file in `config.DATA_DIR`, creates the release as a
draft with `--latest=false` (so "latest release" stays the code release),
uploads the files, checks GitHub's copies against the local sizes and hashes,
publishes the release, and only then writes the entries into the package's
`params/data_manifest.json`. The manifest therefore always matches what was
uploaded. Commit the manifest change afterwards.

A tag is never reused: a rebuilt dataset gets a new tag (`-r2`) and new
manifest entries. Not part of the stable API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .. import config
from .fetch import _sha256

_ASSET_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

# Cited in the release notes. Keep in sync with the README's data section.
_CITATIONS = {
    "malecns_v1.0": [
        "Berg S, Beckett IR, Costa M, et al. (2025). Sexual dimorphism in the "
        "complete connectome of the Drosophila male central nervous system. "
        "bioRxiv.",
    ],
    "flywire-fafb-v783b": [
        "Dorkenwald S, Matsliah A, Sterling AR, et al. (2024). Neuronal wiring "
        "diagram of an adult brain. Nature 634, 124-138.",
        "Schlegel P, Yin Y, Bates AS, et al. (2024). Whole-brain annotation and "
        "multi-connectome cell typing of Drosophila. Nature 634, 139-152.",
    ],
}

_DEFAULT_SOURCE = (
    "local build scripts (s1/s2, not yet in the repository; see docs/plan.md Phase 4)"
)


def _manifest_path() -> Path:
    """Return the manifest inside the clone's source tree, which this tool edits."""
    if config.PROJECT_ROOT is None:
        sys.exit("publish-data edits the source tree; run it from a clone.")
    return (
        config.PROJECT_ROOT
        / "src"
        / "flyem_analysis_starter"
        / "params"
        / "data_manifest.json"
    )


def _dataset_files(dataset: str, folder: Path) -> list[Path]:
    """Return the files in `folder` that belong to `dataset`, by name prefix."""
    files = sorted(
        p
        for p in folder.glob(f"{dataset}_*")
        if p.is_file() and not p.name.endswith(".part")
    )
    if not files:
        raise ValueError(f"No {dataset}_* files in {folder}")
    bad = [p.name for p in files if not _ASSET_NAME.match(p.name)]
    if bad:
        raise ValueError(
            "GitHub would rename these assets; use only letters, digits, "
            f"'.', '_' and '-': {bad}"
        )
    return files


def _build_entries(
    files: Sequence[Path],
    dataset: str,
    tag: str,
    repo: str,
    source: str,
) -> list[dict[str, Any]]:
    """Describe each file as a manifest entry (hash, size, URL, provenance)."""
    neuprint_name = config.DATASETS[dataset].name
    entries = []
    for path in files:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
        entries.append(
            {
                "name": path.name,
                "dataset": dataset,
                "dataset_version": neuprint_name,
                "release": tag,
                "urls": [
                    f"https://github.com/{repo}/releases/download/{tag}/{path.name}"
                ],
                "sha256": _sha256(path),
                "size": path.stat().st_size,
                "build_date": mtime.date().isoformat(),
                "source": source,
            }
        )
    return entries


def _add_entries(manifest: dict[str, Any], entries: Sequence[dict[str, Any]]) -> None:
    """Append entries to a manifest, refusing to reuse a tag or replace a file."""
    tags = {e["release"] for e in entries}
    used = tags & {e["release"] for e in manifest["files"]}
    if used:
        raise ValueError(f"Release tag already in the manifest: {sorted(used)}")
    new_names = {e["name"] for e in entries}
    # A file name maps to exactly one entry; a rebuild drops the older entry.
    manifest["files"] = [
        e for e in manifest["files"] if e["name"] not in new_names
    ] + list(entries)
    manifest["files"].sort(key=lambda e: (e["dataset"], e["name"]))


def _release_notes(dataset: str, entries: Sequence[dict[str, Any]], commit: str) -> str:
    """Write the release notes: dataset, build dates, source, files, citations."""
    lines = [
        f"Prebuilt data for `{dataset}` "
        f"(neuPrint dataset `{config.DATASETS[dataset].name}`).",
        "",
        "Download with `pixi run fetch-data` in a clone, or "
        "`flyem_analysis_starter.data.fetch_data()` in any install. Files are "
        "listed with their SHA-256 hashes in the package's `data_manifest.json`.",
        "",
        f"- Code commit when published: `{commit}`",
        f"- Built by: {entries[0]['source']}",
        "",
        "| File | Size (MiB) | Build date | SHA-256 |",
        "| --- | --- | --- | --- |",
    ]
    for e in entries:
        lines.append(
            f"| `{e['name']}` | {e['size'] / 2**20:.1f} | {e['build_date']} "
            f"| `{e['sha256']}` |"
        )
    lines += ["", "Please cite the dataset when using these files:", ""]
    lines += [f"- {c}" for c in _CITATIONS.get(dataset, ["(add citation)"])]
    return "\n".join(lines) + "\n"


def _gh(*args: str) -> str:
    """Run a `gh` command and return its stdout, exiting on failure."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed:\n{result.stderr}")
    return result.stdout


def _check_uploaded(repo: str, tag: str, entries: Sequence[dict[str, Any]]) -> None:
    """Compare GitHub's asset sizes and digests with the manifest entries."""
    # `gh release view` also finds drafts, which the REST tag lookup does not.
    release = json.loads(_gh("release", "view", tag, "-R", repo, "--json", "assets"))
    assets = {a["name"]: a for a in release["assets"]}
    for e in entries:
        asset = assets.get(e["name"])
        if asset is None:
            sys.exit(f"{e['name']} is missing from release {tag}")
        if asset["size"] != e["size"]:
            sys.exit(f"{e['name']}: GitHub has {asset['size']} bytes, not {e['size']}")
        digest = asset.get("digest")
        if digest != f"sha256:{e['sha256']}":
            sys.exit(f"{e['name']}: GitHub's digest {digest} does not match")


def main(argv: Sequence[str] | None = None) -> None:
    """Command-line entry point behind `pixi run publish-data`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, choices=sorted(config.DATASETS))
    parser.add_argument("--tag", required=True, help="e.g. data-malecns_v1.0-r1")
    parser.add_argument("--source", default=_DEFAULT_SOURCE, help="build provenance")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="hash the files and print the notes and entries; upload nothing",
    )
    args = parser.parse_args(argv)

    if not re.fullmatch(rf"data-{re.escape(args.dataset)}-r\d+", args.tag):
        sys.exit(f"Tag must look like data-{args.dataset}-r<n>, got {args.tag}")
    manifest_path = _manifest_path()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    repo = _gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    repo = repo.strip()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=config.PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    files = _dataset_files(args.dataset, args.data_dir)
    print(f"Hashing {len(files)} files in {args.data_dir} ...")
    entries = _build_entries(files, args.dataset, args.tag, repo, args.source)
    _add_entries(manifest, entries)  # validates the tag before any upload
    notes = _release_notes(args.dataset, entries, commit)

    if args.dry_run:
        print(notes)
        print(json.dumps(entries, indent=2))
        return

    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.md"
        notes_file.write_text(notes, encoding="utf-8")
        _gh(
            "release", "create", args.tag, *map(str, files),
            "--draft", "--latest=false",
            "--title", f"Data: {args.dataset} r{args.tag.rsplit('-r', 1)[1]}",
            "--notes-file", str(notes_file),
        )  # fmt: skip
    _check_uploaded(repo, args.tag, entries)
    _gh("release", "edit", args.tag, "--draft=false", "--latest=false")

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Published {args.tag}; wrote {len(entries)} entries to {manifest_path}.")
    print("Commit the manifest change.")


if __name__ == "__main__":
    main()
