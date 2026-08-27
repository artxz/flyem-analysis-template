# flyem_analysis_template

Add your project description here.

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
├── pixi.toml                    # Pixi dependency config
├── pyproject.toml               # Python project metadata + Jupytext config
├── jupyter_server_config.py     # Notebook ↔ .py auto-sync
├── .env.example                 # Environment variable template
├── test_dependencies.py         # Dependency validation script
├── CLAUDE.md                    # AI assistant context
└── src/
    └── flyem_analysis_template/
        └── __init__.py
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Verify Installation

```bash
pixi run python test_dependencies.py
```
