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
from tuiview import pluginmanager
from tuiview import viewerlayers
from tuiview import vectorrasterizer
from tuiview import viewerLUT
from tuiview import plotwidget
from tuiview.viewerwidget import VIEWER_TOOL_POLYGON, VIEWER_TOOL_NONE
from tuiview.viewerwidget import VIEWER_TOOL_QUERY

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout, QDockWidget, QWidget
from PyQt5.QtGui import QPen

PLOT_PADDING = 0.2  # of the range of data

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

class TimeseriesDockWidget(QDockWidget):
    """
    Dockable window that displays the timeseries plot
    """
    # signals
    profileClosed = pyqtSignal(QDockWidget, name='profileClosed')

    def __init__(self, parent):
        QDockWidget.__init__(self, "Profile", parent)

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()
        self.mainLayout = QVBoxLayout()

        self.plotWidget = plotwidget.PlotLineWidget(self)
        self.mainLayout.addWidget(self.plotWidget)

        self.whitePen = QPen(Qt.white)
        self.whitePen.setWidth(1)
        self.redPen = QPen(Qt.red)
        self.redPen.setWidth(1)
        self.greenPen = QPen(Qt.green)
        self.greenPen.setWidth(1)
        self.bluePen = QPen(Qt.blue)
        self.bluePen.setWidth(1)

        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

    def plotData(self, data, steps):
        """
        Put the data into our plotWidget
        """
        # get rid of curves from last time
        self.plotWidget.removeCurves()

        if len(data.shape) == 2:
            # multi band image
            penList = [self.redPen, self.greenPen, self.bluePen]
            for band in range(3):
                bandData = data[..., band]

                #print(steps, bandData)
                curve = plotwidget.PlotCurve(steps, bandData, penList[band])
                self.plotWidget.addCurve(curve)
        else:
            # single band
            curve = plotwidget.PlotCurve(steps, data, self.whitePen)
            self.plotWidget.addCurve(curve)

        # set the Y Range a bit larger than the data
        minVal = data.min()
        maxVal = data.max()
        rangeVal = maxVal - minVal
        paddingAmount = rangeVal * PLOT_PADDING

        minVal -= paddingAmount
        maxVal += paddingAmount

        self.plotWidget.setYRange(minVal, maxVal)
        
    def closeEvent(self, event):
        """
        Window is being closed - inform plugin
        """
        self.profileClosed.emit(self)

class TimeseriesPlot(QObject):
    """
    Object that is the plugin. Create actions and menu.
    """
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer
        self.plotWindow = None

        # Create actions
        self.pointAct = QAction(self, triggered=self.pointTimeseries)
        self.pointAct.setText("Do timeseries analysis on a point")

        self.polyAct = QAction(self, triggered=self.polyTimeseries)
        self.polyAct.setText("Do timeseries analysis on a polygon")
        self.polyAct.setEnabled(False)

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
        if self.plotWindow is None:
            self.plotWindow = TimeseriesDockWidget(self.viewer)
            self.viewer.addDockWidget(Qt.TopDockWidgetArea, self.plotWindow)
            self.plotWindow.setFloating(True) # detach so it isn't docked by default
            # this works to prevent it trying to dock when dragging
            # but double click still works
            self.plotWindow.setAllowedAreas(Qt.NoDockWidgetArea) 

            # grab the signal the profileDock sends when it is closed
            self.plotWindow.profileClosed.connect(self.profileClosed)


        data = numpy.array(data)
        steps = numpy.array(steps)
        self.plotWindow.plotData(data, steps)

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

    def profileClosed(self, profileDock):
        """
        Plot dock window has been closed. Remove our reference 
        so we open a new one next time.
        """
        self.plotWindow = None
