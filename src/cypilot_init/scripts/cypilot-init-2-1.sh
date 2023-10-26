#!/bin/bash

# 2020 JF/ED / Cybele Services (cf@cybele-sailing.com)
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

echo "Complete Autopilot installation - Install required packages"

# OpenGL
sudo apt-get -y -q install python3-opengl python3-gevent-websocket
# required / Bluetooth BLE
sudo apt-get -y -q install libglib2.0-dev
# required / SciKit Learn
sudo apt-get -y -q install libatlas-base-dev
# required / PySide2
sudo apt-get -y -q install python3-pyside2.qt3dcore python3-pyside2.qt3dinput python3-pyside2.qt3dlogic python3-pyside2.qt3drender python3-pyside2.qtcharts python3-pyside2.qtconcurrent python3-pyside2.qtcore python3-pyside2.qtgui python3-pyside2.qthelp python3-pyside2.qtlocation python3-pyside2.qtmultimedia python3-pyside2.qtmultimediawidgets python3-pyside2.qtnetwork python3-pyside2.qtopengl python3-pyside2.qtpositioning python3-pyside2.qtprintsupport python3-pyside2.qtqml python3-pyside2.qtquick python3-pyside2.qtquickwidgets python3-pyside2.qtscript python3-pyside2.qtscripttools python3-pyside2.qtsensors python3-pyside2.qtsql python3-pyside2.qtsvg python3-pyside2.qttest python3-pyside2.qttexttospeech python3-pyside2.qtuitools python3-pyside2.qtwebchannel python3-pyside2.qtwebsockets python3-pyside2.qtwidgets python3-pyside2.qtx11extras python3-pyside2.qtxml python3-pyside2.qtxmlpatterns
# missing : python-pyside2uic
sudo apt-get -y -q install pyside2-tools
# missing / gpsd
sudo apt-get -y -q install python3-gps
# Install socat which is used to communicate with cyalarm
sudo apt-get -y -q install socat

# Install Bluetooth bluepy - Not installed before because it requires libglib2
sudo pip3 install bluepy==1.3.0

echo ""
read -p "Done - Enter return to exit" RESP