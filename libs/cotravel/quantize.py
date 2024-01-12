#!/usr/bin/env python3

"""
TODO module doc
"""

import datetime
from functools import partial
from math import floor
from typing import Iterable, List, Optional

import numpy as np

from cotravel._types import QTrack, Track
from cotravel.config import (
    ADD_EXTRAPOLATED_PINGS,
    DELTA_T,
    MIN_DIAMETER,
    MIN_PINGS_PER_TIMEBIN,
    MIN_QPINGS,
    MIN_TIMEBIN_FRACTION,
    IMPORT_SUCCESS_logzero,
)
from cotravel.pmap import filtermap
from cotravel.utils import (
    getCentroidWithMask_numpy,
    getDistanceWithMask_numpy,
    interpolate,
    to_timestamp,
)

if IMPORT_SUCCESS_logzero:
    from logzero import logger
else:
    import logging as logger


# TODO making Tracks from lots of csv files crashes sometimes


def filter_qtracks(
    qtracks: Iterable[QTrack],
    min_qpings: float = MIN_QPINGS,
    min_diameter: float = MIN_DIAMETER,
) -> Iterable[QTrack]:
    """
    Yield `QTrack`s from qtracks that satisfy the criteria

    :param qtracks: iterable of `QTrack`s
    :param min_qpings: ignore `QTrack`s with < this many qpings
    :param min_diameter: ignore `QTrack`s with < this diameter
    """
    # qtracks = list(qtracks)
    for q in qtracks:
        if min_qpings and q.num_qpings < min_qpings:
            continue
        if min_diameter and q.diameter < min_diameter:
            continue
        yield q


def quantize_tracks(
    tracks: Iterable[Track],
    qstart_time: Optional[float] = None,
    qend_time: Optional[float] = None,
    delta_t: float = DELTA_T,
    min_timebin_fraction: float = MIN_TIMEBIN_FRACTION,
    min_qpings: int = MIN_QPINGS,
    min_diameter: float = MIN_DIAMETER,
    add_extrapolated_pings: bool = ADD_EXTRAPOLATED_PINGS,
    min_pings_per_timebin: int = MIN_PINGS_PER_TIMEBIN,
    chunksize: int = 10000,
    jobs: int = 4,
    # qgis_obj: Optional[QgsProcessingFeedBack] = None,
    qgis_obj: Optional[object] = None,
) -> List[QTrack]:
    """
    Return a list of `QTracks` from an iterable of `Tracks`

    Optionally, filter out qtracks according to the parameters
    min_qpings and min_diameter

    :param tracks: Iterable of `Track`s
    :param qstart_time: Quantization start (unix time). If omitted, will be set to earliest timestamp in tracks.
    :param qend_time: Quantization end (unix time). If omitted, will be set to latest timestamp in tracks.
    :param delta_t: Quantization window size (seconds)
    :min_timebin_fraction: For the first and last qping, this is the required fraction of the time occupied by input Track to have a nonmasked qping.
    :param min_qpings: Skip QTracks with fewer than this many quantized pings
    :param min_diameter: Skip QTracks with diameter smaller than this (in meters)
    :add_extrapolated_pings: For the first and last qping, whether or not to extrapolate track to the edges of the time bin in the event the input Track doesn't fill up time bin. Default is False.
    :min_pings_per_timebin: minimum number of original pings in timebin for qping to be unmasked. The code simply remasks at this number.
    :param jobs: Number of cpus to use
    :qgis_ojb: An optional QgsProcessingFeedback object that can send back feedback information as well as send forth a cancellation request.
    """
    tracks = list(tracks)
    n_tracks = len(tracks)

    qstart_time = (
        to_timestamp(qstart_time) if qstart_time else min(t.start_time for t in tracks)
    )
    qend_time = (
        to_timestamp(qend_time) if qend_time else max(t.end_time for t in tracks)
    )
    num_qpings = round((float(qend_time) - float(qstart_time)) / float(delta_t))
    _qstart = datetime.datetime.fromtimestamp(qstart_time).isoformat()
    _qend = datetime.datetime.fromtimestamp(qend_time).isoformat()
    logger.debug(f"Quantized track start: {_qstart}")
    logger.debug(f"Quantized track end  : {_qend}")
    logger.debug(f"Quantized bin duration : {delta_t}")
    logger.debug(f"Quantized track length: {num_qpings}")

    quantizer = partial(
        quantize_track,
        qstart_time=qstart_time,
        qend_time=qend_time,
        delta_t=delta_t,
        min_timebin_fraction=min_timebin_fraction,
        add_extrapolated_pings=add_extrapolated_pings,
        min_pings_per_timebin=min_pings_per_timebin,
    )

    logger.info(f"Quantizing {n_tracks} Tracks")
    # qtracks = (quantizer(t) for t in tracks)
    qtracks = filtermap(
        quantizer,
        tracks,
        total=n_tracks,
        chunksize=chunksize,
        jobs=jobs,
        star=False,
        pairs=False,
        qgis_obj=qgis_obj,
    )
    # ignore QTracks with few qpings or small diameter
    return list(
        filter_qtracks(qtracks, min_qpings=min_qpings, min_diameter=min_diameter)
    )


def quantize_track(
    track: Track,
    qstart_time: Optional[float] = None,
    qend_time: Optional[float] = None,
    delta_t: float = DELTA_T,
    min_timebin_fraction: float = MIN_TIMEBIN_FRACTION,
    add_extrapolated_pings: bool = ADD_EXTRAPOLATED_PINGS,
    min_pings_per_timebin: int = MIN_PINGS_PER_TIMEBIN,
    calculate_bin_distances: bool = True,
) -> QTrack:
    """
    Return a `QTrack`, a quantized version of track

    NOTE We assume track.pings is already sorted by time.

    :param track: a `Track` instance
    :param qstart_time: quantization start_time (unix timestamp)
    :param qend_time: quantization end_time (unix timestamp)
    :param delta_t: quantization window size (seconds)
    :param min_timebin_fraction: For the first and last qping, this is the required fraction of the time occupied by input Track to have a nonmasked qping.
    :param add_extrapolated_pings: For the first and last qping, whether or not to extrapolate track to the edges of the time bin in the event the input Track doesn't fill up time bin. Default is False.
    :param min_pings_per_timebin: minimum number of original pings in timebin for qping to be unmasked. The code simply remasks at this number.
    :param calculate_bin_distances: Whether or not to calculate the distance travelled within each time bin.
    """
    if qstart_time is None:
        qstart_time = track.start_time
    if qend_time is None:
        qend_time = track.end_time

    num_qpings = round((qend_time - qstart_time) / delta_t)
    # ans is a list of list of pings [x,y,t]
    ans = [[] for i in range(num_qpings)]
    orig_pings = np.array([0 for i in range(num_qpings)])
    # prevn is the value of n (which time bin) for the previous ping that
    #       lies in the time window [qstart_time, qstart_time + num_qpings*delta_t],
    #       except we artificially start prevn = -1 at the beginning.
    # Note prevn < 0 if there has not yet been a ping with time after qstart_time;
    #       this includes the case where we are at the first ping.
    prevn = -1
    num_track_pings = len(track.pings)
    for i, r in enumerate(track.pings):
        x = [r.x, r.y, r.t]
        # Compute the time bin index n for this x
        nfloat = (x[2] - qstart_time) / delta_t
        n = floor(nfloat)
        # Only do something if n>=0. (we always remember the previous x by prevx in any case)
        # Note we still do something even if n>=num_qpings.
        if n >= 0:
            # If prevn!=n, then we have at least one complete time bin, unless this is the first ping (i==0).
            # So find all such time bins, and add 'edge pings' as appropriate
            if (prevn != n) and (i != 0):
                for k in range(prevn + 1, n + 1):
                    # These are the time bins (k) that get new edge pings
                    # The following y is an edge ping in the sense it is
                    # interpolated at the time boundary between
                    # bin k and bin k+1
                    y = interpolate(prevx, x, k * delta_t + qstart_time)
                    j = k - 1
                    # Put y in end of time bin k-1?
                    if (j >= 0) and (j < num_qpings):
                        ans[j].append(y)
                    j = k
                    # Put y in start of time bin k?
                    if (j >= 0) and (j < num_qpings):
                        ans[j].append(y)
            if n < num_qpings:
                orig_pings[n] += 1
                # x goes in the interior of time bin n as long as
                # it is in the time window (check if n is from 1 through num_qpings-1)
                # and time bin n already has a start edge ping;
                # the only issue arises for the first ping (when i==0)
                # and the last ping (when i==num_qpings-1).
                # If there is already a ping in the bin, then it must include at least
                # the left edge and so it is safe to add ping.
                if len(ans[n]) > 0:
                    ans[n].append(x)
                elif i == 0:  # Test if time is close enough to beginning to keep
                    if (nfloat - n) <= 1 - min_timebin_fraction:
                        ans[n].append(x)
                        if add_extrapolated_pings and (num_track_pings > 1):
                            # extrapolate ping at start of time bin
                            nextr = track.pings[1]
                            nextx = [nextr.x, nextr.y, nextr.t]
                            ans[n] = [
                                interpolate(x, nextx, qstart_time + n * delta_t)
                            ] + ans[n]
                            # ans[n] = [interpolate(x, x,  qstart_time+n*delta_t)]+ans[n]
                # Check if this is the last ping, and if yes,
                # then see if this time bin is worth keeping.
                # Clear the bin if the filled time is less than min_timebin_fraction of bin size
                if i == num_track_pings - 1:
                    if (nfloat - n) < min_timebin_fraction:  # fixed 20200824
                        ans[n] = []
                    else:
                        if add_extrapolated_pings and (num_track_pings > 1):
                            # extrapolate ping at end of time bin
                            ans[n].append(
                                interpolate(prevx, x, qstart_time + (n + 1) * delta_t)
                            )
        # And if n is >= num_qpings, then break (no need to look at any more pings)
        if n >= num_qpings:
            break
        prevn = n
        prevx = x
    # c = np.array([getCentroidWithMask(a) for a in ans])
    c = np.array([getCentroidWithMask_numpy(a) for a in ans])
    orig_bin_distances = None
    if calculate_bin_distances:
        b = np.array([getDistanceWithMask_numpy(a) for a in ans])
        orig_bin_distances = track.rescale * np.ma.array(b[:, 0], mask=b[:, 1])
    # the mask needs to have shape (n,2), but c[:, 2] has shape (n,)
    qpings_may_exist = np.logical_not(np.array(c[:, 2]))
    qtrack = np.ma.array(c[:, 0:2], mask=np.transpose(np.stack([c[:, 2]] * 2)))

    qtrack_object = QTrack(
        ID=track.ID,
        qtrack=qtrack,
        qstart_time=qstart_time,
        qend_time=qend_time,
        delta_t=delta_t,
        orig_pings=orig_pings,
        qpings_may_exist=qpings_may_exist,
        rescale=track.rescale,
        cep_rescale=track.cep_rescale,
        masked_at=0,
        orig_bin_distances=orig_bin_distances,
    )
    if min_pings_per_timebin > 0:
        qtrack_object.remask(min_pings_per_timebin)
    return qtrack_object
