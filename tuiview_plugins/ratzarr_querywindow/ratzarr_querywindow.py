"""
RatZarr Query Window Plugin

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
from osgeo import gdal

from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QObject

from tuiview import pluginmanager
from tuiview.viewerRAT import DEFAULT_FLOAT_FMT, NEWCOL_INT, NEWCOL_FLOAT, NEWCOL_STRING, DEFAULT_CACHE_SIZE
from tuiview.querywindow import RAT_CACHE_CHUNKSIZE
import ratzarr


def name():
    return 'RatZarr Query Window plugin'


def author():
    return 'Sam Gillingham'


def description():
    return 'Tool for adding columns from a linked RatZarr file to the Query Window'
    
    
def action(actioncode, viewer):
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWQUERY:
        handler = ZarrColumnsQuery(viewer)
        
        # make sure the object isn't garbage collected
        viewer.plugins.append(handler)
        

class ZarrColumnsQuery(QObject):
    def __init__(self, querywindow):
        QObject.__init__(self)
        self.querywindow = querywindow

        # load icon from this dir
        cdir = os.path.dirname(__file__)
        iconpath = os.path.join(cdir, 'zarr-pink-stacked.svg')
        self.icon = QIcon(iconpath)
        
        self.ZarrAction = QAction(self, triggered=self.linkZarr)
        self.ZarrAction.setIcon(self.icon)
        self.ZarrAction.setText("Link a RatZarr file to this RAT")
        
        querywindow.toolBar.addAction(self.ZarrAction)
        
    def linkZarr(self):
        print('linking zarr')
        rz = ratzarr.RatZarr('/data/git/tuiview-plugins_gillins/myzarr.zarr')
        if self.querywindow.tableModel is not None:
            if not isinstance(self.querywindow.tableModel.attributes, RatZarrAndGDALRat):
                ratzarr_and_gdal = RatZarrAndGDALRat(self.querywindow.tableModel.attributes, rz)
                self.querywindow.tableModel.attributes = ratzarr_and_gdal
                self.querywindow.tableModel.doUpdate(updateHorizHeader=True)
                # updating of colnames etc done in doUpdate

        
class RatZarrAndGDALRat:
    """
    Class that emulates the interface of tuiview.viewerRAT.ViewerRAT
    but handles a connection to a ratzarr object as well as the GDAL Rat
    """
    columnNames = None  # list
    columnTypes = None  # dict
    columnUsages = None  # dict
    columnFormats = None  # dict
    lookupColName = None  # string
    redColumnIdx = None  # int
    greenColumnIdx = None  # int
    blueColumnIdx = None  # int
    alphaColumnIdx = None  # int
    hasRATColorTable = False
    hasOldStyleColorTable = False
    
    def __init__(self, oldViewerRAT, ratzarrObj):
        self.oldViewerRAT = oldViewerRAT  # tuiview.viewerRAT.ViewerRAT
        self.ratzarrObj = ratzarrObj
        self.columnNames = ratzarrObj.getColumnNames()
        self.columnTypes = {}
        self.columnUsages = {}
        self.columnFormats = {}
        for col in self.columnNames:
            # TODO: get actual type
            self.columnTypes[col] = gdal.GFT_Real
            self.columnUsages[col] = gdal.GFU_Generic
            self.columnFormats[col] = DEFAULT_FLOAT_FMT
            
        self.hasRATColorTable = oldViewerRAT.hasRATColorTable
        self.hasOldStyleColorTable = oldViewerRAT.hasOldStyleColorTable
        self.redColumnIdx = oldViewerRAT.redColumnIdx
        self.greenColumnIdx = oldViewerRAT.greenColumnIdx
        self.blueColumnIdx = oldViewerRAT.blueColumnIdx
        self.alphaColumnIdx = oldViewerRAT.alphaColumnIdx
            
    def hasAttributes(self):
        return self.oldViewerRAT.hasAttributes() or len(self.columnNames) > 0
        
    def getColumnNames(self): 
        colnames = self.oldViewerRAT.getColumnNames()
        colnames.extend(self.columnNames)
        return colnames
        
    def getSaneColumnNames(self, colNameList=None):
        if colNameList is not None:
            return self.oldViewerRAT.getSaneColumnNames(colNameList)
        colnames = self.oldViewerRAT.getSaneColumnNames()
        zarrsanecolnames = self.oldViewerRAT.getSaneColumnNames(colNameList=self.columnNames)
        colnames.extend(zarrsanecolnames)
        return colnames
        
    def getType(self, colName):
        "return the type for a given column name"
        if colName in self.columnNames:
            return self.columnTypes[colName]
        return self.oldViewerRAT.getType(colName)

    def getUsage(self, colName):
        "return the usage for a given column name"
        if colName in self.columnNames:
            return self.columnUsages[colName]
        return self.oldViewerRAT.getUsage(colName)

    def getFormat(self, colName):
        "return the preferred format string for a given column name"
        if colName in self.columnFormats:
            return self.columnFormats[colName]
        return self.oldViewerRAT.getFormat(colName)

    def setFormat(self, colName, fmt):
        "replace the format string for a given column name"
        if colName in self.columnFormats:
            self.columnFormats[colName] = fmt
        else:
            self.oldViewerRAT.setFormat(colName, fmt)

    def getNumColumns(self):
        numcols = self.oldViewerRAT.getNumColumns()
        return numcols + len(self.columnNames)
        
    def getNumRows(self):
        # should all be the same?
        return self.oldViewerRAT.getNumRows()
        
    def getOldStyleColorTableRGBA(self, i):
        return self.oldViewerRAT.getOldStyleColorTableRGBA(i)
        
    def getCacheObject(self, chunkSize):
        ratcache = self.oldViewerRAT.getCacheObject(chunkSize)
        return ZarrAndRATCache(ratcache, self.ratzarrObj, chunkSize)
        
    def getEntireAttribute(self, colName):
        if colName in self.columnNames:
            nrows = self.ratzarrObj.getRowCount()
            return self.ratzarrObj.readBlock(colName, 0, nrows)
        return self.oldViewerRAT.getEntireAttribute(colName)
        
    def getLookupColName(self):
        "Return column to be used to lookup color table"
        return self.lookupColName

    def setLookupColName(self, name):
        "Set column to be used to lookup color table"
        self.lookupColName = name

    def clear(self):
        """
        Removes attributes from this class
        """
        self.columnNames = None  # list
        self.columnTypes = None  # dict
        self.columnUsages = None  # dict
        self.columnFormats = None  # dict
        self.lookupColName = None  # string
        self.oldViewerRAT.clear()
        
    def addColumn(self, colname, coltype):
        self.oldViewerRAT.addColumn(colName, colType)
        
    def addColumnToZarr(self, colname, coltype):
        # TODO: link this into the GUI somehow
        if coltype == NEWCOL_INT:
            coldtype = int
        elif coltype == NEWCOL_FLOAT:
            coldtype = float
        else:
            coldtype = numpy.dtypes.StringDType()
        self.ratzarrObj.createColumn(colName, coldtype)
        
    # readFromGDALBand/findColorTableColumns should already be called on viewerRAT on creation
    
    def arrangeColumnOrder(self, prefColOrder, gdalband):
        # TODO: how do we save ratzarr cols that have been reordered?
        self.oldViewerRAT.arrangeColumnOrder(prefColOrder, gdalband)
        
    def getUserExpressionGlobals(self, cache, isselected, queryRow, 
                            lastselected=None, colNameList=None):
        if colNameList is not None:
            # they have already worked out the columns in the user expression
            # we muct split the list into Zarr and GDAL columns and process
            # separately
            gdalColNameList = []
            zarrColNameList = []
            for col in colNameList:
                if col in self.columnNames:
                    zarrColNameList.append(col)
                else:
                    gdalColNameList.append(col)
                                
            # call the GDAL function to set everything up
            # should be ok even if gdalColNameList is empty
            globaldict = self.oldViewerRAT.getUserExpressionGlobals(cache, isselected,
                queryRow, lastselected, gdalColNameList)
            # now add our cols
            for colName, saneName in (
                    zip(zarrColNameList, self.getSaneColumnNames(zarrColNameList))):
                # use sane names so as not to confuse Python
                colArr = cache.cacheDict.get(colName)
                if colArr is None:
                    raise ValueError(f"Unknown column name '{colName}'")
                globaldict[saneName] = colArr        
    
            return globaldict
        
        # otherwise add all columns (is this code path ever used)?
        globaldict = self.oldViewerRAT.getUserExpressionGlobals(cache, isselected,
            queryRow, lastselected, colNameList)
        # add ours
        for colName, saneName in (
                zip(self.columnNames, self.getSaneColumnNames(self.columnNames))):
            # use sane names so as not to confuse Python
            colArr = cache.cacheDict.get(colName)
            if colArr is None:
                raise ValueError(f"Unknown column name '{colName}'")
            globaldict[saneName] = colArr        

        return globaldict
                 
    def evaluateUserSelectExpression(self, imports, expression, isselected, queryRow, 
            lastselected):
        # pass through. Cache/getUserExpressionGlobals should pull the right data out
        return self.oldViewerRAT.evaluateUserSelectExpression(imports, expression, 
            isselected, queryRow, lastselected)
            
    def evaluateUserEditExpression(self, colName, imports, expression, isselected, 
            queryRow):
        # pass through
        return self.oldViewerRAT.evaluateUserEditExpression(colName, imports, expression, isselected, queryRow)
        
    def exportSelectedRowsToCSV(self, isselected, outDocCsv):
        # pass through for now. Should we have a separate function for exporting
        # the zarr columns? Or do both columns?
        self.oldViewerRAT.exportSelectedRowsToCSV(isselected, outDocCsv)
        
    def setColumnToConstant(self, colName, value, isselected):
        """
        Sets whole column to be a constant value (where isselected == True)
        for keyboard shortcuts etc
        """
        # our own implementation so we can use our own cache object
        self.oldViewerRAT.newProgress.emit("Evaluating User Expression...")
        cache = self.getCacheObject(DEFAULT_CACHE_SIZE)
        nrows = self.getNumRows()

        currRow = 0
        done = False

        while currRow < nrows and not done:
            # guess size
            isselectedSub = isselected[currRow:currRow + DEFAULT_CACHE_SIZE]
            if isselectedSub.any():
                cache.setStartRow(currRow, colName)

                cache.updateColumn(colName, value, isselected)

            currRow += DEFAULT_CACHE_SIZE
            self.oldViewerRAT.newPercent.emit(int((currRow / nrows) * 100))

        self.oldViewerRAT.endProgress.emit()
            
    def writeColumnOrderToGDAL(self, gdaldataset):
        # pass through for now, should work out a way of 
        # saving the zarr col orders also
        self.oldViewerRAT.writeColumnOrderToGDAL(gdaldataset)
        
    
class ZarrAndRATCache:
    """
    Our version of viewerRAT.RATCache that also handles
    reading from the zarr file
    """
    def __init__(self, gdalRATCache, zarrObj, chunkSize):
        self.gdalRATCache = gdalRATCache
        self.zarrObj = zarrObj
        self.chunkSize = chunkSize
        self.zarrColNames = self.zarrObj.getColumnNames()

        self.currStartRow = 0
        self.length = 0
        self.zarrcacheDict = {}

    def getLength(self):
        "Return the length of the current RAT chunk"
        return self.gdalRATCache.length

    # def columnAdded(self, colName): seems not to be used

    def updateCache(self, colName=None):
        """
        Internal method, called when self.currStartRow changed
        If colName is None all columns will be updated, if it is a single
        name or a list of names, then just the named one(s) will
        be update.
        """
        # update GDAL RAT first
        self.gdalRATCache.updateCache(colName)
        # update length
        self.length = self.gdalRATCache.length
        
        for name in self.zarrColNames:
            if colName is None or name == colName or name in colName:
                data = self.zarrObj.readBlock(name, self.currStartRow, self.length)
                self.zarrcacheDict[name] = data

    def setStartRow(self, startRow, colName=None):
        """
        Call this to set the cache to contain the new data
        If colName is None all columns will be updated 
        otherwise just the named one
        """
        self.currStartRow = startRow
        self.gdalRATCache.currStartRow = startRow
        self.updateCache(colName)

    def getValueFromCol(self, colName, row):
        """
        Return the actual value given name of col and 
        a row count based on the full rat
        """
        if colName in self.zarrColNames:
            data = self.zarrcacheDict[colName]
            return data[row - self.currStartRow]
        return self.gdalRATCache.getValueFromCol(colName, row)

    def autoScrollToIncludeRow(self, row):
        """
        For calling from GUI. Qt will ask for a given row
        but we don't want to re-read every time. Most requests will
        be around a location so we only update when we have to.
        """
        if row >= self.currStartRow and row < (self.currStartRow + 
                                self.chunkSize) and len(self.zarrcacheDict) > 0:
            # no need - already have that data
            return

        newStartRow = int(row / self.chunkSize) * self.chunkSize
        self.setStartRow(newStartRow)
        self.gdalRATCache.autoScrollToIncludeRow(row)
        
    def updateColumn(self, colName, data, selectionArray):
        """
        New data for a column. selectionArray is the size of the file's RAT.
        data is just the subset for this cache. 
        Updates only done where selectionArray == True (for the subset we are caching)
        updates cache and data in file
        """
        if colName in self.zarrColNames:
            if not numpy.isscalar(data) and len(data) != self.length:
                msg = 'data wrong length'
                raise viewererrors.AttributeTableTypeError(msg)
    
            selectionArraySubset = selectionArray[
                self.currStartRow:self.currStartRow + self.length]
    
            if not selectionArraySubset.any():
                # nothing to be updated
                return
                
            if not selectionArraySubset.all():
                # some need to be updated
                # keep old where selectionArray == False
                olddata = self.cacheDict[colName] 
            
                # TODO: do we need to coerce to the right type?
                # do the masking
                # it is assumed this will do the right thing when 
                # string lengths are different
                data = numpy.where(selectionArraySubset, data, olddata)

            # update cache
            self.cacheDict[colName] = data
            # write back to file
            self.zarrObj.writeBlock(colName, data, self.currStartRow)
        else:
            self.gdalRATCache.updateColumn(colName, data, selectionArray)
