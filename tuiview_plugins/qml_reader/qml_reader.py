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
import xml.etree.ElementTree as ET

from PySide6.QtGui import QAction
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog

from tuiview import pluginmanager


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
        max_size = int(maximumValue.attrib['maximumValue'])
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
                    max_size = value
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


class QMLReaderStretch(QObject):
    """
    Class for doing the QML reading
    """
    def __init__(self, stretch):
        QObject.__init__(self)
        self.stretch = stretch
        
        self.QMLAction = QAction(self, triggered=self.fromQML)
        self.QMLAction.setText("Read from QML")
        
        stretch.toolBar.addAction(self.QMLAction)
        
    def fromQML(self):
        print('fromQML')
        
        lut = self.stretch.layer.lut.lut
        print(lut.shape)
        
        dirn = os.path.dirname(self.stretch.layer.filename)
        if dirn == '':
            dirn = os.getcwd()
        
        qml, _ = QFileDialog.getOpenFileName(self.stretch,
            "Select QML File", dirn, "QML file (*.qml)")
        if qml != "": 
            colorDict, alphaDict, max_size = parseXML(qml)
            
            viewerstretch = self.stretch.stretchLayout.getStretch()
            viewerstretch.setNoStretch()
            if len(viewerstretch.bands) > 1:
                QMessageBox.critical(self.stretch, name(), 
                        "Must be single band")
                return
                
            
                        



def action(actioncode, window):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWSTRETCH:
        handler = QMLReaderStretch(window)
        window.plugins.append(handler)

