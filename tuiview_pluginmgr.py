#!/usr/bin/env python

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

import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt5.QtWidgets import QTableView, QHBoxLayout, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QAbstractTableModel

from tuiview import pluginmanager

MESSAGE_TITLE = "TuiView Plugin Manager"

def getPluginInfo():
    """
    Return a list of (name, author, description) tuples
    """
    plugins = []
    mgr = pluginmanager.PluginManager()

    # load all the plugins in each directory under the location 
    # of this file
    currPath = os.path.dirname(sys.argv[0])
    for entry in os.scandir(currPath):
        if entry.is_dir():
            mgr.loadPluginsFromDir(entry.path)

    # now go through all the plugins loaded
    for name in mgr.plugins:
        author = getattr(mgr.plugins[name], pluginmanager.PLUGIN_AUTHOR_FN)
        authorTxt = author()
        desc = getattr(mgr.plugins[name], pluginmanager.PLUGIN_DESC_FN)
        descTxt = desc()
        plugins.append((name, authorTxt, descTxt))

    return plugins

class PluginGuiApplicaton(QApplication):
    def __init__(self, pluginInfo):
        QApplication.__init__(self, sys.argv)

        # for settings
        self.setApplicationName('tuiview-plugins')
        self.setOrganizationName('TuiView')

        self.window = PluginGuiWindow(pluginInfo)

class PluginGuiWindow(QMainWindow):
    def __init__(self, pluginInfo):
        QMainWindow.__init__(self)
        self.setWindowTitle(MESSAGE_TITLE)

        self.widget = PluginGuiWidget(self, pluginInfo)
        self.setCentralWidget(self.widget)

        self.resize(500, 500)
        self.show()
    
class PluginGuiWidget(QWidget):
    def __init__(self, parent, pluginInfo):
        QWidget.__init__(self, parent)

        self.tableModel = PluginTableModel(self, pluginInfo)

        self.tableView = QTableView(self)
        self.tableView.setSelectionBehavior(QTableView.SelectRows)
        self.tableView.setModel(self.tableModel)

        self.saveButton = QPushButton(self)
        self.saveButton.setText("Save and Exit")
        self.saveButton.clicked.connect(parent.close)

        self.cancelButton = QPushButton(self)
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(parent.close)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.tableView)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.saveButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout.addLayout(self.buttonLayout)

        self.setLayout(self.mainLayout)

class PluginTableModel(QAbstractTableModel):
    def __init__(self, parent, pluginInfo):
        QAbstractTableModel.__init__(self, parent)
        self.pluginInfo = pluginInfo

    def rowCount(self, parent):
        return len(self.pluginInfo)

    def columnCount(self, parent):
        return 4

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return 'Enabled'
            elif section == 1:
                return 'Name'
            elif section == 2:
                return 'Author'
            elif section == 3:
                return 'Description'

        return None

    def data(self, index, role):
        if not index.isValid():
            return None

        row = index.row()
        column = index.column()
        if role == Qt.CheckStateRole and column == 0:
            return Qt.Checked

        elif role == Qt.DisplayRole:
            if column > 0:
                return self.pluginInfo[row][column-1]

        return None

if __name__ == '__main__':

    pluginInfo = getPluginInfo()

    app = PluginGuiApplicaton(pluginInfo)
    sys.exit(app.exec_())
