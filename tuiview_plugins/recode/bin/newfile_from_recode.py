#!/usr/bin/env python

"""
Takes output from the recode plugin and applies it to create a new 
image.
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

from __future__ import print_function, division
import os
import json
import numpy
import argparse
from rios import applier, cuiprogress
from rios import ratapplier
from osgeo import ogr
from tuiview import vectorrasterizer

# can't import the recode plugin which is a bit of a pain...
RECODE_EXT = ".recode"
"Extension after the image file extension that the recodes are saved to"


def getCmdargs():
    """
    Get commandline arguments
    """
    p = argparse.ArgumentParser()
    p.add_argument('-i', '--input', help="Input raster file")
    p.add_argument('-r', '--recodes', help="Name of recode file. " + 
        "If not specified it is derived from input file name")
    p.add_argument('-o', '--output', help="output raster name")
    p.add_argument('-n', '--norat', default=False, action="store_true",
        help="Don't copy input RAT to output file. Default is to copy RAT")

    cmdargs = p.parse_args()
    if cmdargs.input is None or cmdargs.output is None:
        p.print_help()
        raise SystemExit('Must specify input and output filenames')

    return cmdargs


def riosRecode(info, inputs, outputs, otherArgs):
    """
    Called from RIOS - does the recoding
    """
    data = inputs.input[0]
    ysize, xsize = data.shape
    extent = (info.blocktl.x, info.blocktl.y, info.blockbr.x, 
            info.blockbr.y)

    # as we aren't dealing with an OGR dataset we can't use GDAL
    # so use the TuiView internals again.
    for geom, comment, recodedValues in otherArgs.recodes:
        mask = vectorrasterizer.rasterizeGeometry(geom, extent, 
                    xsize, ysize, 1, True)

        # convert to 0s and 1s to bool
        mask = (mask == 1)

        # apply the codes
        # always sort on the old value??
        for old in sorted(recodedValues.keys()):
            new = recodedValues[old]
            subMask = mask & (data == old)
            data[subMask] = new

    # make 2d
    outputs.output = numpy.expand_dims(data, 0)


def doRecodes(input, output, recodes=None, noRAT=False):
    """
    Calls RIOS to do the recoding.
    """
    inputs = applier.FilenameAssociations()
    inputs.input = input

    outputs = applier.FilenameAssociations()
    outputs.output = output

    if recodes is None:
        recodes = input + RECODE_EXT

    if not os.path.exists(recodes):
        raise SystemExit("Recode file %s does not exist" % recodes)

    recodeFile = open(recodes)
    s = recodeFile.readline()
    recodeFile.close()
    wktrecodes = json.loads(s)

    # convert the wkts to ogr.Geometry so this doesn't have to happen each block
    geomrecodes = []
    for wkt, comment, recodedValues in wktrecodes:
        geom = ogr.CreateGeometryFromWkt(wkt)
        # 'old' key in the dictionary comes back as a string
        # due to the JSON spec. Create a new dictionary
        recodesAsInts = {}
        for key in recodedValues:
            recodesAsInts[int(key)] = recodedValues[key]

        geomrecodes.append((geom, comment, recodesAsInts))

    otherArgs = applier.OtherInputs()
    otherArgs.recodes = geomrecodes

    controls = applier.ApplierControls()
    controls.progress = cuiprogress.GDALProgressBar()
    # always thematic??
    controls.setThematic(True)

    applier.apply(riosRecode, inputs, outputs, otherArgs, controls=controls)

    # now the rat
    if not noRAT and len(otherArgs.colNames) > 0:
        print('copying the RAT')
        progress = cuiprogress.GDALProgressBar()
        ratapplier.copyRAT(input, output, progress)


if __name__ == '__main__':
    cmdargs = getCmdargs()
    doRecodes(cmdargs.input, cmdargs.output, cmdargs.recodes, cmdargs.norat)
