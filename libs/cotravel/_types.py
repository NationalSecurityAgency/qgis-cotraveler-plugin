#!/usr/bin/env python3
from __future__ import annotations

import datetime
from typing import Hashable, Iterable, List, NamedTuple, Optional, Tuple, Union

import numpy as np
import pandas as pd
from cached_property import cached_property
from pandas.core.common import flatten

# a TimestampLike is anything that can be converted into a unix timestamp
TimestampLike = Union[str, datetime.datetime, datetime.date, float]


class Ping(NamedTuple):
    ID: Hashable
    t: float
    x: float
    y: float


class CPing(NamedTuple):
    ID: Hashable
    t: float
    x: float
    y: float
    cep: float


# a ping is either (t,x,y) or (t,x,y,cep)
PingList = Union[
    Iterable[Tuple[float, float, float]], Iterable[Tuple[float, float, float, float]],
]


# either (ID, TIMESTAMP, LON, LAT) or (ID, TIMESTAMP, LON, LAT, CEP)
Columns = Union[Tuple[str, str, str, str], Tuple[str, str, str, str, str]]


class ATrack:
    # TODO make this a base class for both Track and QTrack. Nah.
    def __init__(
        self,
        ID: str,
        atrack: np.ndarray,
        rescale: float = 1,
        dedupe_atrack_pings: bool = True,
    ):
        """
        :param ID: Track identifier
        :param atrack: numpy array of shape (n,2) [(x,y), ...]
        :param dedupe_atrack_pings: If True (default), .atrack pings are deduped.
        """
        self.ID = ID
        self.atrack = atrack
        if dedupe_atrack_pings:
            ans = []
            prev_xy = (np.inf, np.inf)
            for x, y in atrack:
                if (x, y) != prev_xy:
                    prev_xy = x, y
                    ans.append(prev_xy)
            self.atrack = np.array(ans)
        self.rescale = rescale
        self.dedupe_atrack_pings = dedupe_atrack_pings

    def __getstate__(self) -> tuple[str, np.ndarray, float, bool]:
        return (self.ID, self.atrack, self.rescale, self.dedupe_atrack_pings)

    def __setstate__(self, state) -> None:
        (self.ID, self.atrack, self.rescale, self.dedupe_atrack_pings) = state

    @cached_property
    def diameter(self) -> float:
        """
        Return the approximate diameter of self
        Project onto 4 lines (x and y axes, and the lines x = y and x = -y) and
        return the max of the linear differences in each direction
        """
        return _diameter(self.atrack, self.rescale)

    @cached_property
    def total_distance(self) -> float:
        """
        Returns the total distance of self.atrack, which is the sum of the
        length of line segments connecting the pings in atrack.
        """
        return _total_distance(self.atrack, rescale=self.rescale)

    @cached_property
    def centroid(self) -> np.ndarray:
        """
        Return the centroid of self, in native units
        """
        return np.mean(self.atrack, axis=0)


class Track:
    def __init__(
        self,
        ID: str,
        track: PingList,
        rescale: float = 1,
        cep_rescale: float = 1,
        dedupe_atrack_pings: bool = True,
    ):
        """
        :param ID: Track identifier
        :param track: [(t,x,y), ...] or [(t,x,y,cep), ...]
        :param dedupe_atrack_pings: If True (default), .atrack pings are deduped.
        """
        self.ID = ID
        self.track = track
        # TODO class attributes instead of instance?
        self.rescale = rescale
        self.cep_rescale = cep_rescale
        self.dedupe_atrack_pings = dedupe_atrack_pings

    def __getstate__(self) -> tuple[str, PingList, float, float, bool]:
        return (
            self.ID,
            self.track,
            self.rescale,
            self.cep_rescale,
            self.dedupe_atrack_pings,
        )

    def __setstate__(self, state) -> None:
        (
            self.ID,
            self.track,
            self.rescale,
            self.cep_rescale,
            self.dedupe_atrack_pings,
        ) = state

    @cached_property
    def atrack(self) -> np.ndarray:
        """
        np.array of (x,y) pairs 

        if self.dedupe_atrack_pings is True, these pairs are contiguously
        deduped from self.track; excludes identical position even if time
        changes
        """
        if not self.dedupe_atrack_pings:
            return np.array([p[1:3] for p in self.track])
        else:
            # dedupe consecutive pings
            ans = []
            prev_xy = (np.inf, np.inf)
            for p in self.track:
                x, y = p[1:3]
                if (x, y) != prev_xy:
                    prev_xy = x, y
                    ans.append(prev_xy)
            return np.array(ans)

    @cached_property
    def has_cep(self) -> bool:
        p = self.track[0]
        if len(p) == 3:
            return False
        else:
            return True

    @cached_property
    def pings(self) -> list[Ping] | list[CPing]:
        """
        Return list of `Ping`s or `CPing`s from self
        """
        if self.has_cep:
            return [CPing(self.ID, t, x, y, cep) for (t, x, y, cep) in self.track]
        return [Ping(self.ID, t, x, y) for (t, x, y) in self.track]

    def __len__(self) -> int:
        return len(self.track)

    @cached_property
    def start_time(self) -> float:
        return self.pings[0].t

    @cached_property
    def end_time(self) -> float:
        return self.pings[-1].t

    @cached_property
    def first_ping(self) -> Ping | CPing | None:
        if len(self) == 0:
            return None
        return self.pings[0]

    @cached_property
    def last_ping(self) -> Ping | CPing | None:
        if len(self) == 0:
            return None
        return self.pings[-1]

    @cached_property
    def diameter(self) -> float:
        """
        Return the approximate diameter of self
        Project onto 4 lines (x and y axes, and the lines x = y and x = -y) and
        return the max of the linear differences in each direction
        """
        return _diameter(self.atrack, self.rescale)

    @cached_property
    def total_distance(self) -> float:
        """
        Returns the total distance of self.atrack, which is the sum of the length of line segments connecting the pings in atrack.
        """
        return _total_distance(self.atrack, rescale=self.rescale)

    @cached_property
    def centroid(self) -> np.ndarray:
        """
        Return the centroid of self, in native units
        """
        return np.mean(self.atrack, axis=0)

    @cached_property
    def dataframe(self) -> pd.core.frame.DataFrame:
        df = [[i + 1] + list(p) for i, p in enumerate(self.pings)]
        if self.has_cep:
            return pd.DataFrame(df, columns="PING_NUM ID TIMESTAMP LON LAT CEP".split())
        else:
            return pd.DataFrame(df, columns="PING_NUM ID TIMESTAMP LON LAT".split())

    def __eq__(self, other):
        return (
            self.ID == self.ID
            and np.isclose(list(flatten(self.track)), list(flatten(other.track)))
            and np.isclose(self.rescale, other.rescale)
            and np.isclose(self.cep_rescale, other.cep_rescale)
        )


class QTrack:
    # TODO make rescale a class attr instead of an instance attr
    def __init__(
        self,
        ID: str,
        qtrack: np.ma.masked_array,
        qstart_time: float,
        qend_time: float,
        delta_t: float,
        orig_pings: np.ndarray,
        qpings_may_exist: np.ndarray,
        rescale: float = 1,
        cep_rescale: float = 1,
        masked_at: int | None = None,
        orig_bin_distances: np.ma.masked_array | None = None,
        dedupe_atrack_pings: bool = True,
    ):
        """
        Quantized Track

        :param ID: Track identifier
        :param qtrack: a numpy masked array
        :param qstart_time: Quantization start time (unix time)
        :param qend_time: Quantzation end time (unix time)
        :param delta_t: Duration of time bins (in seconds)
        :param orig_pings: a numpy array of how many original pings were in each bin
        :param qpings_may_exist: a numpy array of bool that says a qping may exist here, subject to being masked for other reasons.
        :param rescale: Scaling factor from 'native' qtrack units to meters
        :param cep_rescale: Scaling factor from 'native' qtrack CEP units to
        meters (TODO currently unused)
        :param masked_at: the minimum number of original pings that was used to decide a mask, set to None if unknown. This is used to determine if remask is necessary.
        :param orig_bin_distances: the distance travelled in each bin in a masked array.  Set to None if these distances were not computed at quantization.
        :param dedupe_atrack_pings: If True (default), .atrack pings are deduped.
        :returns: a `QTrack` instance
        """
        self.ID = ID
        self.qtrack = qtrack
        self.qstart_time = qstart_time
        self.qend_time = qend_time
        self.delta_t = delta_t
        self.orig_pings = orig_pings
        self.qpings_may_exist = qpings_may_exist
        self.rescale = rescale
        self.cep_rescale = cep_rescale
        self.masked_at = masked_at
        self.orig_bin_distances = orig_bin_distances
        self.dedupe_atrack_pings = dedupe_atrack_pings
        # Remember to update setstate and getstate if adding more attributes!

    def copy(
        self,
    ) -> QTrack:  # annotation -> QTrack required from __future__ import annotations
        return QTrack(
            self.ID,
            np.ma.MaskedArray.copy(self.qtrack),
            self.qstart_time,
            self.qend_time,
            self.delta_t,
            np.copy(self.orig_pings),
            np.copy(self.qpings_may_exist),
            self.rescale,
            self.cep_rescale,
            self.masked_at,
            self.orig_bin_distances,
            self.dedupe_atrack_pings,
        )

    def remask(self, min_pings_per_timebin: int = 1) -> None:
        """
        Remask self.qtrack in place, masking off qpings where there were
        fewer than min_pings_per_timebin in the corresponding timebin,
        and unmask only if corresponding qpings_may_exist is True.
        """
        if min_pings_per_timebin == self.masked_at:  # No change needed
            return
        self.masked_at = min_pings_per_timebin
        mask1D = np.logical_or(
            self.orig_pings < min_pings_per_timebin,
            np.logical_not(self.qpings_may_exist),
        )
        # reshape to be (n,2)
        newmask = np.transpose(np.stack((mask1D, mask1D)))
        if np.array_equal(self.qtrack.mask, newmask):
            # masks have not changed, so no further changes needed.
            return
        self.qtrack.mask = newmask
        for p in [
            "diameter",
            "centroid",
            "num_qpings",
            "dataframe",
            "first_qping",
            "last_qping",
            "atrack",
            "diameter",
            "centroid",
        ]:
            if p in self.__dict__:
                # print(f"deleting cached property {p}")
                del self.__dict__[p]

    def __getstate__(
        self,
    ) -> tuple[
        str,
        np.ma.masked_array,
        float,
        float,
        float,
        np.ndarray,
        float,
        float,
        int,
        np.ma.masked_array,
        bool,
    ]:
        return (
            self.ID,
            self.qtrack,
            self.qstart_time,
            self.qend_time,
            self.delta_t,
            self.orig_pings,
            self.qpings_may_exist,
            self.rescale,
            self.cep_rescale,
            self.masked_at,
            self.orig_bin_distances,
            self.dedupe_atrack_pings,
        )

    def __setstate__(self, s) -> None:
        (
            self.ID,
            self.qtrack,
            self.qstart_time,
            self.qend_time,
            self.delta_t,
            self.orig_pings,
            self.qpings_may_exist,
            self.rescale,
            self.cep_rescale,
            self.masked_at,
            self.orig_bin_distances,
            self.dedupe_atrack_pings,
        ) = s

    def __len__(self) -> int:
        return len(self.qtrack)

    def __eq__(self, other):
        return (
            self.ID == other.ID
            and np.array_equal(self.qtrack.mask, other.qtrack.mask)
            and np.ma.allequal(self.qtrack, other.qtrack, True)
            and np.array_equal(self.orig_pings, other.orig_pings)
            and np.array_equal(self.qpings_may_exist, other.qpings_may_exist)
            and np.isclose(self.qstart_time, other.qstart_time)
            and np.isclose(self.qend_time, other.qend_time)
            and np.isclose(self.delta_t, other.delta_t)
            and np.isclose(self.rescale, other.rescale)
            and np.isclose(self.cep_rescale, other.cep_rescale)
            and (
                (
                    (self.orig_bin_distances is None)
                    and (other.orig_bin_distances is None)
                )
                or (
                    (self.orig_bin_distances is not None)
                    and (other.orig_bin_distances is not None)
                    and np.ma.allclose(
                        self.orig_bin_distances, other.orig_bin_distances, True
                    )
                )
            )
        )

    @cached_property
    def atrack(self) -> np.array:
        """
        np.array of (x,y) pairs contiguously deduped from self.track;
        excludes identical position even if time changes
        """
        if not self.dedupe_atrack_pings:
            return np.ma.compress_rows(self.qtrack)
        else:
            ans = []
            prev_xy = (np.inf, np.inf)
            for x, y in np.ma.compress_rows(self.qtrack):
                if (x, y) != prev_xy:
                    prev_xy = x, y
                    ans.append(prev_xy)
            return np.array(ans)

    @cached_property
    def diameter(self) -> float:
        """
        Return the approximate diameter of self
        Project onto 4 lines (x and y axes, and the lines x = y and x = -y) and
        return the max of the linear differences in each direction
        """
        return _diameter(self.atrack, self.rescale)

    @cached_property
    def total_distance(self) -> float:
        """
        Returns the total distance of self.atrack, which is the sum of the length of line segments connecting the pings in atrack.
        """
        return _total_distance(self.atrack, rescale=self.rescale)

    @cached_property
    def centroid(self) -> np.ma.masked_array:
        """
        Return the centroid of self, in native units
        """
        return np.ma.mean(self.atrack, axis=0)

    @cached_property
    def num_qpings(self) -> int:
        """
        Number of valid (unmasked) qpings
        """
        # return len(self) - np.count_nonzero(self.qtrack.mask[:, 0])
        return np.ma.count(self.qtrack[:, 0])

    @cached_property
    def first_qping(self) -> Ping | None:
        """
        Returns the first qping where timestamp is the midpoint of time bin time interval.
        """
        i = self.min_index()
        if i is None:
            return None
        t = self.qstart_time + (i + 0.5) * self.delta_t
        latlon = self.qtrack[i]
        return Ping(self.ID, t, latlon[0], latlon[1])

    @cached_property
    def last_qping(self) -> Ping | None:
        """
        Returns the first qping where timestamp is the midpoint of time bin time interval.
        """
        i = self.max_index()
        if i is None:
            return None
        t = self.qstart_time + (i + 0.5) * self.delta_t
        latlon = self.qtrack[i]
        return Ping(self.ID, t, latlon[0], latlon[1])

    @cached_property
    def bin_distances(self) -> np.ma.masked_array:
        """
        returns a  masked array where a distance is computed for each bin where there could be a qping.  
        """
        if self.orig_bin_distances is not None:
            return self.orig_bin_distances
        # if bin distances were not computed at quantization time, then we compute an approximation now.
        good_indices = np.where(self.qpings_may_exist)[0]
        if len(good_indices) <= 1:  # then no way to compute bin distances
            return np.ma.array(np.zeros(len(good_indices)), mask=True)
        unmasked_qpings = np.array(
            self.qtrack
        )  # Force unmask all qpings that may exist.
        # Test if existent qpings are consecutive. If yes, do easier calculation.
        if good_indices[-1] - good_indices[0] == len(good_indices) - 1:
            # we have consecutive indices
            i1 = good_indices[0]
            i2 = good_indices[-1]
            a = np.array(unmasked_qpings[i1 : i2 + 1])
            d = a[1:] - a[:-1]  # differences between consecutive qpings
            n = np.linalg.norm(d, axis=1)  # distances between consecutive qpings
            return np.ma.concatenate(
                (
                    np.ma.array(np.zeros(i1), mask=True),
                    [n[0]],
                    (n[1:] + n[:-1]) / 2,
                    [n[-1]],
                    np.ma.array(np.zeros(len(self) - i2 - 1), mask=True),
                )
            )
        else:
            # we have nonconsecutive indices
            n = []
            ans = np.ma.array(np.zeros(len(self)), mask=True)
            for i in range(len(good_indices) - 1):
                i1 = good_indices[i]
                i2 = good_indices[i + 1]
                n.append(
                    np.linalg.norm(unmasked_qpings[i2] - unmasked_qpings[i1])
                    / (i2 - i1)
                )
            for i in range(1, len(good_indices) - 1):
                ans[good_indices[i]] = (n[i] + n[i - 1]) / 2
            ans[good_indices[0]] = n[0]
            ans[good_indices[-1]] = n[-1]
            return ans

    def min_index(self) -> int | None:
        """
        First False index in self.mask
        """
        m = np.ma.array(range(len(self)), mask=(self.qtrack.mask[:, 0]))
        if m.mask.all():
            return None
        return np.ma.min(m)

    def max_index(self) -> int | None:
        """
        Last False index in self.mask
        """
        m = np.ma.array(range(len(self)), mask=(self.qtrack.mask[:, 0]))
        if m.mask.all():
            return None
        return np.ma.max(m)

    @cached_property
    def dataframe(self) -> pd.core.frame.DataFrame:
        df = []
        ping_num = 1
        for i, (lonlat, orig_pings) in enumerate(zip(self.qtrack, self.orig_pings)):
            if not self.qtrack.mask[i, 0]:
                # t = self.qstart_time + i * self.delta_t
                # The following grabs the midpoint of the time interval
                t = self.qstart_time + (i + 0.5) * self.delta_t
                df.append(
                    [
                        self.ID,
                        ping_num,
                        t,
                        lonlat[0],
                        lonlat[1],
                        orig_pings,
                        self.diameter,
                    ]
                )
            ping_num += orig_pings
        return pd.DataFrame(
            df, columns="ID ORIG_PING_NUM TIMESTAMP LON LAT ORIG_PINGS DIAMETER".split()
        )

    def most_frequent_spot(
        self, granularity_widths: tuple[float, float] = (1, 1), multiplier: int = 5
    ) -> tuple[tuple[float, float], tuple[float, float], float, float]:
        # num_spots:int=1): # TODO?
        """
        :param granularity_widths: Space is tesselated into rectangles of these size.
        :param multiplier: The number of samples is multiplier times the maximum number of rectangles a line segment can pass through.
        Returns most frequently visited geo rectangle as (center of rectangle, dimensions of rectangle, time spent in rectangle, the number of standard deviations this time spent is away from the mean of the other geo rectangles that the piecewise linear path goes through.
        """
        d = _spot_frequencies_from_qtrack(
            self, granularity_widths=granularity_widths, multiplier=multiplier
        )
        best = max(d, key=d.get)
        v = np.array(list(d.values()))
        return (
            tuple(np.array(best) * np.array(granularity_widths)),
            granularity_widths,
            d[best],
            (d[best] - np.mean(v)) / np.std(v),
        )


# needs to be after we define all these things
BaseTrack = Union[Track, QTrack, ATrack]


def _increase_dict_value(a_dict: dict, key: Hashable, val: float):
    a_dict[key] = a_dict.get(key, 0) + val


def _update_spot_frequencies(
    the_dict: dict,
    pt1: tuple[float, float],
    pt2: tuple[float, float],
    delta_t: float,
    granularity_widths: tuple[float, float] = (1, 1),
    multiplier: int = 5,
):
    """
    :param granularity_widths: Space is tesselated into rectangles of these size.
    :param multiplier: The number of samples is multiplier times the maximum number of rectangles a line segment can pass through.
    Returns most frequently visited geo rectangle as (center of rectangle, dimensions of rectangle, time spent in rectangle, the number of standard deviations this time spent is away from the mean of the other geo rectangles that the piecewise linear path goes through.
    """
    v = np.array(pt2) - np.array(pt1)
    g = np.array(granularity_widths)
    n = int(np.sum(np.ceil(np.abs(v / g))) * multiplier)
    pt1_over_g = pt1 / g
    v_over_g = v / g
    time_incr = delta_t / n
    # print((v,g,n))
    [
        _increase_dict_value(
            the_dict,
            tuple(np.round(pt1_over_g + ((i + 0.5) / n) * v_over_g)),
            time_incr,
        )
        for i in range(n)
    ]


def _spot_frequencies_from_qtrack(
    qtr: QTrack, granularity_widths: tuple[float, float] = (1, 1), multiplier: int = 5
) -> dict:
    """
    :param granularity_widths: Space is tesselated into rectangles of these size.
    :param multiplier: The number of samples is multiplier times the maximum number of rectangles a line segment can pass through.
    Returns a dictionary where keys are centers of geo rectangles (scaled up by granularity widths) and values are time spent in each rectangle.
    """
    ans = {}
    unmasked_qpings = np.array(qtr.qtrack)  # Force unmask all qpings that may exist.
    for i in range(len(qtr) - 1):
        if qtr.qpings_may_exist[i] and qtr.qpings_may_exist[i]:
            _update_spot_frequencies(
                ans,
                unmasked_qpings[i],
                unmasked_qpings[i + 1],
                qtr.delta_t,
                granularity_widths=granularity_widths,
                multiplier=multiplier,
            )
    return ans


def _diameter(tr: np.ma.array, rescale: float) -> float:
    """
    Return the diameter of the masked array tr, rescaled by rescale

    Projects onto the x and y axes, as well as the lines x=y and x=-y
    """
    x = tr[:, 0]
    y = tr[:, 1]
    # a=[np.max(x)-np.min(x)]
    # a.append(np.max(y)-np.min(y))
    # a.append( (np.max(x+y)-np.min(x+y))/np.sqrt(2))
    # a.append( (np.max(x-y)-np.min(x-y))/np.sqrt(2))
    # return ans * rescale if ans > 0 else 0
    ans = max(
        np.ma.max(x) - np.ma.min(x),
        np.ma.max(y) - np.ma.min(y),
        (np.ma.max(x + y) - np.ma.min(x + y)) / np.sqrt(2),
        (np.ma.max(x - y) - np.ma.min(x - y)) / np.sqrt(2),
    )
    return ans * rescale if ans > 0 else 0


def _total_distance(arr: np.ndarray, rescale: float = 1) -> float:
    if len(arr) <= 1:
        return 0
    diff = arr[1:] - arr[:-1]
    distances = np.linalg.norm(diff, axis=1)
    return np.sum(distances) * rescale
