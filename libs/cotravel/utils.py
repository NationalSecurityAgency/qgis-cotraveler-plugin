"""
TODO module documentation
"""

import datetime
import logging
import os
from itertools import tee
from typing import Iterable, List, Optional, Tuple, TypeVar, Union

import numpy as np
import pytz

from cotravel._types import QTrack, TimestampLike, _diameter

from .config import IMPORT_SUCCESS_logzero, IMPORT_SUCCESS_maya

if IMPORT_SUCCESS_logzero:
    import logzero
    from logzero import logger
else:
    import logging as logger
if IMPORT_SUCCESS_maya:
    import maya
else:
    import dateutil


# TODO should guess_rescale_factor return a function instead of a scalar?
# TODO compute distances using Haversine or other function as apropriate
#      depending on units, instead of pretending that decimal degrees are
#      Cartesian coordinates
# TODO rename delta_t to bin_duration/bin_size/something else?
# TODO rethink use of filter_qtracks wherever it's called. eg maybe don't
#      call it in quantize_tracks
# TODO have most things that return lists of Tracks/QTracks yield instead
# TODO unify filtermap and filtermap_pairs
# TODO faster way to make sparse QTracks from lots of files?
# TODO rename score_* functions


def configure_logging(
    loglevel: int = 20,
    logfile: Optional[str] = None,
    mode: str = "a",
    quiet: bool = False,
    outdir: Optional[str] = None,
) -> None:
    """
    Configure logging
    """
    if IMPORT_SUCCESS_logzero:
        logzero.logger.handlers[0].level = loglevel
        # logzero.loglevel(loglevel)
    else:
        logging.basicConfig(level = logLevel)
    if quiet:
        if IMPORT_SUCCESS_logzero:
            logzero.logger.handlers[0].level = 100
            # logzero.loglevel(100)
        else:
            logging.basicConfig(level = 100)
    if logfile:
        if outdir:
            if not os.path.isdir(outdir):
                logger.info(f"Creating directory {outdir}")
                os.makedirs(outdir)
            logfile = os.path.join(outdir, logfile)

        # log all debug messages to file
        if mode == "a":
            logger.info(f"Appending logs to {logfile}")
        else:
            logger.info(f"Writing logs to {logfile}")

        if IMPORT_SUCCESS_logzero:
            logzero.logfile(
                logfile, formatter=None, mode=mode, maxBytes=0, loglevel=logging.DEBUG,
            )
        else:
            logging.basicConfig(filename=logfile)
            # Is this correct way? basicConfig also called above.


def to_timestamp(t: TimestampLike) -> float:
    """
    Return unix timestamp from str, datetime.datetime, datetime.date, or number
    """
    if isinstance(t, str):
        #return maya.parse(t).datetime().timestamp()
        return my_parse_to_datetime(t).timestamp()
    elif isinstance(t, datetime.datetime):
        return t.timestamp()
    elif isinstance(t, datetime.date):
        return datetime.datetime(t.year, t.month, t.day, tzinfo=pytz.utc).timestamp()
    else:
        return float(t)


def to_datetime(t: TimestampLike) -> datetime.datetime:
    """
    Return UTC datetime from str, datetime.date, or number
    """
    if isinstance(t, datetime.datetime):
        return t
    elif isinstance(t, str):
        try:
            return my_parse_to_datetime(t)
        except ValueError:
            # raise ValueError(f"{t} cannot be converted to datetime")
            # t is a string rep of a unix timestamp?
            return datetime.datetime.fromtimestamp(float(t), tz=pytz.utc)
    elif isinstance(t, (int, float)):
        return datetime.datetime.fromtimestamp(t, tz=pytz.utc)
    elif isinstance(t, datetime.date):
        return datetime.datetime(t.year, t.month, t.day, tzinfo=pytz.utc)
    else:
        raise ValueError(f"{t} cannot be converted to datetime")


def daterange(start_date: str, end_date: Optional[str] = None) -> List[datetime.date]:
    """
    Return a list of datetime.date objects in the half-open interval
    [start_date, end_date), or a list of length 1 if end_date is omitted.
    """
    _start = my_parse_to_datetime(start_date).date()
    if not end_date:
        _end = _start + datetime.timedelta(days=1)
    else:
        _end = my_parse_to_datetime(end_date).date()
    num_days = (_end - _start).days
    return [_start + datetime.timedelta(days=i) for i in range(num_days)]


def daterange_str(
    start_date: str, end_date: Optional[str] = None, date_fmt="%Y-%m-%d"
) -> List[str]:
    """
    Return a list of string of dates in the half-open interval
    [start_date, end_date), or a list of length 1 if end_date is omitted.
    """
    dates = daterange(start_date, end_date)
    return [datetime.datetime.strftime(d, date_fmt) for d in dates]


def num_common_qpings(qtrack1: QTrack, qtrack2: QTrack) -> int:
    """
    Return the number of qpings in the temporal overlap of qtrack1 and qtrack2
    """
    z = qtrack1.qtrack - qtrack2.qtrack
    return len(z) - np.count_nonzero(z.mask[:, 0])


def average_distance(qtrack1: QTrack, qtrack2: QTrack) -> float:
    """
    Return the average distance (in meters) between the `QTracks`
    """
    z = qtrack1.qtrack - qtrack2.qtrack
    return qtrack1.rescale * np.ma.mean(
        np.ma.array(np.linalg.norm(z, axis=1), mask=z.mask[:, 0]).compressed()
    )


def vector_of_distances(qtrack1: QTrack, qtrack2: QTrack) -> np.ma.masked_array:
    """
    Return the vector of distances (in meters) between the `QTracks`
    """
    z = qtrack1.qtrack - qtrack2.qtrack
    return qtrack1.rescale * np.ma.array(np.linalg.norm(z, axis=1), mask=z.mask[:, 0])


def diameters(qtrack1: QTrack, qtrack2: QTrack) -> Tuple[float, float, float]:
    """
    Return a triple of: the diameter (in meters) of the temporal overlap of the
    `QTrack`s, as well as the diameter of each `QTrack` restricted to this temporal overlap.

    Projects onto the x and y axes, as well as the lines x=y and x=-y

    NOTE assumes QTracks have been remasked
    """
    a1 = np.ma.copy(qtrack1.qtrack)
    a2 = np.ma.copy(qtrack2.qtrack)
    rescale = qtrack1.rescale
    a1.mask = np.logical_or(a1.mask, a2.mask)
    a2.mask = a1.mask

    # TODO without this everything breaks for some reason
    a1 = a1.compressed()
    a2 = a2.compressed()
    n = len(a1) // 2
    a1 = a1.reshape(n, 2)
    a2 = a2.reshape(n, 2)

    c = np.concatenate((a1, a2))
    return (
        _diameter(c, rescale),
        _diameter(a1, rescale),
        _diameter(a2, rescale),
    )


def interpolate(p: List[float], q: List[float], t: float) -> Tuple[float, float]:
    """
    Return point n R^2 (tuple) at time t by linearly interpolating from p to q
    """
    L = (t - p[2]) / (q[2] - p[2])
    return ((1 - L) * p[0] + L * q[0], (1 - L) * p[1] + L * q[1], t)


def getCentroidWithMask_numpy(a: List[List[float]],) -> Tuple[float, float, bool]:
    """
    Return the centriod of a list of [x,y,t] triples
    Requires at least two pings, else [nan, nan, True] is returned; note it is necessary
    to do this if there is only one ping.  The quantize.py code expects this behavior.

    Given the vertices (pings) of a piecewise linear path,
    assuming constant speed between vertices,
    compute its centroid weighted by time, and a bool denoting whether it should be masked
    That is, the time-weighted average of the midpoints of the segments.

    :param a: [ [x,y,t],... ]
    :returns: [x,y, bool] first and second entries form the centroid
    """
    # assumes a is already in order.
    if len(a) < 2:
        return (np.nan, np.nan, True)
    a = np.array(a)
    tt = a[-1, 2] - a[0, 2]
    if tt == 0:
        return (a[0][0], a[0][1], False)
    dt = a[1:, 2] - a[:-1, 2]
    ax = a[1:, 0] + a[:-1, 0]
    ay = a[1:, 1] + a[:-1, 1]
    return (np.dot(dt, ax) / (2 * tt), np.dot(dt, ay) / (2 * tt), False)


def getDistanceWithMask_numpy(a: List[List[float]],) -> Tuple[float, bool]:
    """
    Return the distance travelled by of a list of [x,y,t] triples
    Requires at least two pings, else [0, True] is returned
    Given the vertices (pings) of a piecewise linear path, returns distance travelled followed by a False.
    :param a: [ [x,y,t],... ]
    :returns: [distance, bool] 
    """
    # assumes a is already in order.
    if len(a) < 2:
        return (0, True)
    a = np.array(a)
    d = a[1:, 0:2] - a[:-1, 0:2]
    return (np.sum(np.linalg.norm(d, axis=1)), False)


T = TypeVar("T")


def iterlen(it: Iterable[T]) -> Tuple[Iterable[T], int]:
    """Return iterator along with its length
    """
    # TODO is it faster to use a deque?
    # iterator, _ = tee(iterator)
    # counter = count()
    # deque(zip(__, counter), maxlen=0)
    # n = next(counter)
    # return iterator, n
    it, _ = tee(it)
    return it, sum(1 for i in _)


def qtracks_overlap(qtrack1: QTrack, qtrack2: QTrack) -> bool:
    """Return True iff the QTracks could possibly overlap"""
    # NOTE centroids are in native units, rescale to meters
    return (
        qtrack1.rescale * np.linalg.norm(qtrack1.centroid - qtrack2.centroid)
        <= qtrack1.diameter + qtrack2.diameter
    )


def signed_twice_triangle_area(pt1: Tuple[float], pt2: Tuple[float], pt3: Tuple[float]):
    """
    Returns twice the area of triangle formed by input 3 points times
    sign of 3 points (+ if counterclockwise and - if clockwise)
    """
    (a, b) = pt1
    (c, d) = pt2
    (e, f) = pt3
    return a * d - b * c + c * f - d * e + e * b - f * a


def on_opposite_sides(
    pt1: Tuple[float], pt2: Tuple[float], pt3: Tuple[float], pt4: Tuple[float]
):
    """
    Returns True iff pt1 and pt2 are on opposite sides of the line
    through pt3 and pt4, including the degenerate case when either
    pt1 or pt2 is on the line through pt3 and pt4.
    """
    return (
        signed_twice_triangle_area(pt1, pt3, pt4)
        * signed_twice_triangle_area(pt2, pt3, pt4)
        <= 0
    )


def segments_intersect(
    pt1: Tuple[float], pt2: Tuple[float], pt3: Tuple[float], pt4: Tuple[float]
):
    """
    Returns True if line segments pt1pt2 and pt3pt4 intersection
    """
    return on_opposite_sides(pt1, pt2, pt3, pt4) and on_opposite_sides(
        pt3, pt4, pt1, pt2
    )


def is_non_self_intersecting_polygon(pt_list: List[Tuple[float]]) -> bool:
    """
    Returns True if input list of points is a polygon (3 or more points)
    that is not self_intersecting.
    """
    n = len(pt_list)
    if n < 3:
        return False
    if n == 3:
        return True
    ps = list(pt_list) + [pt_list[0]]  # for convenience
    for i in range(n - 2):
        for j in range(i + 2, n):
            if (i, j) != (0, n - 1):
                if segments_intersect(ps[i], ps[i + 1], ps[j], ps[j + 1]):
                    return False
    return True

def my_parse_to_datetime(s : str) -> datetime.datetime:
    """
    Returns a datetime.dateime object given a string.
    Uses either maya or dateutil.
    """
    if IMPORT_SUCCESS_maya:
        return maya.parse(s).datetime()
    else:
        return dateutil.parser.parse(s)
