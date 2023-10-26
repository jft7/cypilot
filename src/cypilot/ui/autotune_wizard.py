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

# pylint: disable=unused-import,wildcard-import,invalid-name

import cypilot.pilot_path

from PySide2.QtWidgets import *
from PySide2.QtCore import *
from PySide2.QtGui import *

from pilot_path import dprint as print # pylint: disable=redefined-builtin

import pyjson
import os
import time
import sys


from qt_autopilot_control import AutotuneWizard
from client import cypilotClient


def autotune_main():
    host = None if len(sys.argv) <= 1 else sys.argv[1]
    client = False
    try:
        client = cypilotClient('localhost')
        client.connect(False)
    except Exception as e:
        print(e)
        print("Fail to connect to server")

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setCentralWidget(AutotuneWizard(client))
    window.show()
    app.exec_()
     
if __name__ == '__main__':
    autotune_main()
