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

# pylint: disable=invalid-name, attribute-defined-outside-init, consider-using-f-string

import cypilot.pilot_path # pylint: disable=unused-import
from client import cypilotClient
from cypilot.pilot_values import RangeProperty
from pilots.simple import SimplePilot
from multiprocessing import Process
from scipy import interpolate
import pyjson
import time
import numpy as np
import os

from pilot_path import dprint as print # pylint: disable=redefined-builtin

list_of_gain = ['P', 'I', 'D', 'H']
allure = [40, 90, 130]
wind = [5, 20, 35]

class AutotunePilot(SimplePilot):
    def __init__(self, ap, name='autotune', **kwargs):
        """
        Init of Simple Pilot,
        create PIDHGO
        Heritage of SimplePilot

        Heritage of Thread

        Prepair kill Thread

        Args:
            ap (Autopilot object): autopilot which manage server with data
            name (string), default to "autotune": name of the instance log in server
        """
        super(AutotunePilot, self).__init__(ap, name)
        self.daemon = True

        self.ap = ap
        self.n = name
        self.ap_gain("M", 10, 1, 60)

        self.autotune = Autotune(self.n)
        self.autotune.start()

        self.pid.append(self.autotune.pid)

class Autotune(Process):

    def __init__(self, n, *args, **kwargs):
        super(Autotune,self).__init__(*args, **kwargs)
        self.daemon = True
        self.n = n

    def initialisation(self):
        self.dirpath = os.path.expanduser("~/cypilot_settings")
        os.makedirs(self.dirpath, exist_ok=True)
        
        self.mtime = None
        self.client = object()

        self.list_value = []
        self.data = {}

        self.mean_time = 1

        self.wind_angle = 0
        self.wind_speed = 0
        self.gps_speed = 0

        self.mean_wind_speed = 0
        self.mean_wind_angle = 0
        self.mean_gps_speed = 0

        self.tab_of_gain = {}
        self.list_of_gain = list_of_gain
        self.G_gain = 'G'
        self.allure = allure
        self.wind = wind

        self.autotune_dict = {}

        self.generate_JSON_example()

        self.create_auto_tune()

        self.set_client()

    def set_client(self):
        watchlist = ["ap.true_wind_speed", "ap.true_wind_angle", "gps.speed", "ap.pilot.autotune.M"]

        try:
            self.client = cypilotClient('localhost')
            self.client.connect(True)
            for item in watchlist:
                self.client.watch(item)
        except Exception as e:
            print(e)
            print("Fail to connect to server")


    def generate_JSON_example(self):
        """Generate JSON tab of autopilot setting in use to autotune
        When updated, the file must be rename to autotune_settings.txt to be used
        """
        tableau = {}
        for al in self.allure:
            tableau[str(al)] = {}
            for wi in self.wind:
                tableau[str(al)][str(wi)] = {}
                for pa in self.list_of_gain:
                    tableau[str(al)][str(wi)][pa] = 1

        with open(self.dirpath + '/autotune_settings_example.txt', "w") as outfile:
            pyjson.dump(tableau, outfile, indent=4)

    def load_JSON(self):
        path = self.dirpath + '/autotune_settings.txt'
        t = os.path.getmtime(path)
        if t != self.mtime :
            print("Updating autotune settings")
            self.mtime = t
            with open(path, 'r') as f:
                self.tab_of_gain = pyjson.load(f)
                return True
        return False

    def create_auto_tune(self):
        """genrate interpolation function for each gain
        """
        # load tune tab
        if not self.load_JSON():
            return
        # retrieve array for each gain
        dict_of_tune = {}
        for item in self.list_of_gain:
            list_of_array = []
            for w in self.wind:
                na = []
                for a in self.allure:
                    na.append(self.tab_of_gain[str(a)][str(w)][item])
                list_of_array.append(na)
            dict_of_tune[item] = list_of_array

        # create functions and keep them in dict
        a = np.array(self.allure)
        b = np.array(self.wind)
        for item in self.list_of_gain:
            c = np.array(dict_of_tune[item])
            f = interpolate.interp2d(a,b,c, kind='linear')
            self.autotune_dict[item] = f

    def auto_tune(self):
        """update gain with autotune function
        """
        # check if autotune parameters have been updated
        self.create_auto_tune()
        # limit extreme value
        speed = max(min(self.wind), self.mean_wind_speed)
        speed = min(max(self.wind), speed)
        angle = max(min(self.allure), self.mean_wind_angle)
        angle = min(max(self.allure), angle)
        # set new gain
        for item in self.list_of_gain:
            gain_name = 'ap.pilot.' + self.n + '.' + item
            new_value = round(self.autotune_dict[item]([angle],[speed])[0],2)
            self.client.set(gain_name, new_value)
        # set G gain
        gain_name = 'ap.pilot.' + self.n + '.' + self.G_gain
        self.client.set(gain_name, round(self.mean_gps_speed,1))

    def mean_value(self):
        #init parameter
        wind_angle = 0
        wind_speed = 0
        gps_speed = 0
        #append new value
        self.list_value.append((self.wind_angle, self.wind_speed, self.gps_speed))
        #del old value
        while len(self.list_value) > self.mean_time:
            del self.list_value[0]
        #mean value
        for item in self.list_value:
            wind_angle += item[0]
            wind_speed += item[1]
            gps_speed += item[2]

        self.mean_wind_angle = wind_angle / self.mean_time
        self.mean_wind_speed = wind_speed / self.mean_time
        self.mean_gps_speed = gps_speed / self.mean_time

    def retrieve_value(self):
        """Retrieve true wind speed and angle value and gps.speed
        """
        
        # these sensors may have different refresh rates
        # so multiple read are required to read all the values
        # as each individual sensor value is updated in real time
        
        # the timeout for this multiple sensors read should be
        # greater than the longest sensor period : 1.1 s allows
        # to use legacy NMEA sensor with 1 Hz rate
        
        rv_list =  ["ap.true_wind_speed", "ap.true_wind_angle", "gps.speed"]
        rv_values = {}
        rv_time = time.monotonic()
        
        while time.monotonic() - rv_time < 1.1 :
            self.data = self.client.receive(1)
            for v in rv_list :
                if v in self.data :
                    rv_values[v] = self.data[v]
                if "ap.pilot.autotune.M" in self.data:
                    self.mean_time = self.data["ap.pilot.autotune.M"]
            for v in rv_list :
                if v not in rv_values :
                    break
            else:
                self.gps_speed = rv_values["gps.speed"]
                self.wind_angle = rv_values["ap.true_wind_angle"]
                self.wind_speed = rv_values["ap.true_wind_speed"]
                return True
        
        for v in rv_list :
            if v not in rv_values:
                print("Fail to autotune pilot settings, no {} data".format(v))
        return False
            
    def run(self):
        self.initialisation()
        while True:
            time.sleep(1)
            # check if every sensors needed run, if not, gain won't auto update
            if self.retrieve_value() :
                self.mean_value()
                self.auto_tune()

pilot = AutotunePilot

if __name__ == "__main__":
    pass
