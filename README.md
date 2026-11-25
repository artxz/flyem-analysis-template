# flyem-analysis-starter

A starting point for analysing FlyEM connectome data (male CNS, FlyWire/FAFB): a reproducible
Pixi environment, data loaders, a small tested library (`flyem_analysis_starter`) and tutorial
notebooks. Work in progress; see [docs/plan.md](docs/plan.md).

## Setup

### Prerequisites

Install [Pixi](https://pixi.sh):

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

### Install dependencies

```bash
pixi install
```

### Launch Jupyter Lab

```bash
pixi run lab
```

This starts Jupyter Lab with Jupytext auto-sync enabled — notebooks (`.ipynb`) and Python scripts (`.py`) are kept in sync automatically.

## Project Structure

```
├── pixi.toml                    # environment and tasks
├── pyproject.toml               # package metadata, Jupytext and pytest config
├── .env.example                 # neuPrint token and optional overrides
├── src/flyem_analysis_starter/  # the library (installed editable by `pixi install`)
│   ├── config.py                # DATA_DIR, CACHE_DIR, dataset registry
│   ├── neuprint_client.py       # lazy neuPrint connection
│   ├── data/                    # load meta, prop, inprop, flow layers
│   ├── eyemap/                  # eye maps, hex coordinates
│   ├── plotting/                # neurons over brain outlines
│   └── params/                  # lookup tables shipped with the package
├── tutorials/                   # notebooks (.ipynb paired with .py)
├── deferred/                    # code waiting for missing dependencies
└── tests/
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Data

Download the prebuilt files of the default dataset into `DATA_DIR` (add
`--dataset <tag>` for another one, or `--all`):

```bash
pixi run fetch-data
```

Maintainers can rebuild them from neuPrint (needs the token in `.env`) into
`cache/build/<tag>`, and check them against the downloaded files with `--compare`:

```bash
pixi run build-data --dataset malecns_v1.0 --compare
```

Run times on a laptop:

| Step | Male CNS | FlyWire |
|---|---|---|
| `matrices` (meta and connectivity) | about 16 min | about 6 min |
| `flow` (hitting-time layers) | about 5 min | not yet measured |

The flow step was about 3 hours with navis 1.11. It is fast now because the pixi
environment uses navis with the batched `BayesianTraversalModel`
(navis-org/navis#202). `config.FLOW_METHOD = "legacy"` keeps the results
byte-identical to the published files.

## Verify Installation

```bash
pixi run python test_dependencies.py
```
