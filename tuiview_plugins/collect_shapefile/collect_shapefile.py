"""
Collect Shapefile plugin

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

import os
from tuiview import pluginmanager
from tuiview.viewerwidget import VIEWER_TOOL_POLYGON, VIEWER_TOOL_NONE
from tuiview.viewerwidget import VIEWER_TOOL_QUERY, VIEWER_TOOL_POLYLINE
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog, QApplication
from PySide6.QtGui import QAction
from osgeo import ogr
from osgeo import osr

DRIVERNAME = "ESRI Shapefile"
COLLECT_NONE = 0
COLLECT_POLY = 1
COLLECT_LINE = 2
COLLECT_POINT = 3


def name():
    return 'Collect Shapefile'


def author():
    return 'Sam Gillingham'


def description():
    return 'Tool for creating shapefiles by clicking on points on the viewer'


class CollectShapefile(QObject):
    """
    Class that contains the plugin
    """
    def __init__(self, viewer):
        QObject.__init__(self)
        self.ogrds = None
        self.ogrlyr = None
        self.collecting = COLLECT_NONE
        self.isCollecting = False
        self.viewer = viewer
        
        self.newPolyAction = QAction(viewer, triggered=self.newPolyFile)
        self.newPolyAction.setText("Create new Polygon Shapefile")

        self.newLineAction = QAction(viewer, triggered=self.newLineFile)
        self.newLineAction.setText("Create new Line Shapefile")

        self.newPointAction = QAction(viewer, triggered=self.newPointFile)
        self.newPointAction.setText("Create new Point Shapefile")
        
        self.closeAction = QAction(viewer, triggered=self.closeFile)
        self.closeAction.setText("Close Shapefile")
        self.closeAction.setEnabled(False)
        
        self.newFeatureAction = QAction(viewer, triggered=self.newFeature)
        self.newFeatureAction.setText("Collect Feature")
        self.newFeatureAction.setEnabled(False)

        collectMenu = viewer.menuBar().addMenu("&Collect")
        collectMenu.addAction(self.newPolyAction)
        collectMenu.addAction(self.newLineAction)
        collectMenu.addAction(self.newPointAction)
        collectMenu.addAction(self.closeAction)
        collectMenu.addAction(self.newFeatureAction)
        
        # connect to the signal given when user selected new feature
        viewer.viewwidget.polygonCollected.connect(self.newFeatureCollected)

        viewer.viewwidget.polylineCollected.connect(self.newFeatureCollected)
                
        viewer.viewwidget.locationSelected.connect(self.newFeatureCollected)

    def newPolyFile(self):
        "A polygon file"
        self.newFile(ogr.wkbPolygon)
        self.collecting = COLLECT_POLY

    def newLineFile(self):
        "a line file"
        self.newFile(ogr.wkbLineString)
        self.collecting = COLLECT_LINE

    def newPointFile(self):
        "a point file"
        self.newFile(ogr.wkbPoint)
        self.collecting = COLLECT_POINT

    def newFile(self, geomType):
        """
        Create shapefile of the desired type
        """
        fname, _ = QFileDialog.getSaveFileName(None, "Select Shape File name",
                "", "Shape Files (*.shp)")
        if fname is not None and fname != '':
            driver = ogr.GetDriverByName(DRIVERNAME)
            if driver is None:
                raise IOError("%s driver not available" % DRIVERNAME)
    
            self.ogrds = driver.CreateDataSource(fname)
            if self.ogrds is None:
                raise IOError("Unable to create %s" % fname)
    
            # work out the projection
            layer = self.viewer.viewwidget.layers.getTopRasterLayer()
            if layer is None:
                raise ValueError("No raster Layers loaded")
                
            wkt = layer.gdalDataset.GetProjection()
            srs = osr.SpatialReference()
            srs.ImportFromWkt(wkt)
                
            lyrName = os.path.basename(fname)
            lyrName, _ = os.path.splitext(lyrName)
            self.ogrlyr = self.ogrds.CreateLayer(lyrName, srs, geomType)
            if self.ogrlyr is None:
                self.ogrds = None
                raise IOError("Unable to create layer")
    
            self.newPolyAction.setEnabled(False)
            self.newLineAction.setEnabled(False)
            self.newPointAction.setEnabled(False)
            self.closeAction.setEnabled(True)
            self.newFeatureAction.setEnabled(True)
        
    def closeFile(self):
        """
        Close the current data source and reset gui
        """
        self.ogrds.SyncToDisk()
        self.ogrds = None
        self.ogrlyr = None
        self.newPolyAction.setEnabled(True)
        self.newLineAction.setEnabled(True)
        self.newPointAction.setEnabled(True)
        self.closeAction.setEnabled(False)
        self.newFeatureAction.setEnabled(False)
        self.collecting = COLLECT_NONE
        
    def newFeature(self):
        """
        Collect a new feature. Set the tool and wait for a signal
        """
        if self.collecting == COLLECT_POLY:
            self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_POLYGON, id(self))
        elif self.collecting == COLLECT_LINE:
            self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_POLYLINE, id(self))
        else:
            self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))
        self.isCollecting = True
        
    def newFeatureCollected(self, info):
        """
        Signal received that new data arrived. Handle appropriately.
        """
        if self.isCollecting:
            self.viewer.viewwidget.setActiveTool(VIEWER_TOOL_NONE, id(self))

            feat = ogr.Feature(self.ogrlyr.GetLayerDefn())
            
            if self.collecting == COLLECT_POLY:
                # PolygonToolInfo
                poly = info.getWorldPolygon()
            
                ogrpoly = ogr.Geometry(ogr.wkbPolygon)
                ogrring = ogr.Geometry(ogr.wkbLinearRing)
                for n in range(poly.size()):
                    pt = poly[n]
                    ogrring.AddPoint_2D(pt.x(), pt.y())
                
                ogrpoly.AddGeometry(ogrring)
                
                feat.SetGeometry(ogrpoly)
                
            elif self.collecting == COLLECT_LINE:
                # PolylineToolInfo
                poly = info.getWorldPolygon()
            
                feat = ogr.Feature(self.ogrlyr.GetLayerDefn())
                ogrline = ogr.Geometry(ogr.wkbLineString)
                for n in range(poly.size()):
                    pt = poly[n]
                    ogrline.AddPoint_2D(pt.x(), pt.y())
                
                feat.SetGeometry(ogrline)
                
            else:
                # QueryInfo
                feat = ogr.Feature(self.ogrlyr.GetLayerDefn())
                ogrpoint = ogr.Geometry(ogr.wkbPoint)
                ogrpoint.AddPoint_2D(info.easting, info.northing)
                feat.SetGeometry(ogrpoint)

            if self.ogrlyr.CreateFeature(feat) != 0:
                print("Failed to create feature in shapefile")
                
            self.ogrlyr.SyncToDisk()
                
            self.isCollecting = False


def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = CollectShapefile(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
