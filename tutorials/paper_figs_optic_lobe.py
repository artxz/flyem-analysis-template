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
# # Figure styles from Nern et al. (2025), *Connectome-driven neural inventory of a complete visual system*
#
# Paper: `local/papers/mcns-ol.pdf` (Nature 641:1225–1237). Code base:
# [reiserlab/male-drosophila-visual-system-connectome-code](https://github.com/reiserlab/male-drosophila-visual-system-connectome-code).
#
# Panels reproduced here:
#
# | panel | what it shows | how the paper made it |
# |---|---|---|
# | Fig. 5a, bottom | seven cell types of the Dm3 circuit (Tm1, Tm2, TmY4, TmY9a, TmY9b, LC11, LC15) in an optic-lobe slice with layer outlines | Blender "Optic-Lobe" render, `Equator_slice` view: `utils/rend_params.py::get_one_off_params()['Fig5a-3_Pathway_1']` → `utils/gallery_filler.py::generate_one_off` → `gallery_generation/render_optic-lobe.py` |
# | Fig. 6, first panel | MeTu1–MeTu3c visual projection neurons in a half-brain view, colour-matched labels with cell counts | Blender "Full-Brain" render, `half_brain` view: `gallery_generation/generate_full_brain_groups_non_ol.py` (groups from `params/Primary_cell_type_table.xlsx`) |
# | Fig. 7b | expression pattern of split-GAL4 line SS35783 (LPLC4) in brain and VNC | confocal light-microscopy image; no generating code. An EM-based analogue is drawn in the last section |
#
# The paper renders neuron and neuropil meshes with Blender (Cycles) from JSON scene
# descriptions (`gallery_generation/*.json`, template `gallery-descriptions.json.jinja`).
# The camera, slicing and colour definitions in those files are plain numbers, so the same
# views can be drawn in 2D with matplotlib from neuPrint skeletons and ROI meshes. That is
# what this notebook does: the Blender camera (location, XYZ Euler rotation, orthographic
# scale) becomes a projection matrix, the neuron "slicer" becomes a depth mask, the sliced
# layer meshes become plane cross-sections, and the "flat" neuropil meshes become filled
# silhouettes.
#
# Coordinates are neuPrint voxels (8 nm). The Blender scenes use the same units (the scale
# bar is built as `length_um * 1000 / 8`), so every number from
# `params/Rendering_parameters.xlsx` is used unchanged.

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
from utils import olc_client
# The paper used `optic-lobe:v1.1` on https://neuprint.janelia.org. The default `.env`
# dataset (male-cns:v1.0) shares body IDs, ROI meshes and layer meshes with it, so either
# works (the same token is valid for both):
# c = olc_client.connect(instance='https://neuprint.janelia.org', dataset='optic-lobe:v1.1')
c = olc_client.connect(verbose=True)

# %%
import numpy as np
import pandas as pd
import trimesh
from scipy.spatial.transform import Rotation

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection

import navis
import navis.interfaces.neuprint as neu
from neuprint import fetch_neurons, NeuronCriteria as NC

VOXEL_NM = 8
UM = 1000 / VOXEL_NM   # voxels per micrometre

# %% [markdown]
# ## Palettes (`utils/ol_color.py::OL_COLOR`)

# %%
OL_COLOR = {
    # main cell groups: intrinsic (ONIN), connecting (ONCN), VPN, VCN, OL/CB other
    'OL_TYPES':       ['#029e73', '#d55e00', '#0173b2', '#de8f05', '#cc78bc'],
    'OL_DARK_TYPES':  ['#01523c', '#893c00', '#014266', '#935f03', '#943883'],
    'OL_LIGHT_TYPES': ['#5dfed0', '#ffc599', '#85d4fe', '#fdc35e', '#e3b5db'],
    # darkest -> lightest sequence per group
    'OL_IN_SEQ':   ['#01523c', '#029e73', '#02dea0', '#5dfed0', '#d6fff3'],
    'OL_CONN_SEQ': ['#893c00', '#d55e00', '#ff8b33', '#ffc599', '#ffe7d6'],
    'OL_VPN_SEQ':  ['#014266', '#0173b2', '#20b0fe', '#85d4fe', '#d6f1ff'],
    'OL_VCN_SEQ':  ['#4f3202', '#935f03', '#de8f05', '#fdc35e', '#fce7c5'],
    'PALE_AND_YELLOW': ['#C28E1D', '#943883', '#000000'],
    # neuropil layers in the OL slice views: odd layer, even layer, outline
    'OL_NEUROPIL_LAYERS': ['#EEEEEE', '#FAFAFA', '#BABABA'],
    # "flat" neuropil silhouettes of the Full-Brain views are rgb(0.9, 0.9, 0.9)
    'BRAIN_FLAT': '#e6e6e6',
}

# %% [markdown]
# ## Views (`params/Rendering_parameters.xlsx`)
#
# Each Blender view is an orthographic camera (`cam_loc`, XYZ Euler `cam_rot` in degrees,
# `ortho` = width of the field of view in voxels) plus, for the optic-lobe slice views, a
# slicing plane (`slice_loc`, `slice_rot`). `whole_brain` renders at 4096 x 2160 pixels, all
# other views are square.

# %%
VIEWS = {
    'Equator_slice':   dict(cam_loc=[38000, 60000, 30000], cam_rot=[91, -226, 162], ortho=55000,
                            slice_loc=[16682, 34887, 33158], slice_rot=[91, -226, 162]),
    'Dorsal_slice':    dict(cam_loc=[25213, 62771, 15796], cam_rot=[60, -221, 162], ortho=48000,
                            slice_loc=[12812, 23467, 33012], slice_rot=[60, -221, 162]),
    'Ventral_slice':   dict(cam_loc=[46000, 59000, 36500], cam_rot=[110, -226, 162], ortho=54000,
                            slice_loc=[19000, 45000, 33000], slice_rot=[119, -226, 162]),
    'medulla_face_on': dict(cam_loc=[5000, 35000, 30000], cam_rot=[-50, 177, 84], ortho=45000,
                            slice_loc=[5000, 35000, 30000], slice_rot=[-50, 177, 84]),
    'half_brain':      dict(cam_loc=[25000, 23000, 0], cam_rot=[-180, 0, -2], ortho=55000),
    'whole_brain':     dict(cam_loc=[48500, 20000, 0], cam_rot=[-180, 0, -2], ortho=100000,
                            aspect=4096 / 2160),
    # plain frontal view (x to the right, dorsal up), not a paper view
    'frontal':         dict(cam_loc=[0, 0, 0], cam_rot=[-180, 0, 0], ortho=None),
}

# %% [markdown]
# ## Drawing helpers
#
# Blender's camera looks down its local -Z axis; image x is the camera's local +X and image y
# its local +Y. With `R` the (extrinsic XYZ) rotation matrix of the camera, a world point `p`
# maps to `q = R.T @ (p - loc)`; the image coordinates are `(q_x, q_y)` and the depth is
# `-q_z`. The `half_brain`/`whole_brain` rotation `[-180, 0, -2]` is the usual frontal view
# (x right, dorsal up, 2 degree tilt).

# %%
def camera(view):
    """Blender camera -> (rotation matrix, location)."""
    v = VIEWS[view] if isinstance(view, str) else view
    rot = Rotation.from_euler('xyz', v['cam_rot'], degrees=True).as_matrix()
    return rot, np.asarray(v['cam_loc'], float)


def project(xyz, rot, loc):
    """World -> image coordinates (n, 2) and depth along the viewing direction (n,)."""
    q = (np.asarray(xyz, float) - loc) @ rot     # row-wise rot.T @ (p - loc)
    return q[:, :2], -q[:, 2]


def skeleton_segments(neuron, rot, loc, keep=None):
    """Projected parent->child segments of a navis.TreeNeuron, shape (n, 2, 2).
    `keep` is an optional boolean node mask; a segment is drawn only if both ends are kept."""
    nodes = neuron.nodes
    uv, _ = project(nodes[['x', 'y', 'z']].values, rot, loc)
    position = pd.Series(np.arange(len(nodes)), index=nodes.node_id.values)
    child = np.flatnonzero(nodes.parent_id.values >= 0)
    parent = position.reindex(nodes.parent_id.values[child]).values.astype(int)
    if keep is not None:
        both = keep[child] & keep[parent]
        child, parent = child[both], parent[both]
    return np.stack([uv[child], uv[parent]], axis=1)


def draw_neurons(ax, neurons, colors, rot, loc, linewidth=0.8, alpha=1.0, keep=None, zorder=3):
    """Draw skeletons as line collections. `colors` is one colour or one per neuron;
    `keep` is an optional function neuron -> boolean node mask (see `slab_mask`)."""
    if isinstance(colors, str):
        colors = [colors] * len(neurons)
    for n, col in zip(neurons, colors):
        segs = skeleton_segments(n, rot, loc, keep=None if keep is None else keep(n))
        ax.add_collection(LineCollection(segs, colors=col, linewidths=linewidth, alpha=alpha,
                                         capstyle='round', zorder=zorder))


def draw_silhouettes(ax, volumes, rot, loc, color=OL_COLOR['BRAIN_FLAT'], zorder=0):
    """Flat filled projections of ROI meshes (the Blender "flat" ROIs)."""
    for vol in volumes:
        uv, _ = project(vol.vertices, rot, loc)
        ax.add_collection(PolyCollection(uv[vol.faces], facecolors=color, edgecolors='none',
                                         zorder=zorder, rasterized=True))


def slicing_plane(view):
    """Origin and normal of a view's slicing plane (the Blender slicer box's local z axis)."""
    v = VIEWS[view]
    origin = np.asarray(v['slice_loc'], float)
    normal = Rotation.from_euler('xyz', v['slice_rot'], degrees=True).as_matrix()[:, 2]
    return origin, normal


def draw_layer_slices(ax, layer_volumes, view, rot, loc,
                      colors=OL_COLOR['OL_NEUROPIL_LAYERS'], linewidth=0.8, zorder=1):
    """Cross-sections of the layer meshes through the view's slicing plane, filled with
    alternating shades for odd/even layers and outlined (Blender slices the layer meshes
    to 30-voxel slabs, which amounts to the same outline)."""
    origin, normal = slicing_plane(view)
    for i, vol in enumerate(layer_volumes):
        section = trimesh.Trimesh(vol.vertices, vol.faces).section(plane_origin=origin,
                                                                   plane_normal=normal)
        if section is None:
            continue
        for loop in section.discrete:
            uv, _ = project(loop, rot, loc)
            ax.fill(uv[:, 0], uv[:, 1], facecolor=colors[i % 2], edgecolor=colors[2],
                    linewidth=linewidth, zorder=zorder)


def slab_mask(neuron, view, half_width, outside_volumes=()):
    """Node mask reproducing the Blender neuron slicer: keep nodes within +-half_width of the
    slicing plane. Nodes outside `outside_volumes` (the OL neuropils) are always kept: the
    gallery adds a second, unsliced copy of each neuron restricted to the outside of the
    neuropils (the `*-out` object in `_gallery-descriptions_sliced-neuron.json.jinja`)."""
    origin, normal = slicing_plane(view)
    xyz = neuron.nodes[['x', 'y', 'z']].values
    keep = np.abs((xyz - origin) @ normal) < half_width
    if len(outside_volumes):
        keep |= ~volume_mask(neuron, outside_volumes)
    return keep


def volume_mask(neuron, volumes):
    """Node mask: nodes inside any of `volumes`."""
    xyz = neuron.nodes[['x', 'y', 'z']].values
    inside = np.zeros(len(xyz), bool)
    for vol in volumes:
        inside |= navis.in_volume(xyz, vol)
    return inside


def finish_view(ax, view):
    """Frame the axes like the Blender camera (field width `ortho`, image aspect)."""
    v = VIEWS[view]
    ortho, aspect = v['ortho'], v.get('aspect', 1.0)
    ax.set_xlim(-ortho / 2, ortho / 2)
    ax.set_ylim(-ortho / 2 / aspect, ortho / 2 / aspect)
    ax.set_aspect('equal')
    ax.axis('off')


def frame_to(ax, volumes, rot, loc, margin=0.03):
    """Frame the axes to the projected bounding box of `volumes` (plus a margin)."""
    uv = np.vstack([project(v.vertices, rot, loc)[0] for v in volumes])
    lo, hi = uv.min(0), uv.max(0)
    pad = margin * (hi - lo).max()
    ax.set_xlim(lo[0] - pad, hi[0] + pad)
    ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_aspect('equal')
    ax.axis('off')


def add_scalebar(ax, length_um, xy=(0.05, 0.05), color='black', label=True):
    """Horizontal scale bar of `length_um` micrometres; `xy` = bottom-left in axes fraction."""
    x0 = ax.get_xlim()[0] + xy[0] * np.diff(ax.get_xlim())[0]
    y0 = ax.get_ylim()[0] + xy[1] * np.diff(ax.get_ylim())[0]
    ax.plot([x0, x0 + length_um * UM], [y0, y0], color=color, linewidth=2, solid_capstyle='butt')
    if label:
        ax.text(x0, y0 + 0.01 * np.diff(ax.get_ylim())[0], f'{length_um} µm',
                color=color, fontsize=8, va='bottom')


def label_types(ax, labels, colors, x=0.78, y=0.95, dy=-0.06, ha='left', fontsize=10):
    """Colour-matched text labels at Blender `paper_position` coordinates (axes fraction,
    origin bottom-left), one line per type."""
    for i, (lab, col) in enumerate(zip(labels, colors)):
        ax.text(x, y + i * dy, lab, color=col, transform=ax.transAxes, ha=ha, va='top',
                fontsize=fontsize)


def fetch_rois(names):
    """ROI meshes from neuPrint as navis.Volumes; ROIs without a mesh are skipped."""
    vols = []
    for name in names:
        try:
            vols.append(neu.fetch_roi(name, client=c))
        except Exception as err:
            print(f'no mesh for {name} ({type(err).__name__})')
    return vols

# %% [markdown]
# ## Fig. 5a (bottom): cell types in an optic-lobe slice
#
# Body IDs, view, colours and text placement are the `Fig5a-3_Pathway_1` entry of
# `get_one_off_params()`: view `Equator_slice`, neurons sliced to a 12000-voxel (96 µm) slab,
# labels at paper position (0.78, 0.95) stepping down by 0.06. The colour list was
# `PALE_AND_YELLOW + OL_CONN_SEQ + OL_IN_SEQ + OL_VPN_SEQ` indexed by
# `body_color_order = [3, 6, 4, 0, 5, 13, 14]`, which resolves to the entries used below.
# All ME, LO and LOP layer meshes are drawn (Blender draws them as 30-voxel slabs).

# %%
fig5a_types = ['Tm1', 'Tm2', 'TmY4', 'TmY9a', 'TmY9b', 'LC11', 'LC15']
fig5a_bodies = [48193, 45468, 56703, 62719, 62635, 24953, 31391]
fig5a_colors = [OL_COLOR['OL_CONN_SEQ'][0], OL_COLOR['OL_CONN_SEQ'][3], OL_COLOR['OL_CONN_SEQ'][1],
                OL_COLOR['PALE_AND_YELLOW'][0], OL_COLOR['OL_CONN_SEQ'][2],
                OL_COLOR['OL_VPN_SEQ'][0], OL_COLOR['OL_VPN_SEQ'][1]]
view = 'Equator_slice'
slice_width = 12000      # voxels; `slice_width` of `generate_one_off`

# %%
neurons = neu.fetch_skeletons(NC(bodyId=fig5a_bodies), client=c, heal=True)
neurons = neurons.idx[fig5a_bodies]          # same order as the type list
ol_neuropils = fetch_rois(['ME(R)', 'LO(R)', 'LOP(R)'])
layers = fetch_rois([f'ME_R_layer_{i:02d}' for i in range(1, 11)]
                    + [f'LO_R_layer_{i}' for i in range(1, 8)]
                    + [f'LOP_R_layer_{i}' for i in range(1, 5)])
print(f'{len(neurons)} neurons, {len(layers)} layer meshes')

# %%
rot, loc = camera(view)
fig, ax = plt.subplots(figsize=(7, 7))
draw_layer_slices(ax, layers, view, rot, loc)
draw_neurons(ax, neurons, fig5a_colors, rot, loc, linewidth=1.2,
             keep=lambda n: slab_mask(n, view, slice_width / 2, ol_neuropils))
label_types(ax, fig5a_types, fig5a_colors, x=0.78, y=0.95, dy=-0.06)
finish_view(ax, view)
add_scalebar(ax, 50)
plt.show()

# %% [markdown]
# Other views of the same cells: `Dorsal_slice` and `Ventral_slice` are the other slice
# views of the Extended Data galleries; `medulla_face_on` (Fig. 5c,e,f) shows one flattened
# layer mesh (`n_vis`, here M3) instead of slices and does not slice the neurons.

# %%
layer_by_name = {vol.name: vol for vol in layers}
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax, other in zip(axes, ['Dorsal_slice', 'Ventral_slice', 'medulla_face_on']):
    rot, loc = camera(other)
    if other == 'medulla_face_on':
        draw_silhouettes(ax, [layer_by_name['ME_R_layer_03']], rot, loc,
                         color=OL_COLOR['OL_NEUROPIL_LAYERS'][0])
        draw_neurons(ax, neurons, fig5a_colors, rot, loc, linewidth=1.0)
    else:
        draw_layer_slices(ax, layers, other, rot, loc)
        draw_neurons(ax, neurons, fig5a_colors, rot, loc, linewidth=1.0,
                     keep=lambda n, v=other: slab_mask(n, v, slice_width / 2, ol_neuropils))
    finish_view(ax, other)
    ax.set_title(other)
plt.show()

# %% [markdown]
# ## Fig. 6 (first panel): a group of visual projection neurons, half-brain view
#
# `generate_full_brain_groups_non_ol.py` loops over the `figure_group`s of
# `params/Primary_cell_type_table.xlsx` (the first Fig. 6 panel is `MeTu_part1`: MeTu1,
# MeTu2a, MeTu2b, MeTu3a, MeTu3b, MeTu3c), takes all right-hemisphere cells of each type,
# assigns colours in alphabetical order from `OL_TYPES + OL_DARK_TYPES + OL_LIGHT_TYPES`
# reordered by `[0, 6, 2, 13, 4, 5, 1, 7, 3, 9, 12, 10]`, and writes "type (n cells)" labels at
# paper position (0.03, 0.86) stepping down by 0.06. Unilateral VPN groups use the
# `half_brain` view, groups with bilateral cells `whole_brain`. The neuropils are the flat
# OL(R), OL(L) and CB silhouettes (named `Optic(R)`, `Optic(L)`, `CentralBrain` in male-cns).

# %%
group_types = ['MeTu1', 'MeTu2a', 'MeTu2b', 'MeTu3a', 'MeTu3b', 'MeTu3c']
group_side = 'R'
view = 'half_brain'          # 'whole_brain' for bilateral groups

palette = OL_COLOR['OL_TYPES'] + OL_COLOR['OL_DARK_TYPES'] + OL_COLOR['OL_LIGHT_TYPES']
palette = [palette[i] for i in [0, 6, 2, 13, 4, 5, 1, 7, 3, 9, 12, 10]]
group_types = sorted(group_types, key=str.lower)
group_colors = {t: palette[i % len(palette)] for i, t in enumerate(group_types)}

# %%
group_df, _ = fetch_neurons(NC(type=group_types), client=c)
group_df = group_df[group_df.instance.str.endswith(f'_{group_side}')]
group_neurons = neu.fetch_skeletons(NC(bodyId=group_df.bodyId.tolist()), client=c,
                                    heal=False, max_threads=8)
brain = fetch_rois(['CentralBrain', 'Optic(R)', 'Optic(L)'])
counts = group_df.groupby('type').size()
counts

# %%
rot, loc = camera(view)
fig, ax = plt.subplots(figsize=(7, 7))
draw_silhouettes(ax, brain, rot, loc)
type_of = dict(zip(group_df.bodyId, group_df.type))
draw_neurons(ax, group_neurons, [group_colors[type_of[int(n.id)]] for n in group_neurons],
             rot, loc, linewidth=0.4)
labels = [f'{t} ({counts[t]})' if counts[t] > 1 else t for t in group_types]
label_types(ax, labels, [group_colors[t] for t in group_types], x=0.03, y=0.86, dy=-0.06)
finish_view(ax, view)
add_scalebar(ax, 50)
plt.show()

# %% [markdown]
# ## Fig. 7b: split-GAL4 expression pattern in brain and VNC
#
# Fig. 7b is a confocal image of split-GAL4 line SS35783 (LPLC4) over a neuropil reference,
# so there is no figure code to extract for it. The closest connectome-based analogue is the
# paper's own LM-EM comparison (Fig. 7c right: registered EM skeletons over the LM pattern).
# Below, all EM-reconstructed cells of the targeted type are drawn over the neuropil
# silhouettes in LM colours (green cells, grey neuropil, black background), as separate
# brain and VNC panels like the LM figure. LPLC4 has no VNC arbours, so the VNC panel only
# shows the outline; change `lm_type` to a descending neuron type to fill both panels.

# %%
lm_type = 'LPLC4'
lm_side = 'R'
lm_df, _ = fetch_neurons(NC(type=lm_type), client=c)
lm_df = lm_df[lm_df.instance.str.endswith(f'_{lm_side}')]
lm_neurons = neu.fetch_skeletons(NC(bodyId=lm_df.bodyId.tolist()), client=c,
                                 heal=False, max_threads=8)
vnc = fetch_rois(['VNC'])
print(f'{len(lm_neurons)} {lm_type}_{lm_side} neurons')

# %%
rot, loc = camera('frontal')
fig, axes = plt.subplots(2, 1, figsize=(6, 9), facecolor='black',
                         gridspec_kw={'height_ratios': [1, 1.4]})
# brain panel: whole neurons; VNC panel: only the parts inside the VNC (brain and VNC overlap
# in the frontal projection)
keeps = [None, lambda n: volume_mask(n, vnc)]
for ax, vols, title, keep in zip(axes, [brain, vnc], ['Brain', 'VNC'], keeps):
    ax.set_facecolor('black')
    draw_silhouettes(ax, vols, rot, loc, color='#3a3a3a')
    draw_neurons(ax, lm_neurons, '#66ff66', rot, loc, linewidth=0.6, keep=keep)
    frame_to(ax, vols, rot, loc)                    # each panel framed to its own region
    ax.text(0.02, 0.97, title, color='white', transform=ax.transAxes, va='top')
    add_scalebar(ax, 100, color='white')
axes[0].text(0.98, 0.97, f'{lm_type} ({len(lm_neurons)} EM cells, {lm_side})',
             color='#66ff66', transform=axes[0].transAxes, ha='right', va='top')
plt.show()
