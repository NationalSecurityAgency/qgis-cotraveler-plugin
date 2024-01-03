# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QUrl, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication
import processing
from .provider import CoTravelProvider

import os

class CoTraveler(object):
    analysis_dialog = None
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.provider = CoTravelProvider()

    def initGui(self):
        self.toolbar = self.iface.addToolBar('Co-travel Toolbar')
        self.toolbar.setObjectName('CoTravelerToolbar')

        icon = QIcon(os.path.dirname(__file__) + '/icons/synchronous.svg')
        self.synchronousAction = QAction(icon, 'Calculate co-traveler scores', self.iface.mainWindow())
        self.synchronousAction.triggered.connect(self.synchronousAnalysis)
        self.iface.addPluginToMenu('Co-travel tools', self.synchronousAction)
        self.toolbar.addAction(self.synchronousAction)

        icon = QIcon(os.path.dirname(__file__) + '/icons/analyze.svg')
        self.analysisAction = QAction(icon, "Analyze co-travelers", self.iface.mainWindow())
        self.analysisAction.triggered.connect(self.showAnalysisDialog)
        self.iface.addPluginToMenu("Co-travel tools", self.analysisAction)
        self.toolbar.addAction(self.analysisAction)
        
        # Help
        icon = QIcon(os.path.dirname(__file__) + '/icons/help.svg')
        self.helpAction = QAction(icon, "Help", self.iface.mainWindow())
        self.helpAction.triggered.connect(self.help)
        self.iface.addPluginToMenu('Co-travel tools', self.helpAction)
        
        # Add the processing provider
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        self.iface.removePluginMenu('Co-travel tools', self.synchronousAction)
        self.iface.removePluginMenu('Co-travel tools', self.analysisAction)
        self.iface.removePluginMenu("Co-travel tools", self.helpAction)
        self.iface.removeToolBarIcon(self.synchronousAction)
        self.iface.removeToolBarIcon(self.analysisAction)
        if self.analysis_dialog:
            self.iface.removeDockWidget(self.analysis_dialog)
        del self.toolbar
        """Remove the provider."""
        QgsApplication.processingRegistry().removeProvider(self.provider)

    def showAnalysisDialog(self):
        """Display the Co-travel analysis window."""
        if not self.analysis_dialog:
            from .analysis import CoTravelAnalysis
            self.analysis_dialog = CoTravelAnalysis(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.analysis_dialog)
        self.analysis_dialog.show()

    def setAnalysisInputData(self, point_layer, id_name, dt_name):
        if not self.analysis_dialog:
            self.showAnalysisDialog()
        self.analysis_dialog.setAnalysisInputData(point_layer, id_name, dt_name)

    def setAnalysisScoresLayer(self, scores_layer):
        if not self.analysis_dialog:
            self.showAnalysisDialog()
        self.analysis_dialog.setAnalysisScoresLayer(scores_layer)

    def synchronousAnalysis(self):
        processing.execAlgorithmDialog('cotravel:synchronous', {})

    def help(self):
        '''Display a help page'''
        import webbrowser
        url = QUrl.fromLocalFile(os.path.dirname(__file__) + "/index.html").toString()
        webbrowser.open(url, new=2)


