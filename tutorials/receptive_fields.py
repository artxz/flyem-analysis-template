# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
# %load_ext autoreload
# %autoreload 2

# %% [markdown]
# ### Set up

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
from utils import olc_client
c = olc_client.connect(verbose=True)

# %%
import pandas as pd
import numpy as np
import scipy as sp

import plotly.graph_objects as go
import plotly.express as px
import matplotlib.pyplot as plt

import navis
import neuprint
from neuprint import fetch_adjacencies
import connectome_interpreter as ci

# Guard against silently falling back to the pixi-installed copy.
print(f"connectome_interpreter loaded from: {ci.__file__}")

# %%
# import sys
# import os
# from pathlib import Path
# PROJECT_ROOT = Path(os.path.dirname(os.getcwd()))
# sys.path.append(str(PROJECT_ROOT.joinpath('src')))

# from connectome_interpreter import *

# %%
dataset = 'malecns_v1.0'
# dataset = 'fafb_all_neurons'

data_folder = Path(PROJECT_ROOT, 'cache', 'data')

# Eyemap dataset folder, holding right.xlsx and left.xlsx as written by
# `pixi run download-eyemaps`. The plot functions take the folder and pick the
# file(s) themselves via `which_eye`.
eyemap_dir = Path(PROJECT_ROOT, 'params', 'eyemaps', 'eyemap_mcns_f20240701')

results_folder = PROJECT_ROOT / 'results' / dataset
results_folder.mkdir(parents=True, exist_ok=True)

# %% [markdown]
#

# %% [markdown] id="w7A8Y5Xnim_B"
# # Getting data

# %% [markdown] id="anHL7BwJ2AlU"
# `meta` contains information about neurons. <br>
# `conn_mat` is direct connectivity, without signs.
#
# Optional: remove connections between specified cell types

# %% [markdown]
# ## Neuron information

# %%
# get meta
# the idx column records the index of the neuron in inprop
meta = pd.read_csv(data_folder / f'{dataset}_meta.csv', index_col = 0).reset_index()
meta.shape

# %%
# simplify neurotransmitter types and define colors
meta['nt'] = meta['nt'].replace(['histamine', 'dopamine', 'octopamine', 'serotonin'], 'other')          
nt_to_color = {'acetylcholine': '#EE672D', 'glutamate': '#09A64D', 'gaba': '#1F4695', 'other': '#979DA5', 'unclear': '#979DA5'}

#signs from neurotransmitter types
meta['sign'] = meta['nt'].replace({'acetylcholine': 1, 'glutamate': -1, 'gaba': -1, 'other': 1, 'unclear': 1})
#make L1 excitatory
idx_L1 = meta[meta.cell_type == 'L1'].idx.tolist()
meta.loc[idx_L1, 'sign'] = 1

# %%
# make dictionaries that map indices to meta info
idx_to_type = dict(zip(meta.idx, meta.cell_type))
idx_to_instance = dict(zip(meta.idx, meta.instance))
idx_to_coords = dict(zip(meta.idx, meta.coords))
idx_to_root = dict(zip(meta.idx, meta.bodyId))
idx_to_sign = dict(zip(meta.idx, meta.sign))

# %%
# the cell types one can get hex coordinates for
coord_types = meta[~meta.coords.isna()].instance.unique()
coord_types

# %% [markdown]
# ## Propagated connectivity

# %%
# connectivity is a sparse matrix
# pre in rows, post in columns
conn_mat = sp.sparse.load_npz(data_folder / f'{dataset}_prop.npz') #full integer weights

# normalize to get input-normalized weights
total_post = conn_mat.sum(axis=0).A1.astype(float)
col_sums_with_inversion = np.reciprocal(
    total_post, where=total_post != 0
)
conn_mat = conn_mat.multiply(col_sums_with_inversion)
conn_mat = conn_mat.astype(np.float32)

# %% [markdown]
# ## Optional: remove certain connections
# Remove weights between all cell types that start with strings defined by type_del_pre and type_del_post

# %%
# type_del_pre = 'Mi1'
# type_del_post = 'T4a'

# idx_pre = np.array([meta.loc[i,'idx'] for i in meta.index if meta.loc[i,'cell_type'].startswith(type_del_pre)])
# idx_post = np.array([meta.loc[i,'idx'] for i in meta.index if meta.loc[i,'cell_type'].startswith(type_del_post)])

# conn_mat = modify_coo_matrix(conn_mat, idx_pre, idx_post, 0, re_normalize=False)
# conn_mat = conn_mat.tocsc()

# %% [markdown] id="L-gShtZ6H4Lh"
# # anatomical receptive field (ARF)
# Manually specify the following: <br>
# `input_types` is a list of cell types which we treat as inputs. <br>
# `output_types` is a list of cell types which we treat as outputs. <br>
# `nr_hops_max` is the maximum number of hops (steps) allowed in the path search between input and output neurons. <br>
# `direct_thre` is a lower threshold on the direct input-normalized connectivity. If 0 then all connections are considered. <br>
# `signed` indicates whether to use signs (True) or not (False)
#
# Notes: <br>
# `inidx` and `outidx` below we also constrain the `input_types` and `output_types` to be on the right side only. <br>
# `combining_method` below takes the mean connectivity over post neurons but is summed over pre neurons. <br>
# Setting `nr_hops_max` too large (>4) could be slow. Check the plot of the summed effective input weight below. <br>
# If `signed=True` then GABA and glutamate are treated as inhibitory and everything else as excitatory.

# %%
# input_types = ['L1', 'L2', 'L3', 'R8', 'R8d', 'R7', 'R7d', 'HBeyelet']
input_types = ['L1', 'L2', 'L3', 'R8', 'R8d', 'R7', 'R7d']

# output_types = ['T4a', 'T4b', 'T4c', 'T4d']
# output_types = ['T4a']
# output_types = ['LC10a']
# output_types = ['AOTU016_b']
output_types = ['ER4d']

nr_hops_max = 4

direct_thre = 0.00001

signed = True

# %%
# find connectivity indices and print how many neurons
inidx = meta.idx[meta.cell_type.isin(input_types) & (meta.side=='right')]
print('Number of {} neurons: {}'.format(input_types, inidx.shape[0]))
outidx = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='right')]
print('Number of {} neurons: {}'.format(output_types, outidx.shape[0]))

# %%
# summed effective input weights per number of hops
path_lengths = list(range(1, nr_hops_max + 1))
summed_weights = []

for i in path_lengths:
    paths = ci.find_paths_of_length(conn_mat, inidx, outidx, i)
    if (paths is None) or (paths.empty):
        summed_weights.append(0)
        continue

    paths = ci.filter_paths(paths, direct_thre)
    if (paths is None) or (paths.empty):
        summed_weights.append(0)
        continue

    if not signed:
        tmp_df = ci.effective_conn_from_paths(paths, wide=False)
        tmp_df = ci.group_paths(tmp_df, idx_to_type, idx_to_type, combining_method='mean')
        tmp_df = tmp_df.pivot(index='pre', columns='post', values='weight').fillna(0)
    else:
        tmp_df_e, tmp_df_i = ci.signed_effective_conn_from_paths(paths, wide=False, idx_to_nt=idx_to_sign)
        tmp_df_e = ci.group_paths(tmp_df_e, idx_to_type, idx_to_type, combining_method='mean')
        tmp_df_i = ci.group_paths(tmp_df_i, idx_to_type, idx_to_type, combining_method='mean')
        tmp_df_e = tmp_df_e.pivot(index='pre', columns='post', values='weight').fillna(0)
        tmp_df_i = tmp_df_i.pivot(index='pre', columns='post', values='weight').fillna(0)
        tmp_df = tmp_df_e.sub(tmp_df_i, fill_value=0)

    summed_weights.append(tmp_df.abs().values.sum())

fig = px.line(x=path_lengths, y=summed_weights, markers=True)
fig.update_xaxes(range=[0.9, nr_hops_max+.1], title='number of hops')
fig.update_yaxes(title='summed effective input weight')
fig.show()


# %%
#pick the output bodyIds of which the RF shall be shown (change by slider)
outidx_r = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='right')][:1]
outidx_l = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='left')][:1]
rfidx = pd.concat([outidx_r, outidx_l])
rfidx

# %%

# %% [markdown]
# ## one eye
#
# Important:<br>
# `inidx` should refer to input neurons from one side only (left or right). <br>
# This left vs right choice should be consistent with `which_eye` during plotting. <br>
# Use `coords` and `idx_to_coords` to map the effective weights to ME column coordinates. <br>
#
# ARFs are summed over all input bodyIds and input cell types <br>
# `hex_heatmap`: effective weights in ME column coordinates <br>
# `plot_mollweide_projection`: effective weights in visual space (after eyemap)

# %%
# find connectivity indices and print how many neurons
inidx = meta.idx[meta.cell_type.isin(input_types) & (meta.side=='right')]
print('Number of {} neurons: {}'.format(input_types, inidx.shape[0]))
outidx = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='right')]
print('Number of {} neurons: {}'.format(output_types, outidx.shape[0]))

# %%
#pick the output bodyIds of which the RF shall be shown (change by slider)
outidx_r = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='right')][:1]
outidx_l = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='left')][:1]
rfidx = pd.concat([outidx_r, outidx_l])
rfidx

# %%

all_coords = meta['coords'].dropna().unique()
df = pd.DataFrame(
    np.zeros((len(all_coords), len(rfidx))), 
    index=all_coords, 
    columns=rfidx.map(idx_to_root).values)
for i in range(1, nr_hops_max + 1):
    paths = ci.find_paths_of_length(conn_mat, inidx, rfidx, i)
    if (paths is None) or paths.empty:
        continue
    paths = ci.filter_paths(paths, direct_thre)
    if (paths is None) or (paths.empty):
        continue

    # grouping (relabelling pre -> coords, post -> rootId) is no longer done inside
    # effective_conn_from_paths()/signed_effective_conn_from_paths(); call group_paths()
    # explicitly on the long-format output, then pivot to wide ourselves.
    if not signed:
        tmp_df = ci.effective_conn_from_paths(paths, wide=False)
        tmp_df = ci.group_paths(tmp_df, idx_to_coords, idx_to_root, combining_method='mean')
        tmp_df = tmp_df.pivot(index='pre', columns='post', values='weight').fillna(0)
    else:
        tmp_df_e, tmp_df_i = ci.signed_effective_conn_from_paths(paths, wide=False, idx_to_nt=idx_to_sign)
        tmp_df_e = ci.group_paths(tmp_df_e, idx_to_coords, idx_to_root, combining_method='mean')
        tmp_df_i = ci.group_paths(tmp_df_i, idx_to_coords, idx_to_root, combining_method='mean')
        tmp_df_e = tmp_df_e.pivot(index='pre', columns='post', values='weight').fillna(0)
        tmp_df_i = tmp_df_i.pivot(index='pre', columns='post', values='weight').fillna(0)
        tmp_df = tmp_df_e.sub(tmp_df_i, fill_value=0)
    tmp_df = tmp_df[(tmp_df.index != "nan") & (~tmp_df.index.isnull())] #remove inputs without column assignment
    tmp_df.columns = tmp_df.columns.astype(int)
    df.loc[tmp_df.index, tmp_df.columns] += tmp_df

# %%
fig = ci.hex_heatmap(df,
                eyemap_dir=eyemap_dir, which_eye='right',
                  custom_colorscale='RdBu_r',
                  global_min=-np.abs(df.values).max(),
                  global_max=np.abs(df.values).max())
fig.show()

# %%
fig = ci.plot_mollweide_projection(
    df,
    eyemap_dir=eyemap_dir, which_eye='right',
    custom_colorscale='RdBu_r',
    global_min=-np.abs(df.values).max(),
    global_max=np.abs(df.values).max())
fig.show()

# %% [markdown]
# ## both eyes 
#
# Important:<br>
# `inidx` should refer to input neurons from both sides. <br>
# `which_eye = 'both'` <br>
# Use `coords2` and `idx_to_coords2` to map the effective weights to ME column coordinates. <br>

# %%
#pick the output bodyIds of which the RF shall be shown (change by slider)
outidx_r = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='right')][:1]
outidx_l = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='left')][:1]
rfidx = pd.concat([outidx_r, outidx_l])
rfidx

# %% [markdown]
# If no `coords2` column in `meta`, run this to attach it
# ```
# from setup_data.malecns import add_coords2
# meta = add_coords2(meta)
# ```

# %%
idx_to_coords2 = dict(zip(meta.idx, meta.coords2))

inidx_both = meta.idx[meta.cell_type.isin(input_types) & meta.side.isin(('right', 'left'))]
print(f'{len(inidx_both)} input neurons ({len(inidx)} on the right alone)')
print(f'{meta.coords2.notna().sum()} neurons carry coords2, '
      f'{meta.coords2.dropna().nunique()} distinct columns')

print('target neurons per side:', meta.loc[meta.idx.isin(rfidx), 'side'].value_counts().to_dict())

# %%
all_coords = meta['coords2'].dropna().unique()
df = pd.DataFrame(
    np.zeros((len(all_coords), len(rfidx))), 
    index=all_coords, 
    columns=rfidx.map(idx_to_root).values)
for i in range(1, nr_hops_max + 1):
    paths = ci.find_paths_of_length(conn_mat, inidx_both, rfidx, i)
    if (paths is None) or paths.empty:
        continue
    paths = ci.filter_paths(paths, direct_thre)
    if (paths is None) or (paths.empty):
        continue

    # grouping (relabelling pre -> coords, post -> rootId) is no longer done inside
    # effective_conn_from_paths()/signed_effective_conn_from_paths(); call group_paths()
    # explicitly on the long-format output, then pivot to wide ourselves.
    if not signed:
        tmp_df = ci.effective_conn_from_paths(paths, wide=False)
        tmp_df = ci.group_paths(tmp_df, idx_to_coords2, idx_to_root, combining_method='mean')
        tmp_df = tmp_df.pivot(index='pre', columns='post', values='weight').fillna(0)
    else:
        tmp_df_e, tmp_df_i = ci.signed_effective_conn_from_paths(paths, wide=False, idx_to_nt=idx_to_sign)
        tmp_df_e = ci.group_paths(tmp_df_e, idx_to_coords2, idx_to_root, combining_method='mean')
        tmp_df_i = ci.group_paths(tmp_df_i, idx_to_coords2, idx_to_root, combining_method='mean')
        tmp_df_e = tmp_df_e.pivot(index='pre', columns='post', values='weight').fillna(0)
        tmp_df_i = tmp_df_i.pivot(index='pre', columns='post', values='weight').fillna(0)
        tmp_df = tmp_df_e.sub(tmp_df_i, fill_value=0)
    tmp_df = tmp_df[(tmp_df.index != "nan") & (~tmp_df.index.isnull())] #remove inputs without column assignment
    tmp_df.columns = tmp_df.columns.astype(int)
    df.loc[tmp_df.index, tmp_df.columns] += tmp_df

# %%
df_max = np.abs(df.values).max()

# hex_heatmap sizes itself to whichever lattice it draws and holds the hexagons
# regular via scaleanchor, so no `sizing` override is needed for the wider
# two-eye extent.
ci.hex_heatmap(
    df,
    eyemap_dir=eyemap_dir,
    which_eye='both',
    title='both eyes',
    custom_colorscale='RdBu_r',
    global_min=-df_max,
    global_max=df_max,
).show()

# %%
df_max = np.abs(df.values).max()

ci.plot_mollweide_projection(
    df,
    eyemap_dir=eyemap_dir,
    which_eye='both',
    custom_colorscale='RdBu_r',
    global_min=-df_max,
    global_max=df_max,
).show()

# %%
