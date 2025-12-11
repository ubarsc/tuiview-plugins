"""
QML Reader plugin

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
import numpy
import xml.etree.ElementTree as ET

from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog, QMessageBox

from tuiview import pluginmanager
from tuiview import viewerLUT


def name():
    return 'QML Reader'


def author():
    return 'Sam Gillingham'


def description():
    return 'Tool for adding QML reader to stretch and query window'


def parseXML(xml):
    """
    Parse the given .qml as XML and return a dictionary keyed on 
    value which is the color as an RGB string
    """
    tree = ET.parse(xml)
    root = tree.getroot()
    colorDict = {}
    alphaDict = {}
    max_size = 0

    colorrampshader = root.find('./pipe/rasterrenderer/rastershader/colorrampshader')
    if colorrampshader is not None:
        # ramp shader format
        max_size = int(colorrampshader.attrib['maximumValue'])
        for item in colorrampshader.iter('item'):
            value = float(item.attrib['value'])
            color = item.attrib['color']
            colorDict[value] = color
            if 'alpha' in item.attrib:
                alphaDict[value] = float(item.attrib['alpha'])
            else:
                alphaDict[value] = 255.0
            
    else:
        colorpalette = root.find('./pipe/rasterrenderer/colorPalette')
        if colorpalette is not None:
            # color palette format
            for item in colorpalette.iter('paletteEntry'):
                value = float(item.attrib['value'])
                if value > max_size:
                    max_size = int(value)
                color = item.attrib['color']
                colorDict[value] = color
                if 'alpha' in item.attrib:
                    alphaDict[value] = float(item.attrib['alpha'])
                else:
                    alphaDict[value] = 255.0
        else:
            raise ValueError('cannot find colorrampshader or colorPalette in file')
                
    return colorDict, alphaDict, max_size


def getColorVal(colorDict, idx):
    """
    In the given dictionary get the colour indexed by 'idx',
    red=0, green=1, blue=2. Return an array with an item per value
    """
    result = []
    for key in sorted(colorDict.keys()):
        s = colorDict[key][1:]
        sidx = idx * 2 
        s = s[sidx:sidx + 2]
        val = int(s, 16)
        result.append(val)
        
    return numpy.array(result)


def getAlphaVal(alphaDict):
    """
    Like getColorVal(), but for alpha
    """
    result = []
    for key in sorted(alphaDict.keys()):
        a = alphaDict[key]
        result.append(a)
    return numpy.array(result)


def getColorTable(colorDict, alphaDict, maxVal):
    """
    Create a colour table (0-maxVal + 1) for the given dictionary of colours
    0 - maxVal are the colour ramp, maxVal + 1 is zero for nodata
    """
    xobs = numpy.array(sorted(colorDict.keys()))
    xinterp = numpy.linspace(0, maxVal, maxVal + 1)  
    ct = numpy.empty((maxVal + 2, 4), dtype=numpy.uint8)  # + 2 because we need space for nodata
    ct[maxVal + 1, ...] = 0  # nodata etc

    for idx, name in enumerate(['red', 'green', 'blue']):
        yobs = getColorVal(colorDict, idx)
        # print(yobs)
        yinterp = numpy.interp(xinterp, xobs, yobs)
        tuiview_idx = viewerLUT.CODE_TO_LUTINDEX[name]
        ct[0:maxVal + 1, tuiview_idx] = yinterp

    # alpha
    yobs = getAlphaVal(alphaDict)
    yinterp = numpy.interp(xinterp, xobs, yobs)
    ct[0:maxVal + 1, 3] = yinterp

    return ct


class QMLReaderStretch(QObject):
    """
    Class for doing the QML reading
    """
    def __init__(self, stretch):
        QObject.__init__(self)
        self.stretch = stretch
        
        # load icon from this dir
        cdir = os.path.dirname(__file__)
        iconpath = os.path.join(cdir, 'qgis_qml_icon.svg')
        self.icon = QIcon(iconpath)
        
        self.QMLAction = QAction(self, triggered=self.fromQML)
        self.QMLAction.setIcon(self.icon)
        self.QMLAction.setText("Read from QML")
        
        stretch.toolBar.addAction(self.QMLAction)
        
    def fromQML(self):
        
        dirn = os.path.dirname(self.stretch.layer.filename)
        if dirn == '':
            dirn = os.getcwd()

        # ask the user to locate the QML        
        qml, _ = QFileDialog.getOpenFileName(self.stretch,
            "Select QML File", dirn, "QML file (*.qml)")
        if qml != "": 
            colorDict, alphaDict, max_size = parseXML(qml)
            
            viewerstretch = self.stretch.stretchLayout.getStretch()
            if len(viewerstretch.bands) > 1:
                QMessageBox.critical(self.stretch, name(), 
                        "Must be single band")
                return
            
            # close the stretch window as it won't make any sense now
            self.stretch.close()

            # set up the stretch for 0 - max_size and add nodata at max_size + 1
            self.stretch.layer.lut.bandinfo = viewerLUT.BandLUTInfo(1, 0, max_size + 1, 0, 
                max_size, max_size + 1, max_size + 1, max_size + 1)
            self.stretch.layer.lut.lut = getColorTable(colorDict, alphaDict, max_size)
            
            # no stretch (I think this makes sense)
            self.stretch.layer.stretch.setNoStretch()
            
            self.stretch.layer.getImage()
            self.stretch.viewwidget.viewport().update()


def action(actioncode, window):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWSTRETCH:
        handler = QMLReaderStretch(window)
        window.plugins.append(handler)

