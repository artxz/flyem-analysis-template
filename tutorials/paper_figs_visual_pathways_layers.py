# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Layer distribution of optic-lobe cell types: Hoeller, Zhao et al., Fig. S1A
#
# `local/papers/mcns-visualpathway.pdf` is the supplementary information of *The organization
# of visual pathways in the Drosophila brain* (Cell 189, 2026), so its first figure is
# **Fig. S1**. Panel A shows the normalized distribution of hierarchical layers across
# right-optic-lobe cell types, split by cell group (left) and by neurotransmitter type
# (right): one marker+line trace per group, fraction of cell types per integer layer bin.
#
# Code base: [reiserlab/visualpathways](https://github.com/reiserlab/visualpathways)
#
# - `setup_data/s2_layers.py` + `setup_data/flow.py::fetch_instance_flow`: per-neuron
#   hitting times ("layers") with `connectome_interpreter.find_instance_flow`, seeded from the
#   right-eye visual inputs (20 steps, threshold 0.1)
# - `utils/core_data.py::_ensure_ol_sidecars`: per-cell-type median layer for the right OL
# - `utils/plotting_flow.py::plot_flow_by_main_groups` / `plot_flow_by_sign` and
#   `utils/plotting_shared.py::_hist_lines`: the plot
# - `utils/palettes.py::load_colors`: colours
#
# Inputs are the cached files the other tutorials use (`cache/data/malecns_v1.0_meta.csv`,
# `_prop.npz`). The layers need one information-flow run over the whole connectome
# (about an hour); its result is cached in `cache/data/` and reused.

# %% [markdown]
# ## Set up

# %%
"""
This cell does the initial project setup.
A script with this code uses the location of the `.env` file as the anchor for
the whole project (= PROJECT_ROOT). Add `src` directory to sys path.
"""
from pathlib import Path
import sys
from dotenv import load_dotenv, find_dotenv
load_dotenv()
PROJECT_ROOT = Path(find_dotenv()).parent
sys.path.append(str(PROJECT_ROOT.joinpath('src')))
print(f"Project root directory: {PROJECT_ROOT}")

# %%
import numpy as np
import pandas as pd
import scipy.sparse as sp
import plotly.graph_objects as go
import connectome_interpreter as ci

# %%
dataset = 'malecns_v1.0'
data_folder = PROJECT_ROOT / 'cache' / 'data'
side = 'r'                 # flow is seeded from the right eye and analysed for right-OL types
n_steps, hit_thre = 20, 0.1

# %% [markdown]
# ## Neuron metadata: cell groups and signs
#
# The paper takes the groups from Nern et al. Supplementary Table 1 (`main groups`, with
# ONIN + ONCN merged into VIN, and the photoreceptor/lamina seed types set to "visual
# input"). The male CNS `superclass` encodes the same partition, so it is used directly:
# `ol_intrinsic` -> VIN (visual interneurons), `visual_projection` -> VPN,
# `visual_centrifugal` -> VCN. Signs follow `core_data._load_meta_groups`: +1 acetylcholine,
# -1 GABA/glutamate, 0 for everything else.

# %%
meta = pd.read_csv(data_folder / f'{dataset}_meta.csv', index_col=0).reset_index()

SEED_TYPES = ['L1', 'L2', 'L3', 'R7', 'R8', 'R7d', 'R8d', 'HBeyelet']
GROUP_OF_SUPERCLASS = {'ol_intrinsic': 'VIN', 'visual_projection': 'VPN', 'visual_centrifugal': 'VCN'}
meta['main_groups'] = meta.superclass.map(GROUP_OF_SUPERCLASS).fillna('other')
meta.loc[meta.cell_type.isin(SEED_TYPES), 'main_groups'] = 'visual input'
meta['sign'] = meta.nt.map({'acetylcholine': 1, 'gaba': -1, 'glutamate': -1}).fillna(0).astype(int)
meta.main_groups.value_counts()

# %% [markdown]
# ## Layers: information-flow hitting times
#
# `find_instance_flow` propagates activity from the seed instances through the
# input-normalized connectivity and records, for every neuron, the step at which its
# cumulative input first exceeds `hit_thre` (its "layer"). It writes
# `{dataset}_{side}_flow_{n_steps}step_{hit_thre}thre_hit.csv` (per neuron) and
# `..._hit_per_group.csv` (per instance). This is the slow step (about an hour); it is
# skipped when the file exists.

# %%
flow_file = data_folder / f'{dataset}_{side}_flow_{n_steps}step_{hit_thre}thre_hit.csv'
if not flow_file.exists():
    prop = sp.load_npz(data_folder / f'{dataset}_prop.npz').tocsc()        # pre in rows, post in columns
    total_post = np.asarray(prop.sum(axis=0)).ravel().astype(float)
    inprop = prop.multiply(np.divide(1.0, total_post, out=np.zeros_like(total_post),
                                     where=total_post != 0)).tocsc().astype(np.float32)
    ci.find_instance_flow(
        inprop, dict(zip(meta.idx, meta.instance.fillna('unknown'))),
        flow_seed_groups=[f'{t}_{side.upper()}' for t in SEED_TYPES],
        file_path=str(data_folder), save_prefix=f'{dataset}_{side}_flow_',
        flow_steps=n_steps, flow_thre=hit_thre,
    )
flow = pd.read_csv(flow_file).rename(columns={'cell_group': 'instance'})
flow.head()

# %% [markdown]
# Per-cell-type layer = median over the neurons of the instance, for right-OL cell types
# (`_ensure_ol_sidecars`: right-side instances of the OL groups, without the R1-R6 stand-in).

# %%
flow = flow.merge(meta[['idx', 'cell_type', 'main_groups', 'sign']], on='idx', how='left')
ol_neurons = flow[flow.instance.str.endswith(f'_{side.upper()}')
                  & (flow.main_groups != 'other')
                  & (flow.instance != f'R1-R6_{side.upper()}')]
flow_type = (ol_neurons.groupby('instance')
             .agg(cell_type=('cell_type', 'first'), hitting_time=('hitting_time', 'median'),
                  sign=('sign', 'first'), main_groups=('main_groups', 'first'), count=('idx', 'size'))
             .reset_index())
print(f'{len(flow_type)} right-OL cell types')
flow_type.groupby('main_groups').hitting_time.describe()[['count', '50%', 'min', 'max']]

# %% [markdown]
# ## Plot (`plotting_shared._hist_lines`)

# %%
AXIS = dict(showline=True, linewidth=1, linecolor='black', mirror=True,
            ticks='outside', ticklen=5, tickcolor='black')


def hist_lines(df, val, col, bins, color_df, *, names=None, height=400, width=500, norm=True):
    """One marker+line trace per group in `df[col]`: histogram of `df[val]` over `bins`,
    normalized to a fraction of the group's cell types."""
    fig = go.Figure()
    centers = (bins[:-1] + bins[1:]) / 2
    for group in color_df.index:
        sub = df[df[col] == group]
        if sub.empty:
            continue
        counts, _ = np.histogram(sub[val], bins=bins)
        if norm:
            counts = counts / counts.sum()
        fig.add_trace(go.Scatter(
            x=centers, y=counts, mode='markers+lines',
            name=str(names[group] if names else group),
            marker=dict(color=color_df.loc[group, 'color']),
            line=dict(color=color_df.loc[group, 'color']),
        ))
    fig.update_layout(
        font=dict(family='arial', size=18), xaxis_title=val,
        xaxis_range=[bins[0], bins[-1]],
        paper_bgcolor='white', plot_bgcolor='white',
        height=height, width=width,
    )
    fig.update_xaxes(title_standoff=0, **AXIS)
    fig.update_yaxes(title_standoff=2, **AXIS)
    return fig


# colours from `utils/palettes.py::load_colors`
colored_main_groups = pd.DataFrame(['#90f0a6', '#ffc4e2', '#64a0d1', '#cc9e4f'],
                                   index=['visual input', 'VIN', 'VPN', 'VCN'], columns=['color'])
colored_sign = pd.DataFrame(['#EE672D', '#979DA5', '#1F4695'], index=[1, 0, -1], columns=['color'])
sign_names = {1: 'excitatory', 0: 'other', -1: 'inhibitory'}

layer_bins = np.arange(-0.5, 6.5, 1)
layer_axes = dict(xaxis_title='layer', xaxis_range=[-.1, 5.1], xaxis_tickvals=[0, 1, 2, 3, 4, 5],
                  yaxis_title='frac. cell types', yaxis_range=[-.01, 1.01])

# %%
# Fig. S1A left: by cell group
fig = hist_lines(flow_type, 'hitting_time', 'main_groups', layer_bins, colored_main_groups)
fig.update_layout(**layer_axes)
fig.show()

# %%
# Fig. S1A right: by neurotransmitter type
fig = hist_lines(flow_type, 'hitting_time', 'sign', layer_bins, colored_sign, names=sign_names)
fig.update_layout(**layer_axes)
fig.show()
