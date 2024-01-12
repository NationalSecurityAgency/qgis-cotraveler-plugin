"""
Simple visualization tools for simple example notebook
"""

from typing import Any, Dict, Hashable, Iterable, List, Optional, Tuple, Union

import numpy as np
from matplotlib import pyplot as plt

from ._types import Columns, CPing, Ping, PingList, QTrack, Track
from .config import IMPORT_SUCCESS_logzero

if IMPORT_SUCCESS_logzero:
    import logzero
    from logzero import logger
else:
    import logging as logger




def simple_plot_tracks(
    track_list: List[Union[Track, QTrack, List[List[float]]]],
    background_image: Optional[str] = None,
    background_rectangle: Optional[
        Tuple[Tuple[float, float], Tuple[float, float]]
    ] = None,
    display_rectangle: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None,
    track_colors: List[str] = ["cyan", "purple", "pink", "orange", "yellow", "gray",],
    polygon_list: Optional[List[List[Tuple[float, float]]]] = None,
    polygon_colors: List[str] = ["lightgreen", "red"],
    ping_size: Optional[int] = None,
    track_width: Optional[int] = None,
    track_alpha: Optional[float] = None,
    aspect_ratio: Optional[float] = None,
):
    """
    Makes a plot of tracks (can be Track, QTrack, or list of tuples).
    :param track_list: Input list of Track, QTrack, or list of tuples of floats.
    :param background_image: optional image
    :param background_rectangle: required if image is given, in the form [[x1, y1], [x2, y2]]
    :param track_colors: can override default color settings
    :param polygon_list: optional list of list of tuples
    :param polygon_colors: can override default setting which is green for the first polygon and red for the rest.
    :param ping_size: can be used to override default setting of size of dots in plot
    :param track_width: can be used to override default setting of thickness of lines for tracks
    :param track_alpha: can set translucence of tracks
    :param aspect_ratio: can override default
    """
    fig, ax = plt.subplots()
    if background_image:
        image = plt.imread(background_image)
        ax.imshow(
            image,
            extent=[
                background_rectangle[0][0],
                background_rectangle[1][0],
                background_rectangle[0][1],
                background_rectangle[1][1],
            ],
        )
    if polygon_list:
        for i, poly in enumerate(polygon_list):
            this_color = polygon_colors[min(i, len(polygon_colors) - 1)]
            xs = [p[0] for p in poly] + [poly[0][0]]
            ys = [p[1] for p in poly] + [poly[0][1]]
            ax.plot(xs, ys, color=this_color)
    for i, tr in enumerate(track_list):
        this_color = track_colors[min(i, len(track_colors) - 1)]
        if isinstance(tr, Track):
            point_list = tr.track
            print(f"{this_color}: {tr.ID}")
            xs = [p[1] for p in point_list]
            ys = [p[2] for p in point_list]
        elif isinstance(tr, QTrack):
            point_list = tr.qtrack
            print(f"{this_color}: {tr.ID}")
            xs = [p[0] for p in point_list]
            ys = [p[1] for p in point_list]
        else:
            point_list = tr
            print(f"{this_color}: no ID")
            xs = [p[0] for p in point_list]
            ys = [p[1] for p in point_list]
        ax.plot(
            xs,
            ys,
            marker="o",
            markersize=ping_size,
            linewidth=track_width,
            alpha=track_alpha,
            color=this_color,
        )
    if display_rectangle:
        plt.xlim(display_rectangle[0][0], display_rectangle[1][0])
        plt.ylim(display_rectangle[0][1], display_rectangle[1][1])
    if aspect_ratio:
        ax.set_aspect(aspect_ratio)
    plt.show()
