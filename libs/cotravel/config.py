"""
TODO module documentation
"""

import numpy as np

# GLOBAL FLAGS contingent on success of imports
IMPORT_SUCCESS_enlighten = True
try:
    import enlighten
except ImportError:
    IMPORT_SUCCESS_enlighten = False
IMPORT_SUCCESS_logzero = True
try:
    import logzero
except ImportError:
    IMPORT_SUCCESS_logzero = False
IMPORT_SUCCESS_sortedcontainers = True
try:
    import sortedcontainers
except ImportError:
    IMPORT_SUCCESS_sortedcontainers = False
IMPORT_SUCCESS_maya = True
try:
    import maya
except ImportError:
    IMPORT_SUCCESS_maya = False
    import dateutil
IMPORT_SUCCESS_tabulate = True
try:
    import tabulate
except ImportError:
    IMPORT_SUCCESS_tabulate = False
IMPORT_SUCCESS_psutil = True
try:
    import psutil
except ImportError:
    IMPORT_SUCCESS_psutil = False

# units
MILES_TO_KM = 5280 * 12 * 2.54 / 100 / 1000
MILES_TO_METERS = 5280 * 12 * 2.54 / 100
DEGREES_TO_METERS = 3959 * 1.60934 * 1000 * np.pi / 180
RESCALE = DEGREES_TO_METERS

# pings-to-tracks
MIN_PINGS = 2  # minimum number of pings
MAX_VELOCITY = 500  # meters/second; land/sea/air all different?
MAX_CEP = 5000  # meters

# tracks-to-qtracks
MIN_QPINGS = 2  # minimum number of qpings
MIN_DIAMETER = 0  # meters
DELTA_T = 15 * 60  # seconds, qping interval
MIN_TIMEBIN_FRACTION = 0.75  # For the first and last time bins,
# this is the minimum required span of original pings, otherwise qping is masked.
ADD_EXTRAPOLATED_PINGS = False  # Whether to extrapolate the track if needed to fill up the first and last time bins
REQUIRE_POSSIBLE_OVERLAP = False  # Whether to require possible overlap of tracks when scoring synchronous_score
MIN_PINGS_PER_TIMEBIN = 1  # Minimum number of original pings in a time bin required to have an unmasked calculated qping.
MAX_CHUNKSIZE = 1_000_000  #

# qtracks-to-pairs (in addition to above defaults)
MIN_COMMON_QPINGS = 2  # minimum qpings in common
MIN_COMMON_DIAMETER = MIN_DIAMETER  # meters, two qtracks combined
MAX_DIST = np.inf  # meters

DEFAULT_COLUMNS = "ID TIMESTAMP LON LAT".split()

# header for causalpairs-DATE.csv
FIELDS_PAIRS = (
    "device1 device2 avg_dist overlap_start overlap_stop "
    + "total_time total_distance midpoint_times "
    + "diameter_common diameter1 diameter2 "
    + "centlon1 centlat1 centlon2 centlat2 common_qpings "
    + "delta_t qstart_time qend_time"
    #+ " overlap_start overlap_stop overlap_time"
).split()
FIELDS_PAIRS_VITAL = (
    "device1 device2 avg_dist overlap_start overlap_stop "
    + "total_distance "
    + "diameter_common"
).split()

# columns produced by pairs-combine.py
FIELDS_COMBO = (
    "device1 device2 close_count dist_quantile diam_quantile "
    + "close_start close_stop"
).split()
# "centlon1 centlat1 centlon2 centlat2 " +

FIELDS_APART = (
    "device1 device2 "
    + "utid1 utid2 id1 id2 "
    + "close_count apart_count "
    + "dist_quantile diam_quantile "
    + "close_start close_stop "
    + "apart_start apart_stop"
).split()
