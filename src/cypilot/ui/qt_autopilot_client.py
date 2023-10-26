#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (support@netcys.com)
#
# This program incorporates code from modified version of pypilot:
# (C) 2019 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b
#

# pylint: disable=unused-import,wildcard-import,invalid-name

import sys
import math
import os
import re

from PySide2.QtOpenGL import QGLWidget
from PySide2.QtCore import Qt, QTimer, Signal
from PySide2.QtWidgets import QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QCheckBox, QSlider, QScrollArea, QSizePolicy
from PySide2.QtWidgets import QLabel, QComboBox, QPushButton, QProgressBar, QFrame, QSpinBox, QDoubleSpinBox, QApplication, QLineEdit

import cypilot.pilot_path
import pyjson
from pilot_path import PILOT_DIR
from client import cypilotClient


VALUE_DIGITS = 2

def roundN(value):
    if isinstance(value, list):
        return list(map(roundN, value))
    elif isinstance(value, dict):
        ret = {}
        for each in value:
            ret[roundN(each)] = roundN(value[each])
        return ret
    elif isinstance(value, float):
        return round(value, VALUE_DIGITS)
    return value

class DoubleSlider(QSlider):
    """
    Custom slider which return double.
    Inherit from QSlider.
    Args: decimals (int) : nomber of decimal to return
    Signal: doubleValueChanged
    """

    doubleValueChanged = Signal(float)
    signalMouseRelease = Signal(float)


    def __init__(self, decimals=1, *args, **kwargs):
        super(DoubleSlider, self).__init__( *args, **kwargs)
        self._multi = 10 ** decimals

        self.valueChanged.connect(self.emitDoubleValueChanged)

    def emitDoubleValueChanged(self):
        self.doubleValueChanged.emit(self.value())

    def value(self):
        return float(super(DoubleSlider, self).value()) / self._multi

    def setRange(self, min_value, max_value):
        return super(DoubleSlider,self).setRange(
            min_value * self._multi,
            max_value* self._multi
            )

    def setMinimum(self, value):
        return super(DoubleSlider, self).setMinimum(value * self._multi)

    def setMaximum(self, value):
        return super(DoubleSlider, self).setMaximum(value * self._multi)

    def setSingleStep(self, value):
        return super(DoubleSlider, self).setSingleStep(value * self._multi)

    def singleStep(self):
        return float(super(DoubleSlider, self).singleStep()) / self._multi

    def setValue(self, value):
        super(DoubleSlider, self).setValue(int(value * self._multi))

    def minimum(self):
        return float(super(DoubleSlider, self).minimum()) / self._multi

    def maximum(self):
        return float(super(DoubleSlider, self).maximum()) / self._multi

    def changeDecimal(self, newDecimal):
        value = self.value()
        self._multi = newDecimal
        self.setValue(value)

# Dialog with Tabs :
#   - values
#   - filters

class TabDialog(QDialog):
    def __init__(self, parent=None):
        super(TabDialog, self).__init__(parent)

        # initialize CyPilot client
        self.host = 'localhost'
        if len(sys.argv) > 1:
            self.host = sys.argv[1]
        self.client = False
        self.client = cypilotClient(self.host)
        self.client.connect(False)

        # create tab dialog
        tabWidget = QTabWidget()
        self.FilterTab = FilterTab(self.client)
        self.ValueTab = ValueTab(self.client, self.FilterTab)
        tabWidget.addTab(self.ValueTab, "Values")
        tabWidget.addTab(self.FilterTab, "Filters")
        mainLayout = QVBoxLayout()
        mainLayout.addWidget(tabWidget)
        self.setLayout(mainLayout)
        self.resize(800, 500)

        self.setWindowTitle("CyPilot Configuration")

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.receive_messages)
        self.timer.start()

    def receive_messages(self):
        self.client.poll()

        self.ValueTab.update_table(self.client.list_values())

        msg = self.client.receive_single()
        while msg:
            self.ValueTab.receive_message(msg)
            msg = self.client.receive_single()
        return

#
# Value Tab
# ---------
#

class ValueTab(QWidget):
    def __init__(self, client, filter, parent=None):
        super(ValueTab, self).__init__(parent)

        # Filter dialog
        self.filter = filter

        # CyPilot client
        self.client = client
        self.value_list = {}
        self.wxlabel = {}
        self.wxvalue = {}
        self.wxcontrol = {}
        self.oncontrol = {}
        self.srange = {}
        self.line = 0

        # QT Dialog     
        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        scroll = QScrollArea()
        
        content_widget = QWidget()
        scroll.setWidget(content_widget)
        scroll.setWidgetResizable(True)
        
        lay = QVBoxLayout(content_widget)
        
        table_widget = QWidget()
        lay.addWidget(table_widget)
        
        # scroll.setFixedHeight(400)
        mainLayout.addWidget(scroll)

        # Set the layout
        self.table_layout = QGridLayout()
        scroll = QScrollArea()
        # scroll.setWidget(table_widget)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(400)
        table_widget.setLayout(self.table_layout)
        # self.table_layout.addWidget(scroll)

    def update_table(self, value_list):
        if (not value_list or value_list == self.value_list) and self.filter.display_refresh == 0:
            return
        elif self.filter.display_refresh > 0:
            self.client.disconnect()
            self.filter.display_refresh -= 1
            self.client.connect()

        if value_list and value_list != self.value_list:
            self.value_list = value_list
            for name in sorted(value_list):
                t = value_list[name]['type']
                self.client.watch(name, 10 if t == 'SensorValue' else True)

        self.line = 0
        self.wxlabel = {}
        self.wxvalue = {}
        self.wxcontrol = {}
        self.oncontrol = {}
        self.srange = {}

        for i in reversed(range(self.table_layout.count())): 
            widgetToRemove = self.table_layout.itemAt(i).widget()
            self.table_layout.removeWidget(widgetToRemove)
            widgetToRemove.setParent(None)

        for name in sorted(self.value_list):
            # if (name in self.wxlabel) or (self.filter.display_name != '' and not self.filter.display_name in name):
            if (name in self.wxlabel) or (self.filter.display_name != '' and re.search(self.filter.display_name, name) is None):
                continue
            
            def value_line():
                c0 = QLabel(name)
                c0.setStyleSheet("font-weight: bold")
                self.wxlabel[name] = c0
                self.table_layout.addWidget( c0, self.line, 0, alignment=Qt.AlignLeft )

                c1 = QLabel('---')
                self.wxvalue[name] = c1
                self.table_layout.addWidget( c1, self.line, 1, alignment=Qt.AlignCenter )

            t = self.value_list[name]['type']

            if t == 'Property' and self.filter.display_properties:
                value_line()
            
            elif (t == 'BooleanProperty' and self.filter.display_properties) or (t == 'BooleanSetting' and self.filter.display_settings):
                value_line()
                c3 = QCheckBox('')
                self.table_layout.addWidget( c3, self.line, 2)
                self.wxcontrol[name] = c3
                self.oncontrol[c3] = name
                c3.stateChanged.connect(self.onCheckBox)

            elif (t == 'RangeProperty' and self.filter.display_properties) or (t == 'RangeSetting' and self.filter.display_settings):
                value_line()
                r = self.value_list[name]['min'], self.value_list[name]['max']
                c3 = QSlider(Qt.Horizontal)
                self.table_layout.addWidget( c3, self.line, 2)
                c3.setRange(0, 1000)
                self.wxcontrol[name] = c3
                self.oncontrol[c3] = name
                self.srange[c3] = r
                c3.valueChanged.connect(self.onSlider)
                
            elif (t == 'EnumProperty' and self.filter.display_properties) or (t == 'EnumSetting' and self.filter.display_settings):
                value_line()
                c3 = QComboBox()
                self.table_layout.addWidget( c3, self.line, 2)
                for choice in self.value_list[name]['choices']:
                    c3.addItem(str(choice))
                self.wxcontrol[name] = c3
                self.oncontrol[c3] = name
                c3.currentTextChanged.connect(self.onComboBox)
                
            elif t == 'ResettableValue' and self.filter.display_values:
                value_line()
                c3 = QPushButton('Reset')
                self.table_layout.addWidget( c3, self.line, 2)
                self.wxcontrol[name] = c3
                self.oncontrol[c3] = name
                c3.clicked.connect(self.onResetButton)

            elif (t == 'Value' and self.filter.display_values) or (t == 'SensorValue' and self.filter.display_sensorvalues):
                value_line()
                c3 = QLabel('-')
                self.table_layout.addWidget( c3, self.line, 2)
                
            elif t == 'TimeStamp' and self.filter.display_timestamp:
                value_line()
                c3 = QLabel('-')
                self.table_layout.addWidget( c3, self.line, 2)
                
            else:
                continue
            
            self.table_layout.setRowStretch(self.line,0)
            self.line += 1
        
        c0 = QLabel('')
        self.table_layout.addWidget( c0, self.line, 0, alignment=Qt.AlignLeft )
        self.table_layout.setRowStretch(self.line,10)

    def onCheckBox(self,event):
        identity = self.sender()
        self.client.set(self.oncontrol[identity], identity.isChecked())
        
    def onSlider(self,event):
        identity = self.sender()
        r = self.srange[identity]
        v = identity.value() / 1000.0 * (r[1] - r[0]) + r[0]
        self.client.set(self.oncontrol[identity], v)
        
    def onComboBox(self,event):
        identity = self.sender()
        self.client.set(self.oncontrol[identity], identity.currentText())
        
    def onResetButton(self,event):
        identity = self.sender()
        self.client.set(self.oncontrol[identity], 0)

    def receive_message(self,msg):
        name, value = msg
        if name in self.wxvalue:
            value = roundN(value)
            type = self.value_list[name]['type']
            self.wxvalue[name].setText(str(value))
            try:
                if type == 'BooleanProperty' or type == 'BooleanSetting' :
                    self.wxcontrol[name].blockSignals(True)
                    self.wxcontrol[name].setChecked(value)
                    self.wxcontrol[name].blockSignals(False)
                elif type == 'EnumProperty' or type == 'EnumSetting':
                    self.wxcontrol[name].blockSignals(True)
                    self.wxcontrol[name].setEditText(value)
                    self.wxcontrol[name].blockSignals(False)
                elif type == 'RangeProperty' or type == 'RangeSetting':
                    r = self.srange[self.wxcontrol[name]]
                    self.wxcontrol[name].blockSignals(True)
                    self.wxcontrol[name].setValue(int(float(value - r[0])/(r[1]-r[0])*1000))
                    self.wxcontrol[name].blockSignals(False)
                else:
                    self.wxcontrol[name].blockSignals(True)
                    self.wxcontrol[name].setValue(value)
                    self.wxcontrol[name].blockSignals(False)
            except:
                pass
        return

#
# Filter Tab
# -----------
#

class FilterTab(QWidget):
    def __init__(self, client, parent=None):
        super(FilterTab, self).__init__(parent)
        
        #--- read config
        self.configfilename = PILOT_DIR + 'cypilot_clfilter.conf'

        try:
            file = open(self.configfilename)
            clfilter = pyjson.loads(file.readline())
            file.close()
            self.display_settings = clfilter["display_settings"]
            self.display_properties = clfilter["display_properties"]
            self.display_values = clfilter["display_values"]
            self.display_sensorvalues = clfilter["display_sensorvalues"]
            self.display_timestamp = clfilter["display_timestamp"]
            self.display_name = clfilter["display_name"]

        except Exception as e:
            print('Failed to read config file:', self.configfilename, e)
            self.display_settings = True
            self.display_properties = False
            self.display_values = False
            self.display_sensorvalues = False
            self.display_timestamp = False
            self.display_name = ""
        #---

        self.display_refresh = 1
                
        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        
        # QT Dialog
        filter_widget = QWidget()
        mainLayout.addWidget(filter_widget)

        # Set the layout
        filter_layout = QVBoxLayout()
        filter_widget.setLayout(filter_layout)
        
       
        # QT Dialog
        ptype_label = QLabel('Select type of parameters to be displayed (settings, properties, ...):')
        ptype_label.setStyleSheet("font-weight: bold")
        filter_layout.addWidget(ptype_label)

        self.ptype_settings = QCheckBox('Settings')
        self.ptype_settings.setChecked(self.display_settings)
        self.ptype_settings.clicked.connect(self.onFilter)
        filter_layout.addWidget(self.ptype_settings)
        self.ptype_properties = QCheckBox('Properties')
        self.ptype_properties.setChecked(self.display_properties)
        self.ptype_properties.clicked.connect(self.onFilter)
        filter_layout.addWidget(self.ptype_properties)
        self.ptype_values = QCheckBox('Values')
        self.ptype_values.setChecked(self.display_values)
        self.ptype_values.clicked.connect(self.onFilter)
        filter_layout.addWidget(self.ptype_values)
        self.ptype_sensorvalues = QCheckBox('Sensor Values')
        self.ptype_sensorvalues.setChecked(self.display_sensorvalues)
        self.ptype_sensorvalues.clicked.connect(self.onFilter)
        filter_layout.addWidget(self.ptype_sensorvalues)
        self.ptype_timestamp = QCheckBox('Timestamp')
        self.ptype_timestamp.setChecked(self.display_timestamp)
        self.ptype_timestamp.clicked.connect(self.onFilter)
        filter_layout.addWidget(self.ptype_timestamp)

        name_label = QLabel('\nEnter text pattern to select parameter names to be displayed:')
        name_label.setStyleSheet("font-weight: bold")
        filter_layout.addWidget(name_label)

        self.name_properties = QLineEdit(str(self.display_name))
        filter_layout.addWidget(self.name_properties)
        self.name_properties.textChanged.connect(self.onFilter)
        
        comment_label = QLabel("Example of valid patterns: \n"\
                               "    - \'pilot\' : any parameter which name contains \'pilot\'\n"\
                               "    - \'perf|wind\' : any parameter which name contains \'perf\' OR \'wind\'\n"\
                               "    - empty line or \'*\' : all the parameters\n"\
                               "Note that you can enter a regular expression pattern")
        filter_layout.addWidget(comment_label)
                
        filter_layout.addStretch()
        
    def onFilter(self,event):
        self.display_settings = self.ptype_settings.isChecked()
        self.display_properties = self.ptype_properties.isChecked()
        self.display_values = self.ptype_values.isChecked()
        self.display_sensorvalues = self.ptype_sensorvalues.isChecked()
        self.display_timestamp = self.ptype_timestamp.isChecked()
        t = self.name_properties.text()
        self.display_name = t if t != '*' else ''
        
        #--- write config
        clfilter = {"display_settings":self.display_settings,
                    "display_properties":self.display_properties,
                    "display_values":self.display_values,
                    "display_sensorvalues":self.display_sensorvalues,
                    "display_timestamp":self.display_timestamp,
                    "display_name":t}
        try:
            file = open(self.configfilename, 'w')
            file.write(pyjson.dumps(clfilter) + '\n')
            file.close()
        except Exception as e:
            print('Exception writing config file:', self.configfilename, e)
        #---
            
        self.display_refresh += 1

def qt_main():
    app = QApplication(sys.argv)

    tabdialog = TabDialog()
    tabdialog.exec_()
    
if __name__ == '__main__':
    qt_main()
    