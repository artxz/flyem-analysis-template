"""Checks for the data download (`data.fetch`) and publishing (`data.publish`).

Downloads are served from a local HTTP server, so these tests need no network.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from flyem_analysis_starter import config
from flyem_analysis_starter.data import fetch, publish

_REQUIRED_KEYS = {
    "name", "dataset", "dataset_version", "release", "urls", "sha256", "size",
    "build_date", "source", "license",
}  # fmt: skip


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static file handler that does not log every request to stderr."""

    def log_message(self, format: str, *args: Any) -> None:
        """Drop the request log line."""


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Serve a temporary folder over HTTP; yield its base URL and the folder."""
    root = tmp_path / "served"
    root.mkdir()
    handler = functools.partial(_QuietHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", root
    finally:
        httpd.shutdown()
        httpd.server_close()


def _entry(name: str, content: bytes, urls: list[str]) -> dict[str, Any]:
    """Make a manifest entry for some bytes."""
    return {
        "name": name,
        "dataset": "toy_v1",
        "dataset_version": "toy:v1",
        "release": "data-toy_v1-r1",
        "urls": urls,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "build_date": "2026-01-01",
        "source": "test",
        "license": "CC BY 4.0",
    }


@pytest.fixture
def hosted(server: tuple[str, Path]) -> tuple[dict[str, Any], bytes, Path]:
    """Host one file and return its manifest entry, its bytes and the served folder."""
    base, root = server
    content = b"bodyId,instance\n1,a\n" * 1000
    (root / "toy_v1_meta.csv").write_bytes(content)
    return (
        _entry("toy_v1_meta.csv", content, [f"{base}/toy_v1_meta.csv"]),
        content,
        root,
    )


def test_fetch_downloads_and_verifies(hosted, tmp_path, capsys):
    entry, content, _ = hosted
    dest = tmp_path / "data"
    [path] = fetch._fetch_entries([entry], dest, progress=False)
    assert path == dest / entry["name"]
    assert path.read_bytes() == content
    assert not list(dest.glob("*.part"))
    assert "downloaded" in capsys.readouterr().out


def test_fetch_skips_file_with_matching_hash(hosted, tmp_path, capsys):
    entry, content, root = hosted
    dest = tmp_path / "data"
    dest.mkdir()
    (dest / entry["name"]).write_bytes(content)
    (root / entry["name"]).unlink()  # a download attempt would now fail
    fetch._fetch_entries([entry], dest, progress=False)
    assert "up to date" in capsys.readouterr().out


def test_fetch_replaces_file_with_wrong_hash(hosted, tmp_path, capsys):
    entry, content, _ = hosted
    dest = tmp_path / "data"
    dest.mkdir()
    (dest / entry["name"]).write_bytes(b"stale")
    fetch._fetch_entries([entry], dest, progress=False)
    assert (dest / entry["name"]).read_bytes() == content
    assert "differs from the hosted copy" in capsys.readouterr().out


def test_fetch_falls_back_to_next_url(hosted, server, tmp_path):
    entry, content, _ = hosted
    base, _ = server
    entry["urls"] = [f"{base}/missing.csv", *entry["urls"]]
    [path] = fetch._fetch_entries([entry], tmp_path, progress=False)
    assert path.read_bytes() == content


def test_fetch_rejects_bad_hash_and_keeps_old_file(hosted, tmp_path):
    entry, _, root = hosted
    (root / entry["name"]).write_bytes(b"tampered")
    old = tmp_path / entry["name"]
    old.write_bytes(b"old copy")
    with pytest.raises(RuntimeError, match="wrong size or SHA-256"):
        fetch._fetch_entries([entry], tmp_path, progress=False)
    assert old.read_bytes() == b"old copy"
    assert not list(tmp_path.glob("*.part"))


def test_fetch_explains_locked_file(hosted, tmp_path, monkeypatch):
    entry, _, _ = hosted

    def locked(src: object, dst: object) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(fetch.os, "replace", locked)
    with pytest.raises(PermissionError, match="Close notebooks or kernels"):
        fetch._fetch_entries([entry], tmp_path, progress=False)


def test_fetch_data_unknown_dataset(monkeypatch):
    monkeypatch.setattr(
        fetch, "_load_manifest", lambda: {"schema_version": 1, "files": []}
    )
    with pytest.raises(ValueError, match="No hosted data for dataset 'nope'"):
        fetch.fetch_data("nope")


def test_fetch_cli_uses_manifest(hosted, tmp_path, monkeypatch):
    entry, content, _ = hosted
    monkeypatch.setattr(
        fetch, "_load_manifest", lambda: {"schema_version": 1, "files": [entry]}
    )
    fetch.main(["--dataset", "toy_v1", "--data-dir", str(tmp_path)])
    assert (tmp_path / entry["name"]).read_bytes() == content


def test_publish_entries_round_trip_through_fetch(server, tmp_path):
    """Entries written by publish-data are exactly what fetch-data verifies."""
    base, root = server
    tag = config.DEFAULT_DATASET
    src = tmp_path / "src"
    src.mkdir()
    (src / f"{tag}_meta.csv").write_text("a,b\n1,2\n")
    (src / f"{tag}_prop.npz").write_bytes(b"\x00\x01" * 500)
    (src / f"{tag}_prop.npz.part").write_bytes(b"partial")
    (src / "flywire-fafb-v783b_meta.csv").write_text("other dataset\n")

    files = publish._dataset_files(tag, src)
    assert [p.name for p in files] == [f"{tag}_meta.csv", f"{tag}_prop.npz"]
    release = f"data-{tag}-r1"
    entries = publish._build_entries(files, tag, release, "owner/repo", "test")
    assert entries[0]["urls"] == [
        f"https://github.com/owner/repo/releases/download/{release}/{tag}_meta.csv"
    ]
    assert entries[0]["dataset_version"] == config.DATASETS[tag].name

    for p in files:  # "upload": serve the files and point the entries at them
        (root / p.name).write_bytes(p.read_bytes())
    for e in entries:
        e["urls"] = [f"{base}/{e['name']}"]
    dest = tmp_path / "dest"
    fetch._fetch_entries(entries, dest, progress=False)
    for p in files:
        assert (dest / p.name).read_bytes() == p.read_bytes()


def test_publish_refuses_reused_tag_and_bad_names(tmp_path):
    old = _entry("toy_v1_meta.csv", b"x", ["u"])
    manifest = {"schema_version": 1, "files": [old]}
    with pytest.raises(ValueError, match="already in the manifest"):
        publish._add_entries(manifest, [_entry("toy_v1_prop.npz", b"y", ["u"])])

    rebuilt = _entry("toy_v1_meta.csv", b"z", ["u"]) | {"release": "data-toy_v1-r2"}
    publish._add_entries(manifest, [rebuilt])
    assert manifest["files"] == [rebuilt]

    (tmp_path / "toy_v1_meta (1).csv").write_text("x")
    with pytest.raises(ValueError, match="GitHub would rename"):
        publish._dataset_files("toy_v1", tmp_path)


def test_every_dataset_has_licence_and_citation():
    assert set(publish._LICENSES) == set(config.DATASETS)
    assert set(publish._CITATIONS) == set(config.DATASETS)


def test_packaged_manifest_is_well_formed():
    manifest = fetch._load_manifest()
    names = [e["name"] for e in manifest["files"]]
    assert len(names) == len(set(names))
    for e in manifest["files"]:
        assert set(e) == _REQUIRED_KEYS, e["name"]
        assert e["dataset"] in config.DATASETS
        assert e["name"].startswith(f"{e['dataset']}_")
        assert re.fullmatch(r"[A-Za-z0-9._-]+", e["name"])
        assert re.fullmatch(rf"data-{re.escape(e['dataset'])}-r\d+", e["release"])
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"])
        assert e["license"] == publish._LICENSES[e["dataset"]][0]
        assert e["urls"][0].endswith(f"/releases/download/{e['release']}/{e['name']}")
    for dataset in fetch.hosted_datasets():
        hosted = {n for n in names if n.startswith(f"{dataset}_")}
        assert {f"{dataset}_meta.csv", f"{dataset}_prop.npz"} <= hosted


@pytest.mark.data
def test_local_data_matches_manifest():
    """The developer's cache/data copies are the files the manifest describes."""
    entries = fetch._load_manifest()["files"]
    if not entries:
        pytest.skip("no hosted data in the manifest yet")
    for e in entries:
        path = config.DATA_DIR / e["name"]
        if path.is_file():
            assert fetch._matches(path, e), e["name"]
