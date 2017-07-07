"""
Raster Recode plugin

This is a bit of a work in progress, and is more of a demo than anything else.

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

from __future__ import print_function, division
import os
import json
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
from PyQt5.QtWidgets import QLineEdit

DEFAULT_OUTLINE_COLOR = (255, 255, 0, 255)
"Colour that the outlines are shown in, if displayed"
RECODE_EXT = ".recode"
"Extension after the image file extension that the recodes are saved to"

def name():
    "Needed by TuiView"
    return 'Recode'

def author():
    "Needed by TuiView"
    return 'Sam Gillingham'

def action(actioncode, viewer):
    "Needed by TuiView"
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = Recode(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
        
class Recode(QObject):
    """
    Object that is the plugin. Create actions and menu.
    """
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer
        # a list of tuples
        # (geom, comment, dictionary_of_recodes)
        # dictionary_of_recodes keyed on old code
        self.recodeList = []
        self.recodeLayer = None
        self.dataRange = None

        # Create actions
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

        self.saveRecodesAct = QAction(self, triggered=self.saveRecodes)
        self.saveRecodesAct.setText("Save recodes to file")
        self.saveRecodesAct.setEnabled(False)

        # Create menu
        recodeMenu = viewer.menuBar().addMenu("&Recode")
        recodeMenu.addAction(self.startAct)
        recodeMenu.addAction(self.recodeAct)
        recodeMenu.addAction(self.showOutlinesAct)
        recodeMenu.addAction(self.editCodesAct)
        recodeMenu.addAction(self.saveRecodesAct)

        # connect to signals that get fired when polygons, points
        # etc get fired.
        viewer.viewwidget.polygonCollected.connect(self.newPolySelect)
        viewer.viewwidget.locationSelected.connect(self.newLocationSelected)

    def startRecode(self):
        """
        Called when the 'Start Recode' menu item is clicked.
        Makes the top later become a recode layer.
        """
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

            # check not floating point
            firstBand = oldLayer.gdalDataset.GetRasterBand(1)
            numpyType = viewerlayers.GDALTypeToNumpyType(firstBand.DataType)
            if numpy.issubdtype(numpyType, float):
                QMessageBox.critical(self.viewer, name(),
                        "Layer must be integer")
                return

            # remove it
            layerMgr.removeLayer(oldLayer)

            # is there a .recode file?
            recodeName = oldLayer.filename + RECODE_EXT
            if os.path.exists(recodeName):
                msg = ("There is already a recode file for this layer. " +
                        "Do you want to load it?")
                if QMessageBox.question(self.viewer, name(), msg, 
                        QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                    # Load it
                    s = open(recodeName).readline()
                    data = json.loads(s)
                    for wkt, comment, recodes in data:
                        geom = ogr.CreateGeometryFromWkt(wkt)
                        # 'old' key in the dictionary comes back as a string
                        # due to the JSON spec. Create a new dictionary
                        recodesAsInts = {}
                        for key in recodes:
                            recodesAsInts[int(key)] = recodes[key]
                        self.recodeList.append((geom, comment, recodesAsInts))

            # Create a new layer with the same dataset, but of instance
            # 'RecodeRasterLayer' which knows how to perform recodes on the fly.
            newLayer = RecodeRasterLayer(layerMgr, self)
            newLayer.open(oldLayer.gdalDataset, size.width(), size.height(), 
                    oldLayer.stretch, oldLayer.lut)

            layerMgr.addLayer(newLayer)
            self.recodeLayer = newLayer

            # determine the range of data
            dataInfo = numpy.iinfo(numpyType)
            self.dataRange = (dataInfo.min, dataInfo.max)

            # refresh display
            self.recodeLayer.getImage()
            self.viewer.viewwidget.viewport().update()

            # Update menu items so they are enabled
            self.startAct.setEnabled(False)
            self.recodeAct.setEnabled(True)
            self.showOutlinesAct.setEnabled(True)
            self.editCodesAct.setEnabled(True)
            self.saveRecodesAct.setEnabled(True)

    def recodePolygon(self):
        """
        Called when the 'Recode Polygon' menu option is selected.
        Tells TuiView to select a polygon.
        """
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_POLYGON, id(self))

    def newPolySelect(self, toolInfo):
        """
        Called in responce to a new polygon being selected.
        """
        # turn off the tool
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))

        # get the polygon as an ogr.Geometry
        geom = toolInfo.getOGRGeometry()

        # display the dialog with the recodes
        dlg = RecodeDialog(self.viewer, self.dataRange)
        if dlg.exec_() == RecodeDialog.Accepted:
            recodedValues = dlg.getRecodedValues()
            comment = dlg.getComment()
            
            if len(recodedValues) > 0:
                self.recodeList.append((geom, comment, recodedValues))

                self.recodeLayer.getImage()
                self.viewer.viewwidget.viewport().update()

    def toggleOutlines(self, checked):
        """
        Toggle the outlines. Sets the drawOutlines var
        and refreshed display.
        """
        self.recodeLayer.drawOutlines = checked
        self.recodeLayer.getImage()
        self.viewer.viewwidget.viewport().update()

    def editCodes(self):
        """
        Called in response the the 'Edit Codes' menu option.
        Tell TuiView to select a point.
        """
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))

    def newLocationSelected(self, queryInfo):
        """
        A new point was selected - presumeably in response to the 
        request in the editCodes() function. 
        """
        # turn off the tool.
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))

        # find it the polygon that constains this point
        # first create a point
        ptGeom = ogr.Geometry(ogr.wkbPoint)
        ptGeom.AddPoint(queryInfo.easting, queryInfo.northing)
        foundIdx = None
        for idx, (geom, comment, recodes) in enumerate(self.recodeList):
            if geom.Contains(ptGeom):
                # found one. Should we always stop here?
                foundIdx = idx
                break

        if foundIdx is None:
            QMessageBox.critical(self.viewer, name(), 
                        "No polygon found at point")
            return

        geom, comment, oldrecodes = self.recodeList[foundIdx]

        # show the dialog
        dlg = RecodeDialog(self.viewer, self.dataRange, comment, oldrecodes)
        if dlg.exec_() == RecodeDialog.Accepted:
            recodedValues = dlg.getRecodedValues()
            comment = dlg.getComment()
            
            if len(recodedValues) == 0:
                del self.recodeList[foundIdx]
            else:
                self.recodeList[foundIdx] = (geom, comment, recodedValues)
            
            self.recodeLayer.getImage()
            self.viewer.viewwidget.viewport().update()

    def saveRecodes(self):
        """
        Save the recodes to a json file. Called in response to
        menu option.
        """
        # turn ogr.Geometry's into WKT so they can be saved
        data = []
        for geom, comment, recodes in self.recodeList:
            wkt = geom.ExportToWkt()
            data.append((wkt, comment, recodes))

        s = json.dumps(data)

        # find filename to save to
        fname = self.recodeLayer.filename + RECODE_EXT
        fileobj = open(fname, 'w')
        # write the info
        fileobj.write(s + '\n')
        fileobj.close()
        self.viewer.showStatusMessage("Recodes saved to %s" % fname)

class RecodeRasterLayer(viewerlayers.ViewerRasterLayer):
    """
    Our Layer class derived from a normal raster layer. 
    Gets the image data like normal, then applies the recodes
    """
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
        """
        Derived function. Calls the base class to get the image
        then recodes it.
        """
        # call base class implementation.
        viewerlayers.ViewerRasterLayer.getImage(self)
        if self.image.isNull():
            return
        data = self.image.viewerdata

        # get info about where we are.
        extent = self.coordmgr.getWorldExtent()
        (xsize, ysize) = (self.coordmgr.dspWidth, self.coordmgr.dspHeight)

        # apply the recodes
        for geom, comment, recodes in self.recode.recodeList:
            # create a mask
            mask = vectorrasterizer.rasterizeGeometry(geom, extent, 
                    xsize, ysize, 1, True)
            # convert to 0s and 1s to bool
            mask = (mask == 1)

            # apply the codes
            # always sort on the old value??
            for old in sorted(recodes.keys()):
                new = recodes[old]
                subMask = mask & (data == old)
                data[subMask] = new

        # create the image by re-running the lut
        self.image = self.lut.applyLUTSingle(data, self.image.viewermask)

        if self.drawOutlines:
            # paint the outlines onto the image using QPainter
            paint = QPainter(self.image)

            drawpt = QPoint(0, 0) # top left

            # go through the polygons again - can't do this in one
            # pass as the colour we want for the outlines might not
            # be in the LUT.
            for geom, comment, recodes in self.recode.recodeList:
                # this time just get the outlines
                mask = vectorrasterizer.rasterizeGeometry(geom, extent, 
                    xsize, ysize, 1, False)
                # create an image from our mask using our oulinelut
                bgra = self.outlinelut[mask]
                outlineimage = QImage(bgra.data, xsize, ysize, QImage.Format_ARGB32)
                # draw this image onto the original
                paint.drawImage(drawpt, outlineimage)
            paint.end()

class RecodeDialog(QDialog):
    """
    Dialog that allows enter to specify what sort of recoding is to
    happen.
    """
    def __init__(self, parent, dataRange, comment=None, recodedValues=None):
        QDialog.__init__(self, parent)

        self.setWindowTitle("Recode")

        self.tableModel = RecodeTableModel(self, dataRange, recodedValues)
        self.tableView = QTableView(self)
        self.tableView.setModel(self.tableModel)

        self.commentEdit = QLineEdit(self)
        if comment is not None:
            self.commentEdit.setText(comment)

        self.recodeLayout = QVBoxLayout()
        self.recodeLayout.addWidget(self.tableView)
        self.recodeLayout.addWidget(self.commentEdit)

        self.okButton = QPushButton(self, clicked=self.accept)
        self.okButton.setText("OK")

        self.cancelButton = QPushButton(self, clicked=self.reject)
        self.cancelButton.setText("Cancel")

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addLayout(self.recodeLayout)
        self.mainLayout.addLayout(self.buttonLayout)

        self.setLayout(self.mainLayout)
        self.resize(200, 500)

    def getRecodedValues(self):
        """
        returns dictionary of recoded values as user 
        has edited them
        """
        return self.tableModel.recodedValues

    def getComment(self):
        """
        Returns comment as entered by the user
        """
        return self.commentEdit.text()

class RecodeTableModel(QAbstractTableModel):
    """
    Table model. Basically provides information to be displayed
    in the table of recodes.
    """
    def __init__(self, parent, dataRange, recodedValues=None):
        QAbstractTableModel.__init__(self, parent)
        self.dataRange = dataRange
        if recodedValues is None:
            recodedValues = {}
        self.recodedValues = recodedValues

    def rowCount(self, parent):
        return self.dataRange[1] - self.dataRange[0]

    def columnCount(self, parent):
        "Just old and new columns"
        return 2

    def headerData(self, section, orientation, role):
        """
        Get the header labels
        """
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return "Old"
            else:
                return "New"
        return None

    def flags(self, index):
        """
        Flags - the second column is editable
        """
        column = index.column()
        if column == 1:
            return Qt.ItemIsEditable | Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled

    def data(self, index, role):
        """
        Get the data for a cell.
        """
        if role == Qt.DisplayRole:
            column = index.column()
            row = index.row() - self.dataRange[0]

            if column == 1 and row in self.recodedValues:
                # return 'new' code from our dictionary
                return self.recodedValues[row]
            else:
                # just return the row value which happens to be the 'old'
                return str(row)
        return None

    def setData(self, index, value, role):
        """
        Update data from user entry. 
        """
        if role == Qt.EditRole:
            column = index.column()
            if column == 0:
                # we don't edit the 'old'
                return False

            try:
                value = int(value)
            except TypeError:
                # something that can't be turned into an int. Ignore
                return False

            row = index.row() - self.dataRange[0]
            self.recodedValues[row] = value

            # update display
            self.dataChanged.emit(index, index)
            return True

        return False
