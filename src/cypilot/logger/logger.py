#!/usr/bin/env python
#
# (C) 2021 ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

"""Module to log value from server

To do:
- Make it usable to autolearning
- wrap it in process to reduce open/close of file
- limit file size
"""

import time
import csv
import os
from threading import Thread
from multiprocessing import Process, Queue

import cypilot.pilot_path # pylint: disable=unused-import
from client import cypilotClient
from kbhit import KBHit

from pilot_path import dprint as print # pylint: disable=redefined-builtin

class BaseLogger():
    """Class wich manage log"""

    def __init__(self, dirname=False, watchlist=False, sleeping_time=0.2, file_size=200000, autolog=False, quality=False, speed=False, *args, **kwargs):
        """Init function:
        - create data dict
        - connect client to server
        - watch all value from server
        - create a dir if not yet existing to save data

        dirpath [str]: dir name in logfile dir where file will be recorded
        file_size [int]: max file size before create a new one
        watchlist [list of string or False], default to False: list of data to watch
        """
        super().__init__(*args, **kwargs)

        self.data = {}
        self.param = {'filename': '',
                      'state': False,
                      'file_changed': False,
                      'sleeping_time': sleeping_time,
                      'watchlist': watchlist,
                      'file_size': file_size,
                      'quit': False}
        
        self.quality = quality
        self.speed = speed
        
        if autolog:
            self.param['state'] = True

        self.dirname = dirname

        self.client = object()

        if self.dirname is False:
            self.dirpath = os.path.expanduser("~/logfiles") + "/" + "data"
            os.makedirs(self.dirpath, exist_ok=True)
        else:
            self.dirpath = os.path.expanduser("~/logfiles") + "/" + self.dirname
            os.makedirs(self.dirpath, exist_ok=True)

        self.timestart = time.monotonic()

        #self.initialisation()

    def initialisation(self):
        """Initialisation method
        """

        try:
            self.client = cypilotClient('localhost')
            self.client.connect(True)
        except Exception as e:
            print(e)
            print("Fail to connect to server")

        self.update_watchlist(self.param['watchlist'])


    def update_watchlist(self, watch=False):
        """Function which update watchlist

        Args:
            watch (bool or list of str, optional): List of parameter to watch,
            if False watch all of them. Defaults to False.
        """
        self.param['watchlist'] = watch
        previous_state = self.param['state']
        self.param['state'] = False
        list_values = False
        max_time = 10
        timer = 0
        t0 = time.monotonic()
        while timer < max_time and list_values is False:
            time.sleep(1)
            t1 = time.monotonic()
            timer = t1-t0
            self.client.list_values(100)
            list_values = self.client.values.value

        if list_values is False:
            print("Failed to load list values")
            print("Watchlist not updated")
            return
        else:
            if watch is False:
                #retrieve all possible value watchable
                self.param['watchlist'] = []
                for key in list_values:
                    self.param['watchlist'].append(key)

            else:
                #watch only selected
                for item in self.param['watchlist']:
                    if item not in list_values.keys():
                        self.param['watchlist'].remove(item)
                        print(item + " not in server. Won't be logged.")

        #clear watches then watch
        self.client.clear_watches()

        for name in self.param['watchlist']:
            self.client.watch(name)


        # Force change of file erase data to have correct header
        self.param['file_changed'] = True
        self.data = {}

        print("update watchlist succeed")

        self.param['state'] = previous_state

    def update(self):
        """Poll data and update self.data with key in self.param['watchlist']
        """
        d = self.client.receive()

        self.data.update({key : dt for key, dt in d.items() if key in self.param['watchlist']})

    def create_file(self):
        """Create csv file"""
        self.param['filename'] = self.dirpath + '/log_data_' + time.strftime('%Y_%m_%d_%H_%M_%S') + '.csv'

        try:
            with open(self.param['filename'], 'a') as f:
                writer = csv.DictWriter(f, fieldnames=self.param['watchlist'])
                writer.writeheader()
                self.param['file_changed'] = True

        except IOError:
            print('IOError')

    def export_data(self, writer):
        """Export data to CSV file, check file size and create new if maxsize reached
            writer [csv.DictWriter]= writer to file
            """

        # check logging condition and process logging
        if not( self.quality and ('perf.quality_flag' not in self.data or self.data['perf.quality_flag'] is False)
                or self.speed and ('gps.speed' not in self.data or self.data['gps.speed'] < 1) ):
            try:
                writer.writerow(self.data)
                if int(os.path.getsize(self.param['filename'])) > self.param['file_size']:
                    self.create_file()
            except IOError:
                print('IOError')

    def run(self):
        """To be override
        """

    def start_record(self):
        """Set state flag to True"""
        self.param['state'] = True

    def stop_record(self):
        """Set state flag to False"""
        self.param['state'] = False

class SimpleLogger(BaseLogger):
    """Class wich manage logger in full scope
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialisation()

    def run(self):
        kb = KBHit()
        print('Logger started:')
        print(' s: start full log')
        print(' m: start minimal log')
        print(' p: pause log, hit s or m to start a new log (new file name)')
        print(' q: quit program')

        while True:
            if self.param['quit'] is True:
                break
            if not kb.kbhit():
                time.sleep(0.3)
            else:
                k = kb.getch()
                if k == 's':
                    #self.stop_record()
                    self.update_watchlist()
                    time.sleep(1)
                    self.start_record()
                    print('Full Log start, "p" to pause logging')
                elif k == 'm':
                    #self.stop_record()
                    self.update_watchlist(LOGLIST)
                    time.sleep(1)
                    self.start_record()
                    print('Minimal Log start, "p" to pause logging')
                if k == 'q':
                    self.stop_record()
                    print('Exiting')
                    self.param['quit'] = True
                    break

            if self.param['state']:
                self.create_file()
                print('Filename =', str(self.param['filename']))

            while self.param['state']:
                try:
                    with open(self.param['filename'], 'a') as f:
                        self.param['file_changed'] = False
                        writer = csv.DictWriter(f, fieldnames=self.param['watchlist'])
                        while self.param['file_changed'] is False and self.param['state']:
                            self.update()
                            self.export_data(writer)
                            time.sleep(self.param['sleeping_time'])

                            if not kb.kbhit():
                                time.sleep(0.3)
                            else:
                                k = kb.getch()

                                if k == 'q':
                                    self.stop_record()
                                    print('Exiting')
                                    self.param['quit'] = True
                                    break
                                elif k == 'f':
                                    self.stop_record()
                                    print('Log paused, "s" or "m" to start new log')
                                    print('q for quit program')

                except IOError as e:
                    print(e)


class ThreadLogger(BaseLogger, Thread):
    """Class wich manage log with thread management"""

    def __init__(self, *args, **kwargs):
        """Init function:
        inherited from BaseLogger Class
        """
        super().__init__(*args, **kwargs)
        self.initialisation()

    def run(self):
        """[summary]
        """

        while True:
            if self.param['quit'] is True:
                break
            if self.param['state']:
                self.create_file()
                print('Filename =', str(self.param['filename']))

            while self.param['state']:
                try:
                    with open(self.param['filename'], 'a') as f:
                        self.param['file_changed'] = False
                        writer = csv.DictWriter(f, fieldnames=self.param['watchlist'])
                        while self.param['file_changed'] is False and self.param['state']:
                            self.update()
                            self.export_data(writer)
                            time.sleep(self.param['sleeping_time'])
                except IOError as e:
                    print(e)
            time.sleep(1)
        raise InterruptedError

    def exit(self):
        """Set quit flag to True"""
        self.param['quit'] = True


class ProcessLogger(BaseLogger, Process):
    """Class wich manage log with process management"""

    def __init__(self, **kwargs):
        """Init function:
        inherited from BaseLogger Class
        """
        super().__init__(**kwargs)
        self.param['updated_watchlist'] = False
        self.q = Queue()
        self.start()

    def run(self):
        """[summary]
        """
        self.initialisation()
        
        while True:
            self.check_param()
            if self.param['quit'] is True:
                break
            if self.param['state']:
                self.create_file()
                print('Filename =', str(self.param['filename']))

            while self.param['state']:
                try:
                    with open(self.param['filename'], 'a') as f:
                        self.param['file_changed'] = False
                        writer = csv.DictWriter(f, fieldnames=self.param['watchlist'])
                        while self.param['file_changed'] is False and self.param['state']:
                            # print('Test logger')
                            self.update()
                            self.export_data(writer)
                            time.sleep(self.param['sleeping_time'])
                            self.check_param()
                except IOError as e:
                    print(e)
            time.sleep(1)
        raise InterruptedError

    def send_param(self):
        """method to send message to logger process"""
        self.param.pop('filename', None)
        self.q.put(self.param)

    def exit(self):
        """Set quit flag to True"""
        self.param['quit'] = True
        self.send_param()

    def start_record(self):
        """Set state flag to True"""
        super().start_record()
        self.send_param()

    def stop_record(self):
        """Set state flag to False"""
        super().stop_record()
        self.send_param()

    def _update_watchlist(self, watch):
        super().update_watchlist(watch=watch)
        self.param['updated_watchlist'] = False

    def update_watchlist(self, watch=False):
        self.param['watchlist'] = watch
        self.param['updated_watchlist'] = True
        self.send_param()
        time.sleep(1)
        self.param['updated_watchlist'] = False

    def check_param(self):
        """Method wich check in the process if there is new parameter.
        """
        if self.q.empty() is not True:
            new_param = self.q.get()
            if new_param['updated_watchlist'] is True:
                self.param.update(new_param)
                self._update_watchlist(self.param['watchlist'])
            else:
                new_param.pop('watchlist', None)
                self.param.update(new_param)


LOGLIST = [
    'timestamp',
    'ap.enabled',
    'ap.mode',
    'ap.heading',
    'ap.vmg',
    'ap.cmg',
    'ap.heading_error',
    "imu.pitch",
    "imu.roll",
    "imu.pitchrate",
    "imu.rollrate",
    "imu.headingrate",
    "imu.heel",
    "imu.heading",
    "gps.track",
    "gps.speed",
    "wind.speed",
    "rudder.angle",
    "ap.true_wind_angle",
    "ap.wind_angle",
    "ap.true_wind_speed"
    ]

if __name__ == "__main__":
    
    list_of_data_used = [
        'ap.enabled',
        "ap.vmg",
        "ap.cmg"
        ]

    list_of_data_to_learn_heading = [
        "ap.mode",
        "imu.pitch",
        "imu.roll",
        "imu.pitchrate",
        "imu.rollrate",
        "imu.heel",
        "imu.headingrate",
        "imu.heading",
        "gps.track",
        "gps.speed",
        "wind.speed",
        "ap.true_wind_angle",
        "ap.wind_angle",
        "ap.true_wind_speed",
        "rudder.angle"
        ]

    list_of_data_to_learn_cmg =[
        "ap.mode",
        "imu.pitch",
        "imu.roll",
        "imu.pitchrate",
        "imu.rollrate",
        "imu.heel",
        "imu.headingrate",
        "imu.heading",
        "gps.track",
        "gps.speed",
        "wind.speed",
        "ap.true_wind_angle",
        "ap.wind_angle",
        "ap.true_wind_speed",
        "ap.heading",
        "ap.heading_error",
        "rudder.angle"
        ]

    list_of_data_to_learn = list(set(list_of_data_to_learn_heading + list_of_data_to_learn_cmg))
    
    lod = list_of_data_to_learn + list_of_data_used

    #LOG = SimpleLogger()
    #LOG.run()
    
    LOG = ProcessLogger(watchlist=lod, autostart=True)
    #LOG.start()
    time.sleep(3)
    #LOG.start_record()
    
    kbm = KBHit()
    print('Logger started:')
    print(' s: start full log')
    print(' m: start minimal log')
    print(' p: pause log, hit s or m to start a new log (new file name)')
    print(' q: quit program')

    while True:
        if not kbm.kbhit():
            time.sleep(0.3)
        else:
            km = kbm.getch()
            if km == 's':
                #self.stop_record()
                LOG.update_watchlist()
                time.sleep(1)
                LOG.start_record()
                print('Full Log start, "p" to pause logging')
            elif km == 'm':
                #self.stop_record()
                LOG.update_watchlist(lod)
                time.sleep(1)
                LOG.start_record()
                print('Minimal Log start, "p" to pause logging')
            if km == 'q':
                LOG.stop_record()
                print('Exiting')
                LOG.param['quit'] = True
                break
