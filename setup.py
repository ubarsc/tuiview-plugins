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
from distutils.core import setup

# Are we installing the command line scripts?
# this is an experimental option for users who are
# using the Python entry point feature of setuptools and Conda instead
NO_INSTALL_CMDLINE = int(os.getenv('TUIVIEW_NOCMDLINE', '0')) > 0

if NO_INSTALL_CMDLINE:
    scripts_list = None
else:
    scripts_list = ['tuiviewpluginmgr']
    
PLUGINS_DIR = 'tuiview_plugins'
    
packages = [PLUGINS_DIR]
for entry in os.scandir(PLUGINS_DIR):
    if entry.is_dir() and not entry.name.startswith('__'):
        packages.append(PLUGINS_DIR + '/' + entry.name)
        
setup(name='tuiview-plugins',
      version='1.0.0',
      description='Plugins for TuiView',
      author='Sam Gillingham',
      author_email='gillingham.sam@gmail.com',
      scripts=scripts_list,
      packages=packages,
      license='LICENSE.txt', 
      url='https://bitbucket.org/chchrsc/tuiview-plugins'
      )

