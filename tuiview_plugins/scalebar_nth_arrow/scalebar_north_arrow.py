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
from tuiview.viewerstrings import MESSAGE_TITLE
from PyQt5.QtCore import QObject, QRect, Qt
from PyQt5.QtWidgets import QAction, QApplication, QInputDialog, QFileDialog
from PyQt5.QtGui import QPen, QPainter, QColor, QFont, QImage

LINE_WIDTH = 1
LINE_COLOR = QColor(255, 255, 0, 255)
MARGIN_FRACTION = 0.02
ARROW_HEIGHT_FRACTION = 0.07
HALF_ARROW_FRACTION = 0.01
NORTH_CHARACTER = 'N'
SCALE_MIN_FRACTION = 0.3
SCALE_MAX_FRACTION = 0.6
SCALE_NOTCHES_SIZE = 0.005
M_TO_KM_THRESHOLD = 10000

FONT = QFont('FreeMono', 10, 100)


def name():
    return 'Scalebar and North Arrow'


def author():
    return 'Sam Gillingham'


def description():
    return 'Tool for adding a scalebar and/or north arrow'


class ScaleBarNthArrowQueryPointLayer(viewerlayers.ViewerQueryPointLayer):
    """
    Alternative implementation of viewerlayers.ViewerQueryPointLayer that
    calls the base class but also draws scale bar, north arrow, citation or
    logo if required.
    
    Done this way as ViewerQueryPointLayer always stays on top of all the layers.
    """
    def __init__(self, qplayer, nthArrow=True, scaleBar=True, 
            citation=None, logo=None):
        # basically a copy constructor
        self.coordmgr = qplayer.coordmgr
        self.queryPoints = qplayer.queryPoints
        self.image = qplayer.image
        self.nthArrow = nthArrow
        self.scaleBar = scaleBar
        self.citation = citation
        self.logo = logo
        
    def getImage(self):
        """
        Override the base class implementation
        """
        # draw any query points
        super().getImage()
        # check is image isNull - no image loaded or we aren't drawing
        if self.image.isNull() or (not self.nthArrow and not 
                self.scaleBar and self.citation is None and 
                self.logo is None):
            return
        # now draw our stuff

        pen = QPen()
        pen.setWidth(LINE_WIDTH)
        pen.setColor(LINE_COLOR)

        paint = QPainter(self.image)
        paint.setPen(pen)
        paint.setFont(FONT)
        fm = paint.fontMetrics()
        margin = int(self.coordmgr.dspWidth * MARGIN_FRACTION)

        if self.nthArrow:
            n_rect = fm.boundingRect(NORTH_CHARACTER)
        
            # nth arrow
            arrowX = self.coordmgr.dspWidth - margin
            arrowY = margin + n_rect.height()
            arrowHeight = int(self.coordmgr.dspHeight * ARROW_HEIGHT_FRACTION)
            # line
            paint.drawLine(arrowX, arrowY, arrowX, arrowY + arrowHeight)
            # arrow
            arrowSize = int(self.coordmgr.dspWidth * HALF_ARROW_FRACTION)
            paint.drawLine(arrowX, arrowY, arrowX - arrowSize, arrowY + arrowSize)
            paint.drawLine(arrowX, arrowY, arrowX + arrowSize, arrowY + arrowSize)
            # N character
            paint.drawText(int(arrowX - (n_rect.width() / 2)), arrowY, NORTH_CHARACTER)
            
        if self.scaleBar:
            yDspLoc = self.coordmgr.dspHeight - margin
            leftCoord = self.coordmgr.display2world(margin, yDspLoc)
            # check we actually have something loaded
            if leftCoord is not None:
                minSizeDsp = int(self.coordmgr.dspWidth * SCALE_MIN_FRACTION)
                maxSizeDsp = int(self.coordmgr.dspWidth * SCALE_MAX_FRACTION)
                minCoord = self.coordmgr.display2world(margin + minSizeDsp, yDspLoc)
                maxCoord = self.coordmgr.display2world(margin + maxSizeDsp, yDspLoc)
                
                minSizeWld = minCoord[0] - leftCoord[0]
                maxSizeWld = maxCoord[0] - leftCoord[0]
                mult = 10 ** len(str(int(maxSizeWld)))
                size = None
                while True:
                    size = int(maxSizeWld / mult) * mult
                    if size >= minSizeWld:
                        break
                    mult /= 10
                    
                dspXEnd, dspYEnd = self.coordmgr.world2display(leftCoord[0] + size, leftCoord[1])
                dspXEnd = int(dspXEnd)
                dspYEnd = int(dspYEnd)
                paint.drawLine(margin, yDspLoc, dspXEnd, dspYEnd)
                # notches
                halfNotchesSize = int((self.coordmgr.dspWidth * SCALE_NOTCHES_SIZE) / 2)
                paint.drawLine(margin, yDspLoc - halfNotchesSize, margin, yDspLoc + halfNotchesSize)
                paint.drawLine(dspXEnd, yDspLoc - halfNotchesSize, dspXEnd, yDspLoc + halfNotchesSize)
                # 0 point
                zeroRect = fm.boundingRect('0')
                paint.drawText(int(margin - (zeroRect.width() / 2)), yDspLoc - halfNotchesSize - 1, '0') 
                # end text
                if size > M_TO_KM_THRESHOLD:
                    size /= 1000
                    if int(size) == size:
                        size = int(size)
                    # do we need to show a decimal place?
                    sizeText = '{}km'.format(size)
                else:
                    sizeText = '{}m'.format(int(size))
                sizeRect = fm.boundingRect(sizeText)
                paint.drawText(int(dspXEnd - (sizeRect.width() / 2)), dspYEnd - halfNotchesSize - 1, sizeText)
                
        if self.citation is not None:
            rect = QRect(margin, margin, self.image.width() - margin * 2, 
                self.image.height() - margin * 2)
            paint.drawText(rect, Qt.AlignLeft | Qt.AlignTop, self.citation.replace('\\n', '\n'))
            
        if self.logo is not None:
            x = self.image.width() - margin - self.logo.width()
            y = self.image.height() - margin - self.logo.height()
            paint.drawImage(x, y, self.logo)
            
        paint.end()

    
class ScaleBarNthArrow(QObject):
    def __init__(self, viewer):
        QObject.__init__(self)
        
        self.scaleBarAction = QAction(viewer, toggled=self.stateChanged)
        self.scaleBarAction.setCheckable(True)
        self.scaleBarAction.setText("Show Scale Bar")

        self.northArrowAction = QAction(viewer, toggled=self.stateChanged)
        self.northArrowAction.setCheckable(True)
        self.northArrowAction.setText("Show North Arrow")
        
        self.citationAction = QAction(viewer, triggered=self.changeCitation)
        self.citationAction.setText("Set Citation text")
        
        self.logoAction = QAction(viewer, triggered=self.changeLogo)
        self.logoAction.setText("Set logo")
        
        scaleNthArrowMenu = viewer.menuBar().addMenu("Scale Bar")
        scaleNthArrowMenu.addAction(self.scaleBarAction)
        scaleNthArrowMenu.addAction(self.northArrowAction)
        scaleNthArrowMenu.addAction(self.citationAction)
        scaleNthArrowMenu.addAction(self.logoAction)
        
        # checked off to start with
        self.scalebarlayer = registerScaleBarNorthArrow(viewer, False, False, 
            None, None)
        self.viewer = viewer
        
    def stateChanged(self, checked):
        """
        Update what we are drawing from the actions 
        """
        self.scalebarlayer.nthArrow = self.northArrowAction.isChecked()
        self.scalebarlayer.scaleBar = self.scaleBarAction.isChecked()
        # redraw
        self.scalebarlayer.getImage()
        self.viewer.viewwidget.viewport().update()
        
    def changeCitation(self):
        """
        Update the citation
        """
        oldCitation = self.scalebarlayer.citation
        if oldCitation is None:
            oldCitation = ''
        citation, ok = QInputDialog.getText(self.viewer, MESSAGE_TITLE,
            "Enter text for citation (\\n for newline)", text=oldCitation)
        if ok:
            if citation == '':
                citation = None
            self.scalebarlayer.citation = citation
            # redraw
            self.scalebarlayer.getImage()
            self.viewer.viewwidget.viewport().update()
            
    def changeLogo(self):
        """
        Allow the user to select a logo to display
        """
        imageFilter = "Images (*.png *.xpm *.jpg *.tif)"
        fname, filter = QFileDialog.getOpenFileName(self.viewer, "Image File", 
                        filter=imageFilter)
        if fname != '':
            self.scalebarlayer.logo = QImage(fname)
        else:
            self.scalebarlayer.logo = None
                    
        # redraw
        self.scalebarlayer.getImage()
        self.viewer.viewwidget.viewport().update()
        

def registerScaleBarNorthArrow(viewer, nthArrow=True, 
        scaleBar=True, citation=None, logo=None):
    """
    Add the Scale bar and north arrow to the given viewer
    """
    # install our version of the query point layer
    scalebarlayer = ScaleBarNthArrowQueryPointLayer(
        viewer.viewwidget.layers.queryPointLayer, nthArrow, 
        scaleBar, citation, logo)
    viewer.viewwidget.layers.queryPointLayer = scalebarlayer
    
    # straight away get a new querypointlayer 
    # (which should include our nth arrow and scale bar)
    scalebarlayer.getImage()
    viewer.viewwidget.viewport().update()
    return scalebarlayer
    
    
def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = ScaleBarNthArrow(viewer)
        
        # make sure the object isn't garbage collected
        app = QApplication.instance()
        app.savePluginHandler(handler)
