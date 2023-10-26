#!/usr/bin/python3
#
# (C) 2021 ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

# pylint: disable=multiple-imports, unused-import, consider-using-f-string, invalid-name

import cypilot.pilot_path
import sys

from pilots.learningmanager.learningmanager import learning

from PySide2.QtCore import QObject, QRunnable, QThreadPool, Signal,Qt
from PySide2.QtWidgets import (
  QApplication,
  QLabel,
  QMainWindow,
  QPushButton,
  QHBoxLayout,
  QVBoxLayout,
  QWidget,
  QProgressBar,
  QFrame,
  QFileDialog,
  QMessageBox,
  QScrollArea
)

# class for scrollable label
class ScrollLabel(QScrollArea):

    # constructor
    def __init__(self, *args, **kwargs):
        QScrollArea.__init__(self, *args, **kwargs)

        # making widget resizable
        self.setWidgetResizable(True)

        # making qwidget object
        content = QWidget(self)
        self.setWidget(content)

        # vertical box layout
        lay = QVBoxLayout(content)

        # creating label
        self.label = QLabel(content)

        # setting alignment to the text
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # making label multi-line
        self.label.setWordWrap(True)

        # adding label to the layout
        lay.addWidget(self.label)

    # the setText method
    def setText(self, text):
        # setting text to the label
        self.label.setText(text)

class DirWidget(QFrame):
    def __init__(self, title="", path="") -> None:
        super().__init__()
        self.title = title
        self.path = path

        self.titlew = QLabel(self.title)
        self.pathw = QLabel(self.path)
        self.changebutton = QPushButton("Browse")
        self.changebutton.pressed.connect(self.changeFunction)

        hl = QHBoxLayout()
        hl.addWidget(self.pathw)
        hl.addWidget(self.changebutton)

        vl = QVBoxLayout()
        vl.addWidget(self.titlew)
        vl.addLayout(hl)
        self.setLayout(vl)

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLineWidth(2)

    def changeFunction(self):
        folderpath = None
        folderpath = QFileDialog.getExistingDirectory(self, 'Choose a directory')
        if folderpath:
            self.path = folderpath
            self.pathw.setText(folderpath)





class WorkerSignals(QObject):
    """Object wich manage signals from worker
    """
    error = Signal(str)
    result = Signal(str)
    progress = Signal(int)
    information = Signal(str)

class Worker(QRunnable):
    """
    Worker thread, wich work under the GUI
    """
    def __init__(self, parent):
        super().__init__()
        self.signals = WorkerSignals()
        self.parent = parent
        self.path_model = self.parent.path_model
        self.path_data = self.parent.path_data

        self.learning = learning
        self.learning.dirpath = self.path_data
        self.learning.savedir = self.path_model

        self.progress = 0
        self.testresult = None

    def step(self, f, progression=14, message=None):
        """Step for run function

        Args:
            f (function): step function, return nothing
            progression (int, optional): Progression of progress bar. Defaults to 10.
            message (str, optional): Text to show in status. Defaults to None.
        """
        self.signals.information.emit(message)
        f()
        self.progress += progression
        self.signals.progress.emit(self.progress)

    def test(self):
        text = self.learning.test_model()
        if text == "Not enough valid data to test a prediction model":
            self.signals.error.emit(text)
        text = "Models caracteristics: \n" + text
        self.testresult = text


    def run(self):

        try:
            self.step(self.learning.update_data, message='Retrieving data from {}, that could take some time ...'.format(self.learning.dirpath))
            self.step(self.learning.process_data, message="Processing data...")
            self.step(self.learning.define_data, message="Defining new features...")
            self.step(self.learning.define_model, message="Defining model...")
            self.step(self.test, message="Testing model, that could take some time...")
            self.step(self.learning.fit_model, message="Finishing new model, that could take some time...")
            self.step(self.learning.register_model, message="Registering new model...")
            self.signals.information.emit("New model registered:\n" + self.testresult)
            self.signals.progress.emit(0)

        except Exception as E:
            self.signals.progress.emit(0)
            self.signals.error.emit(str(E))

        self.parent.process.setEnabled(True)
        self.parent.dataDir.setEnabled(True)
        self.parent.modelDir.setEnabled(True)



class MainWindow(QMainWindow):
    """Main window
    Instancie threadpool qui gere les QRunnable
    """
    def __init__(self) -> None:
        super().__init__()
        self.threadpool = QThreadPool()

        layout = QVBoxLayout()

        self.path_data = learning.dirpath
        self.path_model = learning.savedir
        self.name_model = learning.model_name

        explication = ("Welcome to autopilot model creator wizard.\n"
            "WARNING: if there is already a file named {nm}.pkl in the save directory, it will be overridden.\n"
            .format(nm = self.name_model)
            )

        self.l = QLabel(explication)
        self.dataDir = DirWidget(title="Extraction directory:", path = self.path_data)
        self.modelDir = DirWidget(title="Save directory:", path = self.path_model)
        self.process = QPushButton("Run")
        self.pl = ScrollLabel()
        self.progress = QProgressBar()

        self.process.pressed.connect(self.process_func)

        layout.addWidget(self.l)
        layout.addWidget(self.dataDir)
        layout.addWidget(self.modelDir)
        layout.addWidget(self.process)
        layout.addWidget(self.pl)
        layout.addWidget(self.progress)

        w = QWidget()
        w.setLayout(layout)

        self.setCentralWidget(w)
        self.show()

    def process_func(self):

        self.process.setEnabled(False)
        self.dataDir.setEnabled(False)
        self.modelDir.setEnabled(False)
        self.path_model = self.modelDir.path
        self.path_data = self.dataDir.path

        worker = Worker(self)
        worker.signals.progress.connect(self.update_progress)
        worker.signals.error.connect(self.error)
        worker.signals.information.connect(self.information)
        self.threadpool.start(worker)

    def error(self, e):
        print(e)
        dl = QMessageBox.critical(self, "Fail", str(e) )
        #dl.exec_()
        self.process.setEnabled(True)
        self.dataDir.setEnabled(True)
        self.modelDir.setEnabled(True)
        self.pl.setText("Execution cancelled.")
        self.progress.setValue(0)

    def information(self, text):
        self.pl.setText(text)

    def update_progress(self, progress):
        self.progress.setValue(progress)
        if progress == 100:
            self.progress.setValue(0)

app = QApplication(sys.argv)
window = MainWindow()
app.exec_()
