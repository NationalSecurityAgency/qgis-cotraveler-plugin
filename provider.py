import os
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
from .synchronous import SynchronousAlgorithm

class CoTravelProvider(QgsProcessingProvider):

    def unload(self):
        QgsProcessingProvider.unload(self)

    def loadAlgorithms(self):
        self.addAlgorithm(SynchronousAlgorithm())

    def icon(self):
        return QIcon(os.path.dirname(__file__) + '/icons/cotravel.svg')

    def id(self):
        return 'cotravel'

    def name(self):
        return 'Co-travel'

    def longName(self):
        return self.name()
