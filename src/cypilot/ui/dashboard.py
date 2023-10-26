#!/usr/bin/env python
#
# (C) 2020 ED for Cybele Services (support@netcys.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b
#

import cypilot.pilot_path

import pyjson

from random import randint

from client import cypilotClient

from PySide2.QtWidgets import *
from PySide2.QtCore import QTimer, Signal, Qt
from PySide2.QtGui import *

from pilot_path import dprint as print

PILOT_DIR = cypilot.pilot_path.PILOT_DIR

data_convert_list = [
    ("imu.heading", "HEAD", " °", 0),
    ("imu.heel", "HEEL", " °", 0),
    ("imu.roll", "ROLL", " °", 0),
    ("imu.pitch", "PITCH", " °", 0),
    ("imu.headingrate", "ROTATION", " °/s", 0),
    ("gps.speed", "SOG", " kt", 1),
    ("sow.speed", "SOW", " kt", 1),
    ("ap.wind_direction", "AWD", " °", 0),
    ("ap.wind_angle", "AWA", " °", 0),
    ("ap.wind_speed", "AWS", " kt", 1),
    ("ap.true_wind_direction", "TWD", " °", 0),
    ("ap.true_wind_angle", "TWA", " °", 0),
    ("ap.true_wind_speed", "TWS", " kt", 1),
    ("perf.sail_advice", "CONFIG", "", 0),
    ("perf.target_spd", "POLAR SPD", " kt", 1),
    ("perf.polar_fract", "POLAR", " %", 1),
    ("perf.drift_direction", "DRIFT DIR", " °", 0),
    ("perf.drift_speed", "DRIFT SPD", " kt", 1),
    ("rudder.angle", "RUDDER", " °", 0 )
]

class DataDisplay(QFrame):
    clicked = Signal()
    def __init__(self, title='Title', data=0, buttons=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = data

        self.title_max_text_size = "AAAAA"
        self.title_min_font_size = 12
        self.title_max_font_size = 100

        self.data_max_text_size = "AAAAAAA"
        self.data_min_font_size = 24
        self.data_max_font_size = 300

        self.title_label = QLabel(title)
        self.data_label = QLabel(str(self.data))

        self.data_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        for label in self.title_label, self.data_label:
            label.setAttribute(Qt.WA_NoSystemBackground)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.setAlignment(Qt.AlignCenter)

        layout = QGridLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        layout.addWidget(self.title_label, 0, 0, 1, 2, alignment=Qt.AlignTop)
        layout.addWidget(self.data_label, 1, 0, 1, 2)
        layout.setRowStretch(1, 1)

        if buttons:
            self.right_button = QPushButton()
            self.right_button.pressed.connect(self.rightF)
            self.left_button = QPushButton()
            self.left_button.pressed.connect(self.leftF)

            for c, button in enumerate((self.left_button, self.right_button)):
                layout.addWidget(button, 0, c, 2, 1)
                button.setMinimumSize(30,120)
                button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
                button.lower()
                button.setFocusPolicy(Qt.NoFocus)
                button.setFlat(True)

                button.setStyleSheet('''
                    QPushButton {
                        border: 1px solid transparent;
                        border-radius: 2px;
                        background: transparent;
                    }
                    QPushButton:hover {
                        border-color: transparent;
                        background: transparent;
                    }
                    QPushButton:pressed {
                        background: transparent;
                        border-color: rgba(100,200,255, 150);
                    }
                ''')
        self.setStyleSheet('''
            QFrame {
                border: 1px solid black;
                border-radius: 0px;
            }
            ''')

    def rightF(self):
        self.data += 1
        self.clicked.emit()

    def leftF(self):
        self.data -=1
        self.clicked.emit()

class DataDisplayWrapper(QWidget):
    resized = Signal()
    def __init__(self, row=2, column=3, refresh=1):
        super().__init__()
        self.filename = PILOT_DIR + 'dashboard.conf'

        try:
            self.client = cypilotClient('localhost')
            self.client.connect(False)
        except Exception as e:
            print(e)
            print("Fail to connect to server")

        self.watchList = []

        self.row = row
        self.column = column

        layout = QGridLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        self.list_of_display = []

        try:
            lod = self.loadListOfIndex()
        except FileNotFoundError:
            lod = []

        for r in range(row):
            for c in range(column):
                try:
                    self.configDataDisplay(layout, r, c, data=lod[0])
                    lod.pop(0)
                except (AttributeError, IndexError):
                    self.configDataDisplay(layout, r, c, data=0)


        self.updateWatchList()

        self.setLayout(layout)

        self.resizeEvent = self.resizeFunction

        self.timer = QTimer()
        self.timer.timeout.connect(self.updateData)
        self.timer.start(refresh*1000)

    def configDataDisplay(self, layout, row, column, data=0):
        d = DataDisplay(data=data)
        self.list_of_display.append(d)
        d.clicked.connect(self.clicked)
        data, index = self.retrieveDataInfo(d.data)
        d.data = index
        d.title_label.setText(data[1])
        layout.addWidget(d, row, column)

    def clicked(self):
        """Set new data title and update data
        """
        data, index = self.retrieveDataInfo(self.sender().data)
        self.sender().data = index
        self.sender().title_label.setText(data[1])
        self.sender().data_label.setText("---")
        self.updateWatchList()
        self.updateData()
        lod = self.retrieveListOfIndex()
        self.saveListOfIndex(lod)

    def saveListOfIndex(self, lod):
        """Save index list to retrieve it for next start
        """
        with open(self.filename,"w") as f:
            pyjson.dump(lod, f)

    def loadListOfIndex(self):
        """Load index list to restart the dash at previous state
        """
        with open(self.filename) as f:
            lod = pyjson.load(f)
        return lod


    def updateWatchList(self):
        wl = []
        for display in self.list_of_display:
            wl.append(data_convert_list[display.data][0])

        cwl = []
        for item in self.client.watches:
            cwl.append(item)

        for item in cwl:
            if item not in wl:
                self.client.watch(item, value = False)

        for item in wl:
            try:
                self.client.watch(item)
            except KeyError as e:
                print("{} not in server", e)

    def updateData(self):
        d = self.client.receive(10)
        for item in self.list_of_display:
            data, index = self.retrieveDataInfo(item.data)
            if data[0] in d:
                item.data_label.setText(str(round(min(d[data[0]], 99999), data[3])) + data[2])

    def retrieveListOfIndex(self):
        lod = []
        for item in self.list_of_display:
            data, index = self.retrieveDataInfo(item.data)
            lod.append(index)
        return lod


    def retrieveDataInfo(self, data):
        """Retrieve data info in data_convert_list and return data info and index in data_convert_list
        Args:
            data (int): index to search
        Returns:
            tuple: list of info (server name, oficial name, unit), index in data_convert_list
        """
        while data >= len(data_convert_list):
            data -= len(data_convert_list)
        while data < 0:
            data += len(data_convert_list)

        return data_convert_list[data], data

    def _fontSizeSearch(self, font, height, width, maxTextSize, minFontSize=8, maxFontSize=100):
        fm = QFontMetrics(font)
        textWidth = fm.horizontalAdvance(maxTextSize, len=-1)
        textHeight = fm.height()

        fontSize = font.pointSize()

        while textHeight < height and textWidth < width:
            fontSize += 1
            if fontSize > maxFontSize:
                fontSize = maxFontSize
                break
            font.setPointSize(fontSize)
            fm = QFontMetrics(font)
            textWidth = fm.horizontalAdvance(maxTextSize, len=-1)
            textHeight = fm.height()

        while textHeight > height or textWidth > width:
            fontSize -= 1
            if fontSize < minFontSize:
                fontSize = minFontSize
                break
            font.setPointSize(fontSize)
            fm = QFontMetrics(font)
            textWidth = fm.horizontalAdvance(maxTextSize, len=-1)
            textHeight = fm.height()

        return font


    def resizeFunction(self, event=None):
        w = self.list_of_display[0]
        widgetWidth = w.rect().width()
        widgetHeight = w.rect().height()

        font_title = self._fontSizeSearch(
                w.title_label.font(),
                widgetHeight/6,
                widgetWidth,
                w.title_max_text_size,
                w.title_min_font_size,
                w.title_max_font_size
            )

        font_data = self._fontSizeSearch(
                w.data_label.font(),
                widgetHeight*5/6,
                widgetWidth,
                w.data_max_text_size,
                w.data_min_font_size,
                w.data_max_font_size
            )

        for widget in self.list_of_display:
            widget.title_label.setFont(font_title)
            widget.data_label.setFont(font_data)




if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setCentralWidget(DataDisplayWrapper(2,4, 0.5))
    window.setWindowTitle("CyPilot Dashboard")
    window.show()

    """
    w = QtWaitingSpinner()
    """

    #w.start()
    #QTimer.singleShot(1000, w.stop)

    sys.exit(app.exec_())