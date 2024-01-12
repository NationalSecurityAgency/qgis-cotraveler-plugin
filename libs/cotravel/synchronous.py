#!/usr/bin/env python3

"""
TODO module documentation
"""

import datetime
import os
import pathlib

# import dill as pickle
import pickle
import warnings
from functools import partial
from typing import Iterable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ._types import QTrack, TimestampLike, Track
from .config import (
    ADD_EXTRAPOLATED_PINGS,
    DEFAULT_COLUMNS,
    DELTA_T,
    FIELDS_PAIRS,
    FIELDS_PAIRS_VITAL,
    MAX_CEP,
    MAX_DIST,
    MAX_VELOCITY,
    MIN_COMMON_DIAMETER,
    MIN_COMMON_QPINGS,
    MIN_DIAMETER,
    MIN_PINGS,
    MIN_PINGS_PER_TIMEBIN,
    MIN_QPINGS,
    MIN_TIMEBIN_FRACTION,
    REQUIRE_POSSIBLE_OVERLAP,
    IMPORT_SUCCESS_logzero,
    IMPORT_SUCCESS_sortedcontainers,
    IMPORT_SUCCESS_tabulate,
)
from .load_tracks import load_tracks_or_qtracks
from .pmap import filtermap_pairs
from .quantize import quantize_tracks
from .utils import (
    _diameter,
    average_distance,
    diameters,
    num_common_qpings,
    qtracks_overlap,
    to_datetime,
    to_timestamp,
    vector_of_distances,
)

if IMPORT_SUCCESS_sortedcontainers:
    from sortedcontainers import SortedList
if IMPORT_SUCCESS_logzero:
    from logzero import logger
else:
    import logging as logger
if IMPORT_SUCCESS_tabulate:
    from tabulate import tabulate


warnings.simplefilter("ignore", RuntimeWarning)
CHUNKSIZE = 1_000_000


def synchronous(
    files1: Union[str, List[str]],
    files2: Optional[List[str]] = (),
    columns1: List[str] = DEFAULT_COLUMNS,
    columns2: List[str] = DEFAULT_COLUMNS,
    ids1: Tuple[str] = (),
    ids2: Tuple[str] = (),
    seed_ids: Tuple[str] = (),
    returned_columns = FIELDS_PAIRS,
    units1: Optional[str] = None,
    units2: Optional[str] = None,
    cep_units1: Optional[str] = None,
    cep_units2: Optional[str] = None,
    parse_times: bool = True,
    start_time: Optional[TimestampLike] = None,
    end_time: Optional[TimestampLike] = None,
    scores_file: Optional[str] = None,
    replace_scores_file: bool = False,
    tracks1_file: Optional[str] = None,
    tracks2_file: Optional[str] = None,
    qtracks1_file: Optional[str] = None,
    qtracks2_file: Optional[str] = None,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    delta_t: float = DELTA_T,
    max_dist: float = MAX_DIST,
    min_pings: int = MIN_PINGS,
    min_timebin_fraction: float = MIN_TIMEBIN_FRACTION,
    add_extrapolated_pings: bool = ADD_EXTRAPOLATED_PINGS,
    min_pings_per_timebin: int = MIN_PINGS_PER_TIMEBIN,
    min_qpings: int = MIN_QPINGS,
    min_common_qpings: int = MIN_QPINGS,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
    min_diameter: float = MIN_DIAMETER,
    min_common_diameter: float = MIN_COMMON_DIAMETER,
    time_window: Optional[float] = None,
    distance_window: Optional[float] = None,
    total_time: Optional[float] = None,
    total_distance: Optional[float] = None,
    within_distance: Optional[float] = None,
    exit_early: bool = True,
    bounding_polygon: Optional[List[Tuple[float, float]]] = None,
    excluded_polygons: Optional[List[List[Tuple[float, float]]]] = None,
    chunksize: int = CHUNKSIZE,
    jobs: Optional[int] = None,
) -> pd.DataFrame:
    """
    Find full-time or part-time synchronous cotraveler pairs.

    If tracks2 is omitted, we score all pairs of tracks from tracks1 with each other. If tracks2 is provided, we score all pairs of tracks where one is from tracks1 and the other is from tracks2

    :param files1: /path/to/files1 or list of /paths/to/files1. Either csvs containing Pings, or pickle files containing QTracks or Tracks
    :param files2: /path/to/files2 or list of /paths/to/files2 (or None)
    :param columns1: Column names for files1 corresponding to ID TIMESTAMP LON LAT [CEP] (ignored if files1 contains QTracks/Tracks)
    :param columns2: Column names for files2 corresponding to ID TIMESTAMP LON LAT [CEP] (ignored if files2 contains QTracks/Tracks)
    :param ids1: List of IDs for files1 (ignore IDs not in this list)
    :param ids2: List of IDs for files2 (ignore IDs not in this list)
    :param seed_ids: List of IDs to use in ids1 as seeds. This is mainly important in the case where files2 is None; in this case we do not want to simply filter files1 by ids1.
    :param returned_columns: Returned dataframe has only these specified columns;
       default is FIELDS_PAIRS from config.py, and use 'all' to return all columns from FIELDS_PAIRS and use 'vital' for FIELDS_PAIRS_VITAL.
    :param units1: Units for LON/LAT in files1 (by default will try to infer from column names)
    :param units2: Units for LON/LAT in files2 (by default will try to infer from column names)
    :param cep_units1: Units for CEP in files1 (by default will try to infer from column name)
    :param cep_units2: Units for CEP in files2 (by default will try to infer from column name)
    :param parse_times: If True, parse timestamps as datetimes
    :param start_time: Start time for global quantization window. Ignore pings before this (ignored if passed QTracks/Tracks instead if pings)
    :param end_time: End time for global quantization window. Ignore pings after this (ignored if passed QTracks/Tracks instead if pings)
    :param scores_file: /path/to/file/to/save/scores
    :param replace_scores_file: If True, overwrite scores_file (if it exists)
    :param tracks1_file: Save Tracks built from files1 to disk as pickle
    :param tracks2_file: Save Tracks built from files2 to disk as pickle
    :param qtracks1_file: Save QTracks built from files1 to disk as pickle
    :param qtracks2_file: Save QTracks built from files2 to disk as pickle
    :param max_cep: Ignore pings with CEP above this value (in meters)
    :param max_velocity: Ignore pings faster than this (helps remove bad pings)
    :param delta_t: Duration of timebins for quantization (in seconds)
    :param max_dist: Only return scores <= this (meters)
    :param min_pings: Ignore Tracks with fewer than this many pings
    :param min_timebin_fraction: For the first and last qping, this is the required fraction of the time occupied by input Track to have a nonmasked qping.
    :param add_extrapolated_pings: For the first and last qping, whether or not to extrapolate track to the edges of the time bin in the event the input Track doesn't fill up time bin. Default is False.
    :param min_pings_per_timebin: minimum number of original pings in timebin for qping to be unmasked. That is, ignore qpings with fewer than this many original pings in the timebin
    :param min_qpings: Ignore QTracks with fewer than this many quantized pings
    :param min_common_qpings: Ignore QTrack pairs with fewer than this many quantized pings in their temporal overlap
    :param require_possible_overlap: whether to ignore pairs that could not have overlapped
    :param min_diameter: Ignore QTracks with (approximate) diameter smaller than this (meters) (Note this refers to the diameter of the whole track,  even for part-time scoring options)
    :param min_common_diameter: Ignore QTrack pairs with (approximate) diameter of their temporal overlap smaller than this (meters)
    :param time_window: If this keyword is set and method is None, then pt_synchronous_score_given_time_window is called.
    :param distance_window: If this keyword is set and method is None, then pt_synchronous_score_given_distance_window is called
    :param total_time: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_time is called.
    :param total_distance: If this keyword is set and method is None, then pIgnore QTrack pairs with (approximate) diameter of their temporal overlap smaller than this (meters)t_synchronous_score_noncontiguous_total_distance is called
    :param within_distance: If this keyword is set and method is None, then pt_synchronous_score_given_within_distance is called
    :param exit_early: If True for the noncontiguous methods, then a result is returned when all possible intervals of twice the given window size are considered and a viable answer is found.
    :param bounding_polygon: if given, a list of vertices (each is a pair of floats) that form a polygon that pings must lie in
    :param excluded_polygons: if given, a list of lists of vertices (each is a pair of floats) that form a polygons that pings must avoid
    :param chunksize: Size of chunks sent to Pool.imap
    :param jobs: Number of cores to use (defaults to all available)

    """
    if scores_file:
        if replace_scores_file:
            logger.info(f"Will write scores to {scores_file}")
        else:
            # TODO check if file exists andupdate log message
            logger.info(f"Will append scores to {scores_file}")

    # check if files{1,2} is a single str representing a path or a list
    if isinstance(files1, (str, pathlib.Path)):
        files1 = [files1]
    if isinstance(files2, (str, pathlib.Path)):
        files2 = [files2]

    logger.info(f"Loading data from {len(files1)} files")

    # Is the following being too smart?
    # (This is the case where we may as well filter files1 by seed_ids.)
    if seed_ids and files2: ids1 = seed_ids

    tracks_or_qtracks1 = load_tracks_or_qtracks(
        *files1,
        columns=columns1,
        parse_times=parse_times,
        start_time=start_time,
        end_time=end_time,
        ids=ids1,
        units=units1,
        cep_units=cep_units1,
        max_cep=max_cep,
        max_velocity=max_velocity,
        min_pings=min_pings,
        bounding_polygon=bounding_polygon,
        excluded_polygons=excluded_polygons,
    )

    if not tracks_or_qtracks1:
        logger.warning("No tracks found")
        return None

    type1 = type(tracks_or_qtracks1[0])

    logger.info(
        f"Built {len(tracks_or_qtracks1):,d} {type1.__name__}s from {len(files1)} files"
    )

    if files2:
        logger.info(f"Loading data from {len(files2)} files")
        tracks_or_qtracks2 = load_tracks_or_qtracks(
            *files2,
            columns=columns2,
            parse_times=parse_times,
            start_time=start_time,
            end_time=end_time,
            ids=ids2,
            units=units2,
            cep_units=cep_units2,
            max_cep=max_cep,
            max_velocity=max_velocity,
            min_pings=min_pings,
        )
        if not tracks_or_qtracks2:
            logger.warning("No tracks found")
            return

        type2 = type(tracks_or_qtracks2[0])
        logger.info(
            f"Built {len(tracks_or_qtracks2):,d} {type2.__name__}s from {len(files2)} files"
        )
    else:
        type2, tracks_or_qtracks2, qtracks2 = None, None, None

    if type1 is QTrack:
        qtracks1 = tracks_or_qtracks1
        tracks1 = None
    else:
        tracks1 = tracks_or_qtracks1
        if tracks1_file:
            logger.info(f"Writing {len(tracks1)} Tracks to {tracks1_file}")
            pickle.dump(tracks1, open(tracks1_file, "wb"))

    if type2 is QTrack:
        qtracks2 = tracks_or_qtracks2 if tracks_or_qtracks2 else None
        tracks1 = None
    else:
        tracks2 = tracks_or_qtracks2 if tracks_or_qtracks2 else None
        if tracks2_file and tracks2 is not None:
            logger.info(f"Writing {len(tracks2)} Tracks to {tracks2_file}")
            pickle.dump(tracks2, open(tracks2_file, "wb"))

    if type1 is Track or type2 is Track:
        # figure out quantization start/end times
        if tracks1 and tracks2:
            # both = itertools.chain(tracks1, tracks2)
            # This doesn't work because we consume both twice!
            both = tracks1 + tracks2
        elif tracks1:
            both = tracks1
        else:
            both = tracks2
        qstart_time = (
            to_timestamp(start_time) if start_time else min(t.start_time for t in both)
        )
        qend_time = (
            to_timestamp(end_time) if end_time else max(t.end_time for t in both)
        )

    # now that we have qstart/qend, we can quantize if necessary
    if type1 is Track:
        qtracks1 = quantize_tracks(
            tracks1,
            qstart_time,
            qend_time,
            delta_t=delta_t,
            min_qpings=min_qpings,
            min_diameter=min_diameter,
            min_timebin_fraction=min_timebin_fraction,
            add_extrapolated_pings=add_extrapolated_pings,
            min_pings_per_timebin=min_pings_per_timebin,
            chunksize=chunksize,
            jobs=jobs,
        )
        if qtracks1_file:
            logger.info(f"Writing {len(qtracks1)} QTracks to {qtracks1_file}")
            pickle.dump(qtracks1, open(qtracks1_file, "wb"))

    if type2 is Track:
        qtracks2 = (
            quantize_tracks(
                tracks2,
                qstart_time,
                qend_time,
                delta_t=delta_t,
                min_qpings=min_qpings,
                min_diameter=min_diameter,
                min_timebin_fraction=min_timebin_fraction,
                add_extrapolated_pings=add_extrapolated_pings,
                min_pings_per_timebin=min_pings_per_timebin,
                chunksize=chunksize,
                jobs=jobs,
            )
            if tracks2 is not None
            else None
        )
        if qtracks2_file and qtracks2 is not None:
            logger.info(f"Writing {len(qtracks2)} QTracks to {qtracks2_file}")
            pickle.dump(qtracks2, open(qtracks2_file, "wb"))

    comparisons = synchronous_scores_from_qtracks(
        qtracks1,
        qtracks2,
        ids = seed_ids,
        returned_columns = returned_columns,
        min_diameter=min_diameter,
        min_qpings=min_qpings,
        min_common_qpings=min_common_qpings,
        min_common_diameter=min_common_diameter,
        min_pings_per_timebin=min_pings_per_timebin,
        max_dist=max_dist,
        time_window=time_window,
        distance_window=distance_window,
        total_time=total_time,
        total_distance=total_distance,
        within_distance=within_distance,
        require_possible_overlap=require_possible_overlap,
        exit_early=exit_early,
        jobs=jobs,
    )

    if IMPORT_SUCCESS_tabulate:
        logger.debug(
            f"\n{tabulate(comparisons, headers=comparisons.columns, showindex=False)}"
        )
        # else do some other debug output?
    if scores_file:
        if replace_scores_file:
            logger.info(f"Writing scores to {scores_file}")
            comparisons.to_csv(scores_file, index=False, mode="w")
        else:
            header = False if os.path.isfile(scores_file) else True
            logger.info(f"Appending scores to {scores_file}")
            comparisons.to_csv(scores_file, index=False, header=header, mode="a")
    return comparisons


def synchronous_scores(
    tracks1: Union[Iterable[Track], Iterable[QTrack]],
    tracks2: Optional[Union[Iterable[Track], Iterable[QTrack]]] = None,
    qstart_time: Optional[TimestampLike] = None,
    qend_time: Optional[TimestampLike] = None,
    delta_t: float = DELTA_T,
    returned_columns = FIELDS_PAIRS,
    min_timebin_fraction: float = MIN_TIMEBIN_FRACTION,
    min_qpings: int = MIN_QPINGS,
    min_diameter: float = MIN_DIAMETER,
    add_extrapolated_pings: bool = ADD_EXTRAPOLATED_PINGS,
    min_pings_per_timebin: int = MIN_PINGS_PER_TIMEBIN,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    min_common_diameter: float = MIN_COMMON_DIAMETER,
    max_dist: float = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
    time_window: Optional[float] = None,
    distance_window: Optional[float] = None,
    total_time: Optional[float] = None,
    total_distance: Optional[float] = None,
    within_distance: Optional[float] = None,
    exit_early: bool = True,
    chunksize: int = 10000,
    jobs: Optional[int] = None,
):
    """
    Compute full-time or part-time contiguous or noncontiguous synchronous scores for all pairs of Tracks or QTracks

    If tracks2 is omitted, we score all pairs of tracks from tracks1 with each other. If tracks2 is provided, we score all pairs of tracks where one is from tracks1 and the other is from tracks2

    Return a DataFrame of scores and other ancillary information for each `QTrack` pair

    :param tracks1: list of `Track`s or `QTrack`s
    :param tracks2: list of`Track`s or `QTrack`s, optional
    :param returned_columns: Returned dataframe has only these specified columns;
       default is FIELDS_PAIRS from config.py, and use 'all' to return all columns from FIELDS_PAIRS and use 'vital' for FIELDS_PAIRS_VITAL.
    :param qstart_time: Start time for global quantization window. Ignore pings before this
    :param qend_time: End time for global quantization window. Ignore pings after this
    :param delta_t: Duration of quantization time bins (in seconds)
    :param min_qpings: ignore a QTrack if it has < this many qpings
    :param min_diameter: ignore a QTrack if its diameter is < this
    :param min_common_qpings: ignore a pair if they have fewer than this many corresponding common qpings
    :param min_common_diameter: ignore a pair if the diameter of their temporal intersection is < this
    :param min_pings_per_timebin: mask (ignore during scoring) qpings with fewer than this many original pings in the timebin
    :param max_dist: ignore pairs who score > this
    :param require_possible_overlap: whether to ignore pairs that could not have overlapped
    :param time_window: If this keyword is set and method is None, then pt_synchronous_score_given_time_window is called.
    :param distance_window: If this keyword is set and method is None, then pt_synchronous_score_given_distance_window is called
    :param total_time: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_time is called.
    :param total_distance: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_distance is called
    :param within_distance: If this keyword is set and method is None, then pt_synchronous_score_given_within_distance is called
    :param exit_early: If True for the noncontiguous methods, then a result is returned when all possible intervals of twice the given window size are considered and a viable answer is found.
    :param jobs: number of processors to use
    """
    tracks1 = list(tracks1)
    tracks2 = list(tracks2) if tracks2 else None

    if type(tracks1[0]) is QTrack:
        qtracks1 = tracks1
        qtracks2 = tracks2 if tracks2 else None

    else:
        # figure out quantization start/end times
        if tracks1 and tracks2:
            # both = itertools.chain(tracks1, tracks2)
            # This doesn't work because we consume both twice!
            both = tracks1 + tracks2
        elif tracks1:
            both = tracks1
        else:
            both = tracks2
        qstart_time = (
            to_timestamp(qstart_time)
            if qstart_time
            else min(t.start_time for t in both)
        )
        qend_time = (
            to_timestamp(qend_time) if qend_time else max(t.end_time for t in both)
        )

        # now that we have qstart/qend, we can quantize if necessary
        qtracks1 = quantize_tracks(
            tracks1,
            qstart_time,
            qend_time,
            delta_t=delta_t,
            min_qpings=min_qpings,
            min_diameter=min_diameter,
            min_timebin_fraction=min_timebin_fraction,
            add_extrapolated_pings=add_extrapolated_pings,
            min_pings_per_timebin=min_pings_per_timebin,
            chunksize=chunksize,
            jobs=jobs,
        )
        if tracks2:
            qtracks2 = quantize_tracks(
                tracks2,
                qstart_time,
                qend_time,
                delta_t=delta_t,
                min_qpings=min_qpings,
                min_diameter=min_diameter,
                min_timebin_fraction=min_timebin_fraction,
                add_extrapolated_pings=add_extrapolated_pings,
                min_pings_per_timebin=min_pings_per_timebin,
                chunksize=chunksize,
                jobs=jobs,
            )
    return synchronous_scores_from_qtracks(
        qtracks1,
        qtracks2,
        returned_columns = returned_columns,
        min_diameter=min_diameter,
        min_qpings=min_qpings,
        min_common_qpings=min_common_qpings,
        min_common_diameter=min_common_diameter,
        min_pings_per_timebin=min_pings_per_timebin,
        max_dist=max_dist,
        time_window=time_window,
        distance_window=distance_window,
        total_time=total_time,
        total_distance=total_distance,
        within_distance=within_distance,
        require_possible_overlap=require_possible_overlap,
        exit_early=exit_early,
        jobs=jobs,
    )


def synchronous_scores_from_qtracks(
    qtracks1: List[QTrack],
    qtracks2: Optional[List[QTrack]] = None,
    ids: Tuple[str] = (),
    returned_columns: Union[List[str], str] = FIELDS_PAIRS_VITAL,
    min_qpings: int = MIN_QPINGS,
    min_diameter: float = MIN_DIAMETER,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    min_common_diameter: float = MIN_COMMON_DIAMETER,
    min_pings_per_timebin: Optional[int] = MIN_PINGS_PER_TIMEBIN,
    max_dist: float = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
    time_window: Optional[float] = None,
    distance_window: Optional[float] = None,
    total_time: Optional[float] = None,
    total_distance: Optional[float] = None,
    within_distance: Optional[float] = None,
    exit_early: bool = True,
    jobs: Optional[int] = None,
    # qgis_obj: Optional[QgsProcessingFeedBack] = None,
    qgis_obj: Optional[object] = None,
) -> pd.DataFrame:
    """
    Compute full-time or part-time contiguous or noncontiguous synchronous scores for all pairs of QTracks

    If qtracks2 is omitted, we score all pairs of qtracks from qtracks1 with each other. If qtracks2 is provided, we score all pairs of qtracks where one is from qtracks1 and the other is from qtracks2

    Return a DataFrame of scores and other ancillary information for each `QTrack` pair

    :param qtracks1: list of `QTrack`s
    :param qtracks2: list of`QTrack`s
    :param ids: filter qtracks1 down to seed tracks with these ids
    :param returned_columns: Returned dataframe has only these specified columns;
       default is FIELDS_PAIRS_VITAL from config.py, and use 'all' to return all columns from FIELDS_PAIRS from config.py and use 'vital' for FIELDS_PAIRS_VITAL.
    :param min_qpings: ignore a QTrack if it has < this many qpings
    :param min_diameter: ignore a QTrack if its diameter is < this
    :param min_common_qpings: ignore a pair if they have fewer than this many corresponding common qpings
    :param min_common_diameter: ignore a pair if the diameter of their temporal intersection is < this
    :param min_pings_per_timebin: mask (ignore during scoring) qpings with fewer than this many original pings in the timebin
    :param max_dist: ignore pairs who score > this
    :param require_possible_overlap: whether to ignore pairs that could not have overlapped
    :param time_window: If this keyword is set and method is None, then pt_synchronous_score_given_time_window is called.
    :param distance_window: If this keyword is set and method is None, then pt_synchronous_score_given_distance_window is called
    :param total_time: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_time is called.
    :param total_distance: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_distance is called
    :param within_distance: If this keyword is set and method is None, then pt_synchronous_score_given_within_distance is called
    :param exit_early: If True for the noncontiguous methods, then a result is returned when all possible intervals of twice the given window size are considered and a viable answer is found.
    :param jobs: number of processors to use
    :rtype: pandas.DataFrame
    """
    _start = datetime.datetime.now()
    if returned_columns == 'all':
        returned_columns = FIELDS_PAIRS
    if returned_columns == 'vital':
        returned_columns = FIELDS_PAIRS_VITAL

    # set min_qpings or min_diameter to zero if no condition given
    if not min_qpings:
        min_qpings = 0
    if not min_diameter:
        min_diameter = 0

    logger.debug(f"Ignoring QTracks with fewer than {min_qpings} qpings")
    logger.debug(f"Ignoring QTracks with diameter < {min_diameter:0.2f}")
    logger.debug(f"Min common qpings: {min_common_qpings}")
    logger.debug(f"Min common diameter: {min_common_diameter}")
    logger.debug(f"Max distance: {max_dist}")
    logger.debug(f"Require possible overlap: {require_possible_overlap}")

    # We should remask always, unless None.
    if min_pings_per_timebin is not None:
        logger.info(f"Remasking QTracks to {min_pings_per_timebin} pings per timebin")
        for q in qtracks1:
            q.remask(min_pings_per_timebin)
        if qtracks2:
            for q in qtracks2:
                q.remask(min_pings_per_timebin)

    # filter qtracks1 according to min_qpings and min_diameter
    qtracks1 = [
        _ for _ in qtracks1 if _.num_qpings >= min_qpings and _.diameter >= min_diameter
    ]
    n1 = len(qtracks1)

    if qtracks2 is None or (qtracks1 is qtracks2):
        logger.debug("Scoring QTracks against themselves")
        # don't score a `QTrack` against itself
        n_pairs = n1 * (n1 - 1) // 2
    else:
        logger.debug("Scoring QTracks against one another")
        # filter qtracks2 according to min_qpings and min_diameter
        qtracks2 = [
            _
            for _ in qtracks2
            if _.num_qpings >= min_qpings and _.diameter >= min_diameter
        ]
        n1, n2 = len(qtracks1), len(qtracks2)
        n_pairs = n1 * n2

    logger.info(f"Scoring {n_pairs:,d} QTrack pairs (using {jobs} jobs)")

    # figure out which scoring function to call
    if (
        time_window is not None
        or distance_window is not None
        or total_time is not None
        or total_distance is not None
        or within_distance is not None
    ):
        # part-time synchronous scoring, either contiguous or noncontiguous
        f = partial(
            pt_synchronous_score,
            time_window=time_window,
            distance_window=distance_window,
            total_time=total_time,
            total_distance=total_distance,
            within_distance=within_distance,
            min_common_qpings=min_common_qpings,
            min_common_diameter=min_common_diameter,
            max_dist=max_dist,
            require_possible_overlap=require_possible_overlap,
            exit_early=exit_early,
        )
    else:
        # full-time synchronous scoring
        f = partial(
            synchronous_score,
            max_dist=max_dist,
            min_common_qpings=min_common_qpings,
            min_common_diameter=min_common_diameter,
            require_possible_overlap=require_possible_overlap,
        )

    if ids:
        logger.info(f"Using {len(ids)} seed qtracks")
       # seed_qtracks = [
       #     _ for _ in qtracks1 if _.ID in ids
       # ]
       # scored_pairs = list(
       #     filtermap_pairs(f, seed_qtracks, qtracks2, jobs=jobs, qgis_obj=qgis_obj)
       # )
    scored_pairs = list(
        filtermap_pairs(f, qtracks1, qtracks2, ids=ids, jobs=jobs, qgis_obj=qgis_obj)
    )
    try:
        # exemplar QTrack, so we can populate extra columns in output dataframe
        q = scored_pairs[0][1][0]
    except IndexError:
        logger.warning("No scored pairs returned")
        return pd.DataFrame(columns=FIELDS_PAIRS)

    # gather desired output columns
    rs = (
        (
            q1.ID,
            q2.ID,
            dist,
            timebin_start,
            timebin_end,
            total_time,
            total_distance,
            midpoint_times,
            diam_common,
            diam1,
            diam2,
            *(q1.centroid.data),
            *(q2.centroid.data),
            n_common_qpings,
        )
        for (
            (
                dist,
                timebin_start,
                timebin_end,
                total_time,
                total_distance,
                midpoint_times,
                diam_common,
                diam1,
                diam2,
                n_common_qpings,
            ),
            (q1, q2),
        ) in scored_pairs
    )

    if within_distance is not None:
        # sort scores in descending order (since we want to maximize counts)
        if IMPORT_SUCCESS_sortedcontainers:
            res = SortedList(
                rs, key=lambda t: (-t[2], t[0], t[1])
            )  # to be deterministic for test module purposes
        else:
            res = sorted(
                rs, key=lambda t: (-t[2], t[0], t[1])
            )  # to be deterministic for test module purposes
    else:
        # sort scores in ascending order (since we want to minimize average distance)
        if IMPORT_SUCCESS_sortedcontainers:
            res = SortedList(
                rs, key=lambda t: (t[2], t[0], t[1])
            )  # to be deterministic for test module purposes
        else:
            res = sorted(
                rs, key=lambda t: (t[2], t[0], t[1])
            )  # to be deterministic for test module purposes

    # make res into a dataframe and add qstart/qend and delta_t
    df = pd.DataFrame(list(res), columns=FIELDS_PAIRS[:16])

    df["delta_t"] = q.delta_t
    df["qstart_time"] = to_datetime(q.qstart_time).isoformat()
    df["qend_time"] = to_datetime(q.qend_time).isoformat()

    df = df[returned_columns]

    if within_distance is not None:
        # rename dist column to count
        df.rename(columns={"avg_dist": "count"}, inplace=True)


    # timing info
    _end = datetime.datetime.now()
    _duration = _end - _start
    if _duration!=0:
        _more_info = f" ({n_pairs/_duration.total_seconds() :.2f} pairs/sec)"
    logger.info(
        f"Scoring took {_duration}{_more_info}"
    )
    return df


def synchronous_score(
    qtrack1: QTrack,
    qtrack2: QTrack,
    max_dist: float = MAX_DIST,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    min_common_diameter: float = MIN_DIAMETER,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
) -> Union[
    None,
    Tuple[
        float,
        datetime.datetime,
        datetime.datetime,
        float,
        float,
        List[datetime.datetime],
        float,
        float,
        float,
        int,
    ],
]:
    """
    Compute full-time synchronous score for a pair of QTracks

    score is the average distance between the QTracks

    Return (score, beginning of first time bin, end of last time bin, total
    time, total distance, list of midpoint times of time bins, common
    diameter, qtrack1 diameter (in the temporal overlap), qtrack2 diameter (in the temporal overlap), number of common qpings)
    when QTracks satisfy the criteria, else None

    :param qtrack1: input QTrack to be scored
    :param qtrack2: input QTrack to be scored
    :param max_dist: a distance filter, return None if the score (average distance between qtrack1 and qtrack2) is greater than this.
    :param min_common_qpings: a filter, return None if number of common qpings is below this.
    :param min_common_diameter: a filter, return None if common diameter is below this.
    :param require_possible_overlap: a filter, return None if it is not possible for two tracks to intersect.
    """

    # (A) common qpings
    n_common_qpings = num_common_qpings(qtrack1, qtrack2)
    if min_common_qpings and n_common_qpings < min_common_qpings:
        return None

    # (B) centroid
    if require_possible_overlap and not qtracks_overlap(qtrack1, qtrack2):
        return None

    # (C) distance
    avg_dist = average_distance(qtrack1, qtrack2)
    if np.isnan(avg_dist):
        # TODO WTF, can this happen? (We already tested above for common qpings
        return None
    if max_dist and avg_dist > max_dist:
        return None

    # (D) diameter
    # Note since we return diameters, we calculate diams regardless whether filter is turned on.
    diams = diameters(qtrack1, qtrack2)
    if min_common_diameter and diams[0] < min_common_diameter:
        return None

    total_distance = np.sum(qtrack1.bin_distances + qtrack2.bin_distances) / 2
    midpoint_times = [
        #timebin_start + (i + 0.5) * qtrack1.delta_t
        qtrack1.qstart_time + (i + 0.5) * qtrack1.delta_t
        for i in range(len(qtrack1))
        # is the following the correct notion? where both qpings are unmasked?
        if not (qtrack1.qtrack.mask[i][0] or qtrack2.qtrack.mask[i][0])
    ]
    #timebin_start = qtrack1.qstart_time
    #timebin_end = qtrack1.qend_time
    timebin_start = midpoint_times[0] - qtrack1.delta_t/2
    timebin_end = midpoint_times[-1] + qtrack1.delta_t/2
    total_time = timebin_end - timebin_start

    # (dist, first timebin start, last timebin end, total time, total distance, list of midpoint times of timebins, common diameter, d1, d2, num common qpings)
    return (
        avg_dist,
        timebin_start,
        timebin_end,
        total_time,
        total_distance,
        midpoint_times,
        *diams,
        n_common_qpings,
    )


def pt_synchronous_score(
    qtrack1: QTrack,
    qtrack2: QTrack,
    time_window: Optional[float] = None,
    distance_window: Optional[float] = None,
    total_time: Optional[float] = None,
    total_distance: Optional[float] = None,
    within_distance: Optional[float] = None,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    min_common_diameter: float = MIN_DIAMETER,
    max_dist: Optional[float] = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,  # What should the default be?
    exit_early: bool = True,
) -> Union[
    None,
    Tuple[
        float,
        datetime.datetime,
        datetime.datetime,
        float,
        float,
        List[datetime.datetime],
        float,
        float,
        float,
        int,
    ],
]:
    """
    Compute part-time synchronous score for a pair of QTracks

    Return (score, beginning of first time bin, end of last time bin, total
    time, total distance, list of midpoint times of time bins, common diameter,
    part-time diameter of qtrack1, part-time diameter of qtrack2, number of
    common qpings) when QTracks satisfy the criteria, else None

    Usage:
      pt_synchronous_score(qtrack1, qtrack2, keyword [for the desired method] = value, *optional keyword parameter)
    Calls the corresponding method based on which keyword value is set (one of time_window, distance_window, total_time, total_distance, or within_distance).
    Exactly one of the keywords must be not None.

    :param qtrack1: first of two Qtracks to be scored together
    :param qtrack2: second of two Qtracks to be scored together
    :param time_window: If this keyword is set and method is None, then pt_synchronous_score_given_time_window is called.
    :param distance_window: If this keyword is set and method is None, then pt_synchronous_score_given_distance_window is called
    :param total_time: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_time is called.
    :param total_distance: If this keyword is set and method is None, then pt_synchronous_score_noncontiguous_total_distance is called
    :param within_distance: If this keyword is set and method is None, then pt_synchronous_score_given_within_distance is called
    :param max_dist: If not None, then is used as a filter so that None is returned if score is > max_dist
    :param require_possible_overlap: If True, then acts as a filter so that None is returned if the two QTracks cannot possibly intersect because distance between their centroids is greater than sum of their diameters.
    :param exit_early: If True for the noncontiguous methods, then a result is returned when all possible intervals of twice the given window size are considered and a viable answer is found.
    """
    acceptable_keywords_as_string = (
        "time_window, distance_window, total_time, total_distance, within_distance"
    )
    parameter_values = [
        time_window,
        distance_window,
        total_time,
        total_distance,
        within_distance,
    ]
    number_of_not_Nones = len(parameter_values) - parameter_values.count(None)
    if number_of_not_Nones == 0:
        raise ValueError(
            f"No method specified; one of the parameters {acceptable_keywords_as_string} must be been set."
        )
    if number_of_not_Nones > 1:
        raise ValueError(
            f"({parameter_values}) Ambiguous call because more than one of the parameters {acceptable_keywords_as_string} has been set."
        )
    if time_window is not None:
        answer = pt_synchronous_score_given_time_window(
            qtrack1,
            qtrack2,
            time_window=time_window,
            min_common_qpings=min_common_qpings,
            max_dist=max_dist,
            require_possible_overlap=require_possible_overlap,
            exit_early=exit_early,
        )
    elif distance_window is not None:
        answer = pt_synchronous_score_given_distance_window(
            qtrack1,
            qtrack2,
            distance_window=distance_window,
            min_common_qpings=min_common_qpings,
            max_dist=max_dist,
            require_possible_overlap=require_possible_overlap,
            exit_early=exit_early,
        )
    elif total_time is not None:
        answer = pt_synchronous_score_noncontiguous_total_time(
            qtrack1,
            qtrack2,
            total_time=total_time,
            min_common_qpings=min_common_qpings,
            max_dist=max_dist,
            require_possible_overlap=require_possible_overlap,
        )
    elif total_distance is not None:
        answer = pt_synchronous_score_noncontiguous_total_distance(
            qtrack1,
            qtrack2,
            total_distance=total_distance,
            min_common_qpings=min_common_qpings,
            max_dist=max_dist,
            require_possible_overlap=require_possible_overlap,
        )
    elif within_distance is not None:
        answer = pt_synchronous_score_given_within_distance(
            qtrack1,
            qtrack2,
            within_distance=within_distance,
            min_common_qpings=min_common_qpings,
            require_possible_overlap=require_possible_overlap,
        )
    else:
        raise ValueError(
            f"Something went wrong when it should not have in pt_synchronous_score"
        )
    if answer is None:
        return None
    (score, pt_start_time, pt_end_time, pt_duration, pt_distance, pt_indices) = answer

    # compute diameters
    # TODO why don't we have to do the same weirdness that we do in utils.diameters ? Because the pt_indices already has the property both tracks are unmasked at these indices.
    pt_diameter_1 = _diameter(qtrack1.qtrack[pt_indices], qtrack1.rescale)
    pt_diameter_2 = _diameter(qtrack2.qtrack[pt_indices], qtrack2.rescale)
    pt_common_diameter = _diameter(
        np.ma.concatenate([qtrack1.qtrack[pt_indices], qtrack2.qtrack[pt_indices]]),
        qtrack1.rescale,
    )

    if min_common_diameter and pt_common_diameter < min_common_diameter:
        return None

    pt_num_bins = len(pt_indices)
    pt_time_midpoints = [
        qtrack1.qstart_time + qtrack1.delta_t * (i + 0.5) for i in pt_indices
    ]
    return (
        score,
        pt_start_time,
        pt_end_time,
        pt_duration,
        pt_distance,
        pt_time_midpoints,
        pt_common_diameter,
        pt_diameter_1,
        pt_diameter_2,
        pt_num_bins,
    )


def pt_synchronous_score_given_time_window(
    qtrack1: QTrack,
    qtrack2: QTrack,
    time_window: float,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    max_dist: Optional[float] = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
    exit_early: bool = True,
) -> Union[
    None,
    Tuple[
        float,  # score
        datetime.datetime,  # start of first time bin
        datetime.datetime,  # end of last time bin
        float,  # total time
        float,  # total distance travelled averaged from two tracks
        List[int],  # indices of time bins
    ],
]:
    """
    Compute part-time synchronous score for a pair of QTracks and a minimum
    duration of a contiguous part-time window

    score is the average distance between the QTracks in a contiguous time
    window of duration >= time_window
    (Note the first and last time bins of this window must be unmasked.)

    Return (score, pt_start_time, pt_end_time, pt_duration, pt_distance_travelled, indices of time bins)
    when QTracks satisfy the criteria, else None

    If exit_early is set to True, it is recommended that this method be used
    when the QTracks are quantized with min_pings_per_timebin=0 (i.e.
    masked_at=0).

    :param qtrack1: input QTrack to be scored
    :param qtrack2: input QTrack to be scored
    :param time_window: input duration sought for part time synchronous co-travel
    :param min_common_qpings: require this many common qpings in the part-time window
    :param max_dist: a distance filter, returns None if score is greater than this.
    :param require_possible_overlap: a filter, returns None if calculation reveals not possible for two tracks to intersect.
    :param exit_early: stop search for min when duration exceeds twice time_window and something is found.
    """

    # (A) common qpings
    pt_num_bins = max(min_common_qpings, int(np.ceil(time_window / qtrack1.delta_t)))
    if num_common_qpings(qtrack1, qtrack2) < pt_num_bins:
        return None

    # (B) centroid
    if require_possible_overlap and not qtracks_overlap(qtrack1, qtrack2):
        return None

    # (C) Get vector of distances, TODO: allow haversine option
    D = vector_of_distances(qtrack1, qtrack2)
    E = 1 - D.mask  # 1 where there is a qping
    cumD = np.ma.cumsum(D)
    cumE = np.cumsum(E)  # Note E, cumE are not masked arrays.
    combined_bin_distances = (qtrack1.bin_distances + qtrack2.bin_distances) / 2
    best_mean = np.inf
    pt_start_time = None
    pt_start_bin_index = None
    pt_duration = None
    pt_num_qpings = None
    pt_indices = []
    for k in range(pt_num_bins - 1, len(D)):
        # looking at (k+1) consecutive time bins
        # if k < len(D):
        if exit_early and (k >= 2 * pt_num_bins) and (pt_start_time is not None):
            break
        else:
            tot_dists = cumD[k:] - cumD[:-k] + D[:-k]
            tot_qpings = cumE[k:] - cumE[:-k] + E[:-k]
            means = tot_dists / tot_qpings
            # Note tot_qpings is at least 2 where unmasked
            if min_common_qpings > 2:  # then we might need to mask more
                means.mask = np.logical_or(means.mask, tot_qpings < min_common_qpings)
            if np.ma.count(means) > 0:  # At least one viable candidate
                curr_argmin = np.ma.argmin(means)
                curr_min = means[curr_argmin]
                if curr_min < best_mean:
                    best_mean = curr_min
                    pt_start_time = qtrack1.qstart_time + curr_argmin * qtrack1.delta_t
                    pt_end_time = (
                        qtrack1.qstart_time + (curr_argmin + k + 1) * qtrack1.delta_t
                    )
                    pt_indices = [
                        i
                        for i in range(curr_argmin, curr_argmin + k + 1)
                        if not D.mask[i]
                    ]
                    pt_duration = len(pt_indices) * qtrack1.delta_t
                    pt_distance_travelled = np.sum(
                        combined_bin_distances[curr_argmin : curr_argmin + k + 1]
                    )
    if pt_start_time is None:
        return None
    if max_dist and best_mean > max_dist:
        return None
    return (
        best_mean,
        pt_start_time,
        pt_end_time,
        pt_duration,
        pt_distance_travelled,
        pt_indices,
    )


def pt_synchronous_score_given_distance_window(
    qtrack1: QTrack,
    qtrack2: QTrack,
    distance_window: float,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    max_dist: Optional[float] = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
    exit_early: bool = True,
) -> Union[
    None, Tuple[float, datetime.datetime, datetime.datetime, float, float, List[int],],
]:
    """
    Compute part-time synchronous score for a pair of QTracks and a minimum distance traveled in a part-time window

    Return (score, pt_start_time, pt_end_time, pt_duration, pt_distance, list of indices of time bins involved)
    when QTracks satisfy the criteria, else None

    score is the average distance between the QTracks in a contiguous window of
    travel >= distance_window

    If exit_early is set to True, it is recommended that this method be used
    when the QTracks are quantized with min_pings_per_timebin=0 (i.e.
    masked_at=0).

    :param qtrack1: input QTrack to be scored
    :param qtrack2: input QTrack to be scored
    :param distance_window: input distance sought for part time synchronous co-travel
    :param min_common_qpings: require this many common qpings in the part-time window
    :param max_dist: a distance filter, returns None if score is greater than this.
    :param require_possible_overlap: a filter, returns None if calculation reveals not possible for two tracks to intersect.
    :param exit_early: stop search for min when duration exceeds twice distance_window and something is found.
    """

    # (A) common qpings
    if min_common_qpings and num_common_qpings(qtrack1, qtrack2) < min_common_qpings:
        return None

    # (B) centroid
    if require_possible_overlap and not qtracks_overlap(qtrack1, qtrack2):
        return None

    # (C) Get vector of distances, TODO: allow haversine option
    D = vector_of_distances(qtrack1, qtrack2)
    E = 1 - D.mask  # 1 where there is a qping
    F = (qtrack1.bin_distances + qtrack2.bin_distances) / 2  # distance each bin
    cumD = np.ma.cumsum(D)
    cumE = np.cumsum(E)  # Note E, cumE are not masked arrays.
    cumF = np.ma.cumsum(F)  # Note E, cumE are not masked arrays.
    best_mean = np.inf
    pt_start_time = None
    pt_start_bin_index = None
    pt_duration = None
    pt_distance = None
    pt_indices = []
    for k in range(1, len(D)):
        # looking at (k+1) consecutive time bins
        tot_dists = cumD[k:] - cumD[:-k] + D[:-k]
        tot_qpings = cumE[k:] - cumE[:-k] + E[:-k]
        tot_travelled = cumF[k:] - cumF[:-k] + F[:-k]
        means = tot_dists / tot_qpings
        # Note tot_qpings is at least 2 where unmasked
        means.mask = np.logical_or(means.mask, tot_travelled < distance_window).filled(
            True
        )
        if min_common_qpings > 2:  # then we might need to mask more
            means.mask = np.logical_or(means.mask, tot_qpings < min_common_qpings)
        if np.ma.count(means) > 0:  # At least one viable candidate
            curr_argmin = np.ma.argmin(means)
            curr_min = means[curr_argmin]
            if curr_min < best_mean:
                best_mean = curr_min
                pt_start_time = qtrack1.qstart_time + curr_argmin * qtrack1.delta_t
                pt_end_time = (
                    qtrack1.qstart_time + (curr_argmin + k + 1) * qtrack1.delta_t
                )
                pt_indices = [
                    i for i in range(curr_argmin, curr_argmin + k + 1) if not D.mask[i]
                ]
                pt_duration = len(pt_indices) * qtrack1.delta_t
                pt_distance_travelled = tot_travelled[curr_argmin]
        if (
            exit_early
            and (pt_start_time is not None)
            and (np.min(tot_travelled) > 2 * distance_window)
        ):
            break
    if pt_start_time is None:
        return None
    if max_dist and best_mean > max_dist:
        return None
    return (
        best_mean,
        pt_start_time,
        pt_end_time,
        pt_duration,
        pt_distance_travelled,
        pt_indices,
    )


def pt_synchronous_score_noncontiguous_total_time(
    qtrack1: QTrack,
    qtrack2: QTrack,
    total_time: float,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    max_dist: Optional[float] = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
) -> Union[
    None, Tuple[float, datetime.datetime, datetime.datetime, float, float, List[int],],
]:
    """
    Compute part-time synchronous score for a pair of QTracks and a total time duration of a collection of non-overlapping noncontiguous time windows

    Return (score, pt_start_time, pt_end_time, pt_duration, pt_distance, list of indices of time bins involved)
    or returns None if conditions not satisfied.

    score is the average distance between the QTracks in the optimum overlap.

    :param qtrack1: input QTrack to be scored
    :param qtrack2: input QTrack to be scored
    :param total_time: input total noncontiguous time sought for part time synchronous co-travel
    :param min_common_qpings: require this many common qpings in the part-time window
    :param max_dist: a distance filter, returns None if score is greater than this.
    :param require_possible_overlap: a filter, returns None if calculation reveals not possible for two tracks to intersect.
    """

    # (A) common qpings
    pt_num_bins = max(min_common_qpings, int(np.ceil(total_time / qtrack1.delta_t)))
    if num_common_qpings(qtrack1, qtrack2) < pt_num_bins:
        return None

    # (B) centroid
    if require_possible_overlap and not qtracks_overlap(qtrack1, qtrack2):
        return None

    # (C) Get vector of distances, TODO: allow haversine option
    D = vector_of_distances(qtrack1, qtrack2)
    sorted_indices = np.argsort(D)
    answer_indices = sorted_indices[:pt_num_bins]
    Dsorted = D[answer_indices]
    F = (qtrack1.bin_distances + qtrack2.bin_distances) / 2  # distance each bin
    pt_distance_travelled = np.sum(F[answer_indices])
    best_mean = np.mean(Dsorted)
    pt_duration = pt_num_bins * qtrack1.delta_t
    if max_dist and best_mean > max_dist:
        return None
    answer_indices.sort()
    pt_indices = list(answer_indices)
    pt_start_time = qtrack1.qstart_time + pt_indices[0] * qtrack1.delta_t
    pt_end_time = qtrack1.qstart_time + (pt_indices[-1] + 1) * qtrack1.delta_t
    return (
        best_mean,
        pt_start_time,
        pt_end_time,
        pt_duration,
        pt_distance_travelled,
        pt_indices,
    )


def pt_synchronous_score_noncontiguous_total_distance(
    qtrack1: QTrack,
    qtrack2: QTrack,
    total_distance: float,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    max_dist: Optional[float] = MAX_DIST,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
) -> Union[
    None, Tuple[float, datetime.datetime, datetime.datetime, float, float, List[int],],
]:
    """
    Compute part-time synchronous score for a pair of QTracks and a minimum total distance traveled in collection of non-overlapping part-time windows


    Return (score, pt_start_time, pt_end_time, pt_duration, pt_distance, list of indices of time bins involved)
    or returns None if conditions not satisfied.

    score is the average distance between the QTracks in the optimum overlap.

    :param qtrack1: input QTrack to be scored
    :param qtrack2: input QTrack to be scored
    :param total_distance: total noncontiguous distance sought for part time synchronous co-travel
    :param min_common_qpings: require this many common qpings in the part-time window
    :param max_dist: a distance filter, returns None if score is greater than this.
    :param require_possible_overlap: a filter, returns None if calculation reveals not possible for two tracks to intersect.
    """

    # (A) common qpings
    if min_common_qpings and num_common_qpings(qtrack1, qtrack2) < min_common_qpings:
        return None

    # (B) centroid
    if require_possible_overlap and not qtracks_overlap(qtrack1, qtrack2):
        return None

    # (C) Get vector of distances, TODO: allow haversine option
    D = vector_of_distances(qtrack1, qtrack2)
    sorted_indices = np.argsort(D)
    Dsorted = D[sorted_indices]
    F = (qtrack1.bin_distances + qtrack2.bin_distances) / 2  # distance each bin
    Fsorted = F[sorted_indices]
    FF = np.ma.cumsum(Fsorted)
    # Find top index so that total distance and min_common_qpings are satisfied.
    best_mean = None
    for i in range(D.count()):  # Use first i+1 smallest distances
        if min_common_qpings and (i + 1 < min_common_qpings):
            pass
        else:
            if FF[i] >= total_distance:
                answer_indices = sorted_indices[: i + 1]
                best_mean = np.mean(Dsorted[: i + 1])
                pt_distance_travelled = FF[i]
                pt_num_qpings = i + 1
                pt_duration = pt_num_qpings * qtrack1.delta_t
                break
    if best_mean is None:
        return None
    if max_dist and best_mean > max_dist:
        return None
    answer_indices.sort()
    pt_indices = list(answer_indices)
    pt_start_time = qtrack1.qstart_time + pt_indices[0] * qtrack1.delta_t
    pt_end_time = qtrack1.qstart_time + (pt_indices[-1] + 1) * qtrack1.delta_t
    return (
        best_mean,
        pt_start_time,
        pt_end_time,
        pt_duration,
        pt_distance_travelled,
        pt_indices,
    )


def pt_synchronous_score_given_within_distance(
    qtrack1: QTrack,
    qtrack2: QTrack,
    within_distance: float,
    min_common_qpings: int = MIN_COMMON_QPINGS,
    require_possible_overlap: bool = REQUIRE_POSSIBLE_OVERLAP,
) -> Union[
    None, Tuple[float, datetime.datetime, datetime.datetime, float, float, List[int],],
]:
    """
    Compute part-time synchronous score for a pair of QTracks where the
    tracks are considered close when they are within a given distance of one
    another in a time bin

    Return (score, pt_start_time, pt_end_time, pt_duration, pt_distance, list of indices of time bins involved)
    or returns None if conditions not satisfied.

    score is the number of time bins where the pair are within the distance threshold.

    :param qtrack1: input QTrack to be scored
    :param qtrack2: input QTrack to be scored
    :param within_distance: distance threshold that is used to count the number of bins where the pair are within the threshold.
    :param min_common_qpings: require this many common qpings in the part-time window
    :param require_possible_overlap: a filter, returns None if calculation reveals not possible for two tracks to intersect.
    """

    # (A) common qpings
    if min_common_qpings and num_common_qpings(qtrack1, qtrack2) < min_common_qpings:
        return None

    # (B) centroid
    if require_possible_overlap and not qtracks_overlap(qtrack1, qtrack2):
        return None

    # (C) Get vector of distances, TODO: allow haversine option
    D = vector_of_distances(qtrack1, qtrack2)
    pt_indices = np.nonzero(D <= within_distance)[0]
    score = len(pt_indices)
    if score == 0:
        return None  # Should we return None when the score is 0?
    pt_duration = score * qtrack1.delta_t
    F = (
        qtrack1.bin_distances + qtrack2.bin_distances
    ) / 2  # distance travelled each bin, averaged from the two tracks
    pt_distance = np.sum(F[pt_indices])
    pt_indices = list(pt_indices)
    pt_start_time = qtrack1.qstart_time + (pt_indices[0]) * qtrack1.delta_t
    pt_end_time = qtrack1.qstart_time + (pt_indices[-1] + 1) * qtrack1.delta_t

    return (
        score,
        pt_start_time,
        pt_end_time,
        pt_duration,
        pt_distance,
        pt_indices,
    )
