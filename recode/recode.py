"""
Raster Recode plugin

Copy into one of the locations mentioned here:
https://bitbucket.org/chchrsc/tuiview/wiki/Plugins
"""
# This file is part of 'TuiView' - a simple Raster viewer
# Copyright (C) 2012  Sam Gillingham
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from tuiview import pluginmanager
from tuiview import viewerlayers
from tuiview import vectorrasterizer
from tuiview.viewerwidget import VIEWER_TOOL_POLYGON, VIEWER_TOOL_NONE

from PyQt5.QtCore import QObject, QAbstractTableModel, Qt
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QTableView, QDialog

def name():
    return 'Recode'

def author():
    return 'Sam Gillingham'

def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = Recode(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
        
class Recode(QObject):
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer
        self.recodeList = []
        self.recodeLayer = None

        self.startAct = QAction(self, triggered=self.startRecode)
        self.startAct.setText("Start Recoding Top Layer")

        self.recodeAct = QAction(self, triggered=self.recodePolygon)
        self.recodeAct.setText("Recode Polygon")
        self.recodeAct.setEnabled(False)

        recodeMenu = viewer.menuBar().addMenu("&Recode")
        recodeMenu.addAction(self.startAct)
        recodeMenu.addAction(self.recodeAct)

        viewer.viewwidget.polygonCollected.connect(self.newPolySelect)

    def startRecode(self):
        widget = self.viewer.viewwidget
        layerMgr = widget.layers
        size = widget.viewport().size()
        # is there a top one?
        oldLayer = layerMgr.getTopRasterLayer()
        if oldLayer is not None:
            # check single band
            if len(oldLayer.stretch.bands) != 1:
                QMessageBox.critical(self.viewer, name(), 
                        "Top layer must be single band")
                return

            # remove it
            layerMgr.removeLayer(oldLayer)

            newLayer = RecodeRasterLayer(layerMgr, self)
            newLayer.open(oldLayer.gdalDataset, size.width(), size.height(), 
                    oldLayer.stretch, oldLayer.lut)

            layerMgr.addLayer(newLayer)
            self.recodeLayer = newLayer

            self.startAct.setEnabled(False)
            self.recodeAct.setEnabled(True)

    def recodePolygon(self):
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_POLYGON, id(self))

    def newPolySelect(self, toolInfo):
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))

        geom = toolInfo.getOGRGeometry()

        dlg = RecodeDialog(self.viewer)
        if dlg.exec_() == RecodeDialog.Accepted:
            recodes = []
            recodedValues = dlg.tableModel.recodedValues
            for key in recodedValues.keys():
                new = recodedValues[key]
                recodes.append((key, new))
            
            if len(recodes) > 0:
                self.recodeList.append((geom, recodes))

                self.recodeLayer.getImage()
                self.viewer.viewwidget.viewport().update()

class RecodeRasterLayer(viewerlayers.ViewerRasterLayer):
    def __init__(self, layermanager, recode):
        viewerlayers.ViewerRasterLayer.__init__(self, layermanager)
        self.recode = recode

    def getImage(self):
        viewerlayers.ViewerRasterLayer.getImage(self)
        if self.image.isNull():
            return
        data = self.image.viewerdata
        savedata = data.copy()

        extent = self.coordmgr.getWorldExtent()
        (xsize, ysize) = (self.coordmgr.dspWidth, self.coordmgr.dspHeight)

        for geom, recodes in self.recode.recodeList:
            mask = vectorrasterizer.rasterizeGeometry(geom, extent, 
                    xsize, ysize, 1, True)
            # convert to 0s and 1s to bool
            mask = (mask == 1)

            for old, new in recodes:
                subMask = mask & (data == old)
                data[subMask] = new

        diffm = data != savedata

        self.image = self.lut.applyLUTSingle(data, self.image.viewermask)

class RecodeDialog(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.setWindowTitle("Recode")

        self.tableModel = RecodeTableModel(self)
        self.tableView = QTableView(self)
        self.tableView.setModel(self.tableModel)

        self.okButton = QPushButton(clicked=self.accept)
        self.okButton.setText("OK")

        self.cancelButton = QPushButton(clicked=self.reject)
        self.cancelButton.setText("Cancel")

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.tableView)
        self.mainLayout.addLayout(self.buttonLayout)

        self.setLayout(self.mainLayout)

class RecodeTableModel(QAbstractTableModel):
    def __init__(self, parent):
        QAbstractTableModel.__init__(self, parent)
        self.recodedValues = {}

    def rowCount(self, parent):
        # TODO: get data type
        return 255

    def columnCount(self, parent):
        return 2

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return "Old"
            else:
                return "New"
        return None

    def flags(self, index):
        column = index.column()
        if column == 1:
            return Qt.ItemIsEditable | Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled

    def data(self, index, role):
        if role == Qt.DisplayRole:
            column = index.column()
            row = index.row()

            if column == 1 and row in self.recodedValues:
                return self.recodedValues[row]

            return str(row)
        return None

    def setData(self, index, value, role):
        if role == Qt.EditRole:
            column = index.column()
            if column == 0:
                return False

            row = index.row()
            self.recodedValues[row] = int(value)

            self.dataChanged.emit(index, index)
            return True

        return False
