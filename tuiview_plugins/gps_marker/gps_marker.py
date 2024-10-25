"""
GPS Marker plugin

Copy into one of the locations mentioned here:
https://github.com/ubarsc/tuiview/wiki/Plugins
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

# Needs gpsd + Python bindings installed
# Python3 version of bindings here: https://github.com/tpoche/gps-python3

import math
try:
    import gps
except ImportError:
    print('gps module not found - plugin will not work as expected')
from tuiview import pluginmanager
from tuiview.viewerlayers import CURSOR_CROSSHAIR
from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QAction
from osgeo import osr

# set in action() below
GEOLINKED_VIEWERS = None


def name():
    return 'GPS Marker'


def author():
    return 'Sam Gillingham'


def description():
    return 'Shows GPS location on the viewer. Requires gpsd.'


class GPSMarker(QObject):
    """
    Class that is the plugin
    """
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer
        self.gpsd = None
        self.timer = None
        self.coordTrans = None

        self.startAct = QAction(self, triggered=self.startLogging)
        self.startAct.setText("Start Logging")

        self.endAct = QAction(self, triggered=self.endLogging)
        self.endAct.setText("End Logging")

        # see what other viewers are doing
        state = self.getOtherGPSMarkerState()
        self.setEnableLogging(state)

        gpsMenu = viewer.menuBar().addMenu("&GPS")
        gpsMenu.addAction(self.startAct)
        gpsMenu.addAction(self.endAct)

    def getOtherGPSMarkerState(self):
        """
        Sees if other GPS Marker plugins are logging or not
        """
        state = True
        app = QApplication.instance()
        for plugin in app.pluginHandlers:
            if isinstance(plugin, GPSMarker) and plugin is not self:
                state = plugin.loggingEnabled
                break
        return state

    def setOtherGPSMarkerState(self, state):
        """
        Tells all the other GPS Marker plugins of the new state
        so they can update GUI
        """
        app = QApplication.instance()
        for plugin in app.pluginHandlers:
            if isinstance(plugin, GPSMarker) and plugin is not self:
                if not state:
                    plugin.setEnableLogging(state)
                else:
                    # it might not have been us that started logging
                    plugin.endLogging(False)

    def setEnableLogging(self, state):
        """
        Called by this object, but also by other instances
        when they need to update the GUI for this plugin
        """
        self.startAct.setEnabled(state)
        self.endAct.setEnabled(not state)
        self.loggingEnabled = state

    def startLogging(self):
        try:
            if self.gpsd is None:
                self.gpsd = gps.GPS(mode=gps.WATCH_ENABLE)
            else:
                self.gpsd.stream(gps.WATCH_ENABLE)
        except OSError: 
            QMessageBox.critical(self.viewer, name(), "Unable to connect to GPS")
            return

        if self.timer is None:
            self.timer = QTimer()
            self.timer.timeout.connect(self.updateGPS)
        self.timer.start(1000)
        self.setEnableLogging(False)
        self.setOtherGPSMarkerState(False)
    
    def endLogging(self, updateOthers=True):
        if self.gpsd is not None:
            self.gpsd.stream(gps.WATCH_DISABLE)

        if self.timer is not None:
            self.timer.stop()

        GEOLINKED_VIEWERS.removeQueryPointAll(id(self))
        self.setEnableLogging(True)
        if updateOthers:
            self.setOtherGPSMarkerState(True)

    def setCoordinateTransform(self):
        """
        Sets up a coordinate transform between the GPS data and the
        coordinate system in use by the viewers. Saved in self.coordTrans
        """
        if GEOLINKED_VIEWERS is not None:
            for viewer in GEOLINKED_VIEWERS.viewers:
                layer = viewer.viewwidget.layers.getTopRasterLayer()
                if layer is not None:
                    wkt = layer.gdalDataset.GetProjection()
                    if wkt is not None and wkt != '':
                        gpsSR = osr.SpatialReference()
                        # GPS uses 4328 but I can't get to work with 
                        # GDAL so using 4326 instead. Hopefully not a big difference...
                        gpsSR.ImportFromEPSG(4326)
                        tuiviewSR = osr.SpatialReference()
                        tuiviewSR.ImportFromWkt(wkt)
                        self.coordTrans = osr.CreateCoordinateTransformation(gpsSR, tuiviewSR)
                        if self.coordTrans is None:
                            print('Unable to create coordinate transform. ' + 
                                'Check GDAL built with proj.4 support')
                        break
                        
    def updateGPS(self):
        if self.gpsd is not None:
            try:
                self.gpsd.next()

                if self.coordTrans is None:
                    self.setCoordinateTransform()
                # still could have failed
                if self.coordTrans is not None:

                    long = self.gpsd.fix.longitude
                    lat = self.gpsd.fix.latitude
                    if (lat != 0 and not math.isnan(lat) and 
                            long != 0 and not math.isnan(long)):
                        (easting, northing, _) = self.coordTrans.TransformPoint(long, lat)
                        if easting == 0 or northing == 0:
                            print('coord transform failed')
                        else:
                            GEOLINKED_VIEWERS.setQueryPointAll(id(self), 
                                easting, northing, Qt.white, 
                                cursor=CURSOR_CROSSHAIR, size=5)

            except StopIteration:
                # no data
                print('no data')


def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_INIT:
        # save the instance of geolinked viewers
        global GEOLINKED_VIEWERS
        GEOLINKED_VIEWERS = viewer

    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = GPSMarker(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
        
        
