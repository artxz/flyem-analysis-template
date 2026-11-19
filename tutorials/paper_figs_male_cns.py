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
# # Figure styles from Berg et al. (2026), *Sexual dimorphism in the complete Drosophila male central nervous system connectome*
#
# Paper: `local/papers/mcns-flagship.pdf` (Cell 189:5504–5526). The paper publishes derived
# data rather than figure code: [flyconnectome/2025malecns](https://github.com/flyconnectome/2025malecns)
# (cluster assignments, male-female edge tables). Its neuron renderings were made with
# [navis](https://github.com/navis-org/navis) and cross-dataset registration with
# [navis-flybrains](https://github.com/navis-org/navis-flybrains) (key resources table); only the
# Fig. 4 whole-brain and optic-lobe slice views used the Blender pipeline of Nern et al.
# (see `paper_figs_optic_lobe.ipynb`). This notebook rebuilds the requested panels from
# neuPrint skeletons and ROI meshes with matplotlib.
#
# | panel | what it shows | data used here |
# |---|---|---|
# | Fig. 1B | all neurons of the connectome coloured at random, neuron counts per region | random sample of traced male CNS neurons |
# | Fig. 1I | one type (DNde003) in FlyWire, hemibrain and MANC, and overlaid in male CNS space | skeletons from the four neuPrint datasets + flybrains transforms |
# | Fig. 3A | male CNS brain vs. female FAFB/FlyWire brain, all neurons | random samples from `male-cns:v1.0` and `flywire-fafb:v783b` |
# | Fig. 3D | an isomorphic cell type, male (left) vs. female (right) in one brain outline | DP1m_adPN of both datasets, FlyWire transformed into male CNS space |
# | Fig. 7P | one connectivity cluster rendered on the whole CNS, coloured by dimorphism | cluster 102 of `mcns_lvl_6_hsbm_communities.feather` + the neuPrint `dimorphism` field |
#
# All views are frontal (x to the right, dorsal up). Male CNS, hemibrain and MANC skeletons
# are in 8-nm voxels; FlyWire skeletons and the flybrains template meshes are in nm.

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
import os
from utils import olc_client
from neuprint import Client, fetch_neurons, fetch_custom, NeuronCriteria as NC

c = olc_client.connect(verbose=True)          # male-cns:v1.0 from `.env`

# The other connectomes are on neuPrint too; the same token is valid on both servers.
# neuprint makes the most recently created Client the default, so every query below passes
# `client=` explicitly.
token = os.environ['NEUPRINT_APPLICATION_CREDENTIALS']
c_fw = Client('https://neuprint-cns.janelia.org', dataset='flywire-fafb:v783b', token=token)
c_hb = Client('https://neuprint.janelia.org', dataset='hemibrain:v1.2.1', token=token)
c_manc = Client('https://neuprint.janelia.org', dataset='manc:v1.2.1', token=token)

# %%
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlretrieve

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection

import navis
import navis.interfaces.neuprint as neu
import flybrains                              # registers template brains + bundled transforms

data_folder = PROJECT_ROOT / 'cache' / 'data'
data_folder.mkdir(parents=True, exist_ok=True)

VOXEL_NM = 8
UM = 1000 / VOXEL_NM          # male CNS voxels per micrometre
GREY = '#e6e6e6'

# %% [markdown]
# ## Drawing helpers
#
# Frontal view: image x = x, image y = -y (neuPrint and FAFB y axes point ventrally). ROI
# meshes are drawn as flat filled silhouettes, skeletons as line collections. `scale`
# converts units (e.g. `1 / UM` to plot male CNS voxels in µm).

# %%
def projected(xyz, view=('x', '-y'), scale=1.0):
    axis = {'x': 0, 'y': 1, 'z': 2}
    xyz = np.asarray(xyz, float)
    return np.column_stack([(-1 if a.startswith('-') else 1) * xyz[:, axis[a.strip('-')]]
                            for a in view]) * scale


def skeleton_segments(neuron, view=('x', '-y'), scale=1.0):
    """Parent->child segments of a skeleton, shape (n, 2, 2)."""
    nodes = neuron.nodes
    uv = projected(nodes[['x', 'y', 'z']].values, view, scale)
    position = pd.Series(np.arange(len(nodes)), index=nodes.node_id.values)
    child = np.flatnonzero(nodes.parent_id.values >= 0)
    parent = position.reindex(nodes.parent_id.values[child]).values.astype(int)
    return np.stack([uv[child], uv[parent]], axis=1)


def draw_neurons(ax, neurons, colors, linewidth=0.5, alpha=1.0, view=('x', '-y'), scale=1.0, zorder=3):
    if isinstance(colors, (str, tuple)):
        colors = [colors] * len(neurons)
    for n, col in zip(neurons, colors):
        ax.add_collection(LineCollection(skeleton_segments(n, view, scale), colors=col,
                                         linewidths=linewidth, alpha=alpha, zorder=zorder))


def draw_silhouettes(ax, meshes, color=GREY, view=('x', '-y'), scale=1.0, zorder=0):
    """Flat filled projections of trimesh / navis.Volume meshes."""
    for m in meshes:
        uv = projected(m.vertices, view, scale)
        ax.add_collection(PolyCollection(uv[np.asarray(m.faces)], facecolors=color,
                                         edgecolors='none', zorder=zorder, rasterized=True))


def finish(ax):
    ax.autoscale_view()
    ax.set_aspect('equal')
    ax.axis('off')


def frame_to(ax, meshes, view=('x', '-y'), scale=1.0, half=None, margin=0.03):
    """Square frame around the projected bounding box of `meshes`; `half` fixes the
    half-width (same value on several axes = same scale)."""
    uv = np.vstack([projected(m.vertices, view, scale) for m in meshes])
    lo, hi = uv.min(0), uv.max(0)
    centre = (lo + hi) / 2
    if half is None:
        half = (hi - lo).max() / 2 * (1 + margin)
    ax.set_xlim(centre[0] - half, centre[0] + half)
    ax.set_ylim(centre[1] - half, centre[1] + half)
    ax.set_aspect('equal')
    ax.axis('off')


def add_scalebar(ax, length, label, xy=(0.05, 0.03), color='black'):
    """Scale bar of `length` data units with a text `label`; `xy` = bottom-left in axes fraction."""
    x0 = ax.get_xlim()[0] + xy[0] * np.diff(ax.get_xlim())[0]
    y0 = ax.get_ylim()[0] + xy[1] * np.diff(ax.get_ylim())[0]
    ax.plot([x0, x0 + length], [y0, y0], color=color, linewidth=2, solid_capstyle='butt')
    ax.text(x0, y0 + 0.01 * np.diff(ax.get_ylim())[0], label, color=color, fontsize=8, va='bottom')


def fetch_rois(names, client=c):
    vols = []
    for name in names:
        try:
            vols.append(neu.fetch_roi(name, client=client))
        except Exception as err:
            print(f'no mesh for {name} ({type(err).__name__})')
    return vols


def fetch_flywire_skeletons(body_ids, client=c_fw, threads=8):
    """FlyWire skeletons from neuPrint (nm). `navis.interfaces.neuprint.fetch_skeletons`
    cannot parse this dataset's skeleton table, so TreeNeurons are built from the raw table."""
    def one(body_id):
        return navis.TreeNeuron(client.fetch_skeleton(body_id, format='pandas'), id=body_id, units='nm')
    with ThreadPoolExecutor(threads) as pool:
        return navis.NeuronList(list(pool.map(one, body_ids)))


brain_rois = ['CentralBrain', 'Optic(R)', 'Optic(L)']
cns = fetch_rois(brain_rois + ['VNC'])
brain = cns[:3]
vnc = cns[3:]

# %% [markdown]
# ## Fig. 1B: all neurons of the connectome
#
# Random colours, frontal view, neuron counts per region. The paper renders every neuron (and
# tilts the VNC down); a random sample of a few thousand skeletons gives the same impression
# in seconds. Region counts are derived from `superclass` (VNC: `vnc_*` and ascending classes;
# optic lobes: `ol_*`/`visual_*` split by soma side; the rest is central brain).

# %%
neurons_df = fetch_custom("""
    MATCH (n:Neuron) WHERE n.status = 'Traced' AND n.superclass IS NOT NULL
    RETURN n.bodyId AS bodyId, n.superclass AS superclass, n.somaSide AS somaSide, n.rootSide AS rootSide
""", client=c)
side = neurons_df.somaSide.fillna(neurons_df.rootSide).fillna('?')
is_vnc = neurons_df.superclass.str.startswith(('vnc_', 'ascending', 'sensory_ascending', 'efferent_ascending'))
is_ol = neurons_df.superclass.str.startswith(('ol_', 'visual_'))
neurons_df['region'] = np.select([is_vnc, is_ol], ['VNC', 'optic lobe (' + side + ')'], 'central brain')
region_counts = neurons_df.region.value_counts()
region_counts

# %%
n_sample = 3000
sample_ids = neurons_df.bodyId.sample(n_sample, random_state=0).tolist()
sample = neu.fetch_skeletons(NC(bodyId=sample_ids), client=c, heal=False, max_threads=8)

# %%
rng = np.random.default_rng(0)
fig, ax = plt.subplots(figsize=(6, 9))
draw_silhouettes(ax, cns)
draw_neurons(ax, sample, [tuple(rng.random(3)) for _ in sample], linewidth=0.3)
finish(ax)
for region, xy in {'central brain': (0.5, 0.99), 'optic lobe (R)': (0.06, 0.7),
                   'optic lobe (L)': (0.94, 0.7), 'VNC': (0.5, 0.0)}.items():
    if region in region_counts:
        ax.text(*xy, f'{region}\n{region_counts[region] / 1000:.1f}k', transform=ax.transAxes,
                ha='center', va='top' if xy[1] > 0.5 else 'bottom', fontsize=9)
add_scalebar(ax, 100 * UM, '100 µm', xy=(0.8, 0.03))
ax.set_title(f'{n_sample} of {len(neurons_df):,} traced neurons', fontsize=10)
plt.show()

# %% [markdown]
# ## Fig. 1I: one cell type across connectomes
#
# Left column of the panel: the matched type in the other datasets, each drawn on its own
# template outline (flybrains meshes `FLYWIRE`, `JRCFIB2018F` = hemibrain, `MANC`). Right:
# the neurons transformed into male CNS space with `navis.xform_brain` and overlaid on the
# male CNS neuron. The cross-dataset type names come from the male CNS neuPrint fields
# `flywireType`, `hemibrainType`, `mancType`.
#
# flybrains ships landmark transforms FlyWire <-> male CNS (`FLYWIRE` -> `JRCFIB2022M`;
# `JRCFIB2022Mraw` is the same space in 8-nm voxels), so the FlyWire overlay works out of the
# box. Hemibrain and MANC need the H5 deformation fields
# (`flybrains.download_jrc_transforms()`, `flybrains.download_jrc_vnc_transforms()`, several
# 100 MB each); without them their overlay is skipped with a message.

# %%
match_type = 'DNde003'
male_df, _ = fetch_neurons(NC(type=match_type), client=c)
male_df[['bodyId', 'instance', 'flywireType', 'hemibrainType', 'mancType']]

# %%
fw_type = male_df.flywireType.dropna().unique().tolist()
hb_type = male_df.hemibrainType.dropna().unique().tolist()
manc_type = male_df.mancType.dropna().unique().tolist()

male = neu.fetch_skeletons(NC(bodyId=male_df.bodyId.tolist()), client=c, heal=True)
fw_df, _ = fetch_neurons(NC(type=fw_type), client=c_fw)
flywire = fetch_flywire_skeletons(fw_df.bodyId.tolist())
hemibrain = neu.fetch_skeletons(NC(type=hb_type), client=c_hb, heal=True)
manc = neu.fetch_skeletons(NC(type=manc_type), client=c_manc, heal=True)
print(f'male CNS {len(male)}, FlyWire {len(flywire)}, hemibrain {len(hemibrain)}, MANC {len(manc)} neurons')

# %%
COL = {'FlyWire': '#e8709f', 'hemibrain': '#f28e2b', 'MANC': '#2cb5c9', 'male CNS': 'black'}
# (dataset, title, neurons, neuron units -> nm, template meshes, mesh units -> nm)
# neuPrint skeletons are in 8-nm voxels except FlyWire (nm); flybrains meshes are in nm,
# the male CNS ROI meshes in voxels.
panels = [
    ('FlyWire', f'FlyWire (female) {"/".join(fw_type)}', flywire, 1.0, [flybrains.FLYWIRE.mesh], 1.0),
    ('hemibrain', f'hemibrain (female) {"/".join(hb_type)}', hemibrain, VOXEL_NM, [flybrains.JRCFIB2018F.mesh], 1.0),
    ('MANC', f'MANC (male) {"/".join(manc_type)}', manc, VOXEL_NM, [flybrains.MANC.mesh], 1.0),
    ('male CNS', f'male CNS {match_type}', male, VOXEL_NM, cns, VOXEL_NM),
]
fig, axes = plt.subplots(1, 4, figsize=(16, 6))
for ax, (dataset, title, nl, neuron_to_nm, meshes, mesh_to_nm) in zip(axes, panels):
    draw_silhouettes(ax, meshes, scale=mesh_to_nm / 1000)                    # µm
    draw_neurons(ax, nl, COL[dataset], linewidth=0.6, scale=neuron_to_nm / 1000)
    frame_to(ax, meshes, scale=mesh_to_nm / 1000)
    ax.set_title(f'{title} ({len(nl)})', fontsize=10)
    add_scalebar(ax, 100, '100 µm')
plt.show()

# %%
# overlay in male CNS voxel space
overlay = {'male CNS': male}
overlay['FlyWire'] = navis.xform_brain(flywire, source='FLYWIRE', target='JRCFIB2022Mraw')
for name, nl, source in [('hemibrain', hemibrain, 'JRCFIB2018Fraw'), ('MANC', manc, 'MANCraw')]:
    try:
        overlay[name] = navis.xform_brain(nl, source=source, target='JRCFIB2022Mraw')
    except Exception as err:
        print(f'{name}: no bridging transform to the male CNS available ({type(err).__name__}); '
              'run flybrains.download_jrc_transforms() / download_jrc_vnc_transforms() to enable it')

fig, ax = plt.subplots(figsize=(6, 9))
draw_silhouettes(ax, cns)
for i, (name, nl) in enumerate(overlay.items()):
    draw_neurons(ax, nl, COL[name], linewidth=0.8, alpha=0.9)
    ax.text(0.02, 0.98 - 0.04 * i, name, color=COL[name], transform=ax.transAxes, va='top')
finish(ax)
ax.set_title(f'{match_type}: transformed into male CNS space', fontsize=10)
plt.show()

# %% [markdown]
# ## Fig. 3A: male CNS brain vs. female FAFB/FlyWire brain
#
# Same recipe as Fig. 1B for the two brains (no VNC), drawn side by side in µm at the same
# scale. FlyWire skeletons have roughly ten times more nodes than male CNS skeletons and are
# downsampled for drawing.

# %%
n_sample = 800
male_ids = neurons_df[neurons_df.region != 'VNC'].bodyId.sample(n_sample, random_state=0).tolist()
male_brain = neu.fetch_skeletons(NC(bodyId=male_ids), client=c, heal=False, max_threads=8)

fw_ids = fetch_custom("MATCH (n:Neuron) WHERE n.type IS NOT NULL RETURN n.bodyId AS bodyId",
                      client=c_fw).bodyId
fw_ids = fw_ids.sample(n_sample, random_state=0).tolist()
female_brain = navis.downsample_neuron(fetch_flywire_skeletons(fw_ids), 10, inplace=False)
print(f'{len(male_brain)} male, {len(female_brain)} female neurons')

# %%
rng = np.random.default_rng(1)
brains = [(male_brain, brain, 1 / UM, 'Male CNS (male)'),
          (female_brain, [flybrains.FLYWIRE.mesh], 1 / 1000, 'FAFB/FlyWire (female)')]
# same scale on both panels: half-width of the larger brain (µm)
half = max(np.ptp(np.vstack([projected(m.vertices, scale=s) for m in meshes]), axis=0).max()
           for _, meshes, s, _ in brains) / 2 * 1.03

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
for ax, (nl, meshes, to_um, title) in zip(axes, brains):
    draw_silhouettes(ax, meshes, scale=to_um)
    draw_neurons(ax, nl, [tuple(rng.random(3)) for _ in nl], linewidth=0.3, scale=to_um)
    frame_to(ax, meshes, scale=to_um, half=half)
    ax.set_title(title)
    add_scalebar(ax, 100, '100 µm')
plt.show()

# %% [markdown]
# ## Fig. 3D: an isomorphic cell type, male vs. female
#
# One neuron per sex in a single brain outline: the male cell on the viewer's left, the
# female (FlyWire) cell transformed into male CNS space on the right, separated by the
# midline of the central-brain mesh. Colours follow the paper (male green, female magenta).

# %%
iso_type = 'DP1m_adPN'
MALE, FEMALE = '#1b7f3b', '#c51b7d'

iso_df, _ = fetch_neurons(NC(type=iso_type), client=c)
iso_male = neu.fetch_skeletons(NC(bodyId=iso_df.bodyId.tolist()), client=c, heal=True)
iso_fw_df, _ = fetch_neurons(NC(type=iso_df.flywireType.dropna().unique().tolist()), client=c_fw)
iso_female = navis.xform_brain(fetch_flywire_skeletons(iso_fw_df.bodyId.tolist()),
                               source='FLYWIRE', target='JRCFIB2022Mraw')

midline = brain[0].vertices[:, 0].mean()           # CentralBrain mesh centre
left = [n for n in iso_male if n.nodes.x.mean() < midline]
right = [n for n in iso_female if n.nodes.x.mean() > midline]
print(f'{len(iso_male)} male / {len(iso_female)} female neurons; showing {len(left)} male left, {len(right)} female right')

# %%
fig, ax = plt.subplots(figsize=(7, 5))
draw_silhouettes(ax, brain)
draw_neurons(ax, left, MALE, linewidth=0.9)
draw_neurons(ax, right, FEMALE, linewidth=0.9)
finish(ax)
ax.axvline(midline, color='grey', linewidth=0.8)
ax.text(0.25, 0.97, 'male', color=MALE, transform=ax.transAxes, ha='center', va='top', fontsize=12)
ax.text(0.75, 0.97, 'female', color=FEMALE, transform=ax.transAxes, ha='center', va='top', fontsize=12)
ax.set_title(f'{iso_type} (isomorphic)', style='italic', fontsize=11)
add_scalebar(ax, 100 * UM, '100 µm')
plt.show()

# %% [markdown]
# ## Fig. 7P: a connectivity cluster on the whole CNS
#
# Level-6 hierarchical stochastic block model communities of the male central brain are
# published in `supplemental_data/mcns_lvl_6_hsbm_communities.feather` (one row per
# community with its `types` and `bodyId` arrays and an `enriched` flag). Cluster 102 is the
# community most enriched for male-specific and dimorphic types (pC1/P1, mAL). Neurons are
# coloured by the neuPrint `dimorphism` field: blue = male-specific, gold = sexually
# dimorphic (the "potentially ..." labels are merged with their parent class).

# %%
communities_file = data_folder / 'mcns_lvl_6_hsbm_communities.feather'
if not communities_file.exists():
    urlretrieve('https://github.com/flyconnectome/2025malecns/raw/main/supplemental_data/'
                'mcns_lvl_6_hsbm_communities.feather', communities_file)
communities = pd.read_feather(communities_file).set_index('community_id')
communities[['type_n', 'enriched']].head()

# %%
cluster_id = 102
cluster = communities.loc[cluster_id]
cluster_df, _ = fetch_neurons(NC(bodyId=[int(b) for b in cluster.bodyId]), client=c)
cluster_neurons = neu.fetch_skeletons(NC(bodyId=cluster_df.bodyId.tolist()), client=c,
                                      heal=False, max_threads=8)
print(f'cluster {cluster_id}: {cluster.type_n} types, {len(cluster_df)} neurons; '
      f'types: {", ".join(cluster.types[:8])}, ...')
cluster_df.dimorphism.value_counts(dropna=False)

# %%
DIMORPHISM_COLOR = {'male-specific': '#3d7bd9', 'potentially male-specific': '#3d7bd9',
                    'sexually dimorphic': '#e0a81e', 'potentially sexually dimorphic': '#e0a81e'}
color_of = dict(zip(cluster_df.bodyId, cluster_df.dimorphism.map(DIMORPHISM_COLOR).fillna('#9a9a9a')))

fig, ax = plt.subplots(figsize=(6, 9))
draw_silhouettes(ax, cns)
draw_neurons(ax, cluster_neurons, [color_of[int(n.id)] for n in cluster_neurons], linewidth=0.5)
finish(ax)
ax.set_title(f'cluster {cluster_id}', fontsize=11)
ax.text(0.98, 0.06, 'male-specific', color=DIMORPHISM_COLOR['male-specific'],
        transform=ax.transAxes, ha='right')
ax.text(0.98, 0.02, 'sexually dimorphic', color=DIMORPHISM_COLOR['sexually dimorphic'],
        transform=ax.transAxes, ha='right')
add_scalebar(ax, 100 * UM, '100 µm')
plt.show()
