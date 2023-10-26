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
import numpy
import os
from PIL import Image
from PySide2.QtOpenGL import QGLWidget
from PySide2.QtCore import Qt, QTimer
from PySide2.QtWidgets import QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QScrollArea, QSizePolicy
from PySide2.QtWidgets import QLabel, QPushButton, QProgressBar, QFrame, QSpinBox, QDoubleSpinBox, QApplication
from OpenGL.GL import *
import pywavefront
from pywavefront import visualization

import cypilot.pilot_path
import quaternion
from client import cypilotClient

BOAT3D_MODEL = "Sailboat"

# BOATQ_DEFAULT = [-0.32060682, -0.32075041, 0.73081691, -0.51013437]
BOATQ_DEFAULT = [-0.25, -0.22, 0.85, -0.41]

class GLWidget(QGLWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fusionQPose = [1, 0, 0, 0]
        # looking at boat from nice angle
        self.Q = BOATQ_DEFAULT
        self.Scale = 3
        self.compasstex = 0
        self.obj = False
        self.texture_compass = True
        self.last = False
        os.chdir(os.path.abspath(os.path.dirname(__file__)))
        
    def resizeGL(self,w,h):
        self.dim = w,h
              
    def paintGL(self):
        width, height = self.dim
        if width < 10 or height < 10:
            print('boatplot: invalid display dimensions', width, height)
            return
        
        def glRotateQ(q):
            try:
                glRotatef(quaternion.angle(q)*180/math.pi, q[1], q[2], q[3])
            except:
                pass
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glPushMatrix()

        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        ar = 0.5 * width / height
        glFrustum(-ar, ar, -0.5, 0.5, 2.0, 300.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glClearColor(65.0/255.0, 199.0/255.0, 245.0/255.0, 0)
        glClearDepth(100)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        dist = 12
        glTranslatef(0, 0, -dist)
        glScalef(self.Scale, self.Scale, self.Scale)
        glRotateQ(self.Q)

        if self.obj:
            glPushMatrix()
            glRotateQ(self.fusionQPose)
            s = .2
            glScalef(s, s, s)
            glRotatef(90, 0, 0, -1)
            glRotatef(90, -1, 0, 0)
            glEnable(GL_LIGHTING)
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.5,0.5,0.5,0.5])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [0.1,0.1,0.1,0.1])
            glEnable(GL_LIGHT0)
            visualization.draw(self.obj)
            glDisable(GL_LIGHTING)
            glPopMatrix()
        else:
            try:
                self.obj = pywavefront.Wavefront(BOAT3D_MODEL + '.obj')
            except Exception as e:
                print('Failed to load', BOAT3D_MODEL, 'Error', e)

        glEnable(GL_DEPTH_TEST)
        
        # draw texture compass
        if self.compasstex == 0:
            try:
                img = Image.open('compass.png')
            except:
                print('compass.png not found, texture compass cannot be used')
                self.texture_compass = False
                return

            self.compasstex = glGenTextures(1)

            data = numpy.array(list(img.getdata()), numpy.int8)
            glBindTexture(GL_TEXTURE_2D, self.compasstex)

            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
                            GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexImage2D( GL_TEXTURE_2D, 0, GL_RGBA, img.size[0], img.size[1], 0, GL_RGBA, GL_UNSIGNED_BYTE, data )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
   
        glBindTexture(GL_TEXTURE_2D, self.compasstex)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0), glVertex3f(1, -1, 0)
        glTexCoord2f(1, 0), glVertex3f(1,  1, 0)
        glTexCoord2f(1, 1), glVertex3f(-1,  1, 0)
        glTexCoord2f(0, 1), glVertex3f(-1, -1, 0)
        glEnd()
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)
        glPopMatrix()

    def reshape(self, width, height):
        self.dim = width, height
    
    def position(self, fusionQPose):
        self.fusionQPose = fusionQPose
        self.update()
        
    def mouseMoveEvent(self, e):
        x = e.globalX()
        y = e.globalY()
        if self.last:
            dx, dy = x - self.last[0], y - self.last[1]
            q = quaternion.angvec2quat((dx**2 + dy**2)**.4/180*math.pi, [dy, dx, 0])
            self.Q = quaternion.multiply(q, self.Q)
            self.update()
        self.last = x, y

    def mousePressEvent(self, e):
        pass

# Dialog with Tabs :
#   - IMU with boat 3D display
#   - rudder calibration procedure
#   - dialog to set any variable registered as "setting"

class TabDialog(QDialog):
    def __init__(self, parent=None):
        super(TabDialog, self).__init__(parent)
        
        # initialize CyPilot client
        self.host = 'localhost'
        if len(sys.argv) > 1:
            self.host = sys.argv[1]
        self.client = False
        self.client = cypilotClient(self.host)

        # create tab dialog
        tabWidget = QTabWidget()
        self.IMUTab = IMUTab(self.client)
        self.RudderTab = RudderTab(self.client)
        self.SettingsTab = SettingsTab(self.client)
        tabWidget.addTab(self.IMUTab, "IMU")
        tabWidget.addTab(self.RudderTab, "Rudder")
        tabWidget.addTab(self.SettingsTab, "Settings")
        mainLayout = QVBoxLayout()
        mainLayout.addWidget(tabWidget)
        self.setLayout(mainLayout)
        self.resize(500, 500)

        self.setWindowTitle("CyPilot Calibration")
        
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.receive_messages)
        self.timer.start()
        
    def receive_messages(self):
        self.client.poll()
        
        values_list = self.client.list_values()
        if values_list:
            self.SettingsTab.enumerate_settings(values_list)

        msg = self.client.receive_single()
        while msg:
            self.IMUTab.receive_message(msg)
            self.RudderTab.receive_message(msg)
            self.SettingsTab.receive_message(msg)
            msg = self.client.receive_single()
        return

#
# IMU Tab
# -------
#

class IMUTab(QWidget):
    def __init__(self, client, parent=None):
        super(IMUTab, self).__init__(parent)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        # CyPilot client
        self.client = client
        self.fusionQPose = [1, 0, 0, 0]
        self.alignmentQ = [1, 0, 0, 0]
        self.controltimes = {}
        self.heading_offset = None
        self.reference = 'compass'
        if self.client:
            watchlist = ['imu.fusionQPose', ('imu.alignmentCounter', .2), ('imu.heading', .5),
                    ('imu.alignmentQ', 1), ('imu.pitch', .5), ('imu.roll', .5), ('imu.heel', .5), ('imu.heading_offset', 1)]
            for name in watchlist:
                if isinstance(name, tuple):
                    name, watch = name
                else:
                    watch = True            
                self.client.watch(name,watch)

        # QT Dialog
        central_widget = QWidget()
        mainLayout.addWidget(central_widget)

        self.glWidget = GLWidget()

        self.glWidgetArea = QScrollArea()
        self.glWidgetArea.setWidget(self.glWidget)
        self.glWidgetArea.setWidgetResizable(True)
        self.glWidgetArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.glWidgetArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.glWidgetArea.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.glWidgetArea.setMinimumSize(50, 50)

        # Set the layout
        self.central_layout = QGridLayout()

        self.glBoatLayout = QVBoxLayout()
        self.imuValuesLayout = QGridLayout()
        self.imuCalibrationLayout = QHBoxLayout()
        self.imuAlignmentLayout = QGridLayout()
        self.rudderCalibrationLayout = QHBoxLayout()
        
        self.central_layout.addLayout(self.glBoatLayout,0,0)
        self.central_layout.addLayout(self.imuValuesLayout,1,0)
        self.central_layout.addLayout(self.imuCalibrationLayout,2,0)
        self.central_layout.addLayout(self.imuAlignmentLayout,3,0)

        # Boat model part
        self.glBoatLayout.addWidget(self.glWidgetArea)
        central_widget.setLayout(self.central_layout)
        
        # IMU values part
        self.imuValues = {
            "headingLabel" : (QLabel("Heading"), 0, 0),
            "pitchLabel" : (QLabel("Pitch"), 0, 1),
            "rollLabel" : (QLabel("Roll"), 0, 2),
            "heelLabel" : (QLabel("Heel"), 0, 3),
            "headingDash" : (QLabel("---"), 1, 0),
            "pitchDash" : (QLabel("---"), 1, 1),
            "rollDash" : (QLabel("---"), 1, 2),
            "heelDash" : (QLabel("---"), 1, 3)
        }
        for item in self.imuValues:
            self.imuValuesLayout.addWidget(self.imuValues[item][0], self.imuValues[item][1], self.imuValues[item][2], alignment=Qt.AlignHCenter)
            self.imuValues[item][0].setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            if self.imuValues[item][1] == 1:
                self.imuValues[item][0].setStyleSheet("font-weight: bold")
     
        # IMU calibration part
        self.buttonLevel = QPushButton("Boat is level")
        self.progressLevel = QProgressBar()
        self.imuCalibrationLayout.addWidget(self.buttonLevel)
        self.imuCalibrationLayout.addWidget(self.progressLevel)
        
        self.buttonLevel.pressed.connect(self.onButtonLevel)
        
        # IMU alignment part
        self.labelAlignment = QLabel("Alignment:")
        self.buttonAlignment = QPushButton("Reset")
        self.labelReference = QLabel("Reference:")
        self.buttonReference = QPushButton("Boat")
        self.labelHeadingOffset = QLabel("Heading Offset:")
        self.spinboxHeadingOffset = QSpinBox(Minimum=-180,Maximum=180,Suffix='°')
        self.spinboxHeadingOffset.setEnabled(False)
        
        self.imuAlignmentLayout.addWidget(self.labelAlignment, 0, 0)
        self.imuAlignmentLayout.addWidget(self.buttonAlignment, 0, 1)
        self.imuAlignmentLayout.addWidget(self.labelReference, 0, 2)
        self.imuAlignmentLayout.addWidget(self.buttonReference, 0, 3)
        self.imuAlignmentLayout.addWidget(self.labelHeadingOffset, 0, 4)
        self.imuAlignmentLayout.addWidget(self.spinboxHeadingOffset, 0, 5)
        
        self.buttonAlignment.pressed.connect(self.onButtonAlignment)
        self.buttonReference.pressed.connect(self.onButtonReference)
        self.spinboxHeadingOffset.valueChanged.connect(self.onSpinboxHeadingOffset)
        
    def receive_message(self,msg):
        name, value = msg

        if name == 'imu.alignmentQ':
            self.alignmentQ = value
        elif name == 'imu.fusionQPose':
            if not value:
                return

            aligned = quaternion.normalize(quaternion.multiply(value, self.alignmentQ))
            value = aligned

            if self.reference == 'Boat':
                ang = quaternion.toeuler(self.fusionQPose)[2] - quaternion.toeuler(aligned)[2]
                self.glWidget.Q = quaternion.multiply(self.glWidget.Q, quaternion.angvec2quat(ang, [0, 0, 1]))

            self.fusionQPose = value
            self.glWidget.position(value)
        elif name == 'imu.alignmentCounter':
            self.progressLevel.setValue(100 - value)
            self.buttonLevel.setEnabled((value == 0))
        elif name == 'imu.pitch':
            self.imuValues["pitchDash"][0].setText(str(round(value,3))+ " °")
        elif name == 'imu.roll':
            self.imuValues["rollDash"][0].setText(str(round(value,3))+ " °")
        elif name == 'imu.heel':
            self.imuValues["heelDash"][0].setText(str(round(value,3))+ " °")
        elif name == 'imu.heading':
            self.imuValues["headingDash"][0].setText(str(round(value,3))+ " °")
        elif name == 'imu.heading_offset':
            self.spinboxHeadingOffset.setValue(value)
            if self.heading_offset == None:
                self.spinboxHeadingOffset.setEnabled(True)
            self.heading_offset = value
        self.update()

    def onButtonLevel(self):
        self.client.set('imu.alignmentCounter', 100)
        
    def onButtonAlignment(self):
        # reset alignment
        self.client.set('imu.alignmentQ', False)
        self.glWidget.Q = BOATQ_DEFAULT
        
    def onButtonReference(self):
        if self.buttonReference.text() == "Boat":
            self.reference = "Sea"
        else:
            self.reference = "Boat"
        self.buttonReference.setText(self.reference)
        
    def onSpinboxHeadingOffset(self):
        heading_offset = self.spinboxHeadingOffset.value()
        self.client.set('imu.heading_offset', heading_offset)

#
# Rudder Tab
# ----------
#

class RudderTab(QWidget):
    def __init__(self, client, parent=None):
        super(RudderTab, self).__init__(parent)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        
        # QT Dialog
        central_widget = QWidget()
        mainLayout.addWidget(central_widget)
        
        # CyPilot client
        self.client = client
        self.rudder_calibrated = False
        self.rudder_range = False
        self.rudder_angle = False
        if self.client:
            watchlist = [('rudder.angle', 1), ('rudder.range', 1), 'rudder.calibrated']
            for name in watchlist:
                if isinstance(name, tuple):
                    name, watch = name
                else:
                    watch = True            
                self.client.watch(name,watch)
        
        # Set the layout
        self.central_layout = QGridLayout()
        central_widget.setLayout(self.central_layout)

        self.rudderValuesLayout = QGridLayout()
        self.rudderCalibrationLayout = QGridLayout()
        self.rudderTestCommentLayout = QVBoxLayout()
        self.rudderTestButtonsLayout = QGridLayout()
        
        # Separator
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.HLine)
        divider1.setFrameShadow(QFrame.Raised)
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setFrameShadow(QFrame.Raised)
        
        self.central_layout.addLayout(self.rudderValuesLayout,0,0)
        self.central_layout.addWidget(divider1,1,0)
        self.central_layout.addLayout(self.rudderCalibrationLayout,2,0)
        self.central_layout.addWidget(divider2,3,0)
        self.central_layout.addLayout(self.rudderTestCommentLayout,4,0)
        self.central_layout.addLayout(self.rudderTestButtonsLayout,5,0)

        # Rudder values part
        self.rudderValues = {
            "rudderLabel" : (QLabel("Rudder Position"), 0, 0),
            "rangeLabel" : (QLabel("Rudder Range"), 0, 1),
            "rudderDash" : (QLabel("---"), 1, 0),
            "rangeDash" : (QLabel("---"), 1, 1)
        }
        for item in self.rudderValues:
            self.rudderValuesLayout.addWidget(self.rudderValues[item][0], self.rudderValues[item][1], self.rudderValues[item][2], alignment=Qt.AlignHCenter)
            self.rudderValues[item][0].setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            if self.rudderValues[item][1] == 1:
                self.rudderValues[item][0].setStyleSheet("font-weight: bold")
        
        # Calibration procedure part
        self.labelCalibration = QLabel("Calibration procedure:")
        self.labelCalibration.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.rudderCalibrationLayout.addWidget(self.labelCalibration,0,0)

        self.step1Label = QLabel("Step1 : reset current calibration            ")
        self.step1Button = QPushButton("Reset calibration")
        self.rudderCalibrationLayout.addWidget(self.step1Label,1,0)
        self.rudderCalibrationLayout.addWidget(self.step1Button,1,2)

        self.step2Label = QLabel("Step2 : enter rudder range                   ")
        self.step2SpinBox = QSpinBox(maximum=90,minimum=0,suffix='°')
        self.step2SpinBox.adjustSize()
        self.step2SpinBox.setEnabled(False)
        self.rudderCalibrationLayout.addWidget(self.step2Label,2,0)
        self.rudderCalibrationLayout.addWidget(self.step2SpinBox,2,2)
        
        self.step3Label = QLabel("Step3 : put full helm to turn starboard      ")
        self.step3Button = QPushButton("Starboard")
        self.step3Button.setEnabled(False)
        self.rudderCalibrationLayout.addWidget(self.step3Label,3,0)
        self.rudderCalibrationLayout.addWidget(self.step3Button,3,2)

        self.step4Label = QLabel("Step4 : put full helm to turn port           ")
        self.step4Button = QPushButton("Port")
        self.step4Button.setEnabled(False)
        self.rudderCalibrationLayout.addWidget(self.step4Label,4,0)
        self.rudderCalibrationLayout.addWidget(self.step4Button,4,2)

        self.step5Label = QLabel("Step5 : put the rudder in the center position")
        self.step5Button = QPushButton("Center")
        self.step5Button.setEnabled(False)
        self.rudderCalibrationLayout.addWidget(self.step5Label,5,0)
        self.rudderCalibrationLayout.addWidget(self.step5Button,5,2)
        
        self.step1Button.pressed.connect(self.onStep1Button)
        self.step2SpinBox.valueChanged.connect(self.onStep2SpinBox)
        self.step3Button.pressed.connect(self.onStep3Button)
        self.step4Button.pressed.connect(self.onStep4Button)
        self.step5Button.pressed.connect(self.onStep5Button)
        
        # Test part
        self.labelTestComment1 = QLabel("Press the buttons to move the helm to turn starboard or port:")
        self.labelTestComment1.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.rudderTestCommentLayout.addWidget(self.labelTestComment1)

        self.test1Button = QPushButton("<<")
        self.test2Button = QPushButton(">>")
        self.rudderTestButtonsLayout.addWidget(self.test1Button,0,0)
        self.rudderTestButtonsLayout.addWidget(self.test2Button,0,2)
        
        self.test1Button.pressed.connect(self.onTest1Button)
        self.test2Button.pressed.connect(self.onTest2Button)

    def receive_message(self,msg):
        name, value = msg
        
        if name == 'rudder.angle':
            self.rudder_angle = value           
            if value and self.rudder_calibrated:
                self.rudderValues["rudderDash"][0].setText(("+" if value > 0 else "")+str(round(value,3))+ " °")
                self.rudderValues["rangeDash"][0].setText("+/- "+str(round(self.rudder_range,3))+ " °")
        elif name == 'rudder.range':
            self.step2SpinBox.setValue(value)
            self.rudder_range = value
        elif name == 'rudder.calibrated':
            self.rudder_calibrated = value
            if value:
                self.step2SpinBox.setEnabled(False)
                self.step3Button.setEnabled(False)
                self.step4Button.setEnabled(False)
                self.step5Button.setEnabled(False)
            else:
                self.step2SpinBox.setEnabled(True)
                self.step3Button.setEnabled(True)
                self.step4Button.setEnabled(False)
                self.step5Button.setEnabled(False)
                self.rudderValues["rudderDash"][0].setText("---")
                self.rudderValues["rangeDash"][0].setText("---")

    def onStep1Button(self):
        self.client.set('rudder.calibration_state', 'reset')
        self.step2SpinBox.setEnabled(True)
        self.step3Button.setEnabled(True)
        self.step4Button.setEnabled(False)
        self.step5Button.setEnabled(False)
        
    def onStep2SpinBox(self):
        self.rudder_range = self.step2SpinBox.value()
        self.client.set('rudder.range', self.rudder_range)
        
    def onStep3Button(self):
        self.step2SpinBox.setEnabled(False)
        self.step3Button.setEnabled(False)
        self.step4Button.setEnabled(True)
        self.client.set('rudder.calibration_state', 'starboard range')
        
    def onStep4Button(self):
        self.step4Button.setEnabled(False)
        self.step5Button.setEnabled(True)
        self.client.set('rudder.calibration_state', 'port range')
        
    def onStep5Button(self):
        self.client.set('rudder.calibration_state', 'centered')

    def onTest1Button(self):
        self.client.set('servo.command', -0.1)

    def onTest2Button(self):
        self.client.set('servo.command', +0.1)

#
# Settings Tab
# ------------
#

class SettingsTab(QWidget):
    def __init__(self, client, parent=None):
        super(SettingsTab, self).__init__(parent)
        
        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        
        # QT Dialog
        central_widget = QWidget()
        mainLayout.addWidget(central_widget)
        
        # CyPilot client
        self.client = client
        self.settings = {}

        # Set the layout
        self.central_layout = QVBoxLayout()
        central_widget.setLayout(self.central_layout)
        
    def update_watches(self):
        if self.client:
            for name in list(self.settings):
                self.client.watch(name,True)
                
    def receive_message(self,msg):
        name, value = msg
        if name in self.settings:
            self.settings[name].blockSignals(True)
            self.settings[name].setValue(value)
            self.settings[name].blockSignals(False)
        return
    
    def enumerate_settings(self, values):
        lvalues = list(values)
        lvalues.sort()
        v = None
        name = None
        for name in lvalues:
            if name in self.settings:
                continue
            if 'units' in values[name] and values[name]['units']:
                v = values[name]
                
                def proc():
                    s = QDoubleSpinBox(Minimum=v['min'],Maximum=v['max'],Suffix=' ' + v['units'])
                    # s.setSingleStep(min(1, (v['max'] - v['min']) / 100.0))
                    # s.setDecimals(-math.log(s.singleStep()) / math.log(10) + 1)
                    self.settings[name] = s
                    l = QLabel(name)
                    
                    sLayout = QGridLayout()
                    sLayout.addWidget(l,0,0)
                    sLayout.addWidget(s,0,1)
                    
                    self.central_layout.addLayout(sLayout)
                    
                    sname = name

                    def onspin(event):
                        value = s.value()
                        self.client.set(sname, s.value())
                        
                    s.valueChanged.connect(onspin)

                proc()
        
        if v != None:
            self.update_watches()

def qt_main():
    app = QApplication(sys.argv)

    tabdialog = TabDialog()
    tabdialog.exec_()
    
if __name__ == '__main__':
    qt_main()
    