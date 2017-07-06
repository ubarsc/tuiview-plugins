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

import numpy
from osgeo import ogr
from tuiview import pluginmanager
from tuiview import viewerlayers
from tuiview import vectorrasterizer
from tuiview import viewerLUT
from tuiview.viewerwidget import VIEWER_TOOL_POLYGON, VIEWER_TOOL_NONE
from tuiview.viewerwidget import VIEWER_TOOL_QUERY

from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtCore import QObject, QAbstractTableModel, Qt, QPoint
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QTableView, QDialog

DEFAULT_OUTLINE_COLOR = (255, 255, 0, 255)

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

        self.showOutlinesAct = QAction(self, toggled=self.toggleOutlines)
        self.showOutlinesAct.setText("Show Outlines of Polygons")
        self.showOutlinesAct.setCheckable(True)
        self.showOutlinesAct.setEnabled(False)

        self.editCodesAct = QAction(self, triggered=self.editCodes)
        self.editCodesAct.setText("Edit recodes of a Polygon")
        self.editCodesAct.setEnabled(False)

        recodeMenu = viewer.menuBar().addMenu("&Recode")
        recodeMenu.addAction(self.startAct)
        recodeMenu.addAction(self.recodeAct)
        recodeMenu.addAction(self.showOutlinesAct)
        recodeMenu.addAction(self.editCodesAct)

        viewer.viewwidget.polygonCollected.connect(self.newPolySelect)
        viewer.viewwidget.locationSelected.connect(self.newLocationSelected)

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
            self.showOutlinesAct.setEnabled(True)
            self.editCodesAct.setEnabled(True)

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

    def toggleOutlines(self, checked):
        self.recodeLayer.drawOutlines = checked
        self.recodeLayer.getImage()
        self.viewer.viewwidget.viewport().update()

    def editCodes(self):
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))

    def newLocationSelected(self, queryInfo):
        # do the edit
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))

        # find it
        ptGeom = ogr.Geometry(ogr.wkbPoint)
        ptGeom.AddPoint(queryInfo.easting, queryInfo.northing)
        foundIdx = None
        for idx, (geom, recodes) in enumerate(self.recodeList):
            if geom.Contains(ptGeom):
                foundIdx = idx
                break

        if foundIdx is None:
            QMessageBox.critical(self.viewer, name(), 
                        "No polygon found at point")
            return

        geom, oldrecodes = self.recodeList[foundIdx]
        # turn oldrecodes back into a dictionary
        dictrecodes = {}
        for key, new in oldrecodes:
            dictrecodes[key] = new

        dlg = RecodeDialog(self.viewer, dictrecodes)
        if dlg.exec_() == RecodeDialog.Accepted:
            recodes = []
            recodedValues = dlg.tableModel.recodedValues
            for key in recodedValues.keys():
                new = recodedValues[key]
                if key != new:
                    recodes.append((key, new))
            
            if len(recodes) == 0:
                del self.recodeList[foundIdx]
            else:
                self.recodeList[foundIdx] = (geom, recodes)
            

            self.recodeLayer.getImage()
            self.viewer.viewwidget.viewport().update()


class RecodeRasterLayer(viewerlayers.ViewerRasterLayer):
    def __init__(self, layermanager, recode):
        viewerlayers.ViewerRasterLayer.__init__(self, layermanager)
        self.recode = recode
        self.drawOutlines = False

        # LUT for drawing outlines if required
        self.outlinelut = numpy.zeros((2, 4), numpy.uint8)
        color = DEFAULT_OUTLINE_COLOR
        for value, code in zip(color, viewerLUT.RGBA_CODES):
            lutindex = viewerLUT.CODE_TO_LUTINDEX[code]
            self.outlinelut[1,lutindex] = value

    def getImage(self):
        viewerlayers.ViewerRasterLayer.getImage(self)
        if self.image.isNull():
            return
        data = self.image.viewerdata

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

        self.image = self.lut.applyLUTSingle(data, self.image.viewermask)

        if self.drawOutlines:
            # paint the outlines onto the image using QPainter

            paint = QPainter(self.image)

            for geom, recodes in self.recode.recodeList:
                mask = vectorrasterizer.rasterizeGeometry(geom, extent, 
                    xsize, ysize, 1, False)
                bgra = self.outlinelut[mask]
                outlineimage = QImage(bgra.data, xsize, ysize, QImage.Format_ARGB32)

                paint.drawImage(QPoint(0, 0), outlineimage)
            paint.end()


class RecodeDialog(QDialog):
    def __init__(self, parent, recodedValues={}):
        QDialog.__init__(self, parent)

        self.setWindowTitle("Recode")

        self.tableModel = RecodeTableModel(self, recodedValues)
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
    def __init__(self, parent, recodedValues):
        QAbstractTableModel.__init__(self, parent)
        self.recodedValues = recodedValues

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
