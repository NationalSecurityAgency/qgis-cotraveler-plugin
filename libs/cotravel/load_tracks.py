"""
Data loading stuff. Read track data from disk, filtering out bad pings
"""

# TODO making Tracks from lots of csv files crashes sometimes

import bisect
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Hashable, Iterable, List, Optional, Tuple, Union

import numpy as np
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from ._types import Columns, CPing, Ping, PingList, QTrack, Track
from .config import (DEGREES_TO_METERS, MAX_CEP, MAX_VELOCITY, MILES_TO_METERS,
                     MIN_PINGS, IMPORT_SUCCESS_enlighten,
                     IMPORT_SUCCESS_logzero,
                     IMPORT_SUCCESS_maya)
from .utils import is_non_self_intersecting_polygon, to_timestamp

#import dill as pickle
import pickle
if IMPORT_SUCCESS_enlighten:
    import enlighten
if IMPORT_SUCCESS_logzero:
    from logzero import logger
else:
    import logging as logger
if IMPORT_SUCCESS_maya:
    import maya
else:
    import dateutil
from .utils import my_parse_to_datetime



# __all__ = tracks_from_csv_files


def load_tracks_or_qtracks(
    *filenames: str,
    columns: Columns = "ID TIMESTAMP LON LAT CEP".split(),
    parse_times: bool = True,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    ids: Optional[List[str]] = None,
    units: Optional[str] = None,
    cep_units: Optional[str] = None,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    min_pings: int = MIN_PINGS,
    show_progress: bool = False,
    autocorrect_lon_lat: bool = True,
    bounding_polygon: Optional[List[Tuple[float]]] = None,
    excluded_polygons: Optional[List[List[Tuple[float]]]] = None,
) -> Union[List[Track], List[QTrack]]:
    """
    Load Tracks or QTracks from pickle files, or Tracks from csvs
    :param autocorrect_lon_lat: whether to autocorrect order of lon, lat if detected out of order. Default is True.
    """
    columns = _autocorrect_lon_lat(columns)
    p = Path(filenames[0])
    if p.suffix == ".pkl":  # Note the "dot"!
        return unpickle_tracks_or_qtracks(*filenames)
    elif p.suffix == ".csv":
        return tracks_from_csv_files(
            *filenames,
            columns=columns,
            parse_times=parse_times,
            start_time=start_time,
            end_time=end_time,
            ids=ids,
            units=units,
            cep_units=cep_units,
            max_cep=max_cep,
            max_velocity=max_velocity,
            min_pings=min_pings,
            show_progress=show_progress,
            bounding_polygon=bounding_polygon,
            excluded_polygons=excluded_polygons,
        )
    else:
        return []  # And some sort of warning??


def unpickle_tracks_or_qtracks(*filenames: str) -> Union[List[Track], List[QTrack]]:
    """
    Load Tracks or QTracks from pickle files
    Important: a pickle file should unpickle to a list of Track or QTrack
    """
    res = []
    for filename in filenames:
        try:
            tracks = pickle.load(open(filename, "rb"))
            if not tracks:
                logger.warning(f"No Tracks or QTracks in {filename}. Skipping")
                continue
            if not isinstance(tracks[0], (Track, QTrack)):
                logger.warning(
                    f"{filename} doesn't contain Tracks or QTracks. Skipping"
                )
            res.extend(tracks)
        except TypeError:
            logger.error(f"Can't unpickle Tracks or QTracks from {filename}. Skipping")

    if not (
        all(isinstance(r, Track) for r in res)
        or all(isinstance(r, QTrack) for r in res)
    ):
        raise SystemExit(
            f"Files aren't homogeneous only Tracks or QTracks {[isinstance(r, Track) for r in res]} {[isinstance(r, QTrack) for r in res]}"
        )
    return res


def tracks_from_csv_files(
    *filenames: str,
    columns: Columns = "ID TIMESTAMP LON LAT CEP".split(),
    parse_times: bool = True,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    ids: Optional[List[str]] = None,
    units: Optional[str] = None,
    cep_units: Optional[str] = None,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    min_pings: int = MIN_PINGS,
    show_progress: bool = False,
    bounding_polygon: Optional[List[Tuple[float]]] = None,
    excluded_polygons: Optional[List[List[Tuple[float]]]] = None,
) -> List[Track]:
    """
    Return a list of `Track`s from filenames

    datetimes are converted to unix time

    :param filenames: list of filenames of .csvs to read pings from
    :param columns: list of column names denoting time, ID, x, y, and (optionally) cep, in that order
    :param parse_times: If True, interpret times as datetimes
    :param start_time: ignore Pings before this
    :param end_time: ignore pings after this
    :param ids: if given, only tracks for these IDs will be returned
    :param units: TODO
    :param cep_units: TODO
    :param max_cep: ignore Pings with CEP > max_cep (in meters)
    :param max_velocity: TODO
    :param min_pings: Skip Tracks with fewer than this many pings
    :param show_progress: If true, count lines in filenames (nicer progress bars)
    :param bounding_polygon: if given, a list of vertices (each is a pair of floats) that form a polygon that pings must lie in
    :param excluded_polygons: if given, a list of lists of vertices (each is a pair of floats) that form a polygons that pings must avoid
    :returns: list of `Track` instances
    :rtype: list
    """
    rows_read = 0
    rows_skipped = 0
    if not IMPORT_SUCCESS_enlighten:
        show_progress=False
    if show_progress:
        manager = enlighten.get_manager()
        pbar_files = manager.counter(
            desc="Parsing Files", total=len(filenames), unit="files"
        )

    # TODO should this be a parameter?
    if len(filenames) <= 20:
        logger.debug(f"Counting lines in {len(filenames)} files")
        if show_progress:
            num_lines = sum(sum(1 for line in open(f)) for f in filenames)
            pbar_lines = manager.counter(
                desc="Building Tracks", total=num_lines, unit="lines"
            )
    else:
        if show_progress:
            pbar_lines = manager.counter(desc="Building Tracks", unit="lines")
        pass

    # convert start/end time from str/datetime to unix timestamp
    if start_time:
        start_time = to_timestamp(start_time)
    if end_time:
        end_time = to_timestamp(end_time)

    # figure out units
    rescale = 1.0
    cep_rescale = 1.0
    if units:
        rescale = guess_rescale_factor(units)
    else:
        rescale = guess_rescale_factor(columns[2])
    logger.debug(f"rescale {rescale}")

    if cep_units:
        cep_rescale = guess_rescale_factor(cep_units)
    elif len(columns) == 5:
        cep_rescale = guess_rescale_factor(columns[-1])
    logger.debug(f"cep_rescale {cep_rescale}")

    if bounding_polygon is not None:
        bounding_poly = Polygon(bounding_polygon)
        if not bounding_poly.is_simple:
            raise ValueError(f"Bounding polygon {bounding_polygon} is not simple.")
    if excluded_polygons is not None:
        excluded_polys = [Polygon(p) for p in excluded_polygons]
        for p in excluded_polys:
            if not p.is_simple:
                raise ValueError(f"Excluded polygon {p} is not simple.")

    # tracks is {ID: [(t,x,y)...]} or {ID: [(t,x,y,cep)...]}
    tracks: Dict[Any, PingList] = defaultdict(list)
    if len(filenames) <= 5:
        logger.info(f"Making Tracks from {' '.join(filenames)}")
    else:
        logger.info(f"Making Tracks from {' '.join(filenames[:5])} ...")
    if ids:
        logger.info(f"Making Tracks for IDs: {ids}")
    logger.info(f"Using columns: {' '.join(columns)}")
    logger.debug(f"max_cep: {max_cep} start_time: {start_time} end_time: {end_time}")
    for filename in filenames:
        with open(filename) as fd:
            has_header = csv.Sniffer().has_header(fd.read(4096))
            fd.seek(0)
            if has_header:
                reader = csv.DictReader(fd)
                for c in columns:
                    if c not in reader.fieldnames:
                        raise KeyError(f"Field {c} not found in {reader.fieldnames}")
            else:
                # just use first len(columns) cols of csv
                reader = csv.DictReader(fd, fieldnames=columns)

            for row in reader:
                rows_read += 1
                if show_progress:
                    pbar_lines.update()
                try:
                    ping = parse_row(row, columns, parse_times=parse_times)
                except Exception as err:
                    # logger.debug(f"Error parsing row {rows_read}: {row} {err}")
                    rows_skipped += 1
                    continue

                if ids and ping.ID not in ids:
                    # logger.debug((f"Ignoring ID {ping.ID}"))
                    continue

                # DIAGNOSTIC CODE: can delete when done
                # if ping.ID=="testID1":
                #     print("Working on ping {}.".format(ping))
                # END DIAGNOSTIC CODE.

                if start_time and ping.t < start_time:
                    # logger.debug((f"Ping too soon {ping.t} < {start_time}"))
                    continue
                if end_time and ping.t >= end_time:
                    # logger.debug((f"Ping too late {ping.t} >= {start_time}"))
                    continue
                if (
                    isinstance(ping, CPing)
                    and max_cep is not None
                    and cep_rescale * ping.cep > max_cep
                ):
                    # logger.debug((f"Ignoring CPing with CEP {ping.cep} " +
                    #              f"({cep_rescale * ping.cep} > {max_cep} )"))
                    continue

                if bounding_polygon is not None:
                    if not bounding_poly.contains(Point(ping.x, ping.y)):
                        continue
                skip_this_ping = False
                if excluded_polygons is not None:
                    for p in excluded_polys:
                        if p.contains(Point(ping.x, ping.y)):
                            skip_this_ping = True
                            break
                if skip_this_ping:
                    continue
                add_ping_to_dict(tracks, ping, dedupe=True)
                # logger.debug(f"tracks len:  {len(tracks)}")

                # DIAGNOSTIC CODE: can delete when done
                # if ping.ID=="testID1":
                #     print("Ping added. track so far: {}".format(np.array(tracks[ping.ID])))
                # END DIAGNOSTIC CODE.

        if show_progress:
            pbar_files.update()
    if show_progress:
        pbar_lines.close()
        pbar_files.close()
        manager.stop()

    logger.debug(f"Read {rows_read} rows from {len(filenames)} files")
    if rows_skipped > 0:
        logger.debug(f"Failed to parse {rows_skipped} rows")

    # DIAGNOSTIC CODE: can delete when done
    # print("Before filter. track so far: {}".format(np.array(tracks["testID1"])))
    # END DIAGNOSTIC CODE.

    # convert each list in tracks to a Track
    ts = (Track(k, tracks[k], rescale=rescale, cep_rescale=cep_rescale) for k in tracks)
    # filter bad pings in each track
    ts_f = filter_tracks(ts, min_pings=min_pings, max_velocity=max_velocity)
    ts_f = list(ts_f)

    # DIAGNOSTIC CODE: can delete when done
    # for t in ts_f:
    #     if t.ID=="testID1":
    #         print("After filter. track so far: {}".format(np.array(t.track)))
    # END DIAGNOSTIC CODE.

    logger.info(f"Made {len(ts_f)} Tracks")
    return ts_f


def guess_rescale_factor(column: str) -> float:
    """
    Guess units from column name, and return a scaling factor which will
    convert to meters, or 1 if units can't be inferred

    :param column: Name of a column
    """
    c = column.lower()
    if c.endswith("dd") or "lon" in c or "lat" in c:
        # decimal degrees
        return DEGREES_TO_METERS
    if c.endswith("nm"):
        # nautical miles
        return MILES_TO_METERS
    if c.endswith("km"):
        # kilometers
        return 1000.0
    # no idea, don't convert
    return 1.0


def parse_row(
    row: Dict[Hashable, Any],
    columns: Union[Tuple[str, str, str, str], Tuple[str, str, str, str, str]] = (
        "ID",
        "TIMESTAMP",
        "LON",
        "LAT",
    ),
    parse_times: bool = True,
) -> Union[Ping, CPing]:
    """
    Return a `Ping`/`CPing` constructed from a row dict as parsed by csv.DictReader

    :param dict row: as returned from csv.DictReader
    :param List[str] columns: keys in row

    TODO parse_times is crazy slow
    """
    len_ = len(columns)
    ID, time, x, y = columns[:4]
    if len_ == 5:
        cep = columns[-1]
    else:
        cep = None

    if parse_times:
        #time = maya.parse(row[time]).datetime().timestamp()
        time = my_parse_to_datetime(row[time]).timestamp()
    else:
        time = float(row[time])

    id = row[ID]
    x, y = map(float, [row[x], row[y]])

    return CPing(id, time, x, y, float(row[cep])) if len_ == 5 else Ping(id, time, x, y)


def add_ping_to_dict(
    tracks: Dict[Hashable, PingList], ping: Union[Ping, CPing], dedupe: bool = False
) -> None:

    """
    Update tracks dictionary in place inserting Ping/CPing

    :param tracks: {ID: [(t1,x1,y1), (t2,x2,y2),...]}
    :param ping: a `Ping`/`CPing` namedtuple
    :param dedupe: if True, ignore ping if it's already in the track
    """
    id = ping.ID
    # only need to keep (timestamp, lon, lat)
    p = ping[1:]

    if tracks[id]:
        if dedupe:
            # OLD CODE: we think this was wrong: i = bisect.bisect_left(tracks[id], p)
            i = bisect.bisect_right(tracks[id], p)
            # insert p if it's not already in the track
            if i == 0 or (tracks[id][i - 1] < p):
                tracks[id].insert(i, p)
        else:
            # just insert anyway
            bisect.insort_left(tracks[id], p)
    else:
        tracks[id] = [p]


def filter_tracks(
    tracks: List[Track],
    min_pings: int = MIN_PINGS,
    max_velocity: float = MAX_VELOCITY,
    max_cep: float = None,  # Default is None, or better as MAX_CEP?,
) -> Iterable[Track]:
    """
    Yield `Track`s from cotravel that satisfy the criteria

    :param tracks: list of `Track`s
    :param min_pings: ignore `Track`s with < this many pings
    :param max_velocity: drop pings from `Track`s faster than this
    TODO use max_cep
    """
    if min_pings:
        logger.debug(f"Ignoring tracks with fewer than {min_pings} pings")
    if max_velocity:
        logger.debug(f"Dropping pings faster than {max_velocity}m/s")
    if max_cep:
        logger.debug(f"Dropping pings with cep greater than {max_cep}")

    # tracks = list(tracks)

    for t in tracks:
        if max_cep:
            t = drop_bad_pings_cep(t, max_cep=max_cep)
        t = drop_bad_pings_velocity(t, max_velocity=max_velocity)
        if min_pings and len(t) < min_pings:
            continue
        yield t


def drop_bad_pings_cep(track: Track, max_cep: float = MAX_CEP) -> Track:
    """
    Remove bad pings from track based on CEP field being too large.
    Does nothing if track has no CEP info.
    """
    if max_cep is None or not track.has_cep:
        return track
    return Track(
        ID=track.ID,
        track=[p for p in track.track if p[3] * track.cep_rescale <= max_cep],
        rescale=track.rescale,
        cep_rescale=track.cep_rescale,
    )


def drop_bad_pings_time_window(
    track: Track, start_time: Optional[float] = None, end_time: Optional[float] = None
) -> Track:
    """
    Remove pings from track outside the given time window constraints, which 
    is the half open interval [start_time, end_time).
    """
    if start_time is None:
        if end_time is None:
            return track
        else:
            return Track(
                ID=track.ID,
                track=[p for p in track.track if p[0] < end_time],
                rescale=track.rescale,
                cep_rescale=track.cep_rescale,
            )
    else:
        if end_time is None:
            return Track(
                ID=track.ID,
                track=[p for p in track.track if p[0] >= start_time],
                rescale=track.rescale,
                cep_rescale=track.cep_rescale,
            )
        else:
            return Track(
                ID=track.ID,
                track=[
                    p for p in track.track if (p[0] >= start_time) and (p[0] < end_time)
                ],
                rescale=track.rescale,
                cep_rescale=track.cep_rescale,
            )


def drop_bad_pings_velocity(track: Track, max_velocity: float = MAX_VELOCITY) -> Track:
    """
    Remove bad pings from track based on velocities exceeding max_velocity

    NOTE currently only uses max_velocity, but could do additional filtering in the future
    Current decision is to make each of these a separate drop_bad_pings_* function.
    TODO add start_time/end_time to ignore pings not in the half-open interval [start,end)
    TODO this depends on time being in *seconds* (which it's not always)

    :param Track track: `Track` instance
    :param float max_velocity: filter pings where the object's estimated
    velocity is > max_velocity
    :return: `Track` with bad pings removed
    """
    if not max_velocity or len(track) <= 2:
        return track

    # keep a ping iff all velocities it participates in are <= max_velocity
    ts = np.array([t[0] for t in track.track])
    xs = np.array([t[1] for t in track.track])
    ys = np.array([t[2] for t in track.track])

    dts = ts[1:] - ts[:-1]
    dxs = xs[1:] - xs[:-1]
    dys = ys[1:] - ys[:-1]
    vs = track.rescale * np.sqrt(dxs ** 2 + dys ** 2) / dts

    new_track = []
    for i, p in enumerate(track.track):
        # first and last ping only participates in 1 velocity
        if i == 0:
            if vs[0] > max_velocity:
                continue
        elif i == len(track.track) - 1:
            if vs[-1] > max_velocity:
                continue
        else:
            # others participate in 2 velocities
            if vs[i] > max_velocity and vs[i - 1] > max_velocity:
                continue
        new_track.append(p)

    # TODO should we just mutate track.track in place instead?
    # If we do, then perhaps this should be a method instead of an external function.
    return Track(
        ID=track.ID,
        track=new_track,
        rescale=track.rescale,
        cep_rescale=track.cep_rescale,
    )


def _autocorrect_lon_lat(columns: Columns):
    """
    Checks that the 3rd and 4th column names are in the order LON LAT
    :param columns: tuple of strings in order ID, timestamp, LON, LAT, optional CEP
        Will correct order into LON LAT when appropriate
    """
    lon_str = columns[2].lower()
    lat_str = columns[3].lower()
    if (
        ("lat" in lon_str)
        and (not ("lon" in lon_str))
        and ("lon" in lat_str)
        and (not ("lat" in lat_str))
    ):
        ans = [columns[0], columns[1], columns[3], columns[2]] + columns[4:]
        logger.warning(
            f"AUTOCORRECTION applied to change {columns} to {ans} to put lon lat columns in correct order."
        )
        return ans
    return columns
