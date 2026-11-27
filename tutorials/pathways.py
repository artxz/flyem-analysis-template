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

data_folder = config.DATA_DIR

normalized = True

results_folder = config.PROJECT_ROOT / 'results' / dataset
results_folder.mkdir(parents=True, exist_ok=True)

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
meta = data.load_meta(dataset)
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
idx_to_instance = dict(zip(meta.idx, meta.instance))
idx_to_type = dict(zip(meta.idx, meta.cell_type))
type_to_nt = dict(zip(meta.cell_type, meta.nt))

# %% [markdown]
# ## Direct connectivity

# %%
# connectivity is a sparse matrix
# pre in rows, post in columns
conn_mat = data.load_prop(dataset) #full integer weights

# normalize to get input-normalized weights
if normalized:
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

# %% [markdown]
# # Barcode plot of effective weights

# %% [markdown]
# For each `output_types` neuron, break down its effective weight from the `input_types` defined above into one stacked ("barcode") bar per output type, colored by input type. Each bar is normalized to sum to 1 in magnitude, so a segment's height is the fraction of the identified input weight coming from that input type (not the fraction of the neuron's total input). Colors match the visual-input palette used throughout the connectome paper figures.
#
# `signed` controls whether the accumulation tracks excitatory vs. inhibitory contributions separately along each path 
#
# `plot_signed`, set independently in the plotting cell below, controls only the *display*: when `True` (and the propagations were run with `signed=True`), each segment is split into an excitatory part (above zero) and an inhibitory part (below zero); otherwise the barcode shows the unsigned (excitatory + inhibitory) magnitude per input type.

# %%
nr_hops_max = 3    # accumulate effective weight over path lengths 1..nr_hops_max
direct_thre = 0.0    # per-hop threshold on the direct weight of each edge in a path (0 = no thresholding)
signed = False        # track excitatory/inhibitory contributions separately along each path

# %%
out_labels = [f'{t}_R' for t in output_types]
in_labels = [f'{t}_R' for t in input_types]
feat_exc = pd.DataFrame(0.0, index=out_labels, columns=in_labels)
feat_inh = pd.DataFrame(0.0, index=out_labels, columns=in_labels)

for n_hop in range(1, nr_hops_max + 1):
    paths = ci.find_paths_of_length(conn_mat, inidx, outidx, n_hop)
    if (paths is None) or paths.empty:
        continue
    paths = ci.filter_paths(paths, direct_thre)
    if (paths is None) or paths.empty:
        continue

    if signed:
        tmp_exc, tmp_inh = ci.signed_effective_conn_from_paths(paths, wide=False, idx_to_nt=idx_to_sign)
    else:
        tmp_exc = ci.effective_conn_from_paths(paths, wide=False)
        tmp_inh = tmp_exc.assign(weight=0.0)

    tmp_exc = ci.group_paths(tmp_exc, idx_to_instance, idx_to_instance, combining_method='mean')
    tmp_inh = ci.group_paths(tmp_inh, idx_to_instance, idx_to_instance, combining_method='mean')
    tmp_exc = tmp_exc.pivot(index='post', columns='pre', values='weight')
    tmp_inh = tmp_inh.pivot(index='post', columns='pre', values='weight')

    feat_exc = feat_exc.add(tmp_exc, fill_value=0).reindex(index=out_labels, columns=in_labels, fill_value=0)
    feat_inh = feat_inh.add(tmp_inh, fill_value=0).reindex(index=out_labels, columns=in_labels, fill_value=0)

feat_exc

# %%
# total identified effective input per output instance, ignoring polarity
row_total = (feat_exc + feat_inh).sum(axis=1)
row_total = row_total.where(row_total > 0, 1)

feat_exc_norm = feat_exc.div(row_total, axis=0)
feat_inh_norm = feat_inh.div(row_total, axis=0)

def _melt_signed(frame, sign_label):
    out = frame.reset_index(names='instance')
    out['instance'] = [s.split('_')[0] for s in out['instance']]
    out.columns = [c if c == 'instance' else c.split('_')[0] for c in out.columns]
    long = out.melt(id_vars='instance', var_name='VI', value_name='fraction')
    long['sign'] = sign_label
    return long

# long-format table with one row per (instance, input type, sign); 'fraction'
# is always >= 0, magnitude only - the plotting cell below applies the sign
feat_norm_long = pd.concat([
    _melt_signed(feat_exc_norm, 'excitatory'),
    _melt_signed(feat_inh_norm, 'inhibitory'),
], ignore_index=True)
feat_norm_long

# %%
import plotly.express as px

# only meaningful if signed=True was used above; set to False to show the
# unsigned (excitatory + inhibitory) barcode even after a signed computation
plot_signed = signed

# same visual-input colors used throughout the connectome paper figures
# (see utils/palettes.py::load_colors in the visualpathways repo)
vi_colors = {
    'L1': '#b4e5cb', 'L2': '#029356', 'L3': '#8fce0a',
    'R7': '#8e56f5', 'R7d': '#4220B4',
    'R8': '#51bfc7', 'R8d': '#099C9C',
    'HBeyelet': '#151515',
}
vi_order = [v for v in vi_colors if v in input_types]

if plot_signed:
    plot_df = feat_norm_long.copy()
    plot_df['fraction'] *= plot_df['sign'].map({'excitatory': 1, 'inhibitory': -1})
    title = 'Barcode of visual-input effective weight (signed)'
else:
    plot_df = feat_norm_long.groupby(['instance', 'VI'], as_index=False)['fraction'].sum()
    title = 'Barcode of visual-input effective weight'

fig = px.bar(
    plot_df, x='instance', y='fraction', color='VI',
    color_discrete_map=vi_colors, category_orders={'VI': vi_order},
    text='VI',
)
fig.update_traces(textposition='inside', insidetextanchor='middle')
fig.add_hline(y=0, line_color='black', line_width=1)
fig.update_layout(
    bargap=0.3, plot_bgcolor='white', paper_bgcolor='white',
    font=dict(family='arial', size=14),
    title=title,
)
if not plot_signed:
    fig.add_hline(y=1, line_color='black', line_width=1)
    fig.update_yaxes(range=[-0.01, 1.01])
fig.update_xaxes(showgrid=False, title_text='output type')
fig.update_yaxes(showgrid=False, title_text='normalized effective weight')
fig.show()

# %% [markdown] id="L-gShtZ6H4Lh"
# # Pathways between cell types of interest
# Edges are linearly scaled by the weights and colored by neurotransmitter predictions of pre (orange: Ach, blue: GABA, green: Glu, gray: rest). <br>
#
# Manually specify the following: <br>
# `input_types` is a list of cell types which we treat as inputs. <br>
# `output_types` is a list of cell types which we treat as outputs. <br>
#
# Notes: <br>
# `inidx` and `outidx` below we also constrain the `input_types` and `output_types` to be on the right side only. <br>
# `combining_method` below takes the mean connectivity over post neurons. <br>
# `interactive` below can open an hmtl file where nodes can be moved around.

# %%
input_types = ['L1', 'L2', 'L3', 'R8', 'R8d', 'R7', 'R7d', 'HBeyelet']
# output_types = ['T4a', 'T4b', 'T4c', 'T4d']
output_types = ['LC10a']

# %%
# find connectivity indices and print how many neurons
inidx = meta.idx[meta.cell_type.isin(input_types) & (meta.side=='right')]
print('Number of {} neurons: {}'.format(input_types, inidx.shape[0]))
outidx = meta.idx[meta.cell_type.isin(output_types) & (meta.side=='right')]
print('Number of {} neurons: {}'.format(output_types, outidx.shape[0]))

# %% [markdown]
# ## plot for each number of hops

# %% [markdown]
# `nr_hops` is a list of the numbers of hops that we're considering between `input_types` and `output_types`. <br>
# `weight_thre` is a list of weights thresholds (one for each number of hops). These are thresholds for the direct connectivity between all pairs of neurons in a path. 

# %%
nr_hops = [1, 2, 3]
if normalized:
    weight_thre = [0.05, 0.001, 0.0001]
else:
    weight_thre = [5, 5, 5]

# %%
for nr_hop, thre_layer in zip(nr_hops, weight_thre):

    paths = ci.find_paths_of_length(conn_mat, inidx, outidx, nr_hop)
    if (paths is None) or (paths.empty):
        print(f'No paths with {nr_hop} hops')
        continue

    paths = ci.group_paths(paths, idx_to_instance, idx_to_instance, 
                        combining_method='mean')

    paths = ci.filter_paths(paths,
                        threshold = thre_layer)
    if (paths is None) or (paths.empty):
        print(f'No paths with {nr_hop} hops and threshold {thre_layer}')
        continue
    
    #remove _side for plotting
    paths['pre'] = [s.split('_')[0] for s in paths['pre']]
    paths['post'] = [s.split('_')[0] for s in paths['post']]    
    
    ci.plot_paths(paths, interactive = False, node_size = 800, edge_width_scale= 10,
               neuron_to_sign = type_to_nt, sign_color_map = nt_to_color,
               edge_text = True, weight_decimals = 2*normalized, figsize=(4+nr_hop*3,7),
                show = False, #allows adding a title afterwards
    )
    plt.title(f'No. hops={nr_hop}, Threshold={thre_layer:.2f}',
            fontname='Times New Roman', fontstyle='italic')

# %% [markdown]
# ## Not working, plot across information flow layers (start from left and right photoreceptors)

# %% [markdown]
# `nr_hops_max` is the maximum number of hops (steps) allowed in the path search between input and output neurons. <br>
# `weight_frac_cumsum` is the cumulative fraction of total effective weight used as a threshold to select the strongest paths. <br>
# `thre_step_min` is the minimum threshold for the direct weight at each step in the path.

# %%
nr_hops_max = 4
weight_frac_cumsum = 0.3
thre_step_min = 0.1

# %%
flow_f = data_folder / f'{dataset}_LR_flow_20step_0.1thre_hit.csv'
if not flow_f.exists():
    print(f'Please download flow file {flow_f} (starting from photoreceptors). Cannot proceed without flow information.')
else:
    flow_type_df = ci.find_instance_flow(
        conn_mat,
        idx_to_instance,
        file_path=data_folder,
        save_prefix=f'{dataset}_LR_flow_', method=config.FLOW_METHOD)
    paths_flow_df, w_filter, w_all, thre_step = ci.layered_el(
        conn_mat, inidx, outidx, nr_hops_max, idx_to_instance,
        thre_cumsum = weight_frac_cumsum, thre_step_min = thre_step_min,
        flow = flow_type_df)

    #remove _side for plotting
    paths_flow_df['pre'] = [s.split('_')[0] for s in paths_flow_df['pre']]
    paths_flow_df['post'] = [s.split('_')[0] for s in paths_flow_df['post']]    
    
    ci.plot_paths(paths_flow_df, interactive = False, node_size = 800, edge_width_scale= 10,
               neuron_to_sign = type_to_nt, sign_color_map = nt_to_color,
               edge_text = True, weight_decimals = 2*normalized, figsize=(10,7),
                show = False, #allows adding a title afterwards
    )
    plt.title(f'Threshold={thre_step:.2f}, cumsum={w_filter/w_all:.2f}',
            fontname='Times New Roman', fontstyle='italic')

# %%

# %%
