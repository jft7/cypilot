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
import signal
import os
import subprocess

from signal import SIGTERM

from PySide2.QtWidgets import (QApplication, QMainWindow, QPlainTextEdit, QVBoxLayout, QWidget)
from PySide2.QtWidgets import (QSystemTrayIcon, QMenu, QAction, QStyle)
from PySide2.QtCore import (QTimer, QSize)
from PySide2.QtGui import (QFont)

import cypilot.pilot_path
from pilot_path import (get_lock, close_autopilot_log_pipe, AUTOPILOT_LOG_PIPE)

LOG_MAX_BLOCK_COUNT = 100
PROGRAM_TO_LAUNCH = 'autopilot.py'


class MainWindow(QMainWindow):
    """
         Сheckbox and system tray icons.
         Will initialize in the constructor.
    """
    check_box = None
    tray_icon = None

    def __init__(self):
        super().__init__()
 
        self.p = None

        self.setMinimumSize(QSize(640, 300))  # Set sizes
        self.setWindowTitle("QT Cypilot")  # Set a title

        self.text = QPlainTextEdit()
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(LOG_MAX_BLOCK_COUNT)
        self.text.setFont(QFont ("Courier"))

        l = QVBoxLayout()
        l.addWidget(self.text)

        w = QWidget()
        w.setLayout(l)

        self.setCentralWidget(w)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_TitleBarUnshadeButton))

        show_action = QAction("Show", self)
        quit_action = QAction("Exit", self)
        hide_action = QAction("Hide", self)
        restart_action = QAction("Restart", self)
        show_action.triggered.connect(self.show)
        hide_action.triggered.connect(self.hide)
        quit_action.triggered.connect(self.quitAction)
        restart_action.triggered.connect(self.restartAction)
        tray_menu = QMenu()
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(restart_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        close_autopilot_log_pipe()

        if not os.path.exists(AUTOPILOT_LOG_PIPE):
            os.mkfifo(AUTOPILOT_LOG_PIPE)
            self.log_file = os.fdopen( os.open(AUTOPILOT_LOG_PIPE, os.O_RDONLY | os.O_NONBLOCK) )

        self.start_process()

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.handle_out)
        self.timer.start()

    # Override closeEvent, to intercept the window closing event
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Tray Cypilot",
            "Cypilot was minimized to Tray",
            QSystemTrayIcon.Information,
            2000
        )

    def message(self, s):
        msg = s.rstrip()
        if len(msg) > 1:
            self.text.appendPlainText(msg)

    def start_process(self):
        if self.p is None:  # No process running.
            autopilot_path = os.path.dirname(os.path.abspath(__file__)) + '/../' + PROGRAM_TO_LAUNCH
            self.p = subprocess.Popen(['python3', autopilot_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding='utf8', errors='ignore')

    def handle_out(self):
        while self.p:
            logline = self.log_file.readline()
            if logline:
                self.message(logline)
            else:
                break

    def quitSignal(self):
        if self.p:
            self.p.send_signal(SIGTERM)
            self.p = None
        time.sleep(3)
        close_autopilot_log_pipe()

    def quitAction(self):
        self.quitSignal()
        QApplication.instance().quit()
        
    def restartAction(self):
        self.quitSignal()
        if not os.path.exists(AUTOPILOT_LOG_PIPE):
            os.mkfifo(AUTOPILOT_LOG_PIPE)
            self.log_file = os.fdopen( os.open(AUTOPILOT_LOG_PIPE, os.O_RDONLY | os.O_NONBLOCK) )
        self.message('-------- AutoPilot has been restarted -------')
        self.start_process()

if __name__ == "__main__":
    get_lock('')

    app = QApplication(sys.argv)
    mw = MainWindow()
    # mw.show()
    # mw.showMinimized()
    mw.hide()

    def handler(signum,frame):
        mw.quitSignal()
        sys.exit(0)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    ret = app.exec_()
    
    # kill autopilot process and exit
    # WARNING : at the moment, we kill the autopilot process on exit, regardless if any other client is connected !!!
    mw.quitSignal()
    sys.exit(ret)

