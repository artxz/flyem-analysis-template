# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: default
#     language: python
#     name: python3
# ---

# %%
# %load_ext autoreload
# %autoreload 2

# %%
"""
Project setup. `flyem_analysis_starter` is installed in the Pixi environment, so no
path setup is needed. Importing `config` reads `.env` (if present) for the neuPrint
token and optional overrides; `config.DATA_DIR` is where the downloaded data lives.
"""
from pathlib import Path
import sys

from flyem_analysis_starter import config, data
print(f"Data folder: {config.DATA_DIR}")

# Prefer a local connectome_interpreter checkout (CI_DEV_PATH in .env) over the
# pixi-installed wheel, so edits in the fork take effect via %autoreload 2.
# insert(0, ...) is required: it must precede site-packages in the search order.
import os
ci_dev_path = os.environ.get('CI_DEV_PATH')
if ci_dev_path and Path(ci_dev_path).is_dir():
    sys.path.insert(0, str(Path(ci_dev_path)))
    print(f"connectome_interpreter dev clone: {ci_dev_path}")
else:
    print("connectome_interpreter: using the pixi-installed package")

# %%
from flyem_analysis_starter.neuprint_client import connect
c = connect(verbose=True)

# %%
import pandas as pd
import numpy as np
import scipy as sp

import plotly.graph_objects as go
import matplotlib.pyplot as plt

import navis
from neuprint import fetch_adjacencies
import connectome_interpreter as ci

# Guard against silently falling back to the pixi-installed copy.
print(f"connectome_interpreter loaded from: {ci.__file__}")

# %%
dataset = 'malecns_v1.0'
# dataset = 'fafb_all_neurons'

data_dir = config.DATA_DIR

results_dir = config.PROJECT_ROOT / 'results' / dataset
results_dir.mkdir(parents=True, exist_ok=True)

# %% [markdown] id="w7A8Y5Xnim_B"
# # Plot neurons with rois

# %% [markdown]
# ## whole cns, front view

# %%
from flyem_analysis_starter.plotting import plot_3d_cns, save_figure

# %%
fig = plot_3d_cns(
    10012, show_meshes=True, show_outline=True, color='green', zoom=3.5,
    scatter_kws={'mode': 'lines', 'black': 'white', 'opacity': 1},
    width=600, height=350)
# fig.update_traces(line={'width': 5}, selector={'type': 'scatter3d'})
fig.data[-1].line.width = 5 

# fig = plot_cns(None, show_meshes=False, color='green',show_outline=True, zoom=3.5, width=600, height=350)
# fig = plot_cns(10012, show_meshes=True, color='green',show_outline=False, zoom=3.5, width=600, height=350)
fig.show()

# %%
# save_figure(fig, Path(results_dir, "cns_outline.pdf"))
save_figure(fig, Path(results_dir, "VS1.png"))
# fig.write_image(Path(results_dir, "cns_outline.pdf"))

# %%
from flyem_analysis_starter.plotting import get_outline_cns

pts = np.asarray(get_outline_cns())        # (3052, 3), all at z=30001 — a planar ring

fig = go.Figure(go.Scatter(
    x=pts[:, 0], y=pts[:, 1],
    mode='lines',
    line={'color': 'black', 'width': 5},
    hoverinfo='skip',
))
fig.update_layout(
    width=600, height=350,
    margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
    showlegend=False,
    paper_bgcolor='#fff', plot_bgcolor='#fff',
    xaxis={'visible': False, 'range': [5000, 91000]},
    yaxis={'visible': False, 'range': [53000, 5000],   # reversed = anterior view
           'scaleanchor': 'x', 'scaleratio': 1},
)

out = Path(results_dir, "cns_outline.pdf")
fig.write_image(out)      # .pdf / .eps work the same way
fig.show()

# %%
from flyem_analysis_starter.plotting import get_outline_cns, CNS_RANGE_X, CNS_RANGE_Y

pts = np.asarray(get_outline_cns())          # (3052, 3), planar ring at z=30001

# same camera basis as plot_3d_cns: eye=-z, up=[-0.05,-1,0]  ->  2.86 deg roll
up = np.array([-0.05, -1.0, 0.0])
up /= np.linalg.norm(up)                     # screen "up" in world coords
right = np.array([-up[1], up[0], 0.0])       # = cross(view_dir=+z, up)

center = np.array([np.mean(CNS_RANGE_X), np.mean(CNS_RANGE_Y), 0.0])
rel = pts - center
xs, ys = rel @ right, rel @ up               # project onto the screen basis

# frame it like the 3-D scene: the CNS box rotated by the same amount
corners = np.array([[x, y, 0.0] for x in CNS_RANGE_X for y in CNS_RANGE_Y]) - center
half_x, half_y = np.abs(corners @ right).max(), np.abs(corners @ up).max()

fig = go.Figure(go.Scatter(
    x=xs, y=ys,
    mode='lines',
    line={'color': 'black', 'width': 5},
    hoverinfo='skip',
))
fig.update_layout(
    width=600, height=350,
    margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
    showlegend=False,
    paper_bgcolor='#fff', plot_bgcolor='#fff',
    xaxis={'visible': False, 'range': [-half_x, half_x]},
    yaxis={'visible': False, 'range': [-half_y, half_y],
           'scaleanchor': 'x', 'scaleratio': 1},
)

out = Path(results_dir, "cns_outline.pdf")
out.parent.mkdir(parents=True, exist_ok=True)
fig.write_image(out)
fig.show()

