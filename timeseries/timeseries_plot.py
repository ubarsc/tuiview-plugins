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
from tuiview.plotscalingdialog import PlotScalingDialog
from tuiview.viewerwidget import VIEWER_TOOL_POLYGON, VIEWER_TOOL_NONE
from tuiview.viewerwidget import VIEWER_TOOL_QUERY

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QActionGroup
from PyQt5.QtWidgets import QVBoxLayout, QDockWidget, QWidget, QToolBar
from PyQt5.QtGui import QPen, QIcon

PLOT_PADDING = 0.05  # of the range of data. Pads this amount above and below min/max

# methods for summarizing a polygon
SUMMARY_MIN = 0
SUMMARY_MAX = 1
SUMMARY_MEAN = 2
SUMMARY_MEDIAN = 3
SUMMARY_STDDEV = 4

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
        QDockWidget.__init__(self, "Timeseries", parent)

        # save this so the data type checks in the scaling dialog work
        self.lastData = None 
        self.lastSteps = None

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()
        self.mainLayout = QVBoxLayout()

        self.plotWidget = plotwidget.PlotLineWidget(self)

        self.whitePen = QPen(Qt.white)
        self.whitePen.setWidth(1)
        self.redPen = QPen(Qt.red)
        self.redPen.setWidth(1)
        self.greenPen = QPen(Qt.green)
        self.greenPen.setWidth(1)
        self.bluePen = QPen(Qt.blue)
        self.bluePen.setWidth(1)

        self.plotScalingAction = QAction(self, triggered=self.onPlotScaling)
        self.plotScalingAction.setText("Set Plot Scaling")
        self.plotScalingAction.setStatusTip("Set Plot Scaling")
        icon = QIcon(":/viewer/images/setplotscale.png")
        self.plotScalingAction.setIcon(icon)

        self.savePlotAction = QAction(self, triggered=self.savePlot)
        self.savePlotAction.setText("&Save Plot")
        self.savePlotAction.setStatusTip("Save Plot")
        self.savePlotAction.setIcon(QIcon(":/viewer/images/saveplot.png"))

        # toolbar
        self.toolbar = QToolBar(self.dockWidget)
        self.toolbar.addAction(self.plotScalingAction)
        self.toolbar.addAction(self.savePlotAction)

        self.mainLayout.addWidget(self.toolbar)
        self.mainLayout.addWidget(self.plotWidget)
        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

        self.resize(400, 300)

        # allow plot scaling to be changed by user
        # Min, Max. None means 'auto'.
        self.plotScaling = (None, None)

    def savePlot(self):
        """
        Save the plot as a file. Either .pdf or .ps QPrinter
        chooses format based on extension.
        """
        from PyQt5.QtGui import QPainter
        from PyQt5.QtPrintSupport import QPrinter
        from PyQt5.QtWidgets import QFileDialog
        fname, filter = QFileDialog.getSaveFileName(self, "Plot File", 
                    filter="PDF (*.pdf);;Postscript (*.ps)")
        if fname != '':
            printer = QPrinter()
            printer.setOrientation(QPrinter.Landscape)
            printer.setColorMode(QPrinter.Color)
            printer.setOutputFileName(fname)
            printer.setResolution(96)
            painter = QPainter()
            painter.begin(printer)
            self.plotWidget.render(painter)
            painter.end()

    def onPlotScaling(self):
        """
        Allows the user to change the Y axis scaling of the plot
        """
        dlg = PlotScalingDialog(self, self.plotScaling, self.lastData)

        if dlg.exec_() == PlotScalingDialog.Accepted:
            self.plotScaling = dlg.getScale()
            # re-plot the 'last' data
            self.plotData(self.lastData, self.lastSteps)

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

        # get the users scaling
        minVal, maxVal = self.plotScaling

        # substitute auto vals
        if minVal is None:
            minVal = data.min()
        if maxVal is None:
            maxVal = data.max()

        # set the X&Y Range a bit larger than the data
        # we always do it regardless of whether this is user range, or auto
        rangeVal = maxVal - minVal
        paddingAmount = rangeVal * PLOT_PADDING

        minVal -= paddingAmount
        maxVal += paddingAmount

        # update plot
        self.plotWidget.setYRange(minVal, maxVal)

        # save the data
        self.lastData = data
        self.lastSteps = steps
        
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
        self.pointActive = False
        self.polyActive = False
        self.lastGeom = None # last polygon
        self.summaryMethod = SUMMARY_MEAN # set setChecked on self.meanAct below

        # Create actions
        self.pointAct = QAction(self, triggered=self.pointTimeseries)
        self.pointAct.setText("Do timeseries analysis on a &point")

        self.polyAct = QAction(self, triggered=self.polyTimeseries)
        self.polyAct.setText("Do timeseries analysis on a p&olygon")

        self.minAct = QAction(self, triggered=self.summaryMin)
        self.minAct.setText("Minimum")
        self.minAct.setCheckable(True)

        self.maxAct = QAction(self, triggered=self.summaryMax)
        self.maxAct.setText("Maximum")
        self.maxAct.setCheckable(True)

        self.meanAct = QAction(self, triggered=self.summaryMean)
        self.meanAct.setText("Mean")
        self.meanAct.setCheckable(True)
        self.meanAct.setChecked(True)

        self.medianAct = QAction(self, triggered=self.summaryMedian)
        self.medianAct.setText("Median")
        self.medianAct.setCheckable(True)

        self.stddevAct = QAction(self, triggered=self.summaryStdDev)
        self.stddevAct.setText("Standard Deviation")
        self.stddevAct.setCheckable(True)

        self.polySummary = QActionGroup(self)
        self.polySummary.setExclusive(True)
        self.polySummary.addAction(self.minAct)
        self.polySummary.addAction(self.maxAct)
        self.polySummary.addAction(self.meanAct)
        self.polySummary.addAction(self.medianAct)
        self.polySummary.addAction(self.stddevAct)

        # Create menu
        tseriesMenu = viewer.menuBar().addMenu("T&imeseries")
        tseriesMenu.addAction(self.pointAct)
        tseriesMenu.addAction(self.polyAct)

        polySummaryMenu = tseriesMenu.addMenu("Polygon Summary Method")
        polySummaryMenu.addAction(self.minAct)
        polySummaryMenu.addAction(self.maxAct)
        polySummaryMenu.addAction(self.meanAct)
        polySummaryMenu.addAction(self.medianAct)
        polySummaryMenu.addAction(self.stddevAct)

        # connect to signals that get fired when polygons, points
        # etc get fired.
        viewer.viewwidget.polygonCollected.connect(self.newPolySelected)
        viewer.viewwidget.locationSelected.connect(self.newLocationSelected)

    def pointTimeseries(self):
        """
        Tell TuiView to select a point.
        """
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))
        self.pointActive = True

    def newLocationSelected(self, queryInfo):
        """
        A point has been selected
        """
        if not self.pointActive:
            # we didn't request this
            return

        # turn off the tool
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))
        self.pointActive = False

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

                        # are we inside this image?
                        if (col < 0 or row < 0 or row >= imgData.shape[0] or 
                                col >= imgData.shape[1]):
                            continue

                        val = imgData[row, col]
                    else:
                        # 3 band image
                        val = []
                        for band in imgData:
                            # are we inside this image?
                            if (col < 0 or row < 0 or row >= band.shape[0] or 
                                    col >= band.shape[1]):
                                continue

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
            self.openPlotWindow()

        data = numpy.array(data)
        steps = numpy.array(steps)
        self.plotWindow.plotData(data, steps)

    def openPlotWindow(self):
        self.plotWindow = TimeseriesDockWidget(self.viewer)
        self.viewer.addDockWidget(Qt.TopDockWidgetArea, self.plotWindow)
        self.plotWindow.setFloating(True) # detach so it isn't docked by default
        # this works to prevent it trying to dock when dragging
        # but double click still works
        self.plotWindow.setAllowedAreas(Qt.NoDockWidgetArea) 

        # grab the signal the profileDock sends when it is closed
        self.plotWindow.profileClosed.connect(self.profileClosed)

    def polyTimeseries(self):
        """
        Tell TuiView to select a polygon.
        """
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_POLYGON, id(self))
        self.polyActive = True
        
    def newPolySelected(self, toolInfo):
        """
        Called in responce to a new polygon being selected.
        """
        if not self.polyActive:
            # not requested by us
            return

        # turn off the tool
        self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))
        self.polyActive = False

        # get the polygon as an ogr.Geometry
        self.lastGeom = toolInfo.getOGRGeometry()

        self.doPolygonSummary()

    def doPolygonSummary(self):
        """
        Does summary of self.lastGeom on all layers and plots results
        Split into separate function so it can be easily called again
        with new summary method
        """
        if self.lastGeom is None:
            return

        data = []
        steps = []
        layerMgr = self.viewer.viewwidget.layers
        count = 0
        for layer in layerMgr.layers:
            if isinstance(layer, viewerlayers.ViewerRasterLayer):
                # it is a raster layer, get out data inside geom
                imgData = layer.image.viewerdata
                imgMask = layer.image.viewermask

                # get info about where we are.
                extent = layer.coordmgr.getWorldExtent()
                (xsize, ysize) = (layer.coordmgr.dspWidth, layer.coordmgr.dspHeight)

                # create a mask
                mask = vectorrasterizer.rasterizeGeometry(self.lastGeom, extent, 
                        xsize, ysize, 1, True)
                # convert to 0s and 1s to bool and add in valid data mask
                mask = (mask == 1) & (imgMask == viewerLUT.MASK_IMAGE_VALUE)

                if not mask.any():
                    # nothing here
                    continue
        
                # get the data
                if isinstance(imgData, numpy.ndarray):
                    # single band image

                    polyData = imgData[mask]
                    val = self.summarizeData(polyData)
                else:
                    # 3 band image
                    val = []
                    for band in imgData:
                        polyData = band[mask]
                        val.append(self.summarizeData(polyData))

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
            self.openPlotWindow()

        data = numpy.array(data)
        steps = numpy.array(steps)
        self.plotWindow.plotData(data, steps)

    def summarizeData(self, data):
        """
        Summarizes the given array using self.summaryMethod
        """
        if self.summaryMethod == SUMMARY_MIN:
            return data.min()
        elif self.summaryMethod == SUMMARY_MAX:
            return data.max()
        elif self.summaryMethod == SUMMARY_MEAN:
            return data.mean()
        elif self.summaryMethod == SUMMARY_MEDIAN:
            return numpy.median(data)
        elif self.summaryMethod == SUMMARY_STDDEV:
            return data.std()
        else:
            raise ValueError('Unknown summary method')

    def profileClosed(self, profileDock):
        """
        Plot dock window has been closed. Remove our reference 
        so we open a new one next time.
        """
        self.plotWindow = None

    def summaryMin(self):
        self.summaryMethod = SUMMARY_MIN
        self.doPolygonSummary()

    def summaryMax(self):
        self.summaryMethod = SUMMARY_MAX
        self.doPolygonSummary()

    def summaryMean(self):
        self.summaryMethod = SUMMARY_MEAN
        self.doPolygonSummary()

    def summaryMedian(self):
        self.summaryMethod = SUMMARY_MEDIAN
        self.doPolygonSummary()

    def summaryStdDev(self):
        self.summaryMethod = SUMMARY_STDDEV
        self.doPolygonSummary()
