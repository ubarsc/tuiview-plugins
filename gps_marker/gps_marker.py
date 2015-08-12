"""
GPS Marker plugin

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

# Needs gpsd + Python bindings installed
# Python3 version of bindings here: https://github.com/tpoche/gps-python3
import gps
from tuiview import pluginmanager
from PyQt4.QtCore import SIGNAL, QObject, QTimer
from PyQt4.QtGui import QAction, QApplication, QMessageBox
from osgeo import osr

# set in action() below
GEOLINKED_VIEWERS = None

def name():
    return 'GPS Marker'

def author():
    return 'Sam Gillingham'

class GPSMarker(QObject):
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer
        self.gpsd = None
        self.timer = None
        self.coordTrans = None

        self.startAct = QAction(self)
        self.startAct.setText("Start Logging")
        self.connect(self.startAct, SIGNAL("triggered()"), self.startLogging)

        self.endAct = QAction(self)
        self.endAct.setText("End Logging")
        self.connect(self.endAct, SIGNAL("triggered()"), self.endLogging)

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
            self.connect(self.timer, SIGNAL("timeout()"), self.updateGPS)
        self.timer.start(1000)
        self.setEnableLogging(False)
        self.setOtherGPSMarkerState(False)
    
    def endLogging(self, updateOthers=True):
        if self.gpsd is not None:
            self.gpsd.stream(gps.WATCH_DISABLE)

        if self.timer is not None:
            self.timer.stop()

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
                    wkt = layer.gdalDataset.GetGetTransform()
                    if wkt is not None and wkt != '':
                        gpsSR = osr.SpatialReference()
                        gpsSR.ImportFromEPSG(4327) # what GPS uses apparently
                        tuiviewSR = osr.SpatialReference()
                        tuiviewSR.ImportFromWkt(wkt)
                        self.coordTrans = osr.CoordinateTransformation(gpsSR, tuiviewSR)
                        break
                        

    def updateGPS(self):
        if self.gpsd is not None:
            try:
                report = self.gpsd.next()

                if self.coordTrans is None:
                    self.setCoordinateTransform()
                # still could have failed
                if self.coordTrans is not None:

                    print(report)
                
                    print(self.gpsd.fix.longitude, self.gpsd.fix.latitude)
            except StopIteration:
                # no data
                pass


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
        
        
