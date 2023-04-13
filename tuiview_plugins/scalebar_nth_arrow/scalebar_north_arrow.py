"""
Scalebar and North Arrow plugin

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

from tuiview import pluginmanager
from tuiview import viewerlayers
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QAction, QApplication
from PyQt5.QtGui import QPen, QPainter, QColor

LINE_WIDTH = 1
LINE_COLOR = QColor(255, 255, 0, 255)
MARGIN_FRACTION = 0.1
ARROW_HEIGHT_FRACTION = 0.15

def name():
    return 'Scalebar and North Arrow'


def author():
    return 'Sam Gillingham'


def description():
    return 'Tool for adding a scalebar and/or north arrow'


class ScaleBarNthArrowQueryPointLayer(viewerlayers.ViewerQueryPointLayer):
    """
    Alternative implementation of viewerlayers.ViewerQueryPointLayer that
    calls the base class but also draws scale bar and north arrow if required.
    
    Done this way as ViewerQueryPointLayer always stays on top of all the layers.
    """
    def __init__(self, qplayer):
        # basically a copy constructor
        self.coordmgr = qplayer.coordmgr
        self.queryPoints = qplayer.queryPoints
        self.image = qplayer.image
        
    def getImage(self):
        """
        """
        # draw any query points
        super().getImage()
        # now draw our stuff
        print("ScaleBarNthArrowQueryPointLayer")

        pen = QPen()
        pen.setWidth(LINE_WIDTH)
        pen.setColor(LINE_COLOR)

        paint = QPainter(self.image)
        paint.setPen(pen)
        
        # nth arrow
        margin = self.coordmgr.dspWidth * MARGIN_FRACTION
        arrowX = int(self.coordmgr.dspWidth - margin)
        arrowY = int(margin)
        arrowHeight = int(self.coordmgr.dspHeight * ARROW_HEIGHT_FRACTION)
        paint.drawLine(arrowX, arrowY, arrowX, arrowY + arrowHeight)
        
        paint.end()
    
class ScaleBarNthArrow(QObject):
    def __init__(self, viewer):
        QObject.__init__(self)
        
        self.scaleBarAction = QAction(viewer)
        self.scaleBarAction.setCheckable(True)
        self.scaleBarAction.setText("Show Scale Bar")

        self.northArrowAction = QAction(viewer)
        self.northArrowAction.setCheckable(True)
        self.northArrowAction.setText("Show North Arrow")
        
        scaleNthArrowMenu = viewer.menuBar().addMenu("Scale Bar")
        scaleNthArrowMenu.addAction(self.scaleBarAction)
        scaleNthArrowMenu.addAction(self.northArrowAction)
        
        # install our version of the query point layer
        scalebarlayer = ScaleBarNthArrowQueryPointLayer(
                viewer.viewwidget.layers.queryPointLayer)
        viewer.viewwidget.layers.queryPointLayer = scalebarlayer
    
def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = ScaleBarNthArrow(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
