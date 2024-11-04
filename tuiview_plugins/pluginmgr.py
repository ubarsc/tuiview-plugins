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

"""
A Gui manager for plugins
"""

import os
import sys
import argparse
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtWidgets import QTableView, QHBoxLayout, QVBoxLayout, QPushButton
from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, QAbstractTableModel, QSettings, Signal

from tuiview import pluginmanager

# import tuiview_plugins. This will either be relative
# to this script if we are being run from the source dir,
# Or will be the actual module if we installed (in the bin
# dir there will be no 'tuiview_plugins' subdir).
import tuiview_plugins
PLUGINS_LOC = os.path.dirname(tuiview_plugins.__file__)
# print('PLUGINS_LOC', PLUGINS_LOC)

MESSAGE_TITLE = "TuiView Plugin Manager"

# for settings
SELECTED_PLUGINS = "SelectedPlugins"

# So we work with older TuiView that doesn't have this
if hasattr(pluginmanager, 'PLUGIN_DESC_FN'):
    PLUGIN_DESC_FN = getattr(pluginmanager, 'PLUGIN_DESC_FN')
else:
    PLUGIN_DESC_FN = 'description'


def getPluginInfo(quiet=False):
    """
    Return a list of (name, author, description, path) tuples
    """
    if quiet:
        # ensure stdout redirected
        f = open(os.devnull, 'w')
        old_stdout = sys.stdout
        sys.stdout = f

    plugins = []
    mgr = pluginmanager.PluginManager()

    # load all the plugins in each directory under PLUGINS_LOC 
    for entry in os.scandir(PLUGINS_LOC):
        if entry.is_dir():
            mgr.loadPluginsFromDir(entry.path)

    # now go through all the plugins loaded
    for name, plugin in mgr.plugins.items():
        author = getattr(plugin, pluginmanager.PLUGIN_AUTHOR_FN)
        authorTxt = author()
        desc = getattr(plugin, PLUGIN_DESC_FN)
        descTxt = desc()

        subdir = os.path.dirname(plugin.__file__)
        path = os.path.join(PLUGINS_LOC, subdir)
        path = os.path.abspath(path)

        plugins.append((name, authorTxt, descTxt, path))

    if quiet:
        # reset 
        sys.stdout = old_stdout

    return plugins


def getAsBashZshString(selectedPaths):
    if len(selectedPaths) == 0:
        return 'unset %s' % pluginmanager.PLUGINS_ENV
    else:
        return 'export %s="%s"' % (pluginmanager.PLUGINS_ENV, ':'.join(selectedPaths))


def getAsCshString(selectedPaths):
    if len(selectedPaths) == 0:
        return 'unsetenv %s' % pluginmanager.PLUGINS_ENV
    else:
        return 'setenv %s "%s"' % (pluginmanager.PLUGINS_ENV, ':'.join(selectedPaths))


def getAsDOSString(selectedPaths):
    if len(selectedPaths) == 0:
        return 'set "%s="' % pluginmanager.PLUGINS_ENV
    else:
        return 'set "%s=%s"' % (pluginmanager.PLUGINS_ENV, ';'.join(selectedPaths))


def getExplanation(selectedPaths):
    expl = """

To load the plugins in TuiView run the following command before running it:

For Bash and Zsh:
%s

For tcsh and csh:
%s

For Windows/DOS:
%s

Run '%s -h' for information on printing this command so it can be sourced/eval'd from your shell.
    """
    return expl % (getAsBashZshString(selectedPaths),
        getAsCshString(selectedPaths), getAsDOSString(selectedPaths),
        os.path.basename(sys.argv[0]))


class PluginGuiApplication(QApplication):
    """
    The application
    """
    def __init__(self, pluginInfo, gui=True):
        QApplication.__init__(self, sys.argv)

        # for settings
        self.setApplicationName('tuiview-plugins')
        self.setOrganizationName('TuiView')

        settings = QSettings()
        selected = settings.value(SELECTED_PLUGINS, "")
        self.selected = selected.split(",")

        valid = [info[0] for info in pluginInfo]

        # strip out any that don't exist
        validSelected = []
        for sel in self.selected:
            if sel in valid:
                validSelected.append(sel)

        if gui:
            self.window = PluginGuiWindow(pluginInfo, validSelected)


class PluginGuiWindow(QMainWindow):
    """
    The window of the app
    """
    def __init__(self, pluginInfo, selected):
        QMainWindow.__init__(self)
        self.setWindowTitle(MESSAGE_TITLE)

        self.widget = PluginGuiWidget(self, pluginInfo, selected)
        self.setCentralWidget(self.widget)

        self.resize(500, 500)
        self.show()


class PluginGuiWidget(QWidget):
    """
    The main widget of the app
    """
    def __init__(self, parent, pluginInfo, selected):
        QWidget.__init__(self, parent)
        self.parent = parent

        self.tableModel = PluginTableModel(self, pluginInfo, selected)
        self.tableModel.selectedChangedSig.connect(self.selectedChanged)

        self.tableView = QTableView(self)
        self.tableView.setSelectionBehavior(QTableView.SelectRows)
        self.tableView.setModel(self.tableModel)
        header = self.tableView.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)

        self.explanation = QTextEdit(self)
        self.explanation.setReadOnly(True)
        self.selectedChanged()  # get the text

        self.saveButton = QPushButton(self)
        self.saveButton.setText("Save and Exit")
        self.saveButton.clicked.connect(self.saveAndExit)

        self.cancelButton = QPushButton(self)
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(parent.close)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.tableView)
        self.mainLayout.addWidget(self.explanation)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.saveButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout.addLayout(self.buttonLayout)

        self.setLayout(self.mainLayout)

    def selectedChanged(self):
        paths = self.tableModel.getPaths()
        expl = getExplanation(paths)
        self.explanation.setText(expl)

    def saveAndExit(self):
        settings = QSettings()
        selected = ','.join(self.tableModel.selected)
        settings.setValue(SELECTED_PLUGINS, selected)
        self.parent.close()


class PluginTableModel(QAbstractTableModel):
    """
    Manage the table
    """
    # signals
    selectedChangedSig = Signal(name='selectedChanged')

    def __init__(self, parent, pluginInfo, selected):
        QAbstractTableModel.__init__(self, parent)
        self.pluginInfo = pluginInfo
        self.selected = selected

    def getPaths(self):
        paths = []
        for sel in self.selected:
            for inf in self.pluginInfo:
                if inf[0] == sel:
                    paths.append(inf[-1])
        return paths

    def flags(self, index):
        "Have to override to make it checkable"
        f = QAbstractTableModel.flags(self, index)
        column = index.column()

        if column == 0:
            return f | Qt.ItemIsUserCheckable
        else:
            return f

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
            name = self.pluginInfo[row][0]
            if name in self.selected:
                return Qt.Checked
            else:
                return Qt.Unchecked

        elif role == Qt.DisplayRole:
            if column > 0:
                return self.pluginInfo[row][column - 1]

        return None

    def setData(self, index, value, role):
        column = index.column()
        if role == Qt.CheckStateRole and column == 0:
            row = index.row()
            name = self.pluginInfo[row][0]
            if Qt.CheckState(value) == Qt.Checked:
                if name not in self.selected:
                    self.selected.append(name)
            else:
                self.selected.remove(name)

            self.selectedChangedSig.emit()

            return True
        return False


def getCmdargs():
    """
    Get commandline arguments
    """
    if sys.platform.startswith('win'):
        defaultShell = 'DOS'
    else:
        defaultShell = os.getenv('SHELL', default='bash')

    p = argparse.ArgumentParser()
    p.add_argument('-s', '--source', default=False, action="store_true", 
        help="Print the command for the given shell "+
            "for the currently selected plugins and exit so this can be " +
            "sourced/eval'd from your shell. ")
    p.add_argument('--shell', default=defaultShell,
        help="Specify the shell to use for --source, default shell taken from the " +
            "$SHELL environment variable.")

    return p.parse_args()


def printSourceLine(shell, selected, info):
    """
    Print line to be sourced
    """
    # get the paths
    selectedPaths = []
    for sel in selected:
        for inf in info:
            if inf[0] == sel:
                selectedPaths.append(inf[-1])

    if shell.endswith('DOS'):
        print(getAsDOSString(selectedPaths))

    elif shell.endswith('bash') or shell.endswith('zsh'):
        print(getAsBashZshString(selectedPaths))

    elif shell.endswith('csh'):
        print(getAsCshString(selectedPaths))

    else:
        raise ValueError('Unsupported shell %s' % shell)


def run():
    """
    Main routine. To be called from the entry point
    """
    cmdargs = getCmdargs()

    pluginInfo = getPluginInfo(cmdargs.source)
    app = PluginGuiApplication(pluginInfo, not cmdargs.source)

    if cmdargs.source:
        # print line and exit
        printSourceLine(cmdargs.shell, app.selected, pluginInfo)
        return 0
    else:
        # display GUI
        return app.exec_()
