#!/usr/bin/env python3
# type: ignore[attr-defined]

"""
TODO module documentation

Module that contains the command line app.

Why does this file exist, and why not put this in __main__?
  You might be tempted to import things from __main__ later, but that will cause
  problems: the code will get executed twice:
  - When you run `python -m cotravel` python will execute
    ``__main__.py`` as a script. That means there won't be any
    ``cotravel.__main__`` in ``sys.modules``.
  - When you import __main__ it will get executed again (as a module) because
    there's no ``cotravel.__main__`` in ``sys.modules``.
  Also see (1) from http://click.pocoo.org/5/setuptools/#setuptools-integration
"""

# TODO make this actually do useful things

import argparse
import datetime
import logging
import random
from enum import Enum
from typing import List, Optional, Tuple, Union

from cotravel import __version__
from cotravel.synchronous import synchronous
from cotravel.utils import configure_logging

from .config import (ADD_EXTRAPOLATED_PINGS, DEFAULT_COLUMNS, DELTA_T,
                     FIELDS_PAIRS, MAX_CEP, MAX_DIST, MAX_VELOCITY,
                     MIN_COMMON_DIAMETER, MIN_COMMON_QPINGS, MIN_DIAMETER,
                     MIN_PINGS, MIN_PINGS_PER_TIMEBIN, MIN_QPINGS,
                     MIN_TIMEBIN_FRACTION, REQUIRE_POSSIBLE_OVERLAP,
                     IMPORT_SUCCESS_logzero, IMPORT_SUCCESS_tabulate)

if IMPORT_SUCCESS_logzero:
    import logzero
    from logzero import logger
else:
    import logging as logger
if IMPORT_SUCCESS_tabulate:
    from tabulate import tabulate


CHUNKSIZE = 1_000_000


def sync(
    files1: List[str],
    files2: Optional[List[str]] = (),
    columns1: List[str] = DEFAULT_COLUMNS,
    columns2: List[str] = DEFAULT_COLUMNS,
    ids1: Tuple[str] = (),
    ids2: Tuple[str] = (),
    units1: Optional[str] = None,
    units2: Optional[str] = None,
    cep_units1: Optional[str] = None,
    cep_units2: Optional[str] = None,
    parse_times: bool = True,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
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
) -> None:
    # TODO docstring
    comparisons = synchronous(
        files1=files1,
        files2=files2,
        columns1=columns1,
        columns2=columns2,
        ids1=ids1,
        ids2=ids2,
        units1=units1,
        units2=units2,
        cep_units1=cep_units1,
        cep_units2=cep_units2,
        parse_times=parse_times,
        start_time=start_time,
        end_time=end_time,
        scores_file=scores_file,
        replace_scores_file=replace_scores_file,
        tracks1_file=tracks1_file,
        tracks2_file=tracks2_file,
        qtracks1_file=qtracks1_file,
        qtracks2_file=qtracks2_file,
        max_cep=max_cep,
        max_velocity=max_velocity,
        delta_t=delta_t,
        max_dist=max_dist,
        min_pings=min_pings,
        min_timebin_fraction=min_timebin_fraction,
        add_extrapolated_pings=add_extrapolated_pings,
        min_pings_per_timebin=min_pings_per_timebin,
        min_qpings=min_qpings,
        min_common_qpings=min_common_qpings,
        require_possible_overlap=require_possible_overlap,
        min_diameter=min_diameter,
        min_common_diameter=min_common_diameter,
        time_window=time_window,
        distance_window=distance_window,
        total_time=total_time,
        within_distance=within_distance,
        exit_early=exit_early,
        bounding_polygon=bounding_polygon,
        excluded_polygons=excluded_polygons,
        chunksize=chunksize,
        jobs=jobs,
    )
    # pretty print the dataframe returned by synchronous
    if IMPORT_SUCCESS_tabulate:
        print(f"\n{tabulate(comparisons, headers=comparisons.columns, showindex=False)}")


def parse_args(args: List[str] = None):
    # common "parent" log parser shared by subcommands
    log_parser = argparse.ArgumentParser(add_help=False)
    log_parser.add_argument(
        "--log-level",
        type=int,
        default=logging.INFO,
        choices=[
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ],
        help="set logging level (10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL)",
    )
    log_parser.add_argument(
        "--log-file", type=Optional[str], help="save logs here",
    )
    log_parser.add_argument(
        "--quiet", type=Optional[bool], default=False, help="Alias for --log-level=50",
    )

    # parent parser for reading tracks from disk
    load_tracks_parser = argparse.ArgumentParser(add_help=False)
    load_tracks_parser.add_argument(
        "--files1",
        required=True,
        metavar="FILE",
        nargs="+",
        help="/path/to/files1 or list of /paths/to/files1. Either csvs containing Pings, or pickle files containing QTracks or Tracks",
    )
    load_tracks_parser.add_argument(
        "--files2",
        # type=Optional[Union[str, List[str]]],
        metavar="FILE",
        default=(),
        nargs="*",
        help="Optional /path/to/files2 or list of /paths/to/files2. Either csvs containing Pings, or pickle files containing QTracks or Tracks",
    )
    load_tracks_parser.add_argument(
        "--columns1",
        # type=str,
        default=DEFAULT_COLUMNS,
        nargs="*",
        help="Column names for files1 corresponding to ID TIMESTAMP LON LAT [CEP] (ignored if files1 contains QTracks/Tracks)",
    )
    load_tracks_parser.add_argument(
        "--columns2",
        # type=str,
        default=DEFAULT_COLUMNS,
        nargs="*",
        help="Column names for files2 corresponding to ID TIMESTAMP LON LAT [CEP] (ignored if files2 contains QTracks/Tracks)",
    )
    load_tracks_parser.add_argument(
        "--ids1",
        default=(),
        nargs="*",
        help="List of IDs for files1 (ignore tracks with IDs not in this list)",
    )
    load_tracks_parser.add_argument(
        "--ids2",
        default=(),
        nargs="*",
        help="List of IDs for files2 (ignore tracks with IDs not in this list)",
    )
    load_tracks_parser.add_argument(
        "--units1",
        default=None,
        help="Units for LON/LAT in files1 (by default will try to infer from column names)",
    )
    load_tracks_parser.add_argument(
        "--units2",
        default=None,
        help="Units for LON/LAT in files2 (by default will try to infer from column names)",
    )
    load_tracks_parser.add_argument(
        "--cep-units1",
        default=None,
        help="Units for CEP in files1 (by default will try to infer from column names)",
    )
    load_tracks_parser.add_argument(
        "--cep-units2",
        default=None,
        help="Units for CEP in files2 (by default will try to infer from column names)",
    )
    load_tracks_parser.add_argument(
        "--no-parse-times",
        action="store_false",
        dest="parse_times",
        help="Don't attempt to parse timestamps as datetimes (ie if timestamps are specified as epoch)",
    )
    load_tracks_parser.add_argument(
        "--start-time",
        type=datetime.datetime,
        default=None,
        help="Start time for global quantization window. Ignore pings before this. This option has no effect if passed QTracks/Tracks instead if pings)",
    )
    load_tracks_parser.add_argument(
        "--end-time",
        type=datetime.datetime,
        default=None,
        help="End time for global quantization window. Ignore pings after this. This option has no effect if passed QTracks/Tracks instead if pings)",
    )
    load_tracks_parser.add_argument(
        "--max-cep",
        type=float,
        default=MAX_CEP,
        help="Ignore pings with CEP above this value (in meters)",
    )
    load_tracks_parser.add_argument(
        "--max-velocity",
        type=float,
        default=MAX_VELOCITY,
        help="Ignore pings faster than this (in meters/second)",
    )

    #  parent parser to handle Track filtering options
    track_filter_parser = argparse.ArgumentParser(add_help=False)
    track_filter_parser.add_argument(
        "--min-pings",
        type=int,
        default=MIN_PINGS,
        help="Ignore Tracks with fewer than this many pings",
    )
    track_filter_parser.add_argument(
        "--min-diameter",
        type=float,
        default=MIN_DIAMETER,
        help="Ignore QTracks with (approximate) diameter smaller than this (in meters) Note this refers to the diameter of the whole track, even for part-time scoring options",
    )
    track_filter_parser.add_argument(
        "--bounding-polygon",
        type=lambda pt: [float(p) for p in pt.split(",")],
        nargs="*",
        default=None,
        help="Ignore pings outside this polygon. Specified as a list of vertices (each a ','-separated pair of floats). eg --bounding-polygon 0,0 0,1 1,1 1,0",
    )
    track_filter_parser.add_argument(
        "--excluded-polygon",
        type=lambda pt: [float(p) for p in pt.split(",")],
        nargs="*",
        action="append",
        default=None,
        help="Ignore pings falling within this polygon. Specified as a list of vertices (each a ','-separated pair of floats). Multiple such polygons can be specified by employing this argument more than once",
    )

    # quantization options
    quantization_parser = argparse.ArgumentParser(add_help=False)
    quantization_parser.add_argument(
        "--delta-t",
        type=int,
        default=DELTA_T,
        help="Duration of timebins for quantization (in seconds)",
    )
    quantization_parser.add_argument(
        "--min-timebin-fraction",
        type=float,
        default=MIN_TIMEBIN_FRACTION,
        help="For the first and last qping, this is the required fraction of the time occupied by input Track to have a nonmasked qping",
    )
    quantization_parser.add_argument(
        "--add-extrapolated-pings",
        action="store_true",
        help="For the first and last qping, whether or not to extrapolate track to the edges of the time bin in the event the input Track doesn't fill up time bin",
    )
    quantization_parser.add_argument(
        "--min-pings-per-timebin",
        type=int,
        default=MIN_PINGS_PER_TIMEBIN,
        help="minimum number of original pings in timebin for qping to be unmasked. That is, ignore qpings with fewer than this many original pings in the timebin",
    )
    quantization_parser.add_argument(
        "--min-qpings",
        type=int,
        default=MIN_QPINGS,
        help="Ignore QTracks with fewer than this many quantized pings",
    )

    # main parser
    parser = argparse.ArgumentParser(
        prog="cotravel",
        description="Detect full-time or part-time synchronous or asynchronous co-travelers",
        add_help=True,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(title="valid subcommands", dest="subcommand",)
    # add a subparser for the sync command, along with the parent parsers
    sync_parser = subparsers.add_parser(
        "sync",
        help="Detect full-time or part-time synchronous co-travelers",
        description="Detect full-time or part-time synchronous co-travelers",
        parents=[
            log_parser,
            load_tracks_parser,
            track_filter_parser,
            quantization_parser,
        ],
    )
    sync_parser.add_argument(
        "--scores-file",
        default=None,
        help=f"/path/to/file/to/save/scores (as csv with colums {FIELDS_PAIRS}",
    )
    sync_parser.add_argument(
        "--replace-scores-file",
        action="store_true",
        help="Overwrite scores_file (if it exists)",
    )
    sync_parser.add_argument(
        "--tracks1-file",
        default=None,
        help="Save Tracks built from files1 to disk at this path",
    )
    sync_parser.add_argument(
        "--tracks2-file",
        default=None,
        help="Save Tracks built from files2 to disk at this path",
    )
    sync_parser.add_argument(
        "--qtracks1-file",
        default=None,
        help="Save QTracks built from files1 to disk at this path",
    )
    sync_parser.add_argument(
        "--qtracks2-file",
        default=None,
        help="Save QTracks built from files2 to disk at this path",
    )
    sync_parser.add_argument(
        "--max-dist",
        type=float,
        default=MAX_DIST,
        # TODO this is wrong for within_distance scoring
        help="Only return scores <= this (in meters)",
    )
    sync_parser.add_argument(
        "--min-common-qpings",
        type=int,
        default=MIN_COMMON_QPINGS,
        help="Ignore QTrack pairs with fewer than this many quantized pings in their temporal overlap",
    )
    sync_parser.add_argument(
        "--require-possible-overlap",
        action="store_true",
        help="whether to ignore pairs that could not have overlapped",
    )
    sync_parser.add_argument(
        "--min-common-diameter",
        type=float,
        default=MIN_COMMON_DIAMETER,
        help="Ignore QTrack pairs with (approximate) diameter of their temporal overlap smaller than this (in meters)",
    )
    sync_parser.add_argument(
        "--time-window",
        type=float,
        default=None,
        help="minimum duration (in seconds) sought for part time synchronous co-travel",
    )
    sync_parser.add_argument(
        "--distance-window",
        type=float,
        default=None,
        help="minimum distance (in meters) sought for part time synchronous co-travel",
    )
    sync_parser.add_argument(
        "--total-time",
        type=float,
        default=None,
        help="total noncontiguous time (in seconds) sought for part time synchronous co-travel",
    )
    sync_parser.add_argument(
        "--total-distance",
        type=float,
        default=None,
        help="total noncontiguous distance sought for part time synchronous co-travel",
    )
    sync_parser.add_argument(
        "--within-distance",
        type=float,
        default=None,
        help="distance threshold that is used to count the number of bins where the pair are within the threshold.",
    )
    sync_parser.add_argument(
        "--no-exit-early",
        action="store_false",
        dest="exit_early",
        help="For the noncontiguous part-time synchronous methods, return when all possible intervals of twice the given window size are considered and a viable answer is found",
    )
    sync_parser.add_argument(
        "--chunksize",
        type=int,
        default=CHUNKSIZE,
        help="size of chunks used in pool.imap",
    )
    sync_parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="Number of cores to use (defaults to all available",
    )

    # add a subparser for the async command
    # TODO finish this subparser once we write aynchronous.py
    async_parser = subparsers.add_parser(
        "async",
        help="Detect full-time or part-time asynchronous co-travelers",
        description="Detect full-time or part-time asynchronous co-travelers",
        parents=[
            log_parser,
            load_tracks_parser,
            track_filter_parser,
            quantization_parser,
        ],
    )

    if args is None:
        return parser.parse_args()
    else:
        return parser.parse_args(args)


def app():
    args = parse_args()
    configure_logging(loglevel=args.log_level, logfile=args.log_file, quiet=args.quiet)

    # dispatch
    d = vars(args)
    if args.subcommand == "sync":
        # call sync by unpacking the attributes of the args Namespace needed by sync
        sync_args = {k: d[k] for k in d if k in sync.__code__.co_varnames}
        return sync(**sync_args)
    elif args.subcommand == "async":
        raise NotImplementedError
        # call async by unpacking the attributes of the args Namespace needed by sync
        # async_args = {k: d[k] for k in d if k in async.__code__.co_varnames}
        # return async(**async_args)


if __name__ == "__main__":
    app()
