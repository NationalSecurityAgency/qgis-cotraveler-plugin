import os

from qgis.PyQt.uic import loadUiType
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDockWidget, QAbstractItemView, QTableWidget, QTableWidgetItem
from qgis.core import Qgis, QgsMapLayerProxyModel, QgsWkbTypes, QgsCoordinateTransform, QgsProject, QgsRectangle
from qgis.utils import isPluginLoaded, plugins
from datetime import datetime
import pytz

import traceback

FORM_CLASS, _ = loadUiType(os.path.join(
    os.path.dirname(__file__), 'cotravel.ui'))


class CoTravelAnalysis(QDockWidget, FORM_CLASS):
    selected_layer = None
    selected_scores = None
    selected_attribute = None
    qtdc = None
    qtdc_layer = None

    def __init__(self, iface, parent):
        super(CoTravelAnalysis, self).__init__(parent)
        self.setupUi(self)
        self.canvas = iface.mapCanvas()
        self.iface = iface
        self.clearButton.setIcon(QIcon(':/images/themes/default/mIconClearText.svg'))
        self.dataComboBox.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.dataComboBox.layerChanged.connect(self.layerChanged)
        self.scoresComboBox.setFilters(QgsMapLayerProxyModel.NoGeometry)
        self.scoresComboBox.layerChanged.connect(self.layerChanged)
        self.idComboBox.fieldChanged.connect(self.fieldChanged)
        self.idFilterEdit.returnPressed.connect(self.on_applyButton_pressed)
        self.resultsTable.setEditTriggers(QTableWidget.NoEditTriggers)
        self.resultsTable.setColumnCount(3)
        self.resultsTable.setSortingEnabled(False)
        self.resultsTable.setHorizontalHeaderLabels(['ID 1','ID 2','Score'])
        self.resultsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.resultsTable.itemSelectionChanged.connect(self.select_feature)

    def showEvent(self, e):
        self.layerChanged()
        self.checkForQTDC()

    def closeEvent(self, e):
        layer = self.dataComboBox.currentLayer()
        if layer:
            layer.setSubsetString('')

    def setAnalysisInputData(self, point_layer, id_name, dt_name):
        self.idFilterEdit.setText('')
        self.dataComboBox.setLayer(point_layer)
        self.layerChanged()
        self.idComboBox.setField(id_name)
        if self.qtdc:
            self.timeFieldComboBox.setField(dt_name)
    
    def setAnalysisScoresLayer(self, scores_layer):
        self.scoresComboBox.setLayer(scores_layer)
        self.on_applyButton_pressed()

    def fieldChanged(self, fieldName):
        self.layerChanged()

    def layerChanged(self):
        if not self.isVisible():
            return
        reset_results = False
        layer = self.dataComboBox.currentLayer()
        if not layer:
            self.clearQTDC()
            self.resultsTable.setRowCount(0)
            return
        if layer != self.selected_layer:
            self.idComboBox.blockSignals(True)
            self.idComboBox.setLayer(layer)
            self.idComboBox.blockSignals(False)
            reset_results = True
            self.clearQTDC()
        
        self.selected_layer = layer
        self.timeFieldComboBox.setLayer(layer)
        scores = self.scoresComboBox.currentLayer()
        if scores != self.selected_scores:
            reset_results = True
        self.selected_scores = scores
        selected_attribute = self.idComboBox.currentField()
        if selected_attribute != self.selected_attribute:
            reset_results = True
        self.selected_attribute = selected_attribute
        if reset_results:
            layer.setSubsetString('')
            self.resultsTable.setRowCount(0)
            self.qtdc_layer = None
            self.overlapStartEdit.setText('')
            self.overlapStopEdit.setText('')

    def select_feature(self):
        layer = self.dataComboBox.currentLayer()
        if not layer:
            return
        fields = layer.fields()
        selectedItems = self.resultsTable.selectedItems()
        if len(selectedItems) == 0:
            if layer:
                layer.setSubsetString('')
            return
        id_field_name = self.idComboBox.currentField()
        # print("id_field_name: {}".format(id_field_name))
        id_field_index = fields.indexFromName(id_field_name)
        # print("id_field_index: {}".format(id_field_index))
        
        ids = set()
        start_time = -1
        stop_time = -1
        for item in selectedItems:
            selectedRow = item.row()
            ids.add(self.resultsTable.item(selectedRow, 0).text())
            ids.add(self.resultsTable.item(selectedRow, 1).text())
            (start, stop) = self.resultsTable.item(selectedRow, 0).data(Qt.UserRole)
            if start_time == -1 or start < start_time:
                start_time = start
            if stop_time == -1 or stop > stop_time:
                stop_time = stop
        utc = datetime.fromtimestamp(start_time, pytz.utc)
        self.overlapStartEdit.setText(utc.strftime('%Y-%m-%dT%H:%M:%SZ'))
        utc = datetime.fromtimestamp(stop_time, pytz.utc)
        self.overlapStopEdit.setText(utc.strftime('%Y-%m-%dT%H:%M:%SZ'))
        field = fields[id_field_index]
        if field.isNumeric():
            ids_str = ",".join(ids)
            exp = '"{}" IN ({})'.format(id_field_name, ids_str)
        else:
            ids_str = "','".join(ids)
            exp = '"{}" IN (\'{}\')'.format(id_field_name, ids_str)
        # print(exp)
        if layer:
            layer.setSubsetString(exp)
        self.zoomToLayer(layer)
        if self.qtdc and self.qtdc_layer:
            if self.qtdc.isLayerLoaded(self.qtdc_layer):
                self.qtdc.reloadLayer(self.qtdc_layer)

    def zoomToLayer(self, layer):
        zoom = self.zoomComboBox.currentIndex() 
        if layer and zoom:
            layer_crs = layer.crs()
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            rect = xform.transform(layer.extent())
            if zoom == 1:
                center = rect.center()
                rect = QgsRectangle(center.x(), center.y(), center.x(), center.y())
            self.canvas.setExtent(rect)
        
    def on_applyButton_pressed(self):
        layer = self.scoresComboBox.currentLayer()
        id_filter = self.idFilterEdit.text().strip()
        if not layer:
            return
        self.resultsTable.setRowCount(0)
        fields = layer.fields().names()
        if 'device1' not in fields or 'device2' not in fields or 'avg_dist' not in fields:
            return
        iter = layer.getFeatures()
        index = 0
        for f in iter:
            id1 = f['device1']
            id2 = f['device2']
            # If a filter is set make sure it matches on of the ids
            if id_filter:
                if id_filter != id1 and id_filter != id2:
                    continue
            score = f['avg_dist']
            self.resultsTable.insertRow(index)
            item = QTableWidgetItem('{}'.format(id1))
            item.setData(Qt.UserRole, (f['overlap_start'], f['overlap_stop']))
            self.resultsTable.setItem(index, 0, item)
            item = QTableWidgetItem('{}'.format(id2))
            self.resultsTable.setItem(index, 1, item)
            try:
                item = QTableWidgetItem('{:.0f}'.format(float(score)))
            except:
                item = QTableWidgetItem('')
            self.resultsTable.setItem(index, 2, item)
            index += 1
        self.resultsTable.resizeColumnsToContents()

    def on_clearButton_pressed(self):
        """"
            This deselects all selected tracks. It doesn't remove them.
        """
        self.resultsTable.clearSelection()
        layer = self.dataComboBox.currentLayer()
        self.zoomToLayer(layer)

    def clearQTDC(self):
        if not self.qtdc:
            return
        if self.qtdc_layer:
            # When the API get set up it needs to clear the existing QTDC Plot
            self.qtdc_layer = None        

    def checkForQTDC(self):
        if isPluginLoaded('QgisTDC'):
            try:
                self.qtdc = plugins['QgisTDC'].getAPI()
                self.qtdcButton.setVisible(True)
                self.timeLabel.setVisible(True)
                self.timeFieldComboBox.setVisible(True)
            except Exception:
                self.qtdcButton.setVisible(False)
                self.timeLabel.setVisible(False)
                self.timeFieldComboBox.setVisible(False)
                s = traceback.format_exc()
                print(s)
        else:
            self.qtdcButton.setVisible(False)
            self.timeLabel.setVisible(False)
            self.timeFieldComboBox.setVisible(False)

    def on_qtdcButton_pressed(self):
        if not self.qtdc:
            return
        if self.qtdc_layer and not self.qtdc.isLayerLoaded(self.qtdc_layer):
            self.qtdc_layer = None
        if self.qtdc_layer:
            # We already are displaying a layer so just make sure it is being displayed
            # and make sure it is reloaded
            self.qtdc.display(True)
            self.qtdc.reloadLayer(self.qtdc_layer)
        else:
            try:
                layer = self.dataComboBox.currentLayer()
                time_field = self.timeFieldComboBox.currentField()
                if layer and time_field:
                    self.qtdc.display(True)
                    self.qtdc_layer = self.qtdc.loadLayer(layer, time_field)
            except Exception:
                s = traceback.format_exc()
                print("In Exception")
                print(s)
                pass
