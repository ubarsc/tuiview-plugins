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
import copy
import numpy
from osgeo import gdal

from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog, QFormLayout, QComboBox, QLineEdit
from PySide6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox

from tuiview import pluginmanager, viewererrors
from tuiview.viewerRAT import formatException, DEFAULT_INT_FMT, DEFAULT_FLOAT_FMT, DEFAULT_STRING_FMT, DEFAULT_CACHE_SIZE
from zarr import dtype as zarrdtype
import ratzarr


def name():
    return 'RatZarr Query Window plugin'


def author():
    return 'Sam Gillingham'


def description():
    return 'Tool for adding columns from a linked RatZarr file to the Query Window'
    
    
def action(actioncode, viewer):
    """
    Hook into a new query window
    """
    if actioncode == pluginmanager.PLUGIN_ACTION_NEWQUERY:
        handler = ZarrColumnsQuery(viewer)
        
        # make sure the object isn't garbage collected
        viewer.plugins.append(handler)
        

class ZarrColumnsQuery(QObject):
    """
    QObject that handles events from our toolbar buttons
    """
    def __init__(self, querywindow):
        QObject.__init__(self)
        self.querywindow = querywindow

        # load icon from this dir
        cdir = os.path.dirname(__file__)
        zarriconpath = os.path.join(cdir, 'zarr-pink-stacked.svg')
        self.zarricon = QIcon(zarriconpath)
        
        self.ZarrAction = QAction(self, triggered=self.linkZarr)
        self.ZarrAction.setIcon(self.zarricon)
        self.ZarrAction.setText("Link a RatZarr file to this RAT")
        
        querywindow.toolBar.addAction(self.ZarrAction)
        
        unzarriconpath = os.path.join(cdir, 'zarr-pink-stacked-cross.svg')
        self.unzarricon = QIcon(unzarriconpath)

        self.UnZarrAction = QAction(self, triggered=self.unLinkZarr)
        self.UnZarrAction.setIcon(self.unzarricon)
        self.UnZarrAction.setText("UnLink the RatZarr file from this RAT")
        self.UnZarrAction.setEnabled(False)

        querywindow.toolBar.addAction(self.UnZarrAction)

        addcoliconpath = os.path.join(cdir, 'zarr-pink-stacked-add.svg')
        self.addcolicon = QIcon(addcoliconpath)
        
        self.addColumnAction = QAction(self, triggered=self.addColZarr)
        self.addColumnAction.setIcon(self.addcolicon)
        self.addColumnAction.setText("Add a Column to the RatZarr file")
        self.addColumnAction.setEnabled(False)

        querywindow.toolBar.addAction(self.addColumnAction)
        
    def linkZarr(self):
        rz = ratzarr.RatZarr('/data/git/tuiview-plugins_gillins/myzarr.zarr')
        # TODO: thematic table model?
        if self.querywindow.tableModel is not None:
            if not isinstance(self.querywindow.tableModel.attributes, RatZarrAndGDALRat):
                rat = self.querywindow.tableModel.attributes
                if rz.getRowCount() != rat.getNumRows():
                    QMessageBox.critical(self.querywindow, name(), 
                        "RatZarr file must have same number of rows as current file's Raster Attribute Table") 
                else:
                    origColNames = set(rat.getColumnNames())
                    rzColNames = set(rz.getColumnNames())
                    if len(origColNames.intersection(rzColNames)) > 0:
                        QMessageBox.critical(self.querywindow, name(), 
                            "Column names must be unique between GDAL and RatZarr files") 
                    else:
                        ratzarr_and_gdal = RatZarrAndGDALRat(rat, rz)
                        self.querywindow.tableModel.attributes = ratzarr_and_gdal
                        self.querywindow.tableModel.doUpdate(updateHorizHeader=True)
                        # updating of colnames etc done in doUpdate
                        # also update the lastLayer which is used for expressions
                        self.querywindow.lastLayer.attributes = ratzarr_and_gdal
                        
                        # allow unlinking
                        self.UnZarrAction.setEnabled(True)
                        # allow adding cols
                        self.addColumnAction.setEnabled(True)
            else:
                QMessageBox.critical(self.querywindow, name(), "RatZarr already linked. Unlink first")
        else:
            QMessageBox.critical(self.querywindow, name(), "Can only link RatZarr to Thematic layers")
            
    def unLinkZarr(self):
        if self.querywindow.tableModel is not None:
            if isinstance(self.querywindow.tableModel.attributes, RatZarrAndGDALRat):
                ratzarr_and_gdal = self.querywindow.tableModel.attributes
                self.querywindow.tableModel.attributes = ratzarr_and_gdal.oldViewerRAT
                self.querywindow.tableModel.doUpdate(updateHorizHeader=True)
                self.querywindow.lastLayer.attributes = ratzarr_and_gdal.oldViewerRAT

                # disallow unlinking
                self.UnZarrAction.setEnabled(False)
                # disallow adding cols
                self.addColumnAction.setEnabled(False)
            else:
                # should never get here as button should be disabled
                QMessageBox.critical(self.querywindow, name(), "RatZarr file not linked")
        else:
            QMessageBox.critical(self.querywindow, name(), "Can only link RatZarr to Thematic layers")
            
    def addColZarr(self):
        if self.querywindow.tableModel is not None:
            if isinstance(self.querywindow.tableModel.attributes, RatZarrAndGDALRat):
                ratzarr_and_gdal = self.querywindow.tableModel.attributes
                dlg = AddColumnZarrDialog(self.querywindow)
                if dlg.exec_() == AddColumnZarrDialog.Accepted:
                    dtype = dlg.getColumnType()
                    colname = dlg.getColumnName()
                    try:
                        # convert zarr type to numpy type
                        ztype = dtype()  # create instance first
                        ratzarr_and_gdal.addColumnToZarr(colname, ztype.to_native_dtype())
                    except Exception as e:
                        QMessageBox.critical(self.querywindow, name(), str(e))

                    self.querywindow.tableModel.doUpdate(updateHorizHeader=True)

        
class RatZarrAndGDALRat:
    """
    Class that emulates the interface of tuiview.viewerRAT.ViewerRAT
    but handles a connection to a ratzarr object as well as the GDAL Rat
    """
    columnNames = None  # list
    columnTypes = None  # dict
    columnTypesNumpy = None  # dict - numpy dtypes
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
        self.columnTypesNumpy = {}
        self.columnUsages = {}
        self.columnFormats = {}
        for col in self.columnNames:
            numpydtype = ratzarrObj.getColumnDtype(col)
            gdaltype = self.NumpyDTypeToGDALType(numpydtype)
            self.columnTypes[col] = gdaltype
            self.columnTypesNumpy[col] = numpydtype
            self.columnUsages[col] = gdal.GFU_Generic
            if gdaltype == gdal.GFT_Integer:
                self.columnFormats[col] = DEFAULT_INT_FMT
            elif gdaltype == gdal.GFT_Real:
                self.columnFormats[col] = DEFAULT_FLOAT_FMT
            else:
                self.columnFormats[col] = DEFAULT_STRING_FMT
            
        self.hasRATColorTable = oldViewerRAT.hasRATColorTable
        self.hasOldStyleColorTable = oldViewerRAT.hasOldStyleColorTable
        self.redColumnIdx = oldViewerRAT.redColumnIdx
        self.greenColumnIdx = oldViewerRAT.greenColumnIdx
        self.blueColumnIdx = oldViewerRAT.blueColumnIdx
        self.alphaColumnIdx = oldViewerRAT.alphaColumnIdx
        # This just needs to exist so viewerlayers.py/ViewerRasterLayer/changeUpdateAccess
        # can del it. Probably a tider way. This isn't as ideal as all references to the
        # open dataset won't be deleted.
        # recreated by readFromGDALBand
        self.gdalRAT = 1
        
    @staticmethod
    def NumpyDTypeToGDALType(numpydtype):
        """
        Chooses the best appropriate Numpy column type based on a numpy dtype
        """
        if numpy.issubdtype(numpydtype, numpy.floating):
            return gdal.GFT_Real
        elif isinstance(numpydtype, numpy.dtypes.StringDType):  # pylint: disable=no-member
            return gdal.GFT_String
        # TODO: date/time?
        return gdal.GFT_Integer
            
    def hasAttributes(self):
        return self.oldViewerRAT.hasAttributes() or len(self.columnNames) > 0
        
    def getColumnNames(self): 
        # NB: copy list so we don't end up just changing it
        colnames = copy.copy(self.oldViewerRAT.getColumnNames())
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

    def setLookupColName(self, zname):
        "Set column to be used to lookup color table"
        self.lookupColName = zname

    def clear(self):
        """
        Removes attributes from this class
        """
        self.columnNames = None  # list
        self.columnTypes = None  # dict -  GDAL types
        self.columnTypesNumpy = None  # dict - numpy dtypes
        self.columnUsages = None  # dict
        self.columnFormats = None  # dict
        self.lookupColName = None  # string
        self.oldViewerRAT.clear()
        
    def addColumn(self, colname, coltype):
        """
        Pass through to GDAL add column
        """
        self.oldViewerRAT.addColumn(colname, coltype)
        
    def addColumnToZarr(self, colname, numpydtype):
        """
        Add as a zarr column
        """
        # TODO: link this into the GUI somehow
        self.ratzarrObj.createColumn(colname, numpydtype)
        self.columnNames.append(colname)
        gdaltype = self.NumpyDTypeToGDALType(numpydtype)
        self.columnTypes[colname] = gdaltype
        self.columnTypesNumpy[colname] = numpydtype
        self.columnUsages[colname] = gdal.GFU_Generic
        if gdaltype == gdal.GFT_Integer:
            self.columnFormats[colname] = DEFAULT_INT_FMT
        elif gdaltype == gdal.GFT_Real:
            self.columnFormats[colname] = DEFAULT_FLOAT_FMT
        else:
            self.columnFormats[colname] = DEFAULT_STRING_FMT

    def readFromGDALBand(self, gdalband, gdaldataset):
        # pass through. This will be called when the dataset
        # is re opened in update mode.
        self.oldViewerRAT.readFromGDALBand(gdalband, gdaldataset)
        # recreate this so it can be deleted by viewerlayers.py/ViewerRasterLayer/changeUpdateAccess
        self.gdalRAT = 1

    # findColorTableColumns should already be called on viewerRAT on creation
    
    def arrangeColumnOrder(self, prefColOrder, gdalband):
        # TODO: how do we save ratzarr cols that have been reordered?
        self.oldViewerRAT.arrangeColumnOrder(prefColOrder, gdalband)
        
    def getUserExpressionGlobals(self, cache, isselected, queryRow, 
                            lastselected=None, colNameList=None):
        if colNameList is not None:
            # they have already worked out the columns in the user expression
            # we must split the list into Zarr and GDAL columns and process
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
            globaldict = self.oldViewerRAT.getUserExpressionGlobals(cache.gdalRATCache, isselected,
                queryRow, lastselected, gdalColNameList)
            # now add our cols
            for colName, saneName in (
                    zip(zarrColNameList, self.getSaneColumnNames(zarrColNameList))):
                # use sane names so as not to confuse Python
                colArr = cache.zarrcacheDict.get(colName)
                if colArr is None:
                    raise ValueError(f"Unknown column name '{colName}'")
                globaldict[saneName] = colArr        
    
            return globaldict
        
        # otherwise add all columns (is this code path ever used)?
        globaldict = self.oldViewerRAT.getUserExpressionGlobals(cache.gdalRATCache, isselected,
            queryRow, lastselected, colNameList)
        # add ours
        for colName, saneName in (
                zip(self.columnNames, self.getSaneColumnNames(self.columnNames))):
            # use sane names so as not to confuse Python
            colArr = cache.zarrcacheDict.get(colName)
            if colArr is None:
                raise ValueError(f"Unknown column name '{colName}'")
            globaldict[saneName] = colArr        

        return globaldict
                 
    def evaluateUserSelectExpression(self, imports, expression, isselected, queryRow, 
            lastselected):
        """
        This largely copied from viewerRAT, but some changes have been made to
        cope with the dual nature of the columns.  
        """
        self.oldViewerRAT.newProgress.emit("Evaluating User Expression...")
        cache = self.getCacheObject(DEFAULT_CACHE_SIZE)
        nrows = self.getNumRows()
        
        # do any imports
        importsDict = {}
        exec(imports, importsDict)

        saneColumnNames = set(self.getSaneColumnNames())
        columnsUsed = self.oldViewerRAT.findVarNamesUsed(expression, saneColumnNames)

        # create the new selected array the full size of the rat
        # we will fill in each chunk as we go
        result = numpy.empty(nrows, dtype=bool)

        currRow = 0

        while currRow < nrows:
            cache.setStartRow(currRow, colName=columnsUsed)
            length = cache.getLength()

            isselectedSub = isselected[currRow:currRow + length]
            if lastselected is not None:
                lastselectedSub = lastselected[currRow:currRow + length]
            else:
                lastselectedSub = None
            globaldict = self.getUserExpressionGlobals(cache, isselectedSub, 
                                queryRow, lastselectedSub,
                                colNameList=columnsUsed)
            globaldict.update(importsDict)

            try:
                resultSub = eval(expression, globaldict)
            except Exception as exc:
                msg = formatException(expression)
                raise viewererrors.UserExpressionSyntaxError(msg) from exc

            # check type of result
            if not isinstance(resultSub, numpy.ndarray):
                msg = 'must return a numpy array'
                raise viewererrors.UserExpressionTypeError(msg)

            if resultSub.dtype.kind != 'b':
                msg = 'must return a boolean array'
                raise viewererrors.UserExpressionTypeError(msg)

            result[currRow:currRow + length] = resultSub
            currRow += DEFAULT_CACHE_SIZE
            self.oldViewerRAT.newPercent.emit(int((currRow / nrows) * 100))

        self.oldViewerRAT.endProgress.emit()
        return result
            
    def evaluateUserEditExpression(self, colName, imports, expression, isselected, 
            queryRow):
        if colName not in self.columnNames:
            # pass through
            self.oldViewerRAT.evaluateUserEditExpression(colName, imports, expression, isselected, queryRow)
        else:
            self.oldViewerRAT.newProgress.emit("Evaluating User Expression...")
            cache = self.getCacheObject(DEFAULT_CACHE_SIZE)
            nrows = self.getNumRows()
    
            currRow = 0
            done = False
            isScalar = False  # user code returns a scalar - we 
            # can take shortcuts since not all the cols need to be read
            resultSub = None
    
            # do any imports
            importsDict = {}
            exec(imports, importsDict)
    
            saneColumnNames = set(self.getSaneColumnNames())
            columnsUsed = self.oldViewerRAT.findVarNamesUsed(expression, saneColumnNames)
    
            while currRow < nrows and not done:
    
                # guess the length
                isselectedSub = isselected[currRow:currRow + DEFAULT_CACHE_SIZE]
                if isselectedSub.any():
    
                    if isScalar:
                        cache.setStartRow(currRow, colName)
                    else:
                        cache.setStartRow(currRow, (columnsUsed + [colName]))
                    length = cache.getLength()
    
                    # re do with correct length
                    isselectedSub = isselected[currRow:currRow + length]
                    globaldict = self.getUserExpressionGlobals(cache, isselectedSub, 
                                    queryRow, colNameList=columnsUsed)
                    globaldict.update(importsDict)
    
                    if not isScalar:
                        # can re-use the first result if scalar
                        # all calls should be the same
                        try:
                            resultSub = eval(expression, globaldict)
                        except Exception as exc:
                            msg = formatException(expression)
                            raise viewererrors.UserExpressionSyntaxError(msg) from exc
    
                    cache.updateColumn(colName, resultSub, isselected)
    
                    if numpy.isscalar(resultSub):
                        isScalar = True
    
                currRow += DEFAULT_CACHE_SIZE
                self.oldViewerRAT.newPercent.emit(int((currRow / nrows) * 100))
    
            self.oldViewerRAT.endProgress.emit()
        
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
        
        for zname in self.zarrColNames:
            if colName is None or zname == colName or zname in colName:
                data = self.zarrObj.readBlock(zname, self.currStartRow, self.length)
                self.zarrcacheDict[zname] = data

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

            # coerce type
            numpydtype = self.zarrObj.getColumnDtype(colName)
            if numpy.isscalar(data):
                data = numpy.full(selectionArraySubset.shape, data, dtype=numpydtype)
            else:
                data = data.astype(numpydtype)
                
            if not selectionArraySubset.all():
                # some need to be updated
                # keep old where selectionArray == False
                olddata = self.zarrcacheDict[colName] 
            
                # it is assumed this will do the right thing when 
                # string lengths are different
                data = numpy.where(selectionArraySubset, data, olddata)

            # update cache
            self.zarrcacheDict[colName] = data
            # write back to file
            self.zarrObj.writeBlock(colName, data, self.currStartRow)
        else:
            self.gdalRATCache.updateColumn(colName, data, selectionArray)


class AddColumnZarrDialog(QDialog):
    """
    Dialog that allows a user to select type of new RAT
    column and enter the name
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.typeCombo = QComboBox()
        # get all the zarr types
        for dname, cls in zarrdtype.data_type_registry.contents.items():
            self.typeCombo.addItem(dname, cls)

        self.nameEdit = QLineEdit()

        self.formLayout = QFormLayout()
        self.formLayout.addRow("Column Type", self.typeCombo)
        self.formLayout.addRow("Column Name", self.nameEdit)

        self.okButton = QPushButton()
        self.okButton.setText("OK")
        self.okButton.clicked.connect(self.onOK)

        self.cancelButton = QPushButton()
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(self.reject)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addLayout(self.formLayout)
        self.mainLayout.addLayout(self.buttonLayout)
        self.nameEdit.setFocus()
        self.setLayout(self.mainLayout)

    def onOK(self):
        if len(self.nameEdit.text()) == 0:
            QMessageBox.critical(self, name(), "Must enter column name")
            self.nameEdit.setFocus()
        else:
            self.accept()

    def getColumnType(self):
        index = self.typeCombo.currentIndex()
        userdata = self.typeCombo.itemData(index)
        return userdata

    def getColumnName(self):
        return self.nameEdit.text()
