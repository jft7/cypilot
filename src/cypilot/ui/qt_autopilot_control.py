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
import time
import os
import subprocess
import signal

from random import randint
from signal import SIGTERM

import cypilot.pilot_path

from client import cypilotClient
from pilots.autotune import list_of_gain

import pyjson

from PySide2.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QSizePolicy, QSlider, QComboBox
from PySide2.QtWidgets import QLabel, QPushButton, QFrame, QApplication, QMessageBox, QMainWindow
from PySide2.QtCore import QMargins, Qt, QTimer, QPoint, Signal

from pilot_path import dprint as print

autopilot = None
def run_autopilot():
    global autopilot
    autopilot_path = os.path.dirname(os.path.abspath(__file__)) + '/qt_autopilot.py'
    autopilot = subprocess.Popen(['python3', autopilot_path], stdout=subprocess.DEVNULL)
    print(autopilot)

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
        self.setValue(self, value)
        
class QFlagButton(QPushButton):
    """Inherited from QPushButton with flag.
    """
    def __init__(self, *args, **kwargs):
        super(QFlagButton, self).__init__(*args, **kwargs)
        self.flag = False
        self.textFlag = ""

class AutoSizeQLabel(QLabel):
    """Inherited from QLabel with autosize function. With new custom event to
    track change of text value
    """

    def __init__(self,  *args, **kwargs):
        super(AutoSizeQLabel, self).__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignCenter)

    def setNum(self, *args, **kwargs):
        super().setNum(*args, **kwargs)

    def setText(self, *args, **kwargs):
        super().setText(*args, **kwargs)


class Setting(QWidget):
    valueChanged = Signal(float)

    def __init__(self, name="NA", defaultValue=5, minValue=0,
        maxValue=10, stepNumber=10, decimals=2, refreshTime=500, *args, **kwargs):

        # inheritance
        super(Setting,self).__init__(*args, **kwargs)

        #retrieve parameter
        self._name = name
        self._defaultValue = defaultValue
        self._minValue = minValue
        self._maxValue = maxValue
        self._stepNumber = stepNumber
        self._decimals = decimals
        self._refreshTime = refreshTime

        #create new parameter
        self._settingValue = defaultValue
        self._actionFlag = False
        self.lastUpdate = time.monotonic()

        #define slider parameter:
        self._step = (self._maxValue-self._minValue)//self._stepNumber
        self._pageStep = self._step * (self._stepNumber // 10)

        #design a box around the widget
        self._box = QFrame()
        self._box.setFrameStyle(
            QFrame.StyledPanel | QFrame.Plain)
        self._box.setMinimumSize(100,160)
        self._box.setSizePolicy(
            QSizePolicy.MinimumExpanding,
            QSizePolicy.MinimumExpanding)

        #create widget to put in the box
        self._name = AutoSizeQLabel(text=str(self._name).upper())
        self._slider = DoubleSlider(decimals=self._decimals)
        self._value = AutoSizeQLabel(text=str(self._defaultValue))
        #create layout for them
        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(QMargins(0,0,0,0))
        self._layout.addWidget(self._name)
        self._layout.addWidget(self._slider, alignment=Qt.AlignHCenter)
        self._layout.addWidget(self._value)
        #set layout to the box
        self._box.setLayout(self._layout)

        #put the box in a layout in the autoSizeSetting widget
        self._outsideLayout = QVBoxLayout()
        self._outsideLayout.setContentsMargins(QMargins(0,0,0,0))
        self._outsideLayout.addWidget(self._box)
        self.setLayout(self._outsideLayout)

        # Tune widget
        # name
        self._name.setSizePolicy(
            QSizePolicy.MinimumExpanding,
            QSizePolicy.Preferred)

        # Slider
        self._slider.setOrientation(Qt.Vertical)
        self._slider.setRange(self._minValue, self._maxValue)
        self._slider.setValue(self._defaultValue)
        self._slider.setSingleStep(self._step)
        self._slider.setPageStep(self._pageStep)
        self._slider.setMinimumSize(10, 50)

        self._slider.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.MinimumExpanding)

        # Value
        self._value.setSizePolicy(
            QSizePolicy.MinimumExpanding,
            QSizePolicy.Preferred)

        # Finally attach slider to value, oth side connection
        self._slider.doubleValueChanged.connect(self.sendNewValue)
        self._slider.actionTriggered.connect(self.onActionTriggered)

    @property
    def settingValue(self):
        return self._settingValue

    @settingValue.setter
    def settingValue(self, value):
        self._actionFlag = False
        self._slider.setValue(value)

    def onActionTriggered(self,action, event=None):
        if action is not None:
            self._actionFlag = True

    def changeLabel(self, value, event=None):
        self.lastUpdate = time.monotonic()
        self._value.setNum(value)
        self._settingValue = value

    def sendNewValue(self, value, event=None):
        self.changeLabel(value)
        if self._actionFlag is True:
            self.valueChanged.emit(value)

class Tuner(QWidget):

    def __init__(self, refresh_time=1, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.host = None
        if len(sys.argv) > 1:
            self.host = sys.argv[1]

        self.client = False
        self.autorun = False
        self.autotune = False

        try:
            self.client = cypilotClient(self.host)
            self.client.connect(False)
        except Exception as e:
            print(e)
            print("Fail to connect to server")
            
        # attempt to launch autopilot if it is not running
        if not self.client.connection and not self.autorun:
            global autopilot
            if ((autopilot is None) or (autopilot.poll() is not None)):
                run_autopilot()
                self.autorun = True
        # and continue ...

        self.list_client_value = dict()

        self._watch_list = [
            "ap.mode",
            "ap.pilot",
            "ap.heading",
            "ap.heading_command",
            "ap.enabled",
        ]

        self.map_command = {
            '<<': -10,
            '<': -1,
            'O/I': 0,
            '>': 1,
            '>>': 10
        }

        self.watch_list = []
        self.gain_list = []
        self.gain_dict = {}
        self.pilot_dict = {}
        self.command_dict = {}
        self.mode_dict = {}

        self._lastpilot = None

        self._refresh_time = refresh_time

        for item in self._watch_list:
            self.client.watch(item)

        self.value = self.client.receive(1.000)
        self.receiveNoError("ap.pilot", 20.0)
        time.sleep(1.0)

        self.timer = QTimer(self)
        self.timer.setInterval(self._refresh_time*1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self._updateWatchList()
        self.chooseWatchList()

        """Create GUI here"""
        
        #baseLayout
        self.baseLayout = QGridLayout()
        self.setLayout(self.baseLayout)

        self.pilotLayout = QHBoxLayout()
        self.commandLayout = QHBoxLayout()
        self.modeLayout = QHBoxLayout()
        self.settingLayout = QHBoxLayout()
        self.dashLayout = QGridLayout()

        self.baseLayout.addLayout(self.pilotLayout, 0, 0)
        self.baseLayout.addLayout(self.dashLayout, 1, 0)
        self.baseLayout.addLayout(self.modeLayout, 2, 0)
        self.baseLayout.addLayout(self.settingLayout, 3, 0)
        self.baseLayout.addLayout(self.commandLayout, 4, 0)

        #pilot part
        for item in self.list_client_value["ap.pilot"]["choices"]:
            self.pilot_dict[item] = QPushButton(item)
            self.pilot_dict[item].clicked.connect(self.pilotFunction)
            self.pilot_dict[item].setStyleSheet('''
                QPushButton:disabled {
                    color: black;
                    font: bold;
                    text-transform: uppercase;
                }
            ''')
            self.pilot_dict[item].setAutoRepeat(True)
            self.pilot_dict[item].setAutoRepeatDelay(1500)
            self.pilotLayout.addWidget(self.pilot_dict[item])

        #command part
        self.list_command = ["<<", "<", "O/I", ">", ">>"]
        for item in self.list_command:
            self.command_dict[item] = QFlagButton(item)
            self.command_dict[item].setStyleSheet('''
                QPushButton:pressed {
                    background: lightgrey;
                    border-radius: 2px;
                }
            ''')
            self.command_dict[item].setAutoRepeat(True)
            self.command_dict[item].setAutoRepeatDelay(3000)
            self.command_dict[item].setAutoRepeatInterval(3000)
            self.command_dict[item].clicked.connect(self.commandFunction)
            self.commandLayout.addWidget(self.command_dict[item])

        #mode part
        for item in self.list_client_value["ap.mode"]["choices"]:
            self.mode_dict[item] = QPushButton(item)
            self.mode_dict[item].clicked.connect(self.modeFunction)
            self.mode_dict[item].setStyleSheet('''
                QPushButton:disabled {
                    color: black;
                    font: bold;
                    text-transform: uppercase;
                }
            ''')
            self.modeLayout.addWidget(self.mode_dict[item])

        #setting part
        self.createGainSettings()

        #dash part
        self.dash = {
            "headingLabel" : (QLabel("Heading"), 0, 0),
            "commandLabel" : (QLabel("Command"), 0, 1),
            "headingDash" : (QLabel("---"), 1, 0),
            "commandDash" : (QLabel("---"), 1, 1)
        }
        for item in self.dash:
            self.dashLayout.addWidget(self.dash[item][0], self.dash[item][1], self.dash[item][2], alignment=Qt.AlignHCenter)
        self.dash["headingDash"][0].setStyleSheet("font-weight: bold")
        self.dash["commandDash"][0].setStyleSheet("font-weight: bold")

        #update
        self.modeUpdateState()
        self.pilotUpdateState()

    def dashUpdate(self):
        command = str(round(self.value["ap.heading_command"])) + " °"
        heading = str(round(self.value["ap.heading"])) + " °"
        self.dash["commandDash"][0].setText(command)
        self.dash["headingDash"][0].setText(heading)

    def createGainSettings(self):
        self.chooseWatchList()
        for item in self.gain_dict:
            self.gain_dict[item].setParent(None)
        self.gain_dict.clear()

        for item in self.gain_list:
            self.receiveNoError(item)
            item_splitted = item.split('.')[-1]
            if "learning" in item:
                for mode in self.list_client_value["ap.pilot.learning.model"]["choices"]:
                    self.gain_dict[mode] = QPushButton(mode)
                    self.gain_dict[mode].clicked.connect(self.learningGainFunction)
                    self.gain_dict[mode].setStyleSheet('''
                        QPushButton:disabled {
                            color: black;
                            font: bold;
                        }
                    ''')
                    self.settingLayout.addWidget(self.gain_dict[mode])
            else:
                self.gain_dict[item] = Setting(name=item_splitted, minValue=self.list_client_value[item]['min'], maxValue=self.list_client_value[item]['max'], defaultValue=self.value[item])
                self.gain_dict[item].valueChanged.connect(self.gainFunction)
                self.settingLayout.addWidget(self.gain_dict[item])

    @property
    def refresh_time(self):
        return self._refresh_time

    @refresh_time.setter
    def refresh_time(self, value):
        self._refresh_time = value
        self.timer.setInterval(value)

    def learningGainFunction(self):
        identity = self.sender().text()
        self.client.set("ap.pilot.learning.model", identity)
        for item in self.gain_dict:
            if item is identity:
                self.gain_dict[item].setEnabled(False)
            else:
                self.gain_dict[item].setEnabled(True)

    def gainFunction(self, value=None):
        if value is not None: #simple/autotune mode
            identity = "ap.pilot." + self.value["ap.pilot"] + "." + self.sender()._name.text()
            # temporary patch to make Ed pilot 'period' functionnality working ...
            if identity not in self.gain_list:
                identity = identity.lower()
            # TBD: keep this option ?
            self.client.set(identity, value)
            self.value[identity]= value

    def gainUpdate(self, receive_now=True):
        if receive_now:
            self.receive()
        if self.value["ap.pilot"] == "learning":
            for item in self.gain_dict:
                if item == self.value["ap.pilot.learning.model"]:
                    self.gain_dict[item].setEnabled(False)
                else:
                    self.gain_dict[item].setEnabled(True)
        else:
            for item in self.gain_dict:
                try:
                    if (time.monotonic() - self.gain_dict[item].lastUpdate) > self._refresh_time:
                        self.gain_dict[item].settingValue = self.value[item]
                except AttributeError: # if refresh occur during createGainSettings function
                    pass

    def refresh(self):
        self.receive()
        self.modeUpdateState(receive_now=False)
        self.pilotUpdateState(receive_now=False)
        self.gainUpdate(receive_now=False)
        self.dashUpdate()
        self.commandUpdateState()

    def modeFunction(self):
        identity = self.sender().text()
        self.client.set("ap.mode", identity)
        self.refresh()

    def modeUpdateState(self, receive_now=True):
        if receive_now:
            mode = self.receiveNoError("ap.mode")
        else:
            mode = self.value["ap.mode"]
        for item in self.mode_dict:
            if item == mode:
                self.mode_dict[item].setEnabled(False)
            else:
                self.mode_dict[item].setEnabled(True)

    def commandFunction(self, event):
        id = self.sender()
        if id.isDown() and id.text() in ['<<', '>>'] and id.flag == False:
            id.flag = True
            id.setStyleSheet('''
                QPushButton:pressed {
                    background: red;
                }
            ''')
        elif id.isDown() and id.text() in ['<<', '>>'] and id.flag :
            id.flag = False
            id.setStyleSheet('''
                QPushButton:pressed {
                    background: lightgrey;
                }
            ''')
        else:
            if id.text() in ['<<', '>>'] and id.flag:
                self.tack(id.text())
                id.flag = False
                id.setStyleSheet('''
                    QPushButton:pressed {
                        background: lightgrey;
                    }
                ''')
            else:
                self.command(id.text())

    def command(self, identity):
        self.receive()
        if self.map_command[identity] != 0:
            new_command = self.value["ap.heading_command"] + self.map_command[identity]
            self.client.set("ap.heading_command", new_command)
        else:
            state = self.value["ap.enabled"]
            new_state = not state
            if new_state:
                self.client.set("ap.heading_command", round(self.value['ap.heading']))
            self.client.set("ap.enabled", new_state)
            if not new_state:
                self.client.set("servo.command", 0)

    def commandUpdateState(self):
        if self.value["ap.enabled"]:
            self.command_dict['O/I'].setStyleSheet('''
                QPushButton {
                    background-color: lightgreen;
                    border-style: outset;
                    border-width: 2px;
                    border-radius: 10px;
                    border-color: beige;
                    font: bold 14px;
                    min-width: 8em;
                    padding: 6px;
                }
            ''')
                
        else:
            self.command_dict['O/I'].setStyleSheet('''
                QPushButton {
                    background-color: orange;
                    border-style: outset;
                    border-width: 2px;
                    border-radius: 10px;
                    border-color: beige;
                    font: bold 14px;
                    min-width: 8em;
                    padding: 6px;
                }
            ''')
        
    def tack(self, identity):
        self.receive()
        if self.value["ap.enabled"]:
            if self.map_command[identity] == -10:
                direction = 'port'
            if self.map_command[identity] == 10:
                direction = 'starboard'
            self.client.set('ap.tack.direction', direction)
            self.client.set('ap.tack.state', 'begin')

    def pilotFunction(self, event):
        button = self.sender()
        identity = button.text()
        if button.isDown() and identity == 'autotune':
            if self.autotune == False:
                self.autotune = True
                button.setStyleSheet('''
                    QPushButton:pressed {
                        color: red;
                        font: bold;
                        text-transform: uppercase;
                    }
                    ''')
        elif self.autotune and identity == 'autotune':
            self.autotune = False
            self.autotuneDialog = AutotuneWizard(self.client,self)
            pos = button.mapToGlobal(QPoint(0, 0))
            self.autotuneDialog.move( pos )
            self.autotuneDialog.setWindowTitle("CyPilot Autotune Settings")
            self.autotuneDialog.show()
        self.client.set("ap.pilot", identity)
        self.value["ap.pilot"] = identity
        self.refresh()

    def pilotUpdateState(self, receive_now=True):
        if receive_now:
            pilot = self.receiveNoError("ap.pilot")
        else:
            pilot = self.value["ap.pilot"]

        if self._lastpilot != pilot:
            self.createGainSettings()
            self._lastpilot = pilot

        for item in self.pilot_dict:
            if item == pilot:
                if not self.autotune:
                    self.pilot_dict[item].setStyleSheet('''
                        QPushButton {
                                color: black;
                                font: bold;
                                text-transform: uppercase;
                            }
                        ''')
            else:
                self.pilot_dict[item].setStyleSheet('''
                    QPushButton {
                            color: black;
                            font: normal;
                            text-transform: lowercase;
                        }
                    ''')

    def _updateWatchList(self):
        list_values = self.client.list_values(10)
        if list_values:
            self.list_client_value = list_values
            for item in list_values["ap.pilot"]["choices"]:
                if item == "learning":
                    self.watch_list.append("ap.pilot.learning.model")
                else:
                    k = "ap.pilot."+ item
                    for i in list_values:
                        if k in i:
                            if "gain" not in i:
                                self.watch_list.append(i)

    def chooseWatchList(self, receive_now=True):
        pilot = self.receiveNoError('ap.pilot')
        self.gain_list = []
        for item in self.watch_list:
            if pilot in item:
                self.client.watch(item, True)
                self.gain_list.append(item)
            else:
                self.client.watch(item, False)
        self.gainSort()

    def gainSort(self):
        ref_list = ['P', 'D', 'I', 'H', 'G', 'O', 'M']
        ref = []
        oth = []
        for item in self.gain_list:
            if item[-1] in ref_list:
                ref.append(item)
            else:
                oth.append(item)
        ref.sort(key= lambda x: ref_list.index(x[-1]))
        oth.sort()
        refoth = ref + oth
        output = []
        for item in refoth:
            if item not in output:
                output.append(item)
        self.gain_list = output

    def receive(self):
        self.value.update(self.client.receive())

    def receiveNoError(self, item, time_out=2.000):
        self.receive()
        try:
            value = self.value[item]
        except KeyError:
            t0 = time.monotonic()
            while item not in self.value:
                self.value.update(self.client.receive(1.000))
                if time.monotonic() - t0 > time_out:
                    self.quickMsg('Error - item not received : '+item)
                    self._lastpilot = None
                    raise TimeoutError
            value = self.value[item]
        return value

    def quickMsg(self, msg):
        tmpMsg = QMessageBox(self)
        tmpMsg.setWindowTitle("CyPilot Info")
        tmpMsg.setText(msg)
        tmpMsg.addButton("OK",QMessageBox.YesRole)
        tmpMsg.exec_()
        
        
class AutotuneWizard(QWidget):
    def __init__(self,  client, control=None, parent=None, modal=True):
        super(AutotuneWizard, self).__init__(parent)
        
        self.client = client
        self.control = control

        self.dirpath = os.path.expanduser("~/cypilot_settings")
        self.tab_of_gain = self.load_JSON()
        
        """Create GUI here"""
        
        #baseLayout
        self.baseLayout = QGridLayout()
        
        self.textLayout = QHBoxLayout()
        self.conditionLayout = QGridLayout()
        self.gainLayout = QHBoxLayout()
        self.buttonLayout = QHBoxLayout()
        
        self.baseLayout.addWidget(QLabel("Choose condition, change gain.\n When it's finished, don't forget to click save."),0, 0)
        self.baseLayout.addLayout(self.conditionLayout, 1, 0)
        self.baseLayout.addLayout(self.gainLayout, 2, 0)
        self.baseLayout.addLayout(self.buttonLayout, 3, 0)
        
        self.comboAllure = QComboBox()
        self.comboWind = QComboBox()
        
        self.conditionLayout.addWidget(QLabel("Wind speed (knts)"), 0, 0)
        self.conditionLayout.addWidget(QLabel("True Wind direction (°)"), 0, 1)
        self.conditionLayout.addWidget(self.comboAllure, 1, 1)
        self.conditionLayout.addWidget(self.comboWind, 1, 0)
        
        self.windList = []
        self.allureList = []
        self.retreiveCondition()
        print(self.tab_of_gain)
        
        for key in self.windList:
            self.comboWind.addItem(key)
            
        for key in self.allureList:
            self.comboAllure.addItem(key)
            
        self.comboWind.activated[str].connect(self.onChanged)
        self.comboAllure.activated[str].connect(self.onChanged)
        
        self.gain_dict = {}
        self.createGainSettings()
        
        self.saveButton = QPushButton("Save")
        self.saveButton.clicked.connect(self.saveFunction)
        self.buttonLayout.addWidget(self.saveButton)
        
        self.setLayout(self.baseLayout)
        
    def saveFunction(self):
        with open(self.dirpath + '/autotune_settings.txt', "w") as outfile:
            pyjson.dump(self.tab_of_gain, outfile, indent=4)
            
    def createGainSettings(self):
        list_client_value = self.control.list_client_value if self.control else self.client.list_values(100)
        
        for item in list_of_gain:
            self.gain_dict[item] = Setting(name=item, 
                                           minValue=list_client_value[("ap.pilot.simple."+ item)]['min'], 
                                           maxValue=list_client_value["ap.pilot.simple."+ item]['max'], 
                                           defaultValue=self.tab_of_gain[self.comboAllure.currentText()][self.comboWind.currentText()][item])
            self.gain_dict[item].valueChanged.connect(self.gainFunction)
            self.gainLayout.addWidget(self.gain_dict[item])
            
    def gainFunction(self):
        id = self.sender()._name.text()
        self.tab_of_gain[self.comboAllure.currentText()][self.comboWind.currentText()][id] = self.gain_dict[id].settingValue
                
    def onChanged(self):
        for item in list_of_gain:
            self.gain_dict[item].settingValue = self.tab_of_gain[self.comboAllure.currentText()][self.comboWind.currentText()][item]
            
    def retreiveCondition(self):
        w = []
        a = []
        for item in self.tab_of_gain:
            a.append(item)
            for i in self.tab_of_gain[item]:
                w.append(i)
                
        w = list(set(w))
        a.sort(key=int)
        w.sort(key=int)
        self.windList = w
        self.allureList = a
        
    def load_JSON(self):
        with open(self.dirpath + '/autotune_settings.txt', 'r') as f:
            return pyjson.load(f)

def qt_main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setCentralWidget(Tuner())
    window.setWindowTitle("CyPilot Control")
    window.show()
    
    def quitSignal():
        if autopilot:
            autopilot.send_signal(SIGTERM)
        time.sleep(2)

    def handler(signum,frame):
        quitSignal()
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    ret = app.exec_()
    
    # kill autopilot process and exit
    # WARNING : at the moment, we kill the autopilot process on exit, regardless if any other client is connected !!!
    quitSignal()

    sys.exit(ret)

if __name__ == '__main__':
    qt_main()

