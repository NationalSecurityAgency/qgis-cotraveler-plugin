#!/usr/bin/env python3

# THIS FILE IS NOT USED ANYMORE, DELETE??

import datetime
import os
import warnings
from typing import Optional

import dateutil.parser

#import dill as pickle
import pickle
#from logzero import logger

from ._types import Columns, Track
from .config import (DEFAULT_COLUMNS, DELTA_T, MAX_CEP, MAX_VELOCITY,
                     MIN_DIAMETER, MIN_PINGS, MIN_QPINGS)
from .load_tracks import load_tracks_or_qtracks, tracks_from_csv_files
from .quantize import quantize_tracks
from .utils import configure_logging, daterange_str, to_timestamp

warnings.simplefilter("ignore", RuntimeWarning)
CHUNKSIZE = 1_000_000


def make_tracks(
    *files: str,
    columns: Columns = DEFAULT_COLUMNS,
    parse_times: bool = True,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    units: Optional[str] = None,
    cep_units: Optional[str] = None,
    outfile: Optional[str] = None,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    min_pings: int = MIN_PINGS,
    loglevel: int = 20,
    logfile: Optional[str] = None,
    quiet: bool = False,
):
    """
    Build Tracks from csvs and save as pickle file
    """
    configure_logging(loglevel=loglevel, logfile=logfile, quiet=quiet)

    if outfile is None:
        raise TypeError("outfile is a required argument")
    if os.path.isfile(outfile):
        logger.warning(f"Will overwrite {outfile}")
    else:
        logger.info(f"Will save Tracks to {outfile}")

    tracks = tracks_from_csv_files(
        *files,
        columns=columns,
        parse_times=parse_times,
        start_time=start_time,
        end_time=end_time,
        ids=None,
        units=units,
        max_cep=max_cep,
        max_velocity=max_velocity,
        min_pings=min_pings,
    )

    if tracks:
        logger.info(f"Writing {len(tracks)} Tracks to {outfile}")
        pickle.dump(tracks, open(outfile, "wb"))
    else:
        logger.warning(f"No tracks to output")


def make_tracks_daily(
    *files: str,
    start_date: str,
    end_date: Optional[str] = None,
    date_fmt: str = "%Y-%m-%d",
    outdir: str = "tracks",
    tracks_prefix: str = "tracks",
    columns: Columns = DEFAULT_COLUMNS,
    units: Optional[str] = None,
    cep_units: Optional[str] = None,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    min_pings: int = MIN_PINGS,
    loglevel: int = 20,
    logfile: Optional[str] = None,
    quiet: bool = False,
):
    """
    Build daily Tracks from csv files containing pings and save to disk as pickle files
    """
    if not os.path.isdir(outdir):
        logger.info(f"Creating directory {outdir}")
        os.makedirs(outdir)

    configure_logging(loglevel=loglevel, logfile=logfile, quiet=quiet, outdir=outdir)

    dates = daterange_str(start_date, end_date, fmt=date_fmt)
    logger.debug(f"Making Tracks for {len(dates)} days")

    for i, date in enumerate(dates):
        logger.info("-" * 30)
        logger.info(f"Day {date} ({i+1} of {len(dates)})")

        date_files = [f for f in files if f.find(date) >= 0]
        if not date_files:
            logger.warning(f"No input files found for {date}")
            continue
        start_time = dateutil.parser.parse(date)
        end_time = start_time + datetime.timedelta(days=1)
        tracks_file = os.path.join(outdir, f"{tracks_prefix}_{date}.pkl")
        if os.path.isfile(tracks_file):
            logger.warning(f"Overwriting {tracks_file}")

        make_tracks(
            *date_files,
            columns=columns,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            units=units,
            cep_units=cep_units,
            outfile=tracks_file,
            max_cep=max_cep,
            max_velocity=max_velocity,
            min_pings=min_pings,
            loglevel=loglevel,
            logfile=logfile,
            quiet=quiet,
        )


def make_qtracks(
    *files: str,
    columns: Columns = DEFAULT_COLUMNS,
    parse_times: bool = True,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    delta_t: float = DELTA_T,
    units: Optional[str] = None,
    cep_units: Optional[str] = None,
    save_tracks: bool = False,
    outfile: Optional[str] = None,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    min_pings: int = MIN_PINGS,
    min_qpings: int = MIN_QPINGS,
    min_diameter: float = MIN_DIAMETER,
    loglevel: int = 20,
    logfile: Optional[str] = None,
    quiet: bool = False,
    chunksize: int = CHUNKSIZE,
    jobs: Optional[int] = None,
):
    """
    Build QTracks from csv files containing pings and save to disk as pickle file
    """
    configure_logging(loglevel=loglevel, logfile=logfile, quiet=quiet)

    if outfile is None:
        raise TypeError(f"outfile is a required argument")
    elif os.path.isfile(outfile):
        logger.warning(f"Will overwrite {outfile}")
    else:
        logger.info(f"Will save QTracks to {outfile}")

    tracks = load_tracks_or_qtracks(
        files,
        columns=columns,
        parse_times=parse_times,
        start_time=start_time,
        end_time=end_time,
        ids=None,
        units=units,
        cep_units=cep_units,
        max_cep=max_cep,
        max_velocity=max_velocity,
        min_pings=min_pings,
    )
    _type = type(tracks[0])
    if _type is not Track:
        raise SystemExit(f"No Track objects found ")

    logger.info(f"Found {len(tracks)} {_type}s in {len(files)} files")

    if save_tracks:
        # TODO: this is messy
        outdir, qtracks_filename = os.path.split(outfile)
        tracks_filename = qtracks_filename.replace("qtracks", "tracks")
        tracks_file = os.path.join(outdir, tracks_filename)
        logger.info(f"Saving {len(tracks)} Tracks to {tracks_file}")
        if os.path.isfile(tracks_file):
            logger.warning(f"Overwriting {tracks_file}")
        pickle.dump(tracks, open(tracks_file, "wb"))

    qstart_time = (
        to_timestamp(start_time) if start_time else min(t.start_time for t in tracks)
    )
    qend_time = to_timestamp(end_time) if end_time else max(t.end_time for t in tracks)
    qtracks = quantize_tracks(
        tracks,
        qstart_time,
        qend_time,
        delta_t=delta_t,
        min_qpings=min_qpings,
        min_diameter=min_diameter,
        chunksize=chunksize,
        jobs=jobs,
    )

    if qtracks:
        logger.info(f"Saving {len(qtracks)} QTracks to {outfile}")
        pickle.dump(qtracks, open(outfile, "wb"))
    else:
        raise SystemExit(f"No QTracks to output")


def make_qtracks_daily(
    *files,
    start_date: str,
    end_date: Optional[str] = None,
    date_fmt: str = "%Y-%m-%d",
    outdir: str = "qtracks",
    qtracks_prefix: str = "qtracks",
    columns: Columns = DEFAULT_COLUMNS,
    delta_t: float = DELTA_T,
    units: Optional[str] = None,
    cep_units: Optional[str] = None,
    save_tracks: bool = False,
    max_cep: float = MAX_CEP,
    max_velocity: float = MAX_VELOCITY,
    min_pings: int = MIN_PINGS,
    min_qpings: int = MIN_QPINGS,
    min_diameter: float = MIN_DIAMETER,
    loglevel: int = 20,
    logfile: Optional[str] = None,
    quiet: bool = False,
    chunksize: int = CHUNKSIZE,
    jobs: Optional[int] = None,
):
    """
    Quantize daily Tracks and save to disk as pickle files
    """
    if not os.path.isdir(outdir):
        logger.info(f"Creating directory {outdir}")
        os.makedirs(outdir)

    configure_logging(loglevel=loglevel, logfile=logfile, quiet=quiet, outdir=outdir)

    dates = daterange_str(start_date, end_date, fmt=date_fmt)
    logger.debug(f"Making Tracks for {len(dates)} days")

    for i, date in enumerate(dates):
        logger.info("-" * 30)
        logger.info(f"Day {date} ({i+1} of {len(dates)})")
        qtracks_file = f"{qtracks_prefix}_{date}.pkl"

        if save_tracks:
            tracks_file = qtracks_file.replace("qtracks", "tracks")
            tracks_file = os.path.join(outdir, tracks_file)
            logger.info(f"Will save Tracks to {tracks_file}")

        qtracks_file = os.path.join(outdir, qtracks_file)

        date_files = [f for f in files if f.find(date) >= 0]
        if not date_files:
            logger.warning(f"No input files found for {date}")
            continue

        start_time = dateutil.parser.parse(date)
        end_time = start_time + datetime.timedelta(days=1)

        make_qtracks(
            *date_files,
            columns=columns,
            start_time=start_time,
            end_time=end_time,
            delta_t=delta_t,
            units=units,
            cep_units=cep_units,
            save_tracks=save_tracks,
            outfile=qtracks_file,
            max_cep=max_cep,
            max_velocity=max_velocity,
            min_pings=min_pings,
            min_qpings=min_qpings,
            min_diameter=min_diameter,
            loglevel=loglevel,
            logfile=logfile,
            quiet=quiet,
            chunksize=chunksize,
            jobs=jobs,
        )
