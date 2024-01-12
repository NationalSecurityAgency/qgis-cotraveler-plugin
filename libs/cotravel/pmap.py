#!/usr/bin/env python3

"""
TODO module documentation
"""
import datetime
import multiprocessing as mp

# import dill as pickle
import pickle
import queue
from itertools import repeat, tee
from typing import Any, Callable, Iterable, Optional, Tuple

from ._types import QTrack
from .config import (
    MAX_CHUNKSIZE,
    IMPORT_SUCCESS_enlighten,
    IMPORT_SUCCESS_logzero,
    IMPORT_SUCCESS_psutil,
)
from .utils import iterlen

if IMPORT_SUCCESS_enlighten:
    import enlighten
# import psutil
if IMPORT_SUCCESS_psutil:
    import psutil
if IMPORT_SUCCESS_logzero:
    from logzero import logger
else:
    import logging as logger


def _fun0(args):
    """
    # TODO ugh, kill me

    if args = (f, x), this is equivalent to f(*x), so
    map(_fun0, (repeat(f), xs)) is equivalent to (f(*x) for x in xs)

    only needed because multiprocessing is the worst
    """
    return args[0](*list(args[1]))


def populate(qin: mp.Queue, it1: Iterable[QTrack], jobs: int) -> None:
    """
    callback for background process to populate qin with elements from it1
    """
    # logger.info(f"{mp.current_process().name} in populate {len(it1)}")
    for i, qtrack in enumerate(it1):
        qin.put((i, qtrack))
        # logger.info(f"{mp.current_process().name} put {(i, qtrack)}")
    # put one sentinel per worker so they all know to stop
    for _ in range(jobs):
        qin.put((None, "QIN_DONE"))
    # logger.info(f"{mp.current_process().name} put {jobs} sentinels")


def calculate(
    f: Callable,
    qin: mp.Queue,
    qout: mp.Queue,
    it1: Iterable[QTrack], # should be either [] or identical to qin
    it2: Iterable[QTrack], # compare all of these to qin
    # qgis_obj: Optional[QgsProcessingFeedBack] = None,
    qgis_obj: Optional[object] = None,
) -> None:
    """
    callback for procs to get qtracks from qin and put computed results
    on qout
    """
    while True:
        i, qt1 = qin.get()
        # logger.info(f"{mp.current_process().name} got {(i, qt1)}")

        # break if we see a sentinel
        if (i, qt1) == (None, "QIN_DONE"):
            qout.put((None, "QOUT_DONE"))
            break

        # compute and put results on qout
        #if it2:
        for qt2 in it2:
            if qgis_obj is not None:
                if qgis_obj.isCanceled():
                    return
            fout = f(qt1, qt2)
            if fout is not None:
                out = (fout, (qt1, qt2))
                qout.put(out)
        #else:
        for j, qt2 in enumerate(it1):
            if j <= i:
                continue
            if qgis_obj is not None:
                if qgis_obj.isCanceled():
                    return
            qtA, qtB = sorted([qt1, qt2], key=lambda qt: qt.ID)
            fout = f(qtA, qtB)
            if fout is not None:
                out = (fout, (qtA, qtB))
                qout.put(out)


def filtermap_pairs(
    f: Callable,
    it1: Iterable[QTrack],
    it2: Optional[Iterable[QTrack]] = None,
    ids: Tuple[str] = (),
    jobs: int = None,
    verbose: bool = False,
    # qgis_obj: Optional[QgsProcessingFeedBack] = None,
    qgis_obj: Optional[object] = None,
) -> Iterable[Tuple[Any, Tuple[QTrack, QTrack]]]:
    """
    The following description is outdated.
    Parallel version of the generator

        ( (f(a,b), (a,b)) for a,b in product(it1, it2)
            if f(a,b) is not None )

    If it2 = None, replace product(it1, it2) with combinations(it1, 2)
    ie don't compute f(a,a), and only compute one of f(a,b) and not f(b,a)
    New description:
    Create seeds, it2seeds, it2rest appropriately so that
    either it2seeds is seeds or nothing.
    We compare seeds to it2seeds only for "a<b" and we compare seeds to all of it2rest.
    # TODO document arguments
    :param ids: filter qtracks1 down to seed tracks with these ids
    """
    # TODO make this consume Iterables of arbitrary objects and not just QTracks?

    # TODO doesn't parallelize as well if len(it1) << len(it2)
    s = datetime.datetime.now()

    # global populate
    # global calculate
    # TODO can we avoid materializing it1 and it2 as lists?
    it1 = list(it1)
    if ids:
        seeds = [_ for _ in it1 if _.ID in ids]
        if it2:
            it2seeds = []
            it2rest = list(it2)
        else:
            it2seeds = seeds
            it2rest = [_ for _ in it1 if _.ID not in ids]
    else:
        seeds = list(it1)
        if it2:
            it2seeds = []
            it2rest = list(it2)
        else:
            it2seeds = seeds
            it2rest = []
    n = len(it2seeds)
    total = (n * (n - 1) // 2) + len(seeds)*len(it2rest)

    if jobs == 1:
        ctr_start = total//100
        ctr = ctr_start
        n_rec = 0
        n_done = 0
        if qgis_obj is not None:
            qgis_obj.setProgress(0)
        for i, qt1 in enumerate(seeds):
            for qt2 in it2rest:
                if qgis_obj is not None:
                    ctr = ctr - 1
                    if ctr <= 0:
                        ctr = ctr_start
                        qgis_obj.setProgress(100 * n_done / total)
                    if qgis_obj.isCanceled():
                        qgis_obj.pushInfo(
                            "WARNING: Scoring step halted with partial progress"
                        )
                        return
                qtA, qtB = sorted([qt1, qt2], key=lambda qt: qt.ID)
                fout = f(qtA, qtB)
                n_done += 1
                if fout is not None:
                    n_rec += 1
                    yield (fout, (qt1, qt2))
            for j, qt2 in enumerate(it2seeds):
                if j <= i:
                    continue
                if qgis_obj is not None:
                    ctr = ctr - 1
                    if ctr <= 0:
                        ctr = ctr_start
                        qgis_obj.setProgress(100 * n_done / total)
                    if qgis_obj.isCanceled():
                        qgis_obj.pushInfo(
                            "WARNING: Scoring step halted with partial progress"
                        )
                        return
                qtA, qtB = sorted([qt1, qt2], key=lambda qt: qt.ID)
                fout = f(qtA, qtB)
                n_done += 1
                if fout is not None:
                    n_rec += 1
                    yield (fout, (qtA, qtB))
        if qgis_obj is not None:
            qgis_obj.setProgress(100)
    else:
        if not jobs:
            jobs = mp.cpu_count()

        qin = mp.Queue()
        qout = mp.Queue()

        # debug tool
        def inform(string: str = "", verbose: bool = verbose) -> None:
            if not verbose:
                return

            logger.debug(string)

            # len(it1) == #qtracks
            # qin.qsize goes to 0 quickly
            # qout.qsize goes to 0 slowly
            # TODO use f-strings in logger
            logger.debug(
                "  results_queued/written/sum= "
                + format(qout.qsize(), "10d")
                + "  "
                + format(n_rec, "10d")
                + "  "
                + format(n_rec + (qout.qsize()), "10d")
            )

            logger.debug(
                "  jobs_running/done/sum=      "
                + format(pcount, "10d")
                + "  "
                + format(n_done, "10d")
                + "  "
                + format(pcount + n_done, "10d")
            )

            if IMPORT_SUCCESS_psutil:
                logger.debug(
                    "  mem %virtual=  "
                    + format(psutil.virtual_memory().percent, "6.2f")
                )
            return

        # spawn process to populate qin
        # logger.info(f"Starting process to populate qin")
        #process = mp.Process(target=populate, args=(qin, it1, jobs))
        process = mp.Process(target=populate, args=(qin, seeds, jobs))
        process.start()

        # spawn worker processes
        logger.debug(f"Starting {jobs} workers")
        procs = [
            mp.Process(target=calculate, args=(f, qin, qout, it2seeds, it2rest, qgis_obj))
            for _ in range(jobs)
        ]
        for p in procs:
            p.daemon = True
            p.start()

        # initial values
        pcount = jobs
        n_rec = 0
        n_rec_prev = -1
        n_done = 0
        n_done_prev = 0

        # get elts from qout, and yield
        inform("Initial:")
        while True:
            if qgis_obj is not None:
                qgis_obj.setProgress(100 * n_rec / total)
                if qgis_obj.isCanceled():
                    qgis_obj.pushInfo(
                        "WARNING: Scoring step halted with partial progress"
                    )
                    return
            try:
                fout, p = qout.get(timeout=1)
                # pout.update()
                # logger.info(f"Got {fout, (a,b)} from qout")
                if (fout, p) == (None, "QOUT_DONE"):
                    n_done += 1
                    # logger.info(f"n_done {n_done}")
                    if n_done == jobs:
                        # logger.info(f"{n_done} {jobs} BREAK")
                        break
                else:
                    # pair p is properly sorted in calculate()
                    n_rec += 1
                    yield fout, p

                if not verbose:
                    continue

                pcount = sum(p.is_alive() for p in procs)

                # kscantw debug
                # qout.qsize() <= 1 or
                # pcount < jobs or

                # if ( n_done == 0 and
                #     ( n_rec_prev < 1 or
                #       ( n_rec / n_rec_prev ) > 1.05 or
                #       psutil.virtual_memory().percent > 90.0 or
                #       psutil.swap_memory().percent > 90.0 ) ):
                if n_done == 0 and (n_rec_prev < 1 or (n_rec / n_rec_prev) > 1.05):
                    inform("Running:")
                    n_rec_prev = n_rec
                    n_done_prev = n_done

                # elif ( n_done > n_done_prev or
                #       psutil.virtual_memory().percent > 90.0 or
                #       psutil.swap_memory().percent > 90.0 ):
                elif n_done > n_done_prev:
                    inform("Finishing:")
                    n_rec_prev = n_rec
                    n_done_prev = n_done

            except queue.Empty:
                # logger.debug( "empty" )    ## here a lot at first
                continue  # keep pulling from queue

        inform("Done:")

        # all procs done
        for p in procs:
            try:
                p.join(0.1)
            except Exception as e:
                logger.warning(f"process failed to close properly {e}")

    dur = datetime.datetime.now() - s
    ts = dur.total_seconds()
    further_info = ""
    if ts != 0:
        further_info = f", {total//ts} its/sec"
    logger.debug(
        f"sent {total:,d}, rec {n_rec:,d} took {dur} {ts :.2f} seconds{further_info}"
    )
    return


def filtermap(
    f: Callable,
    iterator: Iterable[Any],
    filt: Optional[Callable] = None,
    total: Optional[int] = None,
    getlen: bool = False,
    chunksize: Optional[int] = None,
    jobs: Optional[int] = None,
    star: bool = False,
    pairs: bool = False,
    show_progress: bool = False,
    # qgis_obj: Optional[QgsProcessingFeedBack] = None,
    qgis_obj: Optional[object] = None,
):
    """
    Similar to Pool.imap, with optional filtering and progress bars

    With filt=None, equivalent to:
        (f(x) for x in xs)

    With filt(f(x), x) -> bool, equivalent to:
        (f(x) for x in xs if filt(f(x), x))

    If pairs is True, yields tuples of the form (f(x), x) instead of just f(x)
    If star is True, replace all instances above of f(x) with f(*x)

    # TODO document arguments
    """

    iterator = (_ for _ in iterator)
    if total is None and getlen:
        iterator, total = iterlen(iterator)

    if jobs is None:
        jobs = mp.cpu_count()
    if chunksize is None:
        if total:
            chunksize, rem = divmod(total, 4 * jobs)
            # ensure chunksize > 0
            if not chunksize:
                chunksize = rem + 1
            chunksize = min(chunksize, MAX_CHUNKSIZE)
        else:
            chunksize = MAX_CHUNKSIZE

    if not IMPORT_SUCCESS_enlighten:
        show_progress = False
    if show_progress:
        manager = enlighten.get_manager()
        pout = manager.counter(total=total, desc="qout")

    def g(fx, x):
        """
        yield if filt is True, optinally updating progress bar
        TODO better docstring
        """
        if show_progress:
            pout.update()
        if filt is not None:
            if filt(fx, x):
                yield (fx, x) if pairs else fx
        else:
            yield (fx, x) if pairs else fx

    n = 0
    s = datetime.datetime.now()
    if jobs == 1:
        if star:
            rs = ((f(*x), x) for x in iterator)
        else:
            rs = ((f(x), x) for x in iterator)
        for fx, x in rs:
            n += 1
            if qgis_obj is not None:
                qgis_obj.setProgress(100 * n / total)
                if qgis_obj.isCanceled():
                    qgis_obj.pushInfo(
                        "WARNING: Quantization step halted with partial progress"
                    )
                    break
            yield from g(fx, x)
    else:
        with mp.Pool(processes=jobs) as p:
            iterator, it2 = tee(iterator)
            if star:
                # TODO ugh, kill me
                rs = zip(
                    p.imap(_fun0, zip(repeat(f), iterator), chunksize=chunksize), it2,
                )
            else:
                rs = zip(p.imap(f, iterator, chunksize=chunksize), it2)
            for fx, x in rs:
                n += 1
                if qgis_obj is not None:
                    qgis_obj.setProgress(100 * n / total)
                    if qgis_obj.isCanceled():
                        qgis_obj.pushInfo(
                            "WARNING: Quantization step halted with partial progress"
                        )
                        break
                yield from g(fx, x)

    dur = datetime.datetime.now() - s
    logger.info(
        f"map {n} took {dur} {dur.total_seconds() :.2f} seconds, {int(n/dur.total_seconds())} its/sec"
    )
    if show_progress:
        pout.close()
        manager.stop()
