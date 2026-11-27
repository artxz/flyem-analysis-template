import pickle
import re
import unicodedata
from pathlib import Path
import logging
from typing import Any, Union
import datetime
import warnings

import pandas as pd
import numpy as np
from IPython.display import Image, display
import PIL
from PIL import ImageChops, ImageDraw, ImageFont
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib import patches as mpl_patches
from matplotlib import path as mpl_path
from matplotlib.figure import Figure as MplFigure
from sklearn.decomposition import PCA
from scipy.spatial.transform import Rotation as scipy_R # define rotation matrix
import alphashape #make alpha shape

import plotly.graph_objects as go
import plotly.express as px
import plotly.colors as po

from neuprint import NeuronCriteria as NC
import navis
import navis.interfaces.neuprint as neu
import cloudvolume as cv

from .. import config
from ..neuprint_client import _resolve as _resolve_dataset
from ..neuprint_client import get_client
from .ng_view import NG_View
from . import roi_assets

logging.getLogger('navis').setLevel(logging.WARN)


def _dataset_cache_dir(kind:str) -> Path:
    """Return `CACHE_DIR/<kind>/<dataset tag>` for the dataset neuPrint queries go to.

    The dataset is the current default neuPrint client's, if one exists, and
    otherwise the one `connect()` would pick, so cache hits need no connection.
    The registry tag (`malecns_v1.0`) is used rather than the neuPrint name
    (`male-cns:v1.0`), whose colon is not allowed in Windows paths.
    """
    import neuprint

    try:
        client = neuprint.default_client()
        server, dataset = client.server, client.dataset
    except Exception:  # no default client yet
        server, dataset = _resolve_dataset(None, None)
    return config.CACHE_DIR / kind / config.dataset_tag(dataset, server)




def slugify(value, to_lower=True, allow_unicode=False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.

    original source: https://docs.djangoproject.com/en/4.1/_modules/django/utils/text/#slugify
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[\(\)]", "_", value)
    value = re.sub(r"[^\w\s-]", "", value)
    if to_lower:
        value = value.lower()
    return re.sub(r"[-\s]+", "-", value)

def get_synapses(
    body_id:int
  , ignore_cache:bool=False
) -> pd.DataFrame:
    """
    Retrieve synapses for neuron.

    For performance reasons, this function first attempts to load the synapses from a local cache.
    If this fails, the synapses are retrieved from neuprint and saved in the cache. The cache is
    located at `CACHE_DIR/synapses/<dataset>`. To force a reload, you can either set the
    ignore_cache flag or delete files from the cache.

    Parameters
    ----------
    body_id : int
        the body ID of a neuron
    ignore_cache : int, default = False
        When enabled, load the synapses from neuprint and overwrite the currently cached file.

    Returns
    -------
    """
    cachedir = _dataset_cache_dir("synapses")
    cachedir.mkdir(parents=True, exist_ok=True)
    syn_file = cachedir / f"sy_{body_id}.pickle"
    if not ignore_cache and syn_file.is_file():
        with syn_file.open('rb') as syn_fh:
            syns = pickle.load(syn_fh)
    else:
        syns = neu.fetch_synapses(NC(bodyId=body_id), client=get_client())
        with syn_file.open('wb') as syn_fh:
            pickle.dump(syns, syn_fh)
    return syns


def get_skeleton(
    body_id:int
  , ignore_cache:bool=False
) -> neu.NeuronList:
    """
    Get a skeleton for a neuron.

    For performance reasons, this function first attempts to load the skeleton from a local cache.
    If this fails, the skeleton is retrieved from neuprint and saved in the cache. The cache is
    located at `CACHE_DIR/skeletons/<dataset>`. To force a reload, you can either set the
    ignore_cache flag or delete files from the cache.

    Parameters
    ----------
    body_id : int
        the body ID of a neuron
    ignore_cache : bool, default = False
        When enabled, load the skeleton from neuprint and overwrite the currently cached file.

    Returns
    -------
    skel : NeuronList
        A skeleton for the neuron of body_id
    """
    cachedir = _dataset_cache_dir("skeletons")
    cachedir.mkdir(parents=True, exist_ok=True)
    skel_file = cachedir / f"sk_{body_id}.pickle"
    if not ignore_cache and skel_file.is_file():
        with skel_file.open('rb') as skel_fh:
            skel = pickle.load(skel_fh)
    else:
        try:
            skel = neu.fetch_skeletons(NC(bodyId=body_id), client=get_client())
            with skel_file.open('wb') as skel_fh:
                pickle.dump(skel, skel_fh)
        except ValueError:
            skel = None
    return skel


def get_skeletons(
    body_ids:list[int]
  , ignore_cache:bool=False
) -> navis.NeuronList:
    """
    Get skeletons for a list of neurons.

    Retrieve the skeleton of a list of neurons via `get_skeleton()`. Set `ignore_cache` if all of
      the skeletons should be retrieved directly from the database and not your local cache.

    Parameters
    ----------
    body_ids : list of int
        the body IDs of neurons
    ignore_cache : bool, default = False
        When enabled, load the skeleton from neuprint and overwrite the currently cached file.

    Returns
    -------
    skeletons : NeuronList
        A skeleton for the neuron of body_id or a list of skeletons
    """
    skels = []
    for body_id in body_ids:
        skel = get_skeleton(body_id, ignore_cache=ignore_cache)
        skels.append(skel)
    return skels


def get_mesh(
    body_id:int
  , ignore_cache:bool=False
  , lod:int=2
  , save_cache:bool=True
) -> navis.NeuronList:
    """
    Retrieve mesh for neuron.

    For performance reasons, this function first attempts to load the mesh from a local cache.
    If this fails, the mesh is retrieved from neuprint and saved in the cache. The cache is
    located at `CACHE_DIR/meshes/<dataset>`. To force a reload, you can either set the
    ignore_cache flag or delete files from the cache.

    Parameters
    ----------
    body_id : int
        the body ID of a neuron
    ignore_cache : bool, default = False
        When enabled, load the mesh from neuprint and overwrite the currently cached file.
    lod : int, default = 2
        Level of detail for multi-resolution meshes. `None` fetches the finest mesh
        (e.g. ~700k vertices); a higher integer (e.g. `2`) fetches a coarser, much
        lighter mesh — useful when rendering many neurons at once. The returned
        coordinates are in the 8 nm-voxel frame regardless of `lod`. Cached per-LOD.
    save_cache : bool, default = True
        When disabled, a freshly-fetched mesh is not written to the cache — useful
        for one-off fetches (e.g. large batches of body IDs used only once) that would
        otherwise fill the cache with entries you'll never reuse.

    Returns
    -------
    mesh : NeuronList
        A mesh for the neuron of body_id
    """

    cachedir = _dataset_cache_dir("meshes")
    mesh_fn = cachedir / (f"ms_{body_id}.pickle" if lod is None else f"ms_{body_id}_lod{lod}.pickle")
    if not ignore_cache and mesh_fn.is_file():
        with mesh_fn.open('rb') as mesh_fh:
            mesh = pickle.load(mesh_fh)
    else:
        ## FIXME(@floesche): remove SEGMENTATION_SOURCE in the future
        mesh = neu.fetch_mesh_neuron(
            NC(bodyId=body_id)
          , seg_source=config.SEGMENTATION_SOURCE
          , lod=lod
          , client=get_client())
        if save_cache:
            cachedir.mkdir(parents=True, exist_ok=True)
            with mesh_fn.open('wb') as mesh_fh:
                pickle.dump(mesh, mesh_fh)
    return mesh


def get_meshes(
    body_ids:list[int]
  , ignore_cache:bool=False
  , lod:int=2
  , save_cache:bool=True
) -> navis.NeuronList:
    """
    Retrieve mesh for list of neurons.

    Retrieve the meshes of a list of neurons via `get_mesh()`. Set `ignore_cache` if all of the
      meshes should be retrieved directly from the database and not from your local cache.

    Parameters
    ----------
    body_id : list of int
        the body IDs of neuron(s)
    ignore_cache : bool, default = False
        When enabled, load the mesh from neuprint and overwrite the currently cached file.
    lod : int, default = 2
        Level of detail passed to `get_mesh()`. `1` = finest mesh; a higher integer
        (e.g. `2`) fetches lighter meshes, useful for rendering many neurons at once.
    save_cache : bool, default = True
        Passed to `get_mesh()`. Set `False` to skip writing freshly-fetched meshes to
        the cache (e.g. for large one-off batches you won't reuse).

    Returns
    -------
    mesh : NeuronList
        A mesh for the neuron of body_id or a list of meshes
    """
    meshes = []
    for body_id in body_ids:
        mesh = get_mesh(body_id, ignore_cache=ignore_cache, lod=lod, save_cache=save_cache)
        meshes.append(mesh)
    return meshes


def get_roi(
    roi_name:str
  , ignore_cache:bool=False
):
    """
    Retrieve ROI.

    For performance reasons, this function attempts to load the ROI from a local cache first.
    If this fails, the ROI is retrieved from neuprint and saved in the cache. The cache is
    located at `CACHE_DIR/rois/<dataset>`. To force a reload, you can either set the
    `ignore_cache` flag or delete files from the cache folder.

    Parameters
    ----------
    roi_name : str
        the name of an ROI
    ignore_cache : bool, default=False
        When enabled, load the mesh from neuprint and overwrite the currently cached file.

    Returns
    -------
    roi : navis.Volume
        An ROI.
    """
    cachedir = _dataset_cache_dir("rois")
    cachedir.mkdir(parents=True, exist_ok=True)
    roi_fn = cachedir / f"roi_{slugify(roi_name)}.pickle"
    if not ignore_cache and roi_fn.is_file():
        with roi_fn.open('rb') as roi_fh:
            roi = pickle.load(roi_fh)
    else:
        roi = neu.fetch_roi(roi_name, client=get_client())
        with roi_fn.open('wb') as roi_fh:
            pickle.dump(roi, roi_fh)
    return roi


def calc_orient(skeleton:pd.DataFrame) -> list[list[float]]:
    """
    Calculate ideal camera orientations for a Neuron.

    Based on the coordinates skeleton nodes, PCA finds the two primary orientations and returns an
      array with three vectors: the first two principal components and an orthogonal vector to
      these two. The first and the third vector are ideal to position the plotly scene camera.

    Parameters
    ----------
    skeleton : NeuronList
        A skeleton

    Returns
    -------
    orient : list[list[float]]
        three vectors in an array
    """
    if len(skeleton[0].edge_coords) == 0:
        return []
    dim_ed = skeleton[0].edge_coords.shape
    etg = skeleton[0].edge_coords.reshape(dim_ed[0]*dim_ed[1], dim_ed[2])
    etg = np.unique(etg, axis=0) # remove duplicates
    et_mn = etg.mean(axis=0)
    et_norm = etg-et_mn
    pca = PCA(n_components=2)
    pca.fit(et_norm)
    orient = pca.components_
    orient = np.append(
        orient
      , [np.cross(orient[0], orient[1])]
      , axis=0)
    return orient


def group_plotter(
    body_ids:list[int]
  , colors:list[tuple[int]]=None
  , plot_roi:str=None
  , shadow_rois:list[str]=None
  , prune_roi:str=None
  , camera_distance:float=2.0
  , ignore_cache:bool=False
  , plot_synapses:bool=True
  , plot_skeleton:bool=True
  , plot_mesh:bool=False
  , view:NG_View=NG_View.SVD
) -> go.Figure:
    """
    Plot a group of neurons.

    To plot a group of neurons, this functions attempts to retrieve the data from the local cache
    first. If that fails, it loads the skeleton and synapses from neuprint and then stores them in
    the local cache.

    Parameters
    ----------
    body_ids : list[int]
        List of neuron body IDs. The body IDs are given as numbers. The first neuron in this list
        will be used to determine the camera position (maximum visibility). The list can contain
        `None`.
    colors   : list[tuple[int]]
        List of colors. The list should be the same length or shorter than the list of body_ids.
        Each color is represented by a tuple with 4 entries in the range [0…1] representing (red,
        green, blue, alpha). If there are less colors than neurons, the neurons that have not
        received a color will be shown in gray (.5, .5, .5, .7). If the list of `body_ids` contains
        `None`, the associated color will be skipped. If no colors are given, the Plotlys Light24
        palette will be used.
    plot_roi : str, default=None
        Name of a ROI that should be plotted together with the Neurons
    shadow_rois : list[str], default=None
        Names of the ROIs that are used as a backdrop for the sliced neurons.
    prune_roi : str, default=None
        All parts of the neurons outside the ROI will be removed from the plot. Special value
            `slice` will cut a slice for the gallery view.
    camera_distance : float, default=2.0
        For smaller groups of neurons, a value between 1 and 2 should be reasonable.
    ignore_cache : bool, default=False

    Returns
    -------
    fig : go.Figure
        Plotly figure with the skeleton and synapses for all the body IDs. The layout is reasonable
        for this application and differs from the plotly default.
    """
    allowed_s_roi = ['ME(R)', 'LO(R)', 'LOP(R)']
    assert shadow_rois is None or set(shadow_rois) <= set(allowed_s_roi)\
      , f"List of shadow ROIs ({shadow_rois}) is different from  allowed ROIs: {allowed_s_roi}."

    fig = go.Figure()
    if not colors:
        colors = [po.hex_to_rgb(col) for col in px.colors.qualitative.Light24]
        colors = colors * int(np.ceil(len(body_ids) / len(colors)))
        colors = [ tuple([cval / 255 for cval in col]) + (1,) for col in colors]
    if plot_roi:
        roi = get_roi(plot_roi, ignore_cache=ignore_cache)
        f_roi = navis.plot3d(roi, inline=False)
        fig.add_trace(f_roi.data[0])
    if shadow_rois:
        for roi in shadow_rois:
            s_roi_layer_m, _ = get_shadow_roi_layers(roi, ignore_cache=ignore_cache)
            f_roi = navis.plot3d(s_roi_layer_m
                , color=['gray']*10
                , alpha=0.4, inline=False)
            for l_mesh in f_roi.data:
                fig.add_trace(l_mesh)
            _ , s_roi_b = get_shadow_roi(roi, ignore_cache=ignore_cache)
            fig.add_trace(
                go.Scatter3d(x=s_roi_b[:,0], y=s_roi_b[:,1], z=s_roi_b[:,2]
              , mode='lines', line={'color':'gray', 'width':3})
            )
    p_roi = None
    if prune_roi and prune_roi != "slice":
        if prune_roi == plot_roi:
            p_roi = roi
        else:
            p_roi = get_roi(prune_roi, ignore_cache=ignore_cache)
    ori = []
    for idx, body_id in enumerate(body_ids):
        if body_id is None:
            continue
        skel = get_skeleton(body_id=body_id, ignore_cache=ignore_cache)
        if skel is None or skel.empty or len(skel.nodes)==0:
            warnings.warn(
                f"Neuron with Body ID {body_id} does not have a skeleton. Skipping cell.")
            continue
        if plot_synapses:
            syns  = get_synapses(body_id=body_id, ignore_cache=ignore_cache)
        if plot_mesh:
            mesh = get_mesh(body_id=body_id, ignore_cache=ignore_cache)
        if prune_roi == "slice":
            vn = np.array([1, 2, 0])
            vn = vn / np.linalg.norm(vn)
            vt1 = np.array([20e3, 40e3, 35e3]) * 0.85
            vt2 = np.array([22e3, 44e3, 35e3]) * 0.95
            d1 = vt1 @ vn
            d2 = vt2 @ vn
            # get the cross section of a neuron
            if plot_skeleton:
                ind_ske_in = skel[0]\
                    .nodes[['x','y','z']]\
                    .apply(lambda row: row @ vn > d1 and row @ vn < d2, axis=1)
                skel = navis\
                    .subset_neuron(skel[0], ind_ske_in.values, inplace=False)
            if plot_mesh:
                msh_v = pd.DataFrame(mesh[0].vertices, columns=['x', 'y', 'z'])
                ind_msh_in = msh_v.apply(
                    lambda row: row @ vn > d1 and row @ vn < d2
                  , axis=1
                )
                mesh = navis.subset_neuron(mesh[0], ind_msh_in.values, inplace=False)
            if plot_synapses:
                syns_in = syns.apply(
                    lambda row: row[['x', 'y', 'z']] @ vn > d1 and row[['x', 'y', 'z']] @ vn < d2
                  , axis =1
                )
                syns = syns[syns_in]
        elif prune_roi:
            if plot_skeleton:
                skel = navis.in_volume(skel, p_roi)
            if plot_synapses:
                syns = syns[navis.in_volume(syns, p_roi)]
        if len(skel.nodes)==0:
            continue
        if colors and idx < len(colors):
            col = colors[idx]
        else:
            col = (0.5, 0.5, 0.5, 0.7) # Gray
        if len(skel.nodes)>0 and len(ori)==0:
            if view==NG_View.SVD:
                ori = calc_orient(skel)
            else:
                #r = scipy_r.from_quat(view.orientation)
                #ori = r.as_matrix()
                # FIXME(@floesche): use non-static view.
                ori = [[-4, 3, -4], [0, 0, 0], [31304.951684997053, 62609.90336999411, 0.0]]
        col_st = f'rgba({int(col[0]*255)},{int(col[1]*255)},{int(col[2]*255)},{col[3]})'
        if plot_skeleton:
            fig_skel = navis.plot3d(skel, inline=False, color=col[0:4])
            if fig_skel.data:
                fig_skel.data[0].hovertemplate = f"body_id: {body_id}<extra></extra>"
                fig_skel.data[0].name=f"ID {body_id}"
                fig_skel.data[0].legendgroup=idx
                fig_skel.data[0].line.color=col_st
                fig.add_trace(fig_skel.data[0])
        if plot_mesh:
            fig_mesh = navis.plot3d(mesh, inline=False, color=col[0:4])
            if fig_mesh.data:
                fig.add_trace(fig_mesh.data[0])
        if plot_synapses:
            fig.add_trace(go.Scatter3d(
                x=syns['x'], y=syns['y'], z=syns['z'],
                customdata=syns['bodyId'],
                legendgroup=idx,
                name=f"{body_id}",
                mode='markers',
                showlegend=False,
                hovertemplate = 'body_id: %{customdata}<extra></extra>',
                marker = {
                    "size":1.5,
                    "color": f"rgba(5,5,5,{col[3]})",
                    "line": {
                        "width":.5
                        , "color": col_st}
                }
            ))
    zoom = 2.0/camera_distance
    if len(ori) > 0:
        fig.update_scenes(
            camera={
                "up": {"x":ori[0][0], "y":ori[0][1], "z":ori[0][2]}
              , "eye": {
                    "x":ori[2][0]*camera_distance
                  , "y":ori[2][1]*camera_distance
                  , "z":ori[2][2]*camera_distance}
              , "center": {"x":0, "y":0, "z":0}
              , "projection": {"type": "orthographic"}}
            )
    fig.update_layout(
        margin={'l':0, 'r':0, 'b':0, 't':20}
      , showlegend=True
      , scene = {
            # "aspectmode": "manual",
            # "aspectratio": {'x': 1, 'y': 1, 'z':1},
            "xaxis" : {
                "showgrid": False
              , "gridcolor": 'rgba(0,0,0,0)'
              , "showbackground": False
              , "visible": False}
          , "yaxis" : {
                "showgrid": False
              , "gridcolor": 'rgba(0,0,0,0)'
              , "showbackground": False
              , "visible": False}
          , "zaxis" : {
                "showgrid":False
              , "gridcolor": 'rgba(0,0,0,0)'
              , "showbackground":False
              , "visible":False}
          , 'aspectmode': 'cube'   # TODO: figure out why this doesn't work on large plots
          , 'aspectratio': {"x":zoom, "y":zoom, "z":zoom}    # TODO: figure out why this
                                                             # doesn't work when ROIs are plotted
    })
    if prune_roi == 'slice':
        fig.update_layout(
            scene = {
                "xaxis" : {
                    "autorange": False
                  , "range": [5400, 46000] # [5437.458372673634, 45525.45722734322]
                }
              , "yaxis" : {
                    "autorange": False
                  , "range": [23000, 42000] #[23135.281677246094, 41176.317932128906]
                }
              , "zaxis" : {
                    "autorange": False
                  , "range":[23500, 43500] #[22801.495262524946, 43050.66538977197]
                }
            }
        )
    return fig


def get_shadow_roi_layers(
    roi_str:str
  , ignore_cache:bool=False
) -> tuple[list[navis.Volume], list[np.ndarray]]:
    """
    Get rough estimates of slices and boundaries for the layers in one of the 3 OL neuropils
    at a fixed location. The received shapes are smoothed by alpha shape. The slicing plane
    (and location) are arbitrariyl chosen.

    Warning: This is not precise and should only be used for quick estimations.

    Parameters
    ----------
    roi_str : str
        name of the neuropil to slice (either `ME(R)`, `LO(R)`, or `LOP(R)`).
    ignore_cache : bool, default=False
        if true, download the meshes from the original data source each time. Otherwise
        use a filesystem cache.

    Returns
    -------
    layer_m : list[navis.Volume]
        a list of thinly sliced volumes, one for each layer of the neuropil.
    layer_bd : list[np.ndarray]
        a list of numpy arrays that contain 3D points representing the outline around layers.
    """
    # load layer meshes and slice them
    vn = np.array([1, 2, 0]) # normal vector
    vn = vn / np.linalg.norm(vn) # normalize
    vt1 = np.array([20e3, 40e3, 35e3]) * 0.85 # translation vector
    if roi_str == 'ME(R)':
        layer = [None] * 10
        layer_sec = [None] * 10
        layer_m = [None] * 10
        layer_bd = [None] * 10
        # selected layers
        for i in [1,3,5,7,9]:
            layer[i-1] = get_roi(
                f'ME_R_layer_{i:02d}'
              , ignore_cache=ignore_cache)   # load layer meshes with a constructed variable name
            layer_sec[i-1] = layer[i-1].section(vn, vt1)
            layer_sec[i-1] = pd.DataFrame(
                layer_sec[i-1].vertices
              , columns=['x','y','z'])  # convert TrackedArray to dataframe
            pts = layer_sec[i-1].values
            layer_m[i-1], layer_bd[i-1] = alpha_plane(pts, vn, alpha=0.0004)
    elif roi_str == 'LO(R)':
        layer = [None] * 7
        layer_sec = [None] * 7
        layer_m = [None] * 7
        layer_bd = [None] * 7
        # selected layers
        for i in [1,3,5,7]:
            layer[i-1] = get_roi(
                f'LO_R_layer_{i}'
              , ignore_cache=ignore_cache) # load layer meshes with a constructed variable name
            layer_sec[i-1] = layer[i-1].section(vn, vt1)
            layer_sec[i-1] = pd.DataFrame(
                layer_sec[i-1].vertices
              , columns=['x','y','z'])  # convert TrackedArray to dataframe
            pts = layer_sec[i-1].values
            layer_m[i-1], layer_bd[i-1] = alpha_plane(pts, vn, alpha=0.0004)
    elif roi_str == 'LOP(R)':
        layer = [None] * 4
        layer_sec = [None] * 4
        layer_m = [None] * 4
        layer_bd = [None] * 4
        # selected layers
        for i in [1,3]:
            layer[i-1] = get_roi(
                f'LOP_R_layer_{i}'
              , ignore_cache=ignore_cache) # load layer meshes with a constructed variable name
            layer_sec[i-1] = layer[i-1].section(vn, vt1)
            layer_sec[i-1] = pd.DataFrame(
                layer_sec[i-1].vertices
              , columns=['x','y','z'])  # convert TrackedArray to dataframe
            pts = layer_sec[i-1].values
            layer_m[i-1], layer_bd[i-1] = alpha_plane(pts, vn, alpha=0.0004)
    return layer_m, layer_bd


def get_shadow_roi(
    roi_str:str
  , ignore_cache:bool=False
) -> tuple[navis.Volume, np.ndarray]:
    """
    Get rough estimates of slices and boundaries for one of the 3 OL neuropils at a fixed location.
    The received shapes are smoothed by alpha shape. The slicing plane (and location) are
    arbitrariyl chosen.

    Warning: This is not precise and should only be used for quick estimations.

    Parameters
    ----------
    roi_str : str
        name of the neuropil to slice (either `ME(R)`, `LO(R)`, or `LOP(R)`).
    ignore_cache : bool, default=False
        if true, download the meshes from the original data source each time. Otherwise
        use a filesystem cache.

    Returns
    -------
    m : navis.Volume
        a thinly sliced volume of the neuropil.
    bd : np.ndarray
        a numpy arrays that contain 3D points representing the outline around the neuropil.
    """
    vn = np.array([1, 2, 0]) # normal vector
    vn = vn / np.linalg.norm(vn) # normalize
    vt1 = np.array([20e3, 40e3, 35e3]) * 0.85 # translation vector
    bound = get_roi(roi_str, ignore_cache=ignore_cache)
    sec = bound.section(vn, vt1)
    # convert TrackedArray to dataframe
    sec = pd.DataFrame(sec.vertices, columns=['x','y','z'])
    m, bd = alpha_plane(sec.values, vn, alpha=0.0004)
    return m, bd


def show_figure(
    fig:go.Figure
  , width:int=1200, height:int=800
  , static:bool=False
  , showlegend:bool=True
) -> None:
    """
    Outputs figure either as dynamic (default) or static image

    Parameters
    ----------
    fig : go.Figure
        The figure to output
    width : int
        width of the output in px
    height : int
        height of the output in px
    static : bool, default=False
        shows go.Figure after resizing, generates png and displays it in IPython otherwise
    showlegend : bool, default=True
        show or remove legend in the figure
    """
    fig.update_layout(showlegend=showlegend)
    if static:
        img_bytes = fig.to_image(
            format="png"
          , width=width, height=height
          , scale=1)
        display(Image(img_bytes))
    else:
        fig.update_layout(
            width=width,
            height=height
        )
        fig.show(config={"displayModeBar":False})


def save_figure(
    fig:go.Figure|MplFigure
  , path:str|Path
  , width:int=1200, height:int=800
  , scale:float=1
  , dpi:int=300
  , showlegend:bool=False
  , bg_color:str|None=None
  , replace:bool=True
  , tight:bool=True
  , **save_kws:Any
) -> Path:
    """
    Save a plotly or matplotlib figure to an image file at an explicit path.

    Accepts either backend, so it works for both `plot_3d_cns` (plotly) and
    `plot_2d_cns` (matplotlib), dispatching on the type of `fig`. The output format
    comes from the suffix of `path` in both cases (`.png`, `.svg`, `.pdf`, …). There
    is no default output directory: `path` is required, and any missing parent
    directories are created.

    Note that `fig` is modified in place — `showlegend` and the background colors are
    applied to the figure itself rather than to a copy, to avoid duplicating large mesh
    traces.

    A caveat worth knowing when picking a format: plotly renders 3-D traces through
    WebGL, so a `plot_3d_cns` figure saved as `.pdf`/`.svg` is a *bitmap* inside a
    vector container. For genuinely vector output use `plot_2d_cns`, whose matplotlib
    output stays editable.

    Parameters
    ----------
    fig : go.Figure|MplFigure
        figure to be saved, from either backend
    path : str|Path
        full output path *including* the file extension, e.g.
        `results/cell_gallery/lc10a.png`. The extension selects the output format.
    width : int, default=1200
        width of the output image in px. **plotly only** — a matplotlib figure carries
        its own size, set via `figsize` when it was created.
    height : int, default=800
        height of the output image in px. **plotly only**, as `width`.
    scale : float, default=1
        resolution multiplier — `2` doubles the pixel dimensions without changing the
        layout. **plotly only**; use `dpi` for matplotlib.
    dpi : int, default=300
        output resolution. **matplotlib only**; 300 is a reasonable print default.
    showlegend : bool, default=False
        show or remove the legend (both backends)
    bg_color : str, default=None
        background color. `None` (the default) gives a fully transparent background;
        pass any CSS color (`'white'`, `'#fff'`) for an opaque one. Formats without an
        alpha channel (e.g. `.jpg`) cannot represent transparency, so set a color when
        saving to those.
    replace : bool, default=True
        overwrite an existing file. When `False`, a timestamp is inserted before the
        suffix instead, leaving the existing file untouched.
    tight : bool, default=True
        trim surrounding whitespace (`bbox_inches='tight'`). **matplotlib only** —
        plotly framing is controlled by the figure's own margins.
    **save_kws
        extra keyword arguments forwarded to the backend writer, either
        `go.Figure.write_image()` or `MplFigure.savefig()`

    Returns
    -------
    img_fn : Path
        path the image was written to. Differs from `path` when `replace=False` and the
        file already existed.
    """
    if path is None:
        raise ValueError(
            "`path` is required: pass the full output path including the file extension"
            ", e.g. 'results/cell_gallery/lc10a.png'.")
    img_fn = Path(path)
    if not img_fn.suffix:
        raise ValueError(
            f"`path` needs a file extension to select the output format, got '{img_fn}'.")

    img_fn.parent.mkdir(parents=True, exist_ok=True)
    if img_fn.exists() and not replace:
        today_str = datetime.datetime.today().strftime("%Y-%m-%dT%H-%M-%S")
        img_fn = img_fn.with_name(f"{img_fn.stem}_{today_str}{img_fn.suffix}")

    # matplotlib is checked first because it is unambiguous; plotly is then duck-typed
    # on `write_image` so `go.FigureWidget` works as well as `go.Figure`.
    if isinstance(fig, MplFigure):
        if not showlegend:
            for axis in fig.axes:
                legend = axis.get_legend()
                if legend is not None:
                    legend.remove()
        save_kws.setdefault('bbox_inches', 'tight' if tight else None)
        if bg_color is None:
            save_kws.setdefault('transparent', True)
        else:
            save_kws.setdefault('facecolor', bg_color)
            save_kws.setdefault('edgecolor', 'none')
        fig.savefig(img_fn, dpi=dpi, **save_kws)
    elif hasattr(fig, 'write_image'):
        fig.update_layout(
            showlegend=showlegend
          , paper_bgcolor='rgba(0,0,0,0)' if bg_color is None else bg_color
          , plot_bgcolor='rgba(0,0,0,0)' if bg_color is None else bg_color
        )
        fig.write_image(
            img_fn
          , width=width, height=height
          , scale=scale
          , **save_kws)
    else:
        raise TypeError(
            f"`fig` must be a plotly or matplotlib figure, got {type(fig).__name__}.")
    return img_fn


_anterior_font = None


_RASTER_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}


def save_figure_anterior(
    fig:go.Figure|MplFigure
  , path:str|Path
  , label:str|None=None
  , width:int=1523, height:int=850
  , dpi:int=300
  , pad:int=12
  , font_size:int=22
) -> Path:
    """
    Save an anterior-view figure as a tight, pixel-trimmed raster image.

    Wraps `save_figure()`, then (1) auto-trims the white margins left around the
    rendered brain, and (2) optionally draws `label` inside the top-right corner of
    the cropped image — drawn *into the pixels* rather than as a plot annotation, so
    it never shifts the crop or adds whitespace.

    Works with figures from either `plot_3d_cns` (plotly) or `plot_2d_cns`
    (matplotlib). Because the trim and the label are pixel operations, the output
    must be a raster format — saving a vector `.pdf`/`.svg` through this function
    raises. Use `save_figure()` directly for vector output.

    The default `width`/`height` (1523x850) match the CNS frontal aspect ratio
    (the brain is wider than tall), minimizing wasted canvas before the trim.

    Parameters
    ----------
    fig : go.Figure|MplFigure
        figure to save (e.g. from `plot_3d_cns(..., show_silhouette=True)`)
    path : str|Path
        full output path including a raster extension, e.g.
        `results/cell_gallery/lc10a.png`. Always replaced.
    label : str, default=None
        text drawn in the top-right corner; omit for no label
    width, height : int
        render size in px before trimming (plotly figures only)
    dpi : int, default=300
        output resolution for matplotlib figures
    pad : int, default=12
        white border (px) kept around the content after trimming
    font_size : int, default=22
        label font size

    Returns
    -------
    img_fn : Path
        path to the saved image
    """
    suffix = Path(path).suffix.lower()
    if suffix not in _RASTER_SUFFIXES:
        raise ValueError(
            f"`save_figure_anterior` trims and labels pixels, so it needs a raster "
            f"format, got '{suffix}'. Use `save_figure()` for vector output.")

    # `bg_color='white'` is load-bearing, not cosmetic: the trim below locates the
    # content by diffing against a white image, so `save_figure`'s transparent default
    # would flatten to black and defeat the crop.
    img_fn = save_figure(
        fig, path=path
      , width=width, height=height
      , dpi=dpi
      , bg_color='white'
      , replace=True)

    im = PIL.Image.open(img_fn).convert("RGB")
    bbox = ImageChops.difference(im, PIL.Image.new("RGB", im.size, (255, 255, 255))).getbbox()
    if bbox:
        l, t, r, b = bbox
        im = im.crop((
            max(0, l - pad), max(0, t - pad)
          , min(im.width, r + pad), min(im.height, b + pad)))
    if label:
        global _anterior_font
        if _anterior_font is None or _anterior_font.size != font_size:
            _anterior_font = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), font_size)
        draw = ImageDraw.Draw(im)
        tw = draw.textlength(label, font=_anterior_font)
        draw.text((im.width - tw - 10, 8), label, fill=(0, 0, 0), font=_anterior_font)
    im.save(img_fn)
    return img_fn


def alpha_plane(
    pts:np.ndarray
  , vn:np.ndarray
  , alpha:float=0.001
) -> Union[navis.Volume, np.ndarray]:
    """
    Make an alpha shape plane from a point set on a plane in 3D.

    First rotate the points to be on a plane parallel to the XY plane.
    Then generate a 2D alpha shape, and find the boundary points and triangle face indicies.
    Finally construct navis.Volume from original points.

    Parameters
    ----------
    pts : ndarray
        [x y z] points on a plane
    vn : ndarray
        [x y z] normal vector of the plane
    alpha : float, default=0.001
        alpha parameter for alpha shape

    Returns:
    -------
    m : navis.Volume
    pts : ndarray
        [x y z] points on the boundary
    """

    # define rotation to rotate the point to be in the plane parallel to the xy plane
    rot_mat = scipy_R.from_rotvec(
        np.cross(vn, np.array([0,0,1])) * np.arccos(vn @ np.array([0,0,1]))
    )

    pts_rot = rot_mat.apply(pts) # rotate the points
    offset = np.mean(pts_rot[:,2]) # mean of the last column (z coord) as offset
    pts_rot = np.delete(pts_rot, 2, 1) # romove the last column

    # https://alphashape.readthedocs.io/en/latest/alphashape.html
    ss = alphashape.alphasimplices(pts_rot)
    ind = []
    for point_indices, circumradius in ss:
        # print(point_indices, circumradius)
        if circumradius < 1.0 / alpha:
            ind.append(point_indices)
    ind = np.array(ind)

    # make mesh
    m = navis.Volume(vertices=pts, faces=ind)

    # get the boundary points
    alpha_shape = alphashape.alphashape(pts_rot, alpha) # alpha shape with alpha = 0.001
    alpha_shape_ext = np.array(alpha_shape.exterior.coords) # points on the boundary

    # add z coordinate  to alpha_shape_pts
    alpha_shape_pts = np.hstack((alpha_shape_ext, np.ones((alpha_shape_ext.shape[0],1))))
    alpha_shape_pts[:,2] = alpha_shape_pts[:,2] + offset # add offset
    # rotate back to 3d
    alpha_shape_pts = rot_mat.apply(alpha_shape_pts, inverse=True)

    # # DEBUG
    # # plot the mesh
    # fig_m = navis.plot3d(m,
    #     color='black', linewidth=2,
    #     inline=False, backend='plotly')

    # fig_m.show()

    return m, alpha_shape_pts


# CNS bounding box in the 8 nm-voxel frame, shared by `plot_3d_cns` (as plotly scene
# axis ranges) and `plot_2d_cns` (as matplotlib axis limits) so the two framings agree.
CNS_RANGE_X = (5000, 91000)
CNS_RANGE_Y = (5000, 53000)
CNS_RANGE_Z = (10000, 43000)

# Defaults for the pre-built ROI backdrops (see `plotting.roi_assets`). `brain` is the
# central brain plus both optic lobes -- the whole-CNS framing these plotters use;
# `cb` is the central brain alone, matching upstream visualpathways' published panels.
_OUTLINE_REGION = 'brain'
_OUTLINE_COLOR = (0.4, 0.4, 0.4, 1.0)
_OUTLINE_LINEWIDTH = 1.0
_OUTLINE_FILL_COLOR = (0.82, 0.82, 0.82, 1.0)
# plane the 3-D outline rings are drawn on, in the 8 nm-voxel frame; inside
# `CNS_RANGE_Z` and behind the neurons for the anterior camera.
_OUTLINE_Z = 30000


def _rings_to_path(rings:list[np.ndarray]) -> mpl_path.Path:
    """
    Turn a list of outline rings into one fillable matplotlib path with holes.

    Matplotlib fills a compound path by the nonzero winding rule, so a hole only
    reads as a hole if it winds against the exterior. The stored rings carry no
    orientation guarantee, so each one is re-wound here by the sign of its area:
    ring 0 counter-clockwise, every later ring clockwise.

    Parameters
    ----------
    rings : list[np.ndarray]
        `(n, 2)` rings, exterior first, as `roi_assets.get_outline_rings` returns

    Returns
    -------
    path : mpl_path.Path
        the exterior with the remaining rings punched out of it
    """

    paths = []
    for i, ring in enumerate(rings):
        # shoelace formula; positive area means counter-clockwise
        x, y = ring[:, 0], ring[:, 1]
        area = np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))
        ccw_wanted = (i == 0)
        paths.append(mpl_path.Path(ring if (area > 0) == ccw_wanted else ring[::-1]))
    return mpl_path.Path.make_compound_path(*paths)


def plot_3d_cns(
    bodyid:int|list[int]
    , celltype:str|list[str]|None=None
    , show_skeletons:bool=False
    , show_meshes:bool=False
    , show_shell:bool=False
    , show_outline:bool=False
    , show_silhouette:bool=False
    , outline_region:str=_OUTLINE_REGION
    , zoom:float=4.0
    , palette:str='viridis'
    , color:str|tuple[float, ...]|None=None
    , scatter_kws:dict|None=None
    , mesh_lod:int=2
    , annotate:bool=False
    , inline:bool=False
    , **kwargs:Any
) -> go.Figure:
    """
    Plot VPNs with a CNS outline as background, frotal view with slightly modified camera settings.

    Parameters
    ----------
    bodyid : int|list[int]
        body ID(s) of the VPNs. A single int is accepted and wrapped into a list.
    celltype : str|list[str]
        cell type(s) of the VPNs. A single str is accepted and wrapped into a list.
    show_skeletons : bool, default=False
        show the skeleton of the VPNs
    show_meshes : bool, default=False
        show the mesh of the VPNs
    show_shell : bool, default=False
        show the (translucent) shell of the CNS, as the decimated 320k-face mesh
        from `params/rois/roi_meshes` — 10x lighter through WebGL than the full
        3.06M-face shell, and indistinguishable at shell opacity 0.2.
    show_outline : bool, default=False
        show the outline of the CNS, as the pre-built anterior rings drawn at
        `_OUTLINE_Z` (exterior plus the esophageal foramen)
    show_silhouette : bool, default=False
        show the CNS shell flattened to one plane as a flat, opaque gray silhouette
        (the esophageal foramen stays a real hole). See `get_silhouette_cns()`.
    outline_region : str, default='brain'
        which ROI backdrop the shell/outline/silhouette are drawn from: `'brain'`
        (central brain + both optic lobes) or `'cb'` (central brain only).
    zoom : float, default=4.0
        zooming factor
    palette : str, default='viridis'
        color palette for the VPNs (ignored when `color` is given)
    color : color-like, default=None
        a single explicit neuron color (e.g. `(0,0,0,1)` for black) passed straight
        to `navis.plot3d`. Takes precedence over `palette`. The CNS shell/outline/
        silhouette keep their own colors regardless.
    scatter_kws : dict, default=None
        plotly scatter plot settings
    mesh_lod : int, default=2
        level of detail for neuron meshes when `show_meshes=True` (passed to
        `get_meshes()`). `1` = finest; `2` is much lighter for many neurons.
    annotate : bool, default=True
        draw a `celltype:bodyid` text annotation in the top-right corner. Set
        `False` when you intend to add a label later (e.g. `save_figure_anterior`).
    inline : bool, default=False
        show figure inline
    **kwargs :
        additional keyword arguments passed to `navis.plot3d`

    Returns
    -------
    fig : go.Figure
        plotly figure

    """

    if isinstance(bodyid, (int, np.integer)):
        bodyid = [int(bodyid)]
    if isinstance(celltype, str):
        celltype = [celltype]

    if scatter_kws is None:
        scatter_kws = {'mode': 'lines', 'color': 'black', 'opacity':1}

    # range of cns
    range_x = list(CNS_RANGE_X)
    range_y = list(CNS_RANGE_Y)
    range_z = list(CNS_RANGE_Z)
    range_ratio = np.concatenate([np.diff(range_x), np.diff(range_y), np.diff(range_z)])
    range_ratio = range_ratio / np.linalg.norm(range_ratio)
    # multiplicative factor ~ zooming
    range_ratio = range_ratio * zoom

    plotlist = []
    if show_skeletons:
        plotlist += [get_skeletons(bodyid)]
    if show_meshes:
        plotlist += [get_meshes(bodyid, lod=mesh_lod, save_cache=False)]
    if show_shell:
        plotlist += [roi_assets.get_volume(outline_region)]
    if show_outline:
        # one (n, 3) array per ring, so the foramen is not joined to the exterior
        plotlist += get_outline_rings_cns(outline_region)
    if show_silhouette:
        plotlist += [get_silhouette_cns(region=outline_region)]

    # `color` (an explicit neuron color) takes precedence over `palette`. The CNS
    # shell/outline/silhouette are navis.Volumes and keep their own `.color`.
    kwargs.update({'color': color} if color is not None else {'palette': palette})

    fig = navis.plot3d(
        plotlist
      , scatter_kws=scatter_kws
      , inline=inline
      , **kwargs)

    up_x, up_y, up_z = [-0.05, -1 ,0] / np.linalg.norm([-0.05, -1 ,0])       # camera up
    eye_x, eye_y, eye_z = [0, 0, -1]    # camera eye

    fig.update_traces(
        lighting={'ambient':1, 'diffuse':0}
      , selector={'type': 'mesh3d'}
    )

    # add annotation with celltype and bodyid
    if annotate:
        if celltype is not None and len(celltype) > 1:
            anno = [f"{i}:{j}" for i, j in zip(list(celltype), [str(b) for b in bodyid])]
            annotext = '<br>'.join(anno)
        elif celltype is not None:
            annotext = f"{celltype[0]}:{bodyid[0]}"
        else:
            annotext = f"{bodyid[0]}"
        fig.add_annotation({
            'font':{ 'color':'black', 'size': 18}
          , 'x': 1, 'y': 1
          , 'showarrow': False
          , 'text': annotext
          , 'textangle': 0
          , 'xanchor': 'right'
          , 'xref': "paper"
          , 'yref': "paper"
        })

    fig.update_layout(
        margin={'l':0, 'r':0, 'b':0, 't':0}
      , showlegend=False
      , scene = {
            "xaxis" : {
                "showgrid": False
              , "gridcolor": 'rgba(0,0,0,0)'
              , "showbackground": False
              , "visible": False
              , "autorange": False
              , "range": range_x # These are the boundaries of cns
            }
          , "yaxis" : {
                "showgrid": False
              , "gridcolor": 'rgba(0,0,0,0)'
              , "showbackground": False
              , "visible": False
              , "autorange": False
              , "range": range_y
            }
          , "zaxis" : {
                "showgrid": False
              , "gridcolor": 'rgba(0,0,0,0)'
              , "showbackground":False
              , "visible": False
              , "autorange": False
              , "range": range_z
            }
          , "camera":{
                "up": {"x":up_x, "y": up_y, "z": up_z} # canvas/page orientation
              , "center": {"x":0, "y": 0, "z": 0} # translation
              , "eye": {"x":eye_x, "y": eye_y, "z": eye_z} # view direction
              , "projection": {"type": "orthographic"}
            }
          , 'aspectmode':'manual'
          , 'aspectratio': {"x": range_ratio[0], "y": range_ratio[1], "z": range_ratio[2]}
        }

      , paper_bgcolor='#fff'
      , plot_bgcolor='#fff'
    )
    return fig


def plot_2d_cns(
    bodyid:int|list[int]
    , celltype:str|list[str]|None=None
    , show_skeletons:bool=True
    , show_meshes:bool=False
    , show_outline:bool=False
    , outline_region:str=_OUTLINE_REGION
    , outline_fill:bool=False
    , view:tuple=('x', '-y')
    , zoom:float=1.0
    , palette:str='viridis'
    , color:str|tuple[float, ...]|None=None
    , linewidth:float=0.75
    , mesh_lod:int=2
    , rasterize:bool=False
    , annotate:bool=False
    , figsize:tuple=(15.23, 8.5)
    , ax:plt.Axes|None=None
    , **kwargs:Any
) -> tuple[MplFigure, plt.Axes]:
    """
    Plot neurons over a CNS outline as true vector graphics, in the same anterior view
    as `plot_3d_cns`.

    This is the matplotlib counterpart to `plot_3d_cns`. Use it when the output has to be
    real vector graphics: plotly renders 3-D traces through WebGL, so its `.pdf`/`.svg`
    exports embed the whole scene as a bitmap, whereas `navis.plot2d(method='2d')` emits
    matplotlib line collections that stay editable in Illustrator/Inkscape.

    The trade-off is meshes. A single neuron mesh becomes hundreds of thousands of
    individually stroked polygons, which bloats the file and can misorder overlapping
    surfaces (matplotlib sorts by painter's algorithm). Prefer `show_skeletons=True`
    here, and reach for `plot_3d_cns` when you actually need mesh surfaces. If you do
    plot meshes, `rasterize=True` keeps the neurons as a bitmap while leaving text and
    the outline vector.

    Parameters
    ----------
    bodyid : int|list[int]
        body ID(s) to plot. A single int is accepted and wrapped into a list.
    celltype : str|list[str], default=None
        cell type(s), used only for the `annotate` label
    show_skeletons : bool, default=True
        plot neuron skeletons (the vector-friendly option)
    show_meshes : bool, default=False
        plot neuron meshes — see the caveat above
    show_outline : bool, default=False
        draw the CNS boundary as a vector path, read from the pre-built rings in
        `params/rois/roi_outlines` (see `plotting.roi_assets`). Milliseconds, and the
        esophageal foramen comes along as its own ring.

        Only the three stored projections — `xy` (anterior), `xz` (dorsal) and `zy`
        (lateral) — have rings, and the axis order has to match (`('x','-y')` yes,
        the transposed `('y','-x')` no). Any other `view` warns and falls back to
        `navis.plot2d(volume_outlines=True)` over the decimated shell mesh (320k
        faces), measured at ~55 s against the ~10.5 min the full 3.06M-face shell
        used to take.
    outline_region : str, default='brain'
        which backdrop to draw: `'brain'` (central brain + both optic lobes) or
        `'cb'` (central brain only, upstream visualpathways' framing).
    outline_fill : bool, default=False
        fill the outline as a flat gray backdrop — the vector counterpart of
        `get_silhouette_cns()` — instead of stroking the rings. Holes stay holes
        (the rings become one compound `matplotlib.path.Path`). Ignored on the
        fallback path for an unstored view.
    view : tuple, default=('x', '-y')
        projection plane, as `navis.plot2d`'s `view`. The default matches
        `plot_3d_cns`'s anterior camera (x to the right, -y up).
    zoom : float, default=1.0
        `1.0` frames the whole CNS bounding box; larger values crop in around its
        center by that factor.
    palette : str, default='viridis'
        color palette for the neurons (ignored when `color` is given)
    color : color-like, default=None
        a single explicit neuron color, e.g. `'green'` or `(0,0,0,1)`. Takes
        precedence over `palette`.
    linewidth : float, default=0.75
        skeleton stroke width in points
    mesh_lod : int, default=2
        level of detail for neuron meshes when `show_meshes=True`
    rasterize : bool, default=False
        rasterize neurons and meshes while keeping axes and text vector — a middle
        ground for mesh-heavy figures
    annotate : bool, default=False
        draw a `celltype:bodyid` label in the top-right corner
    figsize : tuple, default=(15.23, 8.5)
        matplotlib figure size in inches. The default matches the CNS frontal aspect
        ratio, as `save_figure_anterior`'s pixel defaults do.
    ax : plt.Axes, default=None
        plot into an existing axis instead of creating a figure
    **kwargs :
        additional keyword arguments passed to `navis.plot2d`

    Returns
    -------
    fig : MplFigure
        the matplotlib figure
    ax : plt.Axes
        the axis the neurons were drawn on

    """

    if isinstance(bodyid, (int, np.integer)):
        bodyid = [int(bodyid)]
    if isinstance(celltype, str):
        celltype = [celltype]

    # `get_skeletons`/`get_meshes` return a *list* of NeuronLists, with `None` entries
    # for body IDs that have no skeleton; unwrap to individual neurons and drop those.
    plotlist = []
    if show_skeletons:
        for skel in get_skeletons(bodyid):
            if skel is not None:
                plotlist += list(skel)
    if show_meshes:
        for mesh in get_meshes(bodyid, lod=mesh_lod, save_cache=False):
            if mesh is not None:
                plotlist += list(mesh)
    # Stored rings for this projection, or None for a transposed/oblique view we have
    # no asset for — then the decimated shell goes through `volume_outlines` instead.
    outline_view = roi_assets.view_key(view) if show_outline else None
    if show_outline and outline_view is None:
        warnings.warn(
            f"No pre-built outline for view={view!r}; falling back to the decimated"
            " shell mesh via `volume_outlines`, which takes about a minute."
          , stacklevel=2)
        plotlist += [roi_assets.get_volume(outline_region, color=_OUTLINE_COLOR)]

    kwargs.update({'color': color} if color is not None else {'palette': palette})

    if plotlist:
        fig, ax = navis.plot2d(
            plotlist
          , method='2d'
          , view=view
          , linewidth=linewidth
          , volume_outlines=True
          , rasterize=rasterize
          , figsize=figsize
          , ax=ax
          , **kwargs)
    else:
        # nothing for navis to draw (outline-only figure) — make the axis ourselves
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        else:
            fig = ax.get_figure()

    # The rings are drawn here rather than handed to navis so nothing goes through
    # shapely. Signs need no handling: `navis.plot2d` keeps data positive and inverts
    # the *axis* for a negated view, which the `set_*lim` block below preserves.
    if outline_view is not None:
        rings = roi_assets.get_outline_rings(outline_region, outline_view)
        if outline_fill:
            ax.add_patch(mpl_patches.PathPatch(
                _rings_to_path(rings)
              , facecolor=_OUTLINE_FILL_COLOR
              , edgecolor='none'
              , zorder=-1))
        else:
            for ring in rings:
                ax.plot(
                    ring[:, 0], ring[:, 1]
                  , color=_OUTLINE_COLOR
                  , linewidth=_OUTLINE_LINEWIDTH
                  , zorder=-1)

    # Frame the same box as `plot_3d_cns`. `navis.plot2d` keeps the data in positive
    # coordinates and inverts the matplotlib axis for a negated view (the default
    # '-y'), so limits stay positive and are ordered descending to keep that inversion.
    lims = {'x': CNS_RANGE_X, 'y': CNS_RANGE_Y, 'z': CNS_RANGE_Z}
    for axis_name, spec in zip(('x', 'y'), view[:2]):
        lo, hi = lims[spec.lstrip('-')]
        mid, half = (lo + hi) / 2, (hi - lo) / 2 / zoom
        if spec.startswith('-'):
            getattr(ax, f'set_{axis_name}lim')(mid + half, mid - half)
        else:
            getattr(ax, f'set_{axis_name}lim')(mid - half, mid + half)

    ax.set_aspect('equal')
    ax.set_axis_off()

    if annotate:
        if celltype is not None and len(celltype) > 1:
            annotext = '\n'.join(
                f"{i}:{j}" for i, j in zip(list(celltype), [str(b) for b in bodyid]))
        elif celltype is not None:
            annotext = f"{celltype[0]}:{bodyid[0]}"
        else:
            annotext = f"{bodyid[0]}"
        ax.text(
            0.99, 0.99, annotext
          , transform=ax.transAxes
          , ha='right', va='top'
          , color='black', fontsize=18)

    return fig, ax


def get_shell_cns(ignore_cache:bool=False) -> cv.mesh.Mesh:
    """
    Retrieve shell of CNS using cloudvolume.

    Parameters:
    ----------
    ignore_cache : bool, default=False
        if true, download the meshes from the original data source each time. Otherwise
        use a filesystem cache.

    Returns:
    -------
    roi : cv.mesh.Mesh
        shell of CNS
    """

    cachedir = config.CACHE_DIR / "cns_shell_cv"
    cachedir.mkdir(parents=True, exist_ok=True)
    roi_fn = cachedir / "cns_shell.pickle"
    if not ignore_cache and roi_fn.is_file():
        with roi_fn.open('rb') as roi_fh:
            roi = pickle.load(roi_fh)
    else:
        vol = cv.CloudVolume(
            f"precomputed://{config.SHELL_SOURCE}"
          , use_https=True
          , progress=False
        )
        roi = vol.mesh.get([1,2,3])
        roi.vertices = roi.vertices / 8 # from nm to voxels
        with roi_fn.open('wb') as roi_fh:
            pickle.dump(roi, roi_fh)
    roi.color = (1,1,1, 0.2)
    return roi


# z-plane the CNS shell is flattened onto for the silhouette (behind the neurons,
# in the 8 nm-voxel frame), and the default flat gray fill color.
_SILHOUETTE_Z = 42500
_SILHOUETTE_COLOR = (0.82, 0.82, 0.82, 1.0)
_silhouette_cns = {}


def get_silhouette_cns(
    z_plane:float=_SILHOUETTE_Z
  , color:tuple=_SILHOUETTE_COLOR
  , region:str=_OUTLINE_REGION
) -> navis.Volume:
    """
    CNS shell flattened to a single plane: a uniform, opaque gray silhouette that
    still keeps the esophageal foramen as a real hole (background shows through).

    This is the "filled gray brain" backdrop for anterior-view neuron plots — an
    alternative to `roi_assets.get_volume()` (a near-invisible translucent 3-D mesh)
    and `get_outline_rings_cns()` (just the boundary contour). Plot it with flat shading
    (`plot_3d_cns` already sets `lighting={'ambient':1,'diffuse':0}` on mesh3d traces)
    so it renders as a flat fill rather than a shaded surface. Cached for the session.

    Built from the decimated mesh in `params/rois/roi_meshes` rather than the 3.06M-face
    shell: no download, no per-session flattening of 1.53M vertices, and the foramen
    survives decimation.

    Parameters
    ----------
    z_plane : float, default=42500
        plane (8 nm-voxel frame) the shell vertices are collapsed onto; sits behind
        the neurons for the frontal/anterior camera.
    color : tuple, default=(0.82, 0.82, 0.82, 1.0)
        RGBA fill color of the silhouette.
    region : str, default='brain'
        which ROI mesh to flatten: `'brain'` or `'cb'`.

    Returns
    -------
    sil : navis.Volume
        the flattened CNS shell, colored `color`
    """
    key = (region, z_plane)
    if key not in _silhouette_cns:
        verts, faces = roi_assets.get_mesh(region)
        verts = verts.copy()
        verts[:, 2] = z_plane
        _silhouette_cns[key] = navis.Volume(vertices=verts, faces=faces)
    sil = _silhouette_cns[key]
    sil.color = color
    return sil


def get_outline_rings_cns(
    region:str=_OUTLINE_REGION
  , view:str='xy'
  , z_plane:float=_OUTLINE_Z
) -> list[np.ndarray]:
    """
    Pre-built CNS outline rings, lifted onto one plane in 3-D for `navis.plot3d`.

    Each ring is returned separately so that plotting them as lines does not join
    the esophageal foramen to the exterior with a stray segment.

    Parameters
    ----------
    region : str, default='brain'
        `'brain'` (central brain + optic lobes) or `'cb'` (central brain only)
    view : str, default='xy'
        stored projection; only `'xy'` (anterior) makes sense as a 3-D backdrop for
        `plot_3d_cns`'s camera.
    z_plane : float, default=30000
        plane the rings are placed on, in the 8 nm-voxel frame

    Returns
    -------
    rings : list[np.ndarray]
        `(n, 3)` arrays, exterior first
    """

    rings = []
    for ring in roi_assets.get_outline_rings(region, view):
        pts = np.full((ring.shape[0], 3), float(z_plane))
        # the stored rings are in the two axes of `view`, in that order
        pts[:, 'xyz'.index(view[0])] = ring[:, 0]
        pts[:, 'xyz'.index(view[1])] = ring[:, 1]
        rings.append(pts)
    return rings


def get_outline_cns(
    ignore_cache:bool=False
  , region:str=_OUTLINE_REGION
  , z_plane:float=_OUTLINE_Z
) -> np.ndarray:
    """
    Exterior boundary of the CNS as a planar ring of points (deprecated).

    Kept as a thin wrapper over `get_outline_rings_cns()` for the callers that expect
    a single `(n, 3)` array at `z_plane`. The alphashape route this used to run —
    ~80 min over the 1.53M shell vertices, cached in `cache/cns_outline_cv` — is gone;
    the ring now comes from `params/rois/roi_outlines` in milliseconds.

    Prefer `get_outline_rings_cns()`, which also returns the esophageal foramen, or
    `roi_assets.get_outline_rings()` for the flat 2-D rings.

    Parameters
    ----------
    ignore_cache : bool, default=False
        accepted for backwards compatibility and ignored — there is nothing left to
        recompute. Regenerate the assets with
        `python -m flyem_analysis_starter.plotting.make_roi_assets`.
    region : str, default='brain'
        `'brain'` (central brain + optic lobes) or `'cb'` (central brain only)
    z_plane : float, default=30000
        plane the ring is placed on, in the 8 nm-voxel frame

    Returns
    -------
    bd : np.ndarray
        `(n, 3)` points along the exterior boundary
    """

    if ignore_cache:
        warnings.warn(
            "`ignore_cache` no longer does anything: `get_outline_cns` reads the"
            " pre-built rings. Rebuild them with"
            " `python -m flyem_analysis_starter.plotting.make_roi_assets`."
          , DeprecationWarning, stacklevel=2)
    return get_outline_rings_cns(region=region, view='xy', z_plane=z_plane)[0]
