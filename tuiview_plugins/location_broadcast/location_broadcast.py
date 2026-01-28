"""
Location Broadcast plugin

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
import sys
import time
from tuiview import pluginmanager
from PySide6.QtCore import QObject

TMPDIR = os.getenv('TMP', '/tmp')
if sys.platform == 'win32':
    UID = os.getenv('USERNAME')
else:
    UID = str(os.getuid())
SHAREDFILE = os.path.join(TMPDIR, 'locationbcast_%s' % UID)


class NewLocationHandler(QObject):
    """
    Class that contains the plugin
    """
    def __init__(self, viewer):
        QObject.__init__(self)
        self.viewer = viewer

    def onNewLocation(self, obj):
        "new location to broadcast"
        # obj is a GeolinkInfo, but
        # it doesn't contain the extent (just the centre)
        # easiest just to query the widget again
        layer = self.viewer.viewwidget.layers.getTopRasterLayer()
        if layer is not None:
            extent = layer.coordmgr.getWorldExtent()

            iso_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

            # truncate the existing file and re-write values
            fileobj = open(SHAREDFILE, 'w+')
            fileobj.write('%s %f %f %f %f\n' % (iso_time, extent[0], extent[1], 
                        extent[2], extent[3]))
            fileobj.close()


def name():
    return 'Location Broadcast'


def author():
    return 'Sam Gillingham'


def description():
    return 'Broadcasts location of TuiView so can be read by other applications'


def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWVIEWER:
        handler = NewLocationHandler(viewer)

        viewer.viewwidget.geolinkMove.connect(handler.onNewLocation)

        # make sure the object isn't garbage collected
        viewer.plugins.append(handler)
