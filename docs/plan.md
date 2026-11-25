# FlyEM Analysis Starter Repo — Plan

## Purpose of this repository

This repository is a shared starting point for analysing FlyEM connectome data. It is meant for analysts who are new to the data or the tooling. They fork or clone it to begin their own analysis, instead of assembling an environment, data pipeline and plotting code from scratch.

It provides:

- **A reproducible environment:** a Pixi setup that installs the FlyEM analysis stack (neuprint-python, navis, connectome_interpreter, flybrains, cloud-volume) the same way on Windows, macOS and Linux.
- **Data access:** ready-to-use neuron metadata and connectivity matrices for the male central nervous system (male CNS) and FlyWire/FAFB datasets, plus the scripts that build them from neuPrint.
- **A small shared library:** tested helpers for the recurring tasks: querying neuPrint, building connectivity and effective-connectivity matrices, placing neurons on the eye's hex lattice, computing receptive fields, and plotting neurons over brain outlines.
- **Tutorials:** short notebooks, each teaching one idea and each running top to bottom on a fresh clone.
- **An example gallery:** complete analyses that reproduce published figures (male CNS, optic lobe, visual pathways), showing what the tooling can do end to end.

The repository does not aim to:

- hold any one person's ongoing research. That lives in forks or separate repositories that build on this one.
- replace neuprint-python, navis or connectome_interpreter. It wraps and combines them for FlyEM workflows.

The package is `flyem-analysis-starter` (import name `flyem_analysis_starter`). Two uses are supported:

- an editable clone or fork, the main path, since tutorials, examples and Pixi tasks live in the repo
- a regular install into another project

The library never reads from the repo root. Small lookup tables ship inside the package, downloaded data lives in a per-user data folder, and loaders accept an explicit path. This is how connectome_interpreter (bundled CSVs read with `pkgutil.get_data`), navis (example data found next to `__file__`) and flybrains (transforms in `~/flybrain-data`, overridable with `FLYBRAINS_DATA`) handle the same problem.

### What stays stable

One maintainer (the repository owner) looks after the repository, so the stability promise is deliberately narrow:

- **Stable:** the public API of `src/flyem_analysis_starter/` (the names each subpackage lists in `__all__`, plus `config`) and the file names and columns of the hosted data. Releases are tagged `v0.x.y` and recorded in `CHANGELOG.md`. A public name is removed or renamed only after one release that raises a `DeprecationWarning`, and the changelog says what to change.
- **Not stable:** private helpers (`_` prefix), `deferred/`, `tutorials/` and `examples/`. Notebooks are teaching material to copy and edit. They change whenever the library does, and forks are not expected to merge them.
- **Forks:** keep your own work outside `src/`, `tutorials/` and `examples/` (for example in `analysis/`), so merging upstream changes stays free of conflicts.
- **Support:** issues and pull requests are handled on a best-effort basis. A pull request into `src/` needs tests and a changelog line.

## Goal and success criteria

A new analyst clones the repo, runs two commands and has a working connectivity notebook in under 15 minutes, with no help from the authors.

We are done when:

- `pixi install` then `pixi run fetch-data` gives a working environment plus the male CNS data on Windows, macOS and Linux, and those two commands plus executing `02` take under 15 minutes on each OS (timed by the weekly CI job, and once by hand by someone who did not build the repo).
- Every notebook in `tutorials/` runs top to bottom on a fresh clone: `02`–`04` with no `.env` at all (check: run `02` with no `.env` present); `00`, `01`, `05` after copying `.env.example` to `.env` and adding a neuPrint token.
- Nothing a tutorial needs sits in a gitignored folder (`local/`, `cache/`), apart from downloaded data.
- In a fresh environment outside the repo, installing the built wheel and then calling `flyem_analysis_starter.data.fetch_data()` lets you load `meta` and `prop` and draw one ROI outline (checked in CI).
- A newcomer can look up what `prop`, `inprop`, instance, type and hex coordinates mean without asking anyone.

## Current state

Today, no notebook runs on a fresh clone. The tooling is good, but it depends on files only one machine has.

| Gap | Where | Effect on a newcomer |
| --- | --- | --- |
| No data ships with the repo | `cache/data/` (about 160 MB, gitignored) | Every notebook fails at the first load of `malecns_v1.0_meta.csv` / `_prop.npz` |
| The data build scripts are gitignored | `local/s1_malecns_data.py`, `local/s1_flywirefafb_data.py`, `local/flow.py`, `local/s2_layers.py`, `local/s3_effconn.py` | No way to rebuild the data either |
| Imported modules are missing | `utils.config`, `utils.cache`, `utils.core_data`, `utils.ol_data`, `utils.vic`, `utils.alpha_shape`, `utils.external_rf`, `utils.polarity` (imported by `src/utils/ol_rf.py`; `utils.config` also by the `local/` build scripts) | `ol_rf.py` fails on import; no notebook calls it |
| Project root found via `.env` | `Path(find_dotenv()).parent` in 5 `src` modules and every notebook; `.env` is gitignored | On a fresh clone paths resolve under `tutorials/`; `connect()` raises `KeyError` |
| Notebooks only run out of order | `pathways.ipynb`: the barcode section uses `output_types`, `inidx`/`outidx` defined later; `idx_to_sign` never defined | Restart & Run All fails with `NameError` |
| Most recent work is uncommitted | 4 notebooks, `plotter.py`, `roi_assets.py`, `make_roi_assets.py`, `ng_view.py`, `params/rois/`, `pixi.toml` changes | Not shared; at risk of loss |
| Placeholder docs | `README.md`, `CLAUDE.md` | No setup path, no glossary |
| Notebooks saved with outputs, no paired `.py` | `tutorials/` (`plotting.ipynb` 10.8 MB, `pathways.ipynb` 5.6 MB) | Unreviewable diffs, growing history |
| Dependencies pinned to personal forks | `connectome_interpreter` branch `az-eyemap-path`; `navis` fork commit | Environment can break when a branch moves |
| Copied code and data without source notes | `plotter.py`, `ng_view.py`, `ol_rf.py`, `params/*_col_center_pins.pickle` | Unclear what can be shared or changed; licences unchecked |

### Code and data from other repositories

**Installed libraries**

| Library (source) | What we use | Where |
| --- | --- | --- |
| connectome_interpreter (fork, branch `az-eyemap-path`) | Paths: `find_paths_of_length`, `filter_paths`, `group_paths`, `plot_paths`. Effective weights: `effective_conn_from_paths`, `signed_effective_conn_from_paths`. Flow: `find_instance_flow`, `compress_paths`, `result_summary`, `add_first_n_matrices`, `layered_el`. Hex plots: `hex_heatmap`, `plot_mollweide_projection` (with `eyemap_dir=`) | `pathways`, `receptive_fields`, visual-pathways gallery, `local/flow.py` |
| navis (fork, commit `93de9aff`) | `plot`, `Volume`, `xform_brain`, `in_volume`, `NeuronList`, `TreeNeuron`, `subset_neuron`, `downsample_neuron`, neuPrint skeleton fetch | `plotter.py`, `roi_assets.py`, `make_roi_assets.py`, gallery |
| neuprint-python | `Client`, `NeuronCriteria`, `fetch_neurons`, `fetch_adjacencies`, `fetch_synapses`, `fetch_skeletons`, `fetch_mesh_neuron`, `fetch_roi`, `fetch_custom`, `fetch_all_rois`, `fetch_roi_hierarchy` | `olc_client.py`, `malecns.py`, `plotter.py`, `local/` build scripts |
| navis-flybrains | `download_jrc_transforms`, `download_jrc_vnc_transforms`; templates `FLYWIRE`, `MANC`, `JRCFIB` | male CNS gallery |
| cloud-volume | `CloudVolume`, `.mesh` | brain shell and ROI meshes |
| trimesh | `Trimesh` | optic-lobe gallery (only transitive today) |

**Copied or adapted code and data**

| Source | What came from it | Credited today? |
| --- | --- | --- |
| reiserlab/visualpathways | `params/*_col_center_pins.pickle` (commit `0cae786`); ROI outline layout and `cb` framing in `plotter.py` / `roi_assets.py`; colour handling in `pathways.ipynb`; most likely `ol_rf.py` and the 8 modules it is missing | Pins: commit message only. Code: comments mention it, no header |
| reiserlab/male-drosophila-visual-system-connectome-code | Most likely `plotter.py` and `ng_view.py` (neuroglancer views, `FIXME(@floesche)` notes); optic-lobe gallery reproduces its figures | No |
| artxz.github.io/eyemap-archive (Reiser Lab) | Eye maps fetched by `download_eyemaps.py` | Yes, file header |
| flyconnectome/2025malecns | `mcns_lvl_6_hsbm_communities.feather`, downloaded by the male CNS gallery | Yes, notebook |

What already works well, and should be kept: the eyemap download, the pre-built region of interest (ROI) assets, the hex-coordinate placement in `malecns.py`, and the three paper-figure notebooks.

## Target repository layout

Split the repo into three layers: a stable shared library, short teaching notebooks, and a gallery of full examples. Personal research moves to forks.

```text
flyem-analysis-starter/
├── pixi.toml / pixi.lock      # environment; tasks: lab, fetch-data, build-data, publish-data, download-eyemaps, smoke
├── .env.example               # secrets and optional overrides only
├── README.md                  # quickstart, data sources, glossary link
├── CLAUDE.md / AGENTS.md      # domain concepts for AI assistants
├── src/flyem_analysis_starter/  # __init__.py in every (sub)package; no sys.path edits
│   ├── config.py              # DATA_DIR, CACHE_DIR, PROJECT_ROOT, dataset registry, build constants
│   ├── neuprint_client.py     # lazy connection
│   ├── data/                  # load meta / prop, load_inprop(), flow layers, fetch_data(); build_data CLI
│   ├── eyemap/                # eyemap download, hex and coords2 placement
│   ├── plotting/              # plotter.py, roi_assets.py, ng_view.py, make_roi_assets.py
│   └── params/                # package data: lookup tables, ROI outlines/meshes, bundled eyemap, data_manifest.json
├── deferred/                  # ol_rf.py until its dependencies are recovered, then → src/flyem_analysis_starter/rf.py
├── tutorials/                 # 00_setup … 05_plot_neurons, outputs stripped
├── examples/paper_figs/       # male CNS, optic lobe, visual-pathways figures
└── tests/                     # import and smoke tests, expected reference values
```

| Today | Target |
| --- | --- |
| `src/utils/olc_client.py` | `neuprint_client.py` |
| `src/setup_data/malecns.py` | `data/malecns.py`, unsplit (build functions and hex placement call each other); `add_coords2` re-exported from `flyem_analysis_starter.eyemap` |
| `src/setup_data/download_eyemaps.py` | `eyemap/download.py` |
| `src/setup_data/make_roi_assets.py` | `plotting/make_roi_assets.py` |
| `src/utils/{plotter,roi_assets,ng_view}.py` | `plotting/` |
| `src/utils/ol_rf.py` | `deferred/ol_rf.py` |
| `local/flow.py`, `local/s1_*.py`, `local/s2_layers.py` | `data/flow.py`, `data/build.py` |
| `params/` (committed, about 17 MB) | `src/flyem_analysis_starter/params/` (`git mv`, so history follows) |
| `params/eyemaps/` as a download target | committed `eyemap_mcns_f20240701` stays as package data; new downloads go to `DATA_DIR/eyemaps/` |

Target paths are relative to `src/flyem_analysis_starter/`.

**Where files live.** All locations are set in `config.py`; no other module builds paths.

| What | Location | Override |
| --- | --- | --- |
| Lookup tables, ROI assets, bundled eyemap, `data_manifest.json` | package data, read with `importlib.resources.files("flyem_analysis_starter") / "params"`; read-only at runtime | none |
| Downloaded data (meta, prop, flow layers, further eyemaps) | `DATA_DIR`: `<repo>/cache/data` in an editable clone, otherwise `platformdirs.user_data_dir("flyem-analysis-starter")` | `FLYEM_DATA_DIR` |
| Rebuildable caches (synapses, skeletons, meshes, ROI meshes, CNS shell, `build-data` outputs) | `CACHE_DIR`: `<repo>/cache` in an editable clone, otherwise `platformdirs.user_cache_dir("flyem-analysis-starter")` | `FLYEM_CACHE_DIR` |

An editable clone is detected when the package sits in a `src/` folder next to a `pyproject.toml` whose `[project].name` is `flyem-analysis-starter`. `PROJECT_ROOT` is then that folder; otherwise it is `None`. `cache/` stays gitignored. `cache/data/` is filled only by `fetch-data`, or by a deliberate promotion of a `build-data` output. Tools that write into the source tree (`make_roi_assets.py`) need `PROJECT_ROOT` and fail with a clear message without it.

## Phase 0: Safeguard current work

Commit what exists before restructuring anything, so the reorganisation is reviewable as moves rather than rewrites.

- [x] Add a Pixi dev feature (`pre-commit`, `nbstripout`, `pytest`, `nbconvert`; CI runs `pixi run -e dev …`) and a `test` task; register `markers = ["data", "neuprint"]` under `[tool.pytest.ini_options]`. Install the hooks before the first commit: `nbstripout`, `jupytext --sync`, and `check-added-large-files` with `--maxkb=4000` (`params/rois/roi_meshes/brain_shell.npz` is 3.2 MB)
  - `default` and `dev` share one solve group: solving `dev` on its own overflowed pixi's PyPI resolver stack on Windows
- [x] Add `results/` and `tutorials/results/` to `.gitignore`
- [x] Save executed copies of the untracked notebooks outside git (HTML export to a non-public location until the Audience decision; clear the `connect(verbose=True)` output first, it prints the user's email)
  - In `local/notebook_snapshots/2026-11-19/` (HTML plus the cleaned `.ipynb`), including `pathways.ipynb`
- [x] Before stripping, record reference values as `@pytest.mark.data` expectations: from `pathways.ipynb` / `receptive_fields.ipynb` (top effective weights and signs for one input/output pair, `prop.nnz`, `meta` row count) and a few gallery counts
  - `tests/test_reference_values.py`. `receptive_fields.ipynb` was saved without outputs, so the signed weights (and `prop.nnz`) were measured from `cache/data` with the current code
- [x] Strip outputs from all six notebooks (the four untracked plus tracked `pathways.ipynb`, `receptive_fields.ipynb`) and add Jupytext `.py:percent` pairs. Both files are committed and kept in sync by the hook
- [x] Commit `plotter.py`, `roi_assets.py`, `make_roi_assets.py`, `ng_view.py`, `params/rois/` and the `pixi.toml` / `pixi.lock` changes on `notebook-plotting`
- [x] Check no secrets, tokens or PII are staged (`.env`; notebook outputs — `connect(verbose=True)` prints the user's email, already in tracked `pathways.ipynb` history)
- [x] Rewrite git history to remove the email from the `pathways.ipynb` outputs (`git filter-repo` stripping outputs from every past version), then force-push and tell anyone with a clone to re-clone
  - Done 2026-11-19 with `git filter-branch --index-filter` running nbstripout on every `.ipynb` blob (filter-repo was not installed); only notebook blobs changed, so every SHA from `b15f19d` on is new. The email was in old commits `fafd5d2`, `ea662bd`, `fdd6fb4`; GitHub can still serve those by SHA (also via the 2 forks, which share its object network) until GitHub Support purges them. Backup of the old history: `local/pre-history-rewrite.bundle`
- [x] Merge `notebook-plotting` into `main`, or open a pull request, so later phases branch from one base
  - Pull request opened from `notebook-plotting`; merge it before starting Phase 1

## Phase 1: Installable package and config

Turn `src/` into a real package so notebooks and build code import it the same way everywhere, with no path setup and no dependence on `.env`.

- [x] Rename to `src/flyem_analysis_starter/` following the mapping table, with `__init__.py` in the package and each subpackage (heavy submodules imported lazily); `git mv params src/flyem_analysis_starter/params`; move `ol_rf.py` to `deferred/`
  - Done in a pure-rename commit (`3e476d6`), so `git log --follow` works. Subpackages import submodules on first attribute access (`_lazy.py`); `import flyem_analysis_starter` takes about 0.3 s
- [x] `pyproject.toml`:
  - set `[project].name = "flyem-analysis-starter"` and add `flyem-analysis-starter = { path = ".", editable = true }` under `[pypi-dependencies]` in `pixi.toml`
  - fix the build backend (`setuptools.build_meta`)
  - declare the package data (`[tool.setuptools.package-data] flyem_analysis_starter = ["params/**/*"]`)
  - list `platformdirs` and `python-dotenv` as dependencies (`platformdirs` is only transitive today)
  - drop the placeholder `src/flyem_analysis_template` reference from the README
  - Done. Core dependencies are only what `config`, `data` and `eyemap` need (numpy, pandas, scipy, platformdirs, python-dotenv, tqdm, openpyxl). The heavy stack sits in extras (`neuprint`, `plotting`, `analysis`, `all`), so pixi's PyPI resolver is not asked to re-resolve the conda packages. Version `0.1.0.dev0`
- [x] Add `config.py`. It never uses `.env` to find the root, and never `PIXI_PROJECT_ROOT`, which in another project points at that project. It holds:
  - `PROJECT_ROOT`, `DATA_DIR`, `CACHE_DIR` and the `params` resource root, as in "Where files live", plus `MODEL_COMPARISON_DIR`
  - a dataset registry mapping each tag to its neuPrint server and dataset name (`malecns_v1.0 → neuprint.janelia.org / male-cns:v1.0`, `flywire-fafb-v783b → neuprint-cns.janelia.org / flywire-fafb:v783b`)
  - the build constants `SIDE_CHAR`, `FLYWIRE_SIDE_CHAR`, `HIT_THRE = 0.1`, `N_FLOW = 20`
  - defaults for `SEGMENTATION_SOURCE` and `SHELL_SOURCE`

  `.env` supplies only secrets and overrides. At import, before reading any override, `config.py` calls `load_dotenv(..., override=False)` on `PROJECT_ROOT / ".env"` in a clone, or on `Path.cwd() / ".env"` in an installed copy. A missing file is fine, and no other module calls `find_dotenv`

  Done. Also holds `dataset_tag()` (neuPrint name → registry tag) and `FLYWIRE_DATASET`. `FLYWIRE_SIDE_CHAR = "r"` is a guess: `local/s2_layers.py` imports it, but the value was in the missing `utils/config.py`. Confirm it before the FlyWire flow build
- [x] Replace every module-level `Path(find_dotenv()).parent` anchor (`malecns.py:45`, `download_eyemaps.py:37`, `roi_assets.py:23`, `make_roi_assets.py:53`, `plotter.py:89,127,211,290,1445`):
  - `PARAMS_DIR` / `ROI_DIR` become a `params_path(*parts)` helper over the package resources
  - `download_eyemaps` writes to `DATA_DIR/eyemaps/`, and the eyemap lookup checks there before the bundled copy
  - the five `plotter.py` caches go under `CACHE_DIR`
  - `make_roi_assets.py` writes ROI assets into `PROJECT_ROOT`'s package `params/rois/` and its raw caches into `CACHE_DIR`
  - `plotter.py` / `make_roi_assets.py` read the two sources from config instead of asserting on `os.environ`
  - skeleton and mesh caches are keyed by the registry tag (`CACHE_DIR/skeletons/malecns_v1.0/`, via reverse lookup of `client.dataset`). Never the raw `male-cns:v1.0`: a colon is invalid on Windows
  - Done. Synapse and ROI caches are keyed by dataset too. The tag comes from the current default client, or else from the dataset `connect()` would pick, so cache hits still need no token. The one existing cached skeleton was moved to `cache/skeletons/malecns_v1.0/`
- [x] Data loaders take an optional `data_dir=` (default `DATA_DIR`). A missing file raises `FileNotFoundError` that names both `pixi run fetch-data` and `fetch_data()`
  - `data.load_meta`, `load_prop`, `load_inprop`, `load_flow` and `data_file`, in `data/load.py`
- [x] Make the neuPrint connection lazy so importing never needs a network or token; the getter raises a clear error naming `.env` and `NEUPRINT_APPLICATION_CREDENTIALS` instead of returning `False`, and the `plotter` fetches go through it
  - `neuprint_client.connect(server=, dataset=)` (was `instance=`) accepts a neuPrint name or a registry tag and raises `NeuprintConnectionError`. `verbose=True` no longer prints the account email
- [x] Rewrite every `utils.*` / `setup_data.*` import: internal (`malecns.py:30`, `plotter.py:35-36`), all six notebooks including mid-notebook imports (`plotting.ipynb`: `utils.plotter`, incl. private `_CNS_RANGE_X/Y` → make public; `receptive_fields.ipynb`: `setup_data.malecns`), and Pixi task paths (`download-eyemaps`)
  - Notebook setup cells now import `config, data`; meta/prop reads use `data.load_meta` / `load_prop`; `receptive_fields` gets its eyemap from `eyemap.eyemap_dir()`. The notebooks are otherwise unchanged until the tutorials are built (Phase 4). After the change, `paper_figs_visual_pathways_layers` and `receptive_fields` ran top to bottom with nbconvert (with the local `CI_DEV_PATH` connectome_interpreter clone)
- [x] Tests in `tests/`: every module imports with no `.env`; `import flyem_analysis_starter` works from a directory other than the root; no notebook `.py` pair contains `from utils` or `setup_data`; a temporary `.env` setting `FLYEM_DATA_DIR` changes `DATA_DIR`, and `FLYEM_CACHE_DIR` changes `CACHE_DIR`; no cache path contains `:`; the built wheel contains `params/rois/roi_meshes/brain_shell.npz` and `params/data_manifest.json`; the wheel installed (not editable) into a temporary environment outside the repo imports, reads a `params` file, has `PROJECT_ROOT is None`, and resolves `DATA_DIR` / `CACHE_DIR` to the `platformdirs` locations; `load_inprop()` equals `build_sparse_matrices`' inprop (CSC, float32) on a toy edge list; `add_coords2` on meta without `coords2` reproduces the cached column; each subpackage's `__all__` matches `tests/public_api.txt`, so removing or renaming a public name fails until that file and the changelog are updated on purpose. Mark tests that need data or a token with `@pytest.mark.data` / `@pytest.mark.neuprint`
  - `tests/test_package.py`; all 27 tests pass, the Phase 0 ones included. The old-import check looks at import lines only, because `paper_figs_visual_pathways_layers` cites upstream visualpathways' `setup_data/` paths in prose. The installed-copy test uses `pip install --target` plus `PYTHONPATH` rather than a virtualenv. `params/data_manifest.json` is an empty placeholder until the first upload (Phase 3)
- [x] Give every name in `__all__` a docstring and type hints; anything not meant to be stable is prefixed with `_` or left out of `__all__`
  - Enforced by `test_public_functions_are_documented`. `plotting` exports only the plotters, the cached fetchers and the outline helpers; the rest of `plotter.py` stays reachable but unstable
- [x] Start `CHANGELOG.md`, covering only the stable API (see "What stays stable")
  - Started (Unreleased 0.1.0, with migration notes from `utils` / `setup_data`). The `v0.1.0` tag is the last item of Phase 4

## Phase 2: Data download code

The main blocker for newcomers is getting the data. This phase writes the download and publishing code; the files themselves are built and uploaded in Phase 3. The files are hosted as GitHub release assets on this repository.

- [x] `inprop` is not hosted: `data.load_inprop()` derives it from `prop` (divided by column sums, as in `malecns.py:437-443`), checked with `np.allclose(colsum[colsum > 0], 1, atol=1e-5)`
  - Written in Phase 1. It divides entry by entry like `build_sparse_matrices`, so the two matrices are identical, not just close (3.4 s for male CNS)
- [x] Add `flyem_analysis_starter.data.fetch_data(dataset="malecns_v1.0", data_dir=None)`, with `pixi run fetch-data` as a thin wrapper, so an installed copy can fetch without the repo. It downloads into `config.DATA_DIR` (in a clone, `cache/data/`) via `*.part`, verifies SHA-256, then `os.replace` (works on Windows; on `PermissionError` say "close notebooks using cache/data and rerun"); skips a file only when its existing hash matches; on mismatch re-downloads and says so
  - URLs have the form `https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`. Each manifest entry holds a list of URLs tried in order, so a mirror (for example a Zenodo archive, for a DOI) can be added later without code changes
  - Done in `data/fetch.py`, with `hosted_datasets()` and a CLI (`--dataset`, `--all`, `--data-dir`). Tested against a local HTTP server in `tests/test_data_fetch.py` (download, skip on matching hash, re-download on mismatch, URL fallback, bad hash keeps the old file, locked-file message). The repository is already public, so CI needs no `gh release download` step to get past private-repo downloads
- [x] Keep `data_manifest.json` as package data (`src/flyem_analysis_starter/params/data_manifest.json`) so an installed copy knows the URLs and hashes: file name, release tag, URLs, dataset version, SHA-256, size, build date, source, licence. Each package version therefore pins its data releases
  - Schema version 1, checked by `test_packaged_manifest_is_well_formed`. The file has no entries until the first upload in Phase 3
- [x] Add `pixi run publish-data --dataset malecns_v1.0 --tag data-malecns_v1.0-r1` (maintainer only): hashes each file, creates the release with `gh release create --latest=false`, uploads the files, and writes their entries into `data_manifest.json`, so the manifest cannot drift from what was uploaded
  - Done in `data/publish.py`. It creates the release as a draft, checks GitHub's asset sizes and SHA-256 digests against the local files, then publishes it and writes the manifest. `--dry-run` hashes and prints the notes only (it passes for both datasets on the current `cache/data/` files). Refuses a tag already in the manifest and asset names GitHub would rewrite. Release notes carry each dataset's licence and citations (checked 2026-11-20, see Phase 4)

## Phase 3: Data build and first upload

Make the hosted data reproducible from committed code, then upload it. Decided 2026-11-21: the first upload waits for this build, so the hosted files come from `pixi run build-data` rather than the hand-edited `cache/data/` copies (whose `meta` had `coords2` added by hand), and the release notes can name the build commit. Until the upload, `fetch-data` has nothing to download, so `fetch-data`, the README quickstart, tutorial `00` and the fresh-clone CI job all wait on this phase.

- [x] Rewrite `local/s1_malecns_data.py`, `local/s1_flywirefafb_data.py`, `local/s2_layers.py` as functions in `data/build.py` (today they are top-level percent scripts that connect and download at import); `local/flow.py` becomes `data/flow.py` (no more `import flow as sd`). They need only `neuprint_client`, `data/malecns.py`, `flow.py` and `config`
  - Done 2026-11-22 (`899f1b0`, `e1797ce`): `data/build.py` (steps `matrices` and `flow`), `data/flywire.py`, `data/flow.py`. The connectivity download is chunked (`malecns.fetch_typed_edges`, 20,000 presynaptic neurons per `fetch_adjacencies` call), because one call for the whole male CNS ran out of memory on a 16 GB machine
- [x] Connect from the config dataset registry, not `.env` defaults; take the file prefix from the registry tag (not `c.dataset.split('_')[-1]`, which gives `male-cns:v1.0`); make `save_outputs` take the full prefix instead of hard-coding `malecns_`. Confirm `config.FLYWIRE_SIDE_CHAR` (a guess, see Phase 1) before the FlyWire flow build
  - Done. `FLYWIRE_SIDE_CHAR` is `"l"`: the FlyWire flow uses the left eye, as in visualpathways `src/utils/config.py`. `save_outputs` no longer writes `inprop`
- [x] Expose it as `pixi run build-data --dataset malecns_v1.0`: writes to `CACHE_DIR/build/{dataset}/`, never `DATA_DIR`, so the current `cache/data/` files are not overwritten; each step writes to a temporary directory and renames on success; skips a step only when its build-manifest entry is complete and the hash matches, unless `--force`
  - Done. `build_manifest.json` records each step's output and input hashes, code commit and run time; `--compare` / `--compare-only` check the build against `cache/data/`. Matrices take about 16 min for `malecns_v1.0` and 6 min for `flywire-fafb-v783b` on a laptop
- [x] Run the slow flow hitting-time step (2 h 56 min on one core, about 4.5 GB RAM for `malecns_v1.0`) once as a cluster job, not during development; note in the README which steps are slow and which can go to the cluster
  - Done 2026-11-24 on a laptop, no cluster needed: 270 s for `malecns_v1.0` (built from `a4ea693`). navis now comes from artxz/navis `pr/bayesian-speedup` (navis-org/navis#202, batched `BayesianTraversalModel.run`) and connectome_interpreter from `az-update-navis-call`, which passes `method`; `config.FLOW_METHOD = "legacy"` keeps the navis < 1.12 math of the published files. The README note (Phase 4) can say: matrices about 16 min (male CNS) and 6 min (FlyWire), mostly neuPrint download; flow about 5 min (male CNS) and 1.5 min (FlyWire)
- [x] Acceptance check against the current `cache/data/` files (identified by the `publish-data --dry-run` hashes): matrix shape and nnz, meta columns and row count, `coords2` equal to the cached column, flow CSV columns (`idx`, `hitting_time`, `instance`) and row count (162,084 for `malecns_v1.0`). Explain every difference before publishing
  - Matrices done 2026-11-22, built from `e1797ce`. Both meta files and the FlyWire `prop.npz` are byte-identical to `cache/data/`. The male CNS `prop.npz` holds identical arrays; only the zip entries' "made on" operating-system byte differs (Windows here, Unix for the old file), so hashes depend on the build platform. `coords2` from the build equals the hand-added column. Flow files still to check after the cluster run (FlyWire has no reference flow file, so it is checked by columns and row count only)
  - Male CNS flow done 2026-11-24: both flow CSVs (162,084 neurons; 22,892 instances) are byte-identical to `cache/data/`.
  - FlyWire flow done 2026-11-25 (86 s on a laptop, left eye, `method='legacy'`, built from `f09b943`). No reference file, so checked by structure: `_hit.csv` has columns `idx`, `hitting_time`, `instance` and 129,669 rows (one per meta row, `idx` 0–129,668, unique); `_hit_per_group.csv` has `instance`, `hitting_time` and 17,512 rows; no missing values; hitting times span 0–20 (median 4.09), as in the male CNS files (median 4.23). The lowest hitting times are on L1–L3, R7, R8 and HBeyelet, as for the male CNS right eye
- [ ] Host the built files as release assets: `malecns_v1.0_meta.csv`, `_prop.npz`, flow-layer CSVs, FlyWire `flywire-fafb-v783b_*` (about 160 MB in total; the per-file limit is 2 GiB)
  - `pixi run publish-data --dataset malecns_v1.0 --tag data-malecns_v1.0-r1 --data-dir <CACHE_DIR>/build/malecns_v1.0`, then the same for `flywire-fafb-v783b`; commit `data_manifest.json`. `--source` now defaults to the commits in the folder's `build_manifest.json`, and files changed since the build are refused
  - one data release per dataset build, tagged `data-<dataset>-r<n>` (first `data-malecns_v1.0-r1` and `data-flywire-fafb-v783b-r1`), separate from the `v0.x.y` code tags and created with `--latest=false`, so "latest release" stays the code release
  - assets are never replaced in place: a rebuild gets a new tag (`-r2`) and new manifest entries
  - asset names match the local file names and use only letters, digits, `.`, `_` and `-` (GitHub rewrites other characters)
  - release notes record the dataset version, build date, source commit, licence and the dataset citations
  - the repository is public, so these releases are public as soon as they are published
- [ ] Test the upload: `pixi run fetch-data --all --data-dir <empty folder>` from a fresh clone, and `fetch_data()` from the built wheel outside the repo on a machine with no GitHub login, to confirm anonymous downloads work; then `pytest -m data` against the downloaded files
- [ ] Later, not blocking the upload: bring `ol_rf.py`, s1 section 6 (input RF data) and `s3_effconn.py` into the shared library. Recover or rewrite the eight missing modules it needs, move `deferred/ol_rf.py` to `src/flyem_analysis_starter/rf.py`, and add `s3_effconn` as an optional `build-data` step

## Phase 4: Tutorials and documentation

Each tutorial teaches one idea, runs top to bottom in a few minutes, and is built from material that already exists. `02`–`04` read only cached data and never call `connect()`, so they can be written during Phase 3 against the local `cache/data/` files; `00`, `01`, `05` need a token. Each tutorial passes Restart & Run All before it is committed.

| Tutorial | Teaches | Built from |
| --- | --- | --- |
| `00_setup` | Environment check, token, `fetch-data` | `test_dependencies.py`, notebook setup cells |
| `01_query_neuprint` | Fetch neurons, synapses, adjacencies | `olc_client.py`, neuprint-python calls in notebooks |
| `02_connectivity_matrices` | `meta`, `prop` vs `inprop`, instance vs type | Data sections of `pathways.ipynb`; `load_inprop()` |
| `03_pathways` | Effective weights, barcode plots, multi-hop paths | `pathways.ipynb` minus the unfinished flow-layer section; move the `input_types`/`output_types` and `inidx`/`outidx` cells above the barcode section and define `idx_to_sign = dict(zip(meta.idx, meta.sign))` (as in `receptive_fields.ipynb`); drop the `connect` cell and unused `fetch_adjacencies` import |
| `04_receptive_fields` | Hex lattice, one eye vs both eyes, `coords2` | `receptive_fields.ipynb`; drop the `connect` cell and unused `fetch_adjacencies` import |
| `05_plot_neurons` | Skeletons, meshes, brain outlines | `plotting.ipynb`, `roi_assets.py` |

The three paper-figure notebooks move to `examples/paper_figs/`, unchanged except their setup/import cells and one guard: in `paper_figs_visual_pathways_layers`, a missing flow file raises `FileNotFoundError("run pixi run fetch-data")` unless `RECOMPUTE_FLOW = True` is set (the recompute takes about 5 minutes).

- [ ] `README.md` (the quickstart and tutorial `00` are finished after the Phase 3 upload):
  - two-command quickstart (`pixi install`, `pixi run fetch-data`) for `02`–`04`; for `00`, `01`, `05` also "copy `.env.example` to `.env` and add your token"
  - a short "use it from your own project" section: install, `fetch_data()`, where the data and cache folders are and how to move them
  - how to get a neuPrint token, datasets covered, data provenance, licences and citations, where to ask for help
- [x] `.env.example` (done: neuPrint server, dataset, token placeholder, `SEGMENTATION_SOURCE`, `SHELL_SOURCE`, plotting backends, `CI_DEV_PATH`): add `FLYEM_DATA_DIR` and `FLYEM_CACHE_DIR` once `config.py` exists, and keep the source values in sync with the `config.py` defaults
  - Added in Phase 1 (commented out), and the server, dataset and sources are marked optional
- [ ] Glossary (README section or `docs/glossary.md`): `prop`, `inprop`, instance, type, hex1/hex2, `coords2`, effective connectivity, flow layers
- [ ] `CLAUDE.md` / `AGENTS.md`: fill Key Concepts from the glossary and point to the package layout, so AI assistants give correct answers
- [ ] `CONTRIBUTING.md`: what is stable and what is copy-and-edit (from "What stays stable"), where to keep your own work in a fork, what a pull request into `src/` needs (tests, a changelog line, a `tests/public_api.txt` update if the API changes), and that one maintainer reviews on a best-effort basis
- [ ] Source notes: a one-line "Adapted from <repo>, <path or commit>" header in each copied file (`plotter.py`, `ng_view.py`, `ol_rf.py`, `roi_assets.py`) and a `params/README.md` entry for the column pins. Confirm the uncertain origins (`plotter.py`, `ng_view.py`, `ol_rf.py`) against the local clones of the paper repos
- [ ] README "Acknowledgements and third-party code" section built from the tables in Current state; check each source repository's licence is compatible with public sharing
- [ ] Public-repository checks (the repository is already public, so these are overdue rather than gating):
  - ask GitHub Support to purge the old commits that held the email (`fafd5d2`, `ea662bd`, `fdd6fb4`)
  - check that no cluster paths or internal hostnames appear in docs or notebooks
  - [x] confirm the male CNS and FlyWire terms allow redistributing the derived matrices. Checked 2026-11-20: male CNS v1.0 is CC BY 4.0 (male-cns.janelia.org/download); FlyWire public release v783 is CC BY-NC 4.0 (flywire.ai/guidelines; its Zenodo connectivity record says CC BY 4.0, and the stricter licence is used). Both allow redistribution with attribution, FlyWire for non-commercial use only. The licence and citations go into each release's notes and manifest entries; the README still needs them
- [ ] Tag `v0.1.0` once Phases 1–4 are done (needs the Distribution decision below); move the changelog's Unreleased section under it

## Phase 5: Dependencies and automated checks

Keep the environment reproducible for people who did not build it, and catch breakage before a newcomer does.

**Dependencies**

- [ ] Upstream the `connectome_interpreter` changes on `az-eyemap-path` and the `navis` fork commit, or pin both to tags that will not move. First check what each fork adds that upstream lacks: `eyemap_dir=` in `hex_heatmap` / `plot_mollweide_projection` (tutorial `04`), and whatever `find_instance_flow` needs from the navis fork
- [ ] Keep `pixi.lock` committed; note in the README that a PyPI-to-conda swap needs a clean `.pixi` rebuild (stale pip files caused an OpenMP crash before)
- [ ] List `trimesh` explicitly, since the optic-lobe notebook imports it directly
- [ ] Add `ruff` (lint and format) to the pre-commit hooks set up in Phase 0

**Automated checks (GitHub Actions)**

- [ ] On every push: `pixi install` on Linux and Windows, import every module, run `pytest -m "not data and not neuprint"`, build the wheel and run the installed-copy tests outside the checkout, and fail if any `.py`/`.ipynb` pair is out of sync
- [ ] On pull requests, a "fresh clone" job on ubuntu, windows and macos (arm64): clean checkout, `pixi install`, `pixi run fetch-data` (data restored from an Actions cache, filled from the Phase 3 release assets), the remaining tests, and every notebook in `tutorials/` executed with nbconvert. `02`–`04` run with the neuPrint variables unset; `00`, `01`, `05` skip when no token secret is available (fork PRs)
- [ ] Protect `main` with required status checks (the push job) instead of required reviews: with one maintainer there is no second reviewer, so CI is the gate
- [ ] Weekly, the same job with the Actions cache disabled, so `fetch-data` does a real cold download; it times `pixi install`, `fetch-data` and executing `02`, and fails above 15 minutes. The on-demand run also executes the gallery
- [ ] Replace `test_dependencies.py` with `pixi run smoke`, which imports the real stack (`neuprint`, `navis`, `connectome_interpreter`, `torch`, `cloudvolume`, `flybrains`) and runs one tiny neuPrint query

## Open decisions

Decided on 2026-11-19:

- **Audience:** public. The licence check, data-terms check and history purge are required (Phase 4), and the Janelia shared drive is ruled out for hosting.
- **Package name:** `flyem-analysis-starter` (import `flyem_analysis_starter`).
- **Use:** both an editable clone and a regular install are supported, following the connectome_interpreter, navis and flybrains approach (see Purpose and "Where files live").
- **Data hosting:** GitHub release assets on this repository (code in Phase 2, upload in Phase 3). They are fast and reliable from GitHub Actions, and data releases sit next to the code tags. Accepted trade-offs: no DOI, and the data goes with the repository if it is deleted or leaves GitHub. A Zenodo archive of a data release can be added later as a second URL in the manifest.
- **Maintenance model:** middle ground. The public API in `src/` is kept stable with releases; tutorials and examples are copy-and-edit material (see "What stays stable").
- **Owners:** one maintainer (the repository owner) for all phases. With no second reviewer, required CI checks gate `main` (Phase 5). The hand-timed run in the success criteria still needs one person who did not build the repo.

Decided on 2026-11-21: the first data upload waits for the data build (Phase 3).

Still open, and needed only before the first release (`v0.1.0`):

| Decision | Options | Affects |
| --- | --- | --- |
| Distribution | Install from the Git URL only, or also publish releases to PyPI | README install line, release workflow; PyPI fits the middle-ground model but adds a publishing step per release for one maintainer |

Order: Phases 0 → 5 in sequence. The one overlap: tutorials `02`–`04` (Phase 4) can be written during Phase 3, since they read only local data. Phases were reordered and renumbered on 2026-11-22, moving the data build ahead of the tutorials; Phases 0–2 kept their numbers, so commit messages and branch names (`phase1-package`, `phase2-data`) still match.
