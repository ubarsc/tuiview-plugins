"""
Timeseries Plot plugin

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

def name():
    "Needed by TuiView"
    return 'Timeseries Plot'

def author():
    "Needed by TuiView"
    return 'Sam Gillingham'

def description():
    "Needed by TuiView"
    return 'Creates timeseries plots for points and polygons from images loaded in the viewer'

def action(actioncode, viewer):
    "Needed by TuiView"
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = TimeseriesPlot(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
        
class TimeseriesPlot(QObject):
    """
    Object that is the plugin. Create actions and menu.
    """
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer

        # Create actions
        self.pointAct = QAction(self, triggered=self.pointTimeseries)
        self.pointAct.setText("Do timeseries analysis on a point")

        self.polyAct = QAction(self, triggered=self.polyTimeseries)
        self.polyAct.setText("Do timeseries analysis on a polygon")

        # Create menu
        tseriesMenu = viewer.menuBar().addMenu("T&imeseries")
        tseriesMenu.addAction(self.pointAct)
        tseriesMenu.addAction(self.polyAct)

        # connect to signals that get fired when polygons, points
        # etc get fired.
        viewer.viewwidget.polygonCollected.connect(self.newPolySelected)
        viewer.viewwidget.locationSelected.connect(self.newLocationSelected)

    def pointTimeseries(self):
        """
        Tell TuiView to select a point.
        """
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))

    def newLocationSelected(self, queryInfo):
        """
        A point has been selected
        """
        # turn off the tool
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))

        # queryInfo.data contains the data for the top layer, but we 
        # need to go through each layer
        data = []
        steps = []
        layerMgr = self.viewer.viewwidget.layers
        count = 0
        for layer in layerMgr.layers:
            if isinstance(layer, viewerlayers.ViewerRasterLayer):
                # it is a raster layer, get out data at queryInfo.easting, queryInfo.northing
                imgData = layer.image.viewerdata
                imgMask = layer.image.viewermask

                col, row = layer.coordmgr.world2display(queryInfo.easting, 
                                    queryInfo.northing)

                mask = imgMask[row, col]
                if mask == viewerLUT.MASK_IMAGE_VALUE:
                    if isinstance(imgData, numpy.ndarray):
                        # single band image
                        val = imgData[row, col]
                    else:
                        # 3 band image
                        val = []
                        for band in imgData:
                            val.append(band[row, col])

                    # check there isn't a mix of single band and multi band
                    if len(data) > 0 and isinstance(val, list) != isinstance(data[0], list):
                        QMessageBox.critical(self.viewer, name(), 
                            "Images cannot be a mix of single and multi bands")
                        return

                    data.append(val)
                    steps.append(count)

                count += 1

        print(data, steps)

    def polyTimeseries(self):
        """
        Tell TuiView to select a polygon.
        """
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_POLYGON, id(self))
        
    def newPolySelected(self, toolInfo):
        """
        Called in responce to a new polygon being selected.
        """
        # turn off the tool
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))
