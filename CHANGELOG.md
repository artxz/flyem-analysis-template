# Changelog

This file covers the stable API only: the names each module lists in `__all__`
(recorded in `tests/public_api.txt`), `flyem_analysis_starter.config`, and the file
names and columns of the hosted data. Tutorials, examples, `deferred/` and private
`_` helpers change without notice. A public name is removed or renamed only after one
release that raises a `DeprecationWarning`, and the entry below says what to change.

## Unreleased (0.1.0)

### Added

- Package `flyem_analysis_starter`, installed editable by `pixi install` and
  installable into other projects. Subpackages load on first use, so importing needs
  no network or neuPrint token.
- `config`: `PROJECT_ROOT`, `DATA_DIR`, `CACHE_DIR` (overridable with
  `FLYEM_DATA_DIR` / `FLYEM_CACHE_DIR`), `params_path()`, the dataset registry
  (`DATASETS`, `dataset_tag()`), and the build and plotting-source constants.
  `FLOW_METHOD = "legacy"` keeps the flow layers on the navis < 1.12 traversal
  math that made the published files.
- `neuprint_client`: `connect()` and `get_client()`. They raise
  `NeuprintConnectionError` with setup instructions instead of returning `False`.
- `data`: `load_meta()`, `load_prop()`, `load_inprop()` (derived from `prop`),
  `load_flow()`, `data_file()`. All take `data_dir=`; a missing file raises
  `FileNotFoundError` saying how to download it.
- `data.fetch_data()` and `pixi run fetch-data`: download a dataset's prebuilt
  files into `DATA_DIR` and verify their SHA-256 hashes against the package's
  `params/data_manifest.json`. `data.hosted_datasets()` lists what is available.
- `eyemap`: `eyemap_dir()`, `download_eyemaps()`, `add_coords2()`, `coords2_x()`,
  `hex_b_from_hex()`, `add_binocular_hex()`, `DEFAULT_EYEMAP`.
- `plotting`: `plot_2d_cns()`, `plot_3d_cns()`, `show_figure()`, `save_figure()`,
  the cached fetchers (`get_skeleton(s)`, `get_mesh(es)`, `get_synapses()`,
  `get_roi()`), brain outlines (`get_outline_cns()`, `get_outline_rings_cns()`,
  `get_shell_cns()`, `roi_assets`), `CNS_RANGE_X/Y/Z` and `NG_View`.

### Changed (from the pre-package `utils` / `setup_data` modules)

- `utils.olc_client.connect(instance=...)` is now
  `neuprint_client.connect(server=...)`.
- `utils.plotter._CNS_RANGE_X/Y/Z` are now public: `plotting.CNS_RANGE_X/Y/Z`.
- Skeleton, mesh, synapse and ROI caches moved from `cache/<kind>/` to
  `CACHE_DIR/<kind>/<dataset tag>/` (for example `cache/skeletons/malecns_v1.0/`).
  Move existing files there to keep using them.
- Eyemap downloads go to `DATA_DIR/eyemaps/` instead of `params/eyemaps/`. The
  bundled male CNS eyemap is found by `eyemap.eyemap_dir()`.
