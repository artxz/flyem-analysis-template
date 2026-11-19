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

Supported use is an editable clone or fork of this repository; installing the package non-editably into another project is not supported (the library reads `params/` and `cache/` from the repo root).

## Goal and success criteria

A new analyst clones the repo, runs two commands and has a working connectivity notebook in under 15 minutes, with no help from the authors.

We are done when:

- `pixi install` then `pixi run fetch-data` gives a working environment plus the male CNS data on Windows, macOS and Linux, and those two commands plus executing `02` take under 15 minutes on each OS (timed by the weekly CI job, and once by hand by someone who did not build the repo).
- Every notebook in `tutorials/` runs top to bottom on a fresh clone: `02`–`04` with no `.env` at all (check: run `02` with no `.env` present); `00`, `01`, `05` after copying `.env.example` to `.env` and adding a neuPrint token.
- Nothing a tutorial needs sits in a gitignored folder (`local/`, `cache/`), apart from downloaded data.
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
| reiserlab/visualpathways | `params/*_col_center_pins.pickle` (commit `fdd6fb4`); ROI outline layout and `cb` framing in `plotter.py` / `roi_assets.py`; colour handling in `pathways.ipynb`; most likely `ol_rf.py` and the 8 modules it is missing | Pins: commit message only. Code: comments mention it, no header |
| reiserlab/male-drosophila-visual-system-connectome-code | Most likely `plotter.py` and `ng_view.py` (neuroglancer views, `FIXME(@floesche)` notes); optic-lobe gallery reproduces its figures | No |
| artxz.github.io/eyemap-archive (Reiser Lab) | Eye maps fetched by `download_eyemaps.py` | Yes, file header |
| flyconnectome/2025malecns | `mcns_lvl_6_hsbm_communities.feather`, downloaded by the male CNS gallery | Yes, notebook |

What already works well, and should be kept: the eyemap download, the pre-built region of interest (ROI) assets, the hex-coordinate placement in `malecns.py`, and the three paper-figure notebooks.

## Target repository layout

Split the repo into three layers: a stable shared library, short teaching notebooks, and a gallery of full examples. Personal research moves to forks.

```text
flyem-analysis/
├── pixi.toml / pixi.lock      # environment; tasks: lab, fetch-data, build-data, download-eyemaps, smoke
├── .env.example               # secrets and optional overrides only
├── README.md                  # quickstart, data sources, glossary link
├── CLAUDE.md / AGENTS.md      # domain concepts for AI assistants
├── src/flyem_analysis/        # editable install; __init__.py in every (sub)package; no sys.path edits
│   ├── config.py              # PROJECT_ROOT, paths, dataset registry, build constants
│   ├── neuprint_client.py     # lazy connection
│   ├── data/                  # load meta / prop, load_inprop(), flow layers; build_data CLI
│   ├── eyemap/                # eyemap download, hex and coords2 placement
│   └── plotting/              # plotter.py, roi_assets.py, ng_view.py, make_roi_assets.py
├── deferred/                  # ol_rf.py until its dependencies are recovered, then → src/flyem_analysis/rf.py
├── params/                    # small committed lookup tables, ROI outlines
├── tutorials/                 # 00_setup … 05_plot_neurons, outputs stripped
├── examples/paper_figs/       # male CNS, optic lobe, visual-pathways figures
└── tests/                     # import and smoke tests, expected reference values
```

| Today | Target |
| --- | --- |
| `src/utils/olc_client.py` | `neuprint_client.py` |
| `src/setup_data/malecns.py` | `data/malecns.py`, unsplit (build functions and hex placement call each other); `add_coords2` re-exported from `flyem_analysis.eyemap` |
| `src/setup_data/download_eyemaps.py` | `eyemap/download.py` |
| `src/setup_data/make_roi_assets.py` | `plotting/make_roi_assets.py` |
| `src/utils/{plotter,roi_assets,ng_view}.py` | `plotting/` |
| `src/utils/ol_rf.py` | `deferred/ol_rf.py` |
| `local/flow.py`, `local/s1_*.py`, `local/s2_layers.py` | `data/flow.py`, `data/build.py` |

The package name `flyem_analysis` is a placeholder (see Open decisions). `cache/` stays gitignored; `cache/data/` is filled only by `fetch-data` (or a deliberate promotion of a `build-data` output).

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
- [ ] Rewrite git history to remove the email from the `pathways.ipynb` outputs (`git filter-repo` stripping outputs from every past version), then force-push and tell anyone with a clone to re-clone
  - The email is in 3 pushed commits (`fafd5d2`, `ea662bd`, `fdd6fb4`) of a public repo. After the force-push GitHub can still serve the old commits by SHA until GitHub Support purges them
- [ ] Merge `notebook-plotting` into `main`, or open a pull request, so later phases branch from one base

## Phase 1: Installable package and config

Turn `src/` into a real package so notebooks and build code import it the same way everywhere, with no path setup and no dependence on `.env`.

- [ ] Rename to `src/flyem_analysis/` following the mapping table, with `__init__.py` in the package and each subpackage (heavy submodules imported lazily); move `ol_rf.py` to `deferred/`
- [ ] Add `flyem_analysis = { path = ".", editable = true }` under `[pypi-dependencies]` in `pixi.toml` and set `pyproject.toml` `[project].name = "flyem_analysis"` to match; fix the `pyproject.toml` build backend (`setuptools.build_meta`) and drop the placeholder `src/flyem_analysis_template` reference from the README
- [ ] Add `config.py`: `PROJECT_ROOT` from the package location (editable install), falling back to `PIXI_PROJECT_ROOT` — never `.env`; `cache/`, `params/`, `DATA_DIR` (overridable with `FLYEM_DATA_DIR`), `MODEL_COMPARISON_DIR`; a dataset registry mapping each tag to its neuPrint server and dataset name (`malecns_v1.0 → neuprint.janelia.org / male-cns:v1.0`, `flywire-fafb-v783b → neuprint-cns.janelia.org / flywire-fafb:v783b`); `SIDE_CHAR`, `FLYWIRE_SIDE_CHAR`, `HIT_THRE = 0.1`, `N_FLOW = 20`; defaults for `SEGMENTATION_SOURCE`, `SHELL_SOURCE`. `.env` supplies only secrets and overrides: `config.py` calls `load_dotenv(PROJECT_ROOT / ".env", override=False)` at import (a missing file is fine) before reading any override, and no other module calls `find_dotenv`
- [ ] Replace every module-level `Path(find_dotenv()).parent` anchor with config paths (`malecns.py:45`, `download_eyemaps.py:37`, `roi_assets.py:23`, `make_roi_assets.py:53`, `plotter.py:89,127,211,290,1445`); `plotter.py` / `make_roi_assets.py` read the two sources from config instead of asserting on `os.environ`; key the skeleton and mesh caches by the registry tag (`cache/skeletons/malecns_v1.0/`, via reverse lookup of `client.dataset`; never the raw `male-cns:v1.0`, a colon is invalid on Windows)
- [ ] Make the neuPrint connection lazy so importing never needs a network or token; the getter raises a clear error naming `.env` and `NEUPRINT_APPLICATION_CREDENTIALS` instead of returning `False`, and the `plotter` fetches go through it
- [ ] Rewrite every `utils.*` / `setup_data.*` import: internal (`malecns.py:30`, `plotter.py:35-36`), all six notebooks including mid-notebook imports (`plotting.ipynb`: `utils.plotter`, incl. private `_CNS_RANGE_X/Y` → make public; `receptive_fields.ipynb`: `setup_data.malecns`), and Pixi task paths (`download-eyemaps`)
- [ ] Tests in `tests/`: every module imports with no `.env`; `import flyem_analysis` works from a directory other than the root; no notebook `.py` pair contains `from utils` or `setup_data`; a temporary `.env` setting `FLYEM_DATA_DIR` changes `DATA_DIR`; no cache path contains `:`; `load_inprop()` equals `build_sparse_matrices`' inprop (CSC, float32) on a toy edge list; `add_coords2` on meta without `coords2` reproduces the cached column. Mark tests that need data or a token with `@pytest.mark.data` / `@pytest.mark.neuprint`
- [ ] Give public functions docstrings and type hints; keep private helpers prefixed with `_`
- [ ] Write a short `CHANGELOG.md` so users of forks can see what changed in the shared library

## Phase 2: Data download

The main blocker for newcomers. Depends only on Phase 1 and the existing `cache/data/` files, not on Build. Until hosting is decided, `fetch-data` can point at a temporary shared-drive or local source.

- [ ] Host the prebuilt files: `malecns_v1.0_meta.csv`, `_prop.npz`, flow-layer CSVs, FlyWire `flywire-fafb-v783b_*` (about 160 MB in total). `inprop` is not hosted: `data.load_inprop()` derives it from `prop` (divided by column sums, as in `malecns.py:437-443`), checked with `np.allclose(colsum[colsum > 0], 1, atol=1e-5)`. Do not rebuild via s1 (re-queries neuPrint and overwrites meta/prop that were backfilled with `coords2`)
- [ ] Add `pixi run fetch-data`: downloads into `config.DATA_DIR` (default `cache/data/`) via `*.part`, verifies SHA-256, then `os.replace` (works on Windows; on `PermissionError` say "close notebooks using cache/data and rerun"); skips a file only when its existing hash matches; on mismatch re-downloads and says so
- [ ] Keep a `data_manifest.json` in the repo: file name, dataset version, hash, build date, source script version

## Phase 3: Tutorials and documentation

Each tutorial teaches one idea, runs top to bottom in a few minutes, and is built from material that already exists. `02`–`04` read only cached data and never call `connect()`; `00`, `01`, `05` need a token. Each tutorial passes Restart & Run All before it is committed.

| Tutorial | Teaches | Built from |
| --- | --- | --- |
| `00_setup` | Environment check, token, `fetch-data` | `test_dependencies.py`, notebook setup cells |
| `01_query_neuprint` | Fetch neurons, synapses, adjacencies | `olc_client.py`, neuprint-python calls in notebooks |
| `02_connectivity_matrices` | `meta`, `prop` vs `inprop`, instance vs type | Data sections of `pathways.ipynb`; `load_inprop()` |
| `03_pathways` | Effective weights, barcode plots, multi-hop paths | `pathways.ipynb` minus the unfinished flow-layer section; move the `input_types`/`output_types` and `inidx`/`outidx` cells above the barcode section and define `idx_to_sign = dict(zip(meta.idx, meta.sign))` (as in `receptive_fields.ipynb`); drop the `connect` cell and unused `fetch_adjacencies` import |
| `04_receptive_fields` | Hex lattice, one eye vs both eyes, `coords2` | `receptive_fields.ipynb`; drop the `connect` cell and unused `fetch_adjacencies` import |
| `05_plot_neurons` | Skeletons, meshes, brain outlines | `plotting.ipynb`, `roi_assets.py` |

The three paper-figure notebooks move to `examples/paper_figs/`, unchanged except their setup/import cells and one guard: in `paper_figs_visual_pathways_layers`, a missing flow file raises `FileNotFoundError("run pixi run fetch-data")` unless `RECOMPUTE_FLOW = True` is set (the recompute takes about 3 h on one core).

- [ ] `README.md`: two-command quickstart (`pixi install`, `pixi run fetch-data`) for `02`–`04`; for `00`, `01`, `05` also "copy `.env.example` to `.env` and add your token"; how to get a neuPrint token, datasets covered, data provenance, where to ask for help
- [ ] `.env.example` (done: neuPrint server, dataset, token placeholder, `SEGMENTATION_SOURCE`, `SHELL_SOURCE`, plotting backends, `CI_DEV_PATH`): add `FLYEM_DATA_DIR` once `config.py` exists, and keep the source values in sync with the `config.py` defaults
- [ ] Glossary (README section or `docs/glossary.md`): `prop`, `inprop`, instance, type, hex1/hex2, `coords2`, effective connectivity, flow layers
- [ ] `CLAUDE.md` / `AGENTS.md`: fill Key Concepts from the glossary and point to the package layout, so AI assistants give correct answers
- [ ] `CONTRIBUTING.md`: how changes get into the shared library versus a personal fork
- [ ] Source notes: a one-line "Adapted from <repo>, <path or commit>" header in each copied file (`plotter.py`, `ng_view.py`, `ol_rf.py`, `roi_assets.py`) and a `params/README.md` entry for the column pins. Confirm the uncertain origins (`plotter.py`, `ng_view.py`, `ol_rf.py`) against the local clones of the paper repos
- [ ] README "Acknowledgements and third-party code" section built from the tables in Current state; check each source repository's licence is compatible before the repo goes public (see Audience)

## Phase 4: Dependencies, automated checks and data build

Keep the environment reproducible for people who did not build it, and catch breakage before a newcomer does.

**Dependencies**

- [ ] Upstream the `connectome_interpreter` changes on `az-eyemap-path` and the `navis` fork commit, or pin both to tags that will not move. First check what each fork adds that upstream lacks: `eyemap_dir=` in `hex_heatmap` / `plot_mollweide_projection` (tutorial `04`), and whatever `find_instance_flow` needs from the navis fork
- [ ] Keep `pixi.lock` committed; note in the README that a PyPI-to-conda swap needs a clean `.pixi` rebuild (stale pip files caused an OpenMP crash before)
- [ ] List `trimesh` explicitly, since the optic-lobe notebook imports it directly
- [ ] Add `ruff` (lint and format) to the pre-commit hooks set up in Phase 0

**Automated checks (GitHub Actions)**

- [ ] On every push: `pixi install` on Linux and Windows, import every module, run `pytest -m "not data and not neuprint"`, and fail if any `.py`/`.ipynb` pair is out of sync
- [ ] On pull requests, a "fresh clone" job on ubuntu, windows and macos (arm64): clean checkout, `pixi install`, `pixi run fetch-data` (data restored from an Actions cache), the remaining tests, and every notebook in `tutorials/` executed with nbconvert. `02`–`04` run with the neuPrint variables unset; `00`, `01`, `05` skip when no token secret is available (fork PRs). Needs data hosting reachable from GitHub Actions (see Data hosting)
- [ ] Weekly, the same job with the Actions cache disabled, so `fetch-data` does a real cold download; it times `pixi install`, `fetch-data` and executing `02`, and fails above 15 minutes. The on-demand run also executes the gallery
- [ ] Replace `test_dependencies.py` with `pixi run smoke`, which imports the real stack (`neuprint`, `navis`, `connectome_interpreter`, `torch`, `cloudvolume`, `flybrains`) and runs one tiny neuPrint query

**Data build (independent track; blocks none of the success criteria)**

- [ ] Rewrite `local/s1_malecns_data.py`, `local/s1_flywirefafb_data.py`, `local/s2_layers.py` as functions in `data/build.py` (today they are top-level percent scripts that connect and download at import); `local/flow.py` becomes `data/flow.py` (no more `import flow as sd`). They need only `neuprint_client`, `data/malecns.py`, `flow.py` and `config`
- [ ] Later item, after the build works: bring `ol_rf.py`, s1 section 6 (input RF data) and `s3_effconn.py` into the shared library. Recover or rewrite the eight missing modules it needs, move `deferred/ol_rf.py` to `src/flyem_analysis/rf.py`, and add `s3_effconn` as an optional `build-data` step
- [ ] Connect from the config dataset registry, not `.env` defaults; take the file prefix from the registry tag (not `c.dataset.split('_')[-1]`, which gives `male-cns:v1.0`); make `save_outputs` take the full prefix instead of hard-coding `malecns_`
- [ ] Expose it as `pixi run build-data --dataset malecns_v1.0`: writes to `cache/build/{dataset}/`, never `cache/data/`; each step writes to a temporary directory and renames on success; skips a step only when its build-manifest entry is complete and the hash matches, unless `--force`; the build manifest is promoted to `data_manifest.json` deliberately
- [ ] Acceptance check against the hosted files: matrix shape and nnz, meta columns and row count, flow CSV columns (`idx`, `hitting_time`, `instance`) and row count (162,084 for `malecns_v1.0`)
- [ ] Note in the README which steps are slow (the flow hitting-time file took 2 h 56 min on one core, about 4.5 GB RAM) and which can go to the cluster

## Open decisions

These change what gets built. Data hosting blocks only the final source URL in Phase 2; the others need answers before Phase 1 starts.

| Decision | Options | Affects |
| --- | --- | --- |
| Audience | Janelia-internal only, or public | Data hosting, token instructions, whether cluster paths may appear in docs, licence check for copied code |
| Data hosting | Janelia shared drive, Zenodo record, GitHub release assets | `fetch-data` implementation, access control, versioning, whether CI can reach the data |
| Maintenance model | Shared library kept stable with releases, or copy-and-diverge starter | Effort on tests, changelog and versioning |
| Package name | `flyem_analysis` or another | Imports in every notebook; rename is cheapest now |
| Owners | One owner per phase | Who reviews pull requests into `main` |

Suggested order: Phase 0 this week, then Phase 1 (package, config, import migration, import tests), then Phase 2 (download), then 3, then 4. The data build in Phase 4 can run in parallel at any point after Phase 1.
