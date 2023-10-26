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

import cypilot.pilot_path # pylint: disable=unused-import
import sys,time
import traceback

from pilots.learningmanager.learningmanager_v2 import learning

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
  QScrollArea,
  QCheckBox
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
    def __init__(self, parent, test=False, quality=False):
        super().__init__()
        self.signals = WorkerSignals()
        self.parent = parent
        self.path_model = self.parent.path_model
        self.path_data = self.parent.path_data

        self.learning = learning
        self.learning.dirpath = self.path_data
        self.learning.savedir = self.path_model
        self.learning.quality = quality

        self.progress = 0
        self.testresult = None

        self.test = test

    def step(self, f, progression=20, message=None, **kwargs):
        """Step for run function

        Args:
            f (function): step function, return nothing
            progression (int, optional): Progression of progress bar. Defaults to 20.
            message (str, optional): Text to show in status. Defaults to None.
        """
        self.signals.information.emit(message)
        f(**kwargs)
        self.progress += progression
        self.signals.progress.emit(self.progress)



    def run(self):

        try:
            if not self.test:
                self.step(self.learning.retrieve_filepaths, message='Retrieving filepaths {}...'.format(self.learning.dirpath))
                time.sleep(2)
                self.step(self.learning.update_scaler, message='Fit scaler...')
                time.sleep(2)
                self.step(self.learning.update_model, message='Fit model...')
                time.sleep(2)
                self.step(self.learning.finish_model, message='Finish model...')
                time.sleep(2)
                self.step(self.learning.register_model, message="Registering new model...")
                #self.signals.information.emit("New model registered\n" )
                self.signals.progress.emit(0)
            else:
                self.step(self.learning.retrieve_filepaths, message='Retrieving filepaths {}...'.format(self.learning.dirpath))
                time.sleep(2)
                self.step(self.learning.update_data, message='Retrieve dat for test...', limit=500000)
                time.sleep(2)
                self.step(self.learning.load_model, message='Load Model...')
                time.sleep(2)
                self.step(self.learning.test_model, message='Test model, that could take some time...', progression=40)


        except Exception as E:
            self.signals.progress.emit(0)
            self.signals.error.emit(str(E) + "\n" + str(traceback.format_exc()))

        self.parent.process.setEnabled(True)
        self.parent.dataDir.setEnabled(True)
        self.parent.modelDir.setEnabled(True)
        self.parent.test.setEnabled(True)

class Stream(QObject):
    newText = Signal(str)

    def __init__(self, parent, stdout=sys.stdout):
        super().__init__(parent)
        self.stdout = stdout

    def write(self, text):
        self.stdout.write(text)
        self.stdout.flush()
        self.newText.emit(str(text))


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
        self.quality = QCheckBox("Only quality labeled data")
        self.process = QPushButton("Run")
        self.test = QPushButton("Test")
        self.pl = ScrollLabel()
        self.progress = QProgressBar()

        self.process.pressed.connect(self.process_func)
        self.test.pressed.connect(self.process_func)

        layout.addWidget(self.l)
        layout.addWidget(self.dataDir)
        layout.addWidget(self.modelDir)
        layout.addWidget(self.quality)
        layout.addWidget(self.process)
        layout.addWidget(self.test)
        layout.addWidget(self.pl)
        layout.addWidget(self.progress)

        w = QWidget()
        w.setLayout(layout)

        streamer = Stream(self)
        streamer.newText.connect(self.onUpdateText)
        sys.stdout = streamer

        self.setCentralWidget(w)
        self.show()

    def process_func(self):
        self.test.setEnabled(False)
        self.process.setEnabled(False)
        self.dataDir.setEnabled(False)
        self.modelDir.setEnabled(False)
        self.quality.setEnabled(False)
        self.path_model = self.modelDir.path
        self.path_data = self.dataDir.path

        if self.sender().text() == "Run":
            worker = Worker(self, quality=self.quality.isChecked())
        elif self.sender().text() == "Test":
            worker = Worker(self, test=True, quality=self.quality.isChecked())
        worker.signals.progress.connect(self.update_progress)
        worker.signals.error.connect(self.error)
        worker.signals.information.connect(self.information)
        self.threadpool.start(worker)

    def error(self, e):
        print(e)
        dl = QMessageBox.critical(self, "Fail", str(e) )
        #dl.exec_()
        self.test.setEnabled(True)
        self.process.setEnabled(True)
        self.dataDir.setEnabled(True)
        self.modelDir.setEnabled(True)
        self.pl.setText("Execution cancelled.")
        self.progress.setValue(0)

    def information(self, text):
        self.pl.setText(text)

    def onUpdateText(self, text):
        if text != "\n":
            self.pl.setText(text)

    def update_progress(self, progress):
        self.progress.setValue(progress)
        if progress == 100:
            self.progress.setValue(0)

app = QApplication(sys.argv)
window = MainWindow()
app.exec_()
