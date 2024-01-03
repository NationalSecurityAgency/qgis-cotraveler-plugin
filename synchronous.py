import os
import sys
from datetime import datetime
import dateutil.parser
from collections import defaultdict
from typing import Any, Dict, Hashable, Iterable, List, Optional, Tuple, Union
from cotravel._types import Ping, PingList, Track
from cotravel.config import (
    DEGREES_TO_METERS, MIN_PINGS, MAX_VELOCITY,
    MIN_PINGS_PER_TIMEBIN, MIN_DIAMETER, MIN_QPINGS, MIN_COMMON_DIAMETER,
    MIN_COMMON_QPINGS)
from cotravel.load_tracks import add_ping_to_dict, filter_tracks
from cotravel.quantize import quantize_tracks
from cotravel.synchronous import synchronous_scores_from_qtracks
from qgis.core import (
    QgsPointXY, QgsFeature, QgsGeometry, QgsField, QgsFields,
    QgsProject, QgsWkbTypes, QgsCoordinateReferenceSystem)

from qgis.core import (
    QgsProcessing,
    QgsProcessingUtils,
    QgsProcessingAlgorithm,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink)

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QVariant, QUrl, QDateTime
from qgis.utils import plugins

import traceback


class AttachScoresLayer(QgsProcessingLayerPostProcessorInterface):
    def postProcessLayer(self, layer, context, feedback):
        if layer.isValid():
            cotravel = plugins['cotraveler']
            cotravel.setAnalysisScoresLayer(layer)

    # Hack to work around sip bug!
    @staticmethod
    def create() -> 'AttachScoresLayer':
        """
        Returns a new instance of the post processor, keeping a reference to the sip
        wrapper so that sip doesn't get confused with the Python subclass and call
        the base wrapper implementation instead... ahhh sip, you wonderful piece of sip
        """
        AttachScoresLayer.instance = AttachScoresLayer()
        return AttachScoresLayer.instance

"""
Notes:
    qgis.utils.plugins  # Dictionary of plugins
    qgis.utils.isPluginLoaded('QgisTDC')
"""

class SynchronousAlgorithm(QgsProcessingAlgorithm):
    """
    Algorithm to time zone attribute.
    """

    PrmInputLayer = 'InputLayer'
    PrmOutputResults = 'OutputResults'
    PrmTimestamp = 'Timestamp'
    PrmTrackID = 'TrackID'
    PrmTimeBinSize = 'TimeBinSize'
    PrmAutoBinSize = 'AutoBinSize'
    PrmAutoNumberOfBins = 'AutoNumberOfBins'
    PrmPartTimeMinScore = 'PartTimeMinScore'
    PrmMinPingsPerTrack = 'MinPingsPerTrack'
    PrmMaximumVelocity = 'MaximumVelocity'
    PrmMinPingsPerTimeBin = 'MinPingsPerTimeBin'
    PrmMinDiameter = 'MinDiameter'
    PrmMinQPings = 'MinQPings'
    PrmMinCommonDiameter = 'MinCommonDiameter'
    PrmMinCommonQPings = 'MinCommonQPings'
    PrmMaxDistance = 'MaxDistance'
    PrmSeeds = "Seeds"
    PrmRemoveFilter = 'RemoveFilter'
    PrmTimeBinSizeMode = 'TimeBinSizeMode'
    

    def initAlgorithm(self, config):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.PrmInputLayer,
                'Input point layer',
                [QgsProcessing.TypeVectorPoint])
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PrmTimestamp,
                'Timestamp attribute',
                parentLayerParameterName=self.PrmInputLayer,
                type=QgsProcessingParameterField.Any,
                optional=False)
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PrmTrackID,
                'Track group ID attribute',
                parentLayerParameterName=self.PrmInputLayer,
                type=QgsProcessingParameterField.Any,
                optional=False)
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.PrmSeeds,
                'Group IDs (seeds) to look for. One per line.',
                multiLine=True,
                optional=True)
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PrmRemoveFilter,
                'Remove layer feature filter before procesing',
                True,
                optional=True)
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PrmTimeBinSizeMode,
                'Method to calculate time bin size',
                options=['Manually enter time bin size', 'Automatically determine size from # of time bins'],
                defaultValue=1,
                optional=False)
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PrmAutoNumberOfBins,
                'Number of time bins for automatic bin size',
                QgsProcessingParameterNumber.Integer,
                defaultValue=100,
                minValue=1,
                optional=True)
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PrmTimeBinSize,
                'Time bin size in minutes (unused in automatic mode)',
                QgsProcessingParameterNumber.Double,
                defaultValue=15,
                minValue=0,
                optional=True)
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PrmPartTimeMinScore,
                'Part time minimum score (minutes)',
                QgsProcessingParameterNumber.Double,
                defaultValue=0,
                minValue=0,
                optional=True)
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.PrmOutputResults,
                'Scores output',
                type=QgsProcessing.TypeVector)
        )
        # Set up Advanced Parameters
        param = QgsProcessingParameterNumber(
            self.PrmMaxDistance,
            'Maximum allowed score (meters)',
            QgsProcessingParameterNumber.Double,
            defaultValue=20000,
            minValue=0,
            optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
                self.PrmMinPingsPerTrack,
                'Minimum pings per track',
                QgsProcessingParameterNumber.Integer,
                defaultValue=MIN_PINGS,
                minValue=1,
                optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
                self.PrmMaximumVelocity,
                'Maximum velocity in meters per second',
                QgsProcessingParameterNumber.Double,
                defaultValue=MAX_VELOCITY,
                minValue=0,
                optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
            self.PrmMinPingsPerTimeBin,
            'Minimum pings per time bin',
            QgsProcessingParameterNumber.Integer,
            defaultValue=0,
            minValue=0,
            optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
            self.PrmMinDiameter,
            'Minimum diameter (meters)',
            QgsProcessingParameterNumber.Double,
            defaultValue=MIN_DIAMETER,
            minValue=0,
            optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
            self.PrmMinQPings,
            'Minimum qpings',
            QgsProcessingParameterNumber.Integer,
            defaultValue=MIN_QPINGS,
            minValue=0,
            optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
            self.PrmMinCommonDiameter,
            'Minimum common diameter (meters)',
            QgsProcessingParameterNumber.Double,
            defaultValue=MIN_COMMON_DIAMETER,
            minValue=0,
            optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterNumber(
            self.PrmMinCommonQPings,
            'Minimum common qpings',
            QgsProcessingParameterNumber.Integer,
            defaultValue=MIN_COMMON_QPINGS,
            minValue=0,
            optional=True)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def processAlgorithm(self, parameters, context, feedback):
        self.parameters = parameters
        source = self.parameterAsSource(parameters, self.PrmInputLayer, context)
        self.f_timestamp = self.parameterAsString(parameters, self.PrmTimestamp, context)
        self.f_track_id = self.parameterAsString(parameters, self.PrmTrackID, context)
        seed_str = self.parameterAsString(parameters, self.PrmSeeds, context)
        min_pings = self.parameterAsInt(parameters, self.PrmMinPingsPerTrack, context)
        max_velocity = self.parameterAsDouble(parameters, self.PrmMaximumVelocity, context)
        auto_bin_size = self.parameterAsInt(parameters, self.PrmTimeBinSizeMode, context)
        remove_filter = self.parameterAsBool(parameters, self.PrmRemoveFilter, context)
        auto_number_of_bins = self.parameterAsInt(parameters, self.PrmAutoNumberOfBins, context)
        time_bin_size = self.parameterAsDouble(parameters, self.PrmTimeBinSize, context)
        time_bin_size = time_bin_size * 60.0  # Needs to be in seconds
        part_time_min_score = self.parameterAsDouble(parameters, self.PrmPartTimeMinScore, context)
        if part_time_min_score:
            part_time_min_score = part_time_min_score * 60.0  # Need to be in seconds
        else:
            part_time_min_score = None

        if remove_filter:
            layer = self.parameterAsLayer(parameters, self.PrmInputLayer, context)
            if layer:
                layer.setSubsetString('')
        # Advance Parameters
        min_pings_per_timebin = self.parameterAsInt(parameters, self.PrmMinPingsPerTimeBin, context)
        min_diameter = self.parameterAsDouble(parameters, self.PrmMinDiameter, context)
        min_qpings = self.parameterAsInt(parameters, self.PrmMinQPings, context)
        min_common_diameter = self.parameterAsDouble(parameters, self.PrmMinCommonDiameter, context)
        min_common_qpings = self.parameterAsInt(parameters, self.PrmMinCommonQPings, context)
        max_dist = self.parameterAsDouble(parameters, self.PrmMaxDistance, context)
        
        fields = source.fields()
        epsg4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        src_crs = source.sourceCrs()
        if src_crs != epsg4326:
            raise QgsProcessingException("Input layer must be CRS EPSG:4326. Please convert and rerun")
            
        s = seed_str.strip()
        seeds = []
        if s != '':
            for l in s.splitlines():
                l = l.strip()
                if l != '':
                    seeds.append(l)
        seeds = tuple(seeds)

        # tracks is {ID: [(t,x,y)...]} or {ID: [(t,x,y,cep)...]}
        tracks: Dict[Any, PingList] = defaultdict(list)
        rescale = DEGREES_TO_METERS
        cep_rescale = DEGREES_TO_METERS
        # Get an iterator for all the vector point features
        feedback.setProgressText("Loading Features")
        feedback.setProgress(0)
        iterator = source.getFeatures()
        time_min = sys.float_info.max
        time_max = -1
        for cnt, feature in enumerate(iterator):
            if feedback.isCanceled():
                break
            try:
                # One of the feature attributes is a UNIX timestamp
                dt = feature[self.f_timestamp]
                if isinstance(dt, str):
                    t_unix = dateutil.parser.parse(dt).timestamp()
                elif isinstance(dt, QDateTime):
                    t_unix = dt.toPyDateTime().timestamp()
                else:
                    t_unix = float(dt)
                if t_unix < time_min:
                    time_min = t_unix
                if t_unix > time_max:
                    time_max = t_unix
                # Get the latitude and longitude for each feature
                pt = feature.geometry().asPoint()
                lat = pt.y()
                lon = pt.x()
                if self.f_track_id:
                    track_id = feature[self.f_track_id]
                else:
                    track_id = None
                ping = Ping(track_id, t_unix, lon, lat)
                add_ping_to_dict(tracks, ping, dedupe=True)
            except Exception:
                s = traceback.format_exc()
                feedback.pushInfo(s)
                pass
        if auto_bin_size:
            time_bin_size = ((time_max - time_min) / auto_number_of_bins)  # In seconds
            feedback.pushInfo('Automatic time bin size (minutes): {}'.format(time_bin_size / 60))

        feedback.setProgressText("Creating Tracks")
        feedback.setProgress(10)
        if feedback.isCanceled():
            return {}
        ts = (Track(k, tracks[k], rescale=rescale, cep_rescale=cep_rescale) for k in tracks)

        if feedback.isCanceled():
            return {}
        ts_f = filter_tracks(ts, min_pings=min_pings, max_velocity=max_velocity)
        ts_f = list(ts_f)

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("Quantizing Tracks")
        qtracks = quantize_tracks(ts_f, jobs=1, delta_t=time_bin_size, min_pings_per_timebin=min_pings_per_timebin,
            min_diameter=min_diameter, min_qpings=min_qpings, qgis_obj=feedback)

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("Creating Track Scores")
        df = synchronous_scores_from_qtracks(qtracks, jobs=1,
            min_pings_per_timebin=min_pings_per_timebin, time_window=part_time_min_score,
            min_diameter=min_diameter, min_common_diameter=min_common_diameter,
            min_common_qpings=min_common_qpings, max_dist=max_dist, ids=seeds, qgis_obj=feedback)

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("Generating Ouput Results")
        fields = QgsFields()
        for col in df.columns:
            if col == 'device1' or col == 'device2':
                fields.append(QgsField(col, QVariant.String))
            else:
                fields.append(QgsField(col, QVariant.Double))
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.PrmOutputResults, context, fields,
            QgsWkbTypes.NoGeometry)
        for index, row in df.iterrows():
            l_row = []
            for i, r in enumerate(tuple(row)):
                # Append the first two device names as strings and the rest as double values
                if i <= 1:
                    l_row.append('{}'.format(r))
                else:
                    l_row.append(r)
            # l_row = ['{}'.format(r) for r in tuple(row)]
            if seeds and l_row[0] == l_row[1]:
                continue
            f = QgsFeature()
            f.setAttributes(l_row)
            sink.addFeature(f)

        if context.willLoadLayerOnCompletion(dest_id):
            context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(AttachScoresLayer.create())
        return {self.PrmOutputResults: dest_id}

    def postProcessAlgorithm(self, context, feedback):
        retval = super().postProcessAlgorithm(context, feedback)
        cotravel = plugins['cotraveler']
        cotravel.showAnalysisDialog()
        input_layer = self.parameterAsLayer(self.parameters, self.PrmInputLayer, context)
        cotravel.setAnalysisInputData(input_layer, self.f_track_id, self.f_timestamp)
        return retval

    def name(self):
        return 'synchronous'

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), 'icons/synchronous.svg'))

    def displayName(self):
        return 'Calculate co-traveler scores'

    def helpUrl(self):
        file = os.path.dirname(__file__) + '/index.html'
        if not os.path.exists(file):
            return ''
        return QUrl.fromLocalFile(file).toString(QUrl.FullyEncoded)

    def createInstance(self):
        return SynchronousAlgorithm()

