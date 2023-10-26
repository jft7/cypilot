#!/usr/bin/env python
#
# (C) 2022 ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

"""Remplir un dataframe panda from .pol
entrainer un odel de regression lineaire
utiliser le model de regression linaire pour prédire la vitesse cible
etablir un pourcentage entre vitesse fond et vitesse cible
renvoyer les valeur sur le serveur
"""

# pylint: disable=attribute-defined-outside-init

import cypilot.pilot_path # pylint: disable=unused-import
from client import cypilotClient
from cypilot.pilot_values import Property, SensorValue, EnumSetting, BooleanSetting
from multiprocessing import Process
import time
import json
import pandas as pd
import csv
from scipy import interpolate
from scipy.spatial.qhull import QhullError
import math

from pilot_path import dprint as print # pylint: disable=redefined-builtin
from pilot_path import PILOT_DIR


class Perf():

    def __init__(self):
        self.polar_path = PILOT_DIR + 'interpolate_polar.csv'
        self.sailect_path = PILOT_DIR + 'interpolate_sailect.sailselect'
        self.process = None # allow to gracefully terminate autopilot if process creation was not successful (missing csv, etc.)

        try:
            self.polar_f = self.create_polar_function()
            self.sailect_data = self.sailect_data_extract()
            self.process = Process(target=self.tprocess, daemon=True, name='Perf')
            self.process.start()

        except Exception as e:
            print(e)
            print("Performance data won't be available")

    def saildef_data_extract(self):
        saildef = {}
        with open(PILOT_DIR + "boat_config.json", 'r') as file:
            saildef = json.load(file)
        return saildef

    def sailect_data_extract(self):
        with open(self.sailect_path) as f:
            sailect = pd.read_csv(f, delimiter=";")
            sailect.rename(columns={"TWA\\TWS": "TWA"}, inplace=True)
            sailect = sailect.set_index("TWA")
            sailect.columns = sailect.columns.astype(float)
        return sailect

    def sailect_f(self, wind_angle, wind_speed):
        i = self.sailect_data.index.get_indexer([wind_angle], method="nearest")
        c = self.sailect_data.columns.get_indexer([wind_speed], method="nearest")
        return self.sailect_data[self.sailect_data.columns[c[0]]][self.sailect_data.index[i[0]]]


    def polar_data_extract(self):
        polar = []
        speed_list = []
        with open(self.polar_path) as csvfile:
            reader = csv.reader(csvfile, delimiter= ';')
            for row in reader:
                polar.append(row)
            if polar[0][0] == "TWA\\TWS":
                for i in range(len(polar)):
                    if i != 0:
                        for j in range(len(polar[i])):
                            if j != 0:
                                if polar[i][j] != None: 
                                    #remove all None value
                                    speed_list.append([float(polar[i][0]),float(polar[0][j]),float(polar[i][j])])
        return pd.DataFrame(speed_list, columns=["TWA","TWS","BSP"])

    def create_polar_function(self):
        df = self.polar_data_extract()
        twatws = df[['TWA', 'TWS']].to_numpy()
        bsp = df["BSP"].to_numpy()
        try:
            f = interpolate.LinearNDInterpolator(twatws,bsp)
        except (ValueError, QhullError) as E:
            print(E)
            print('Fail to create perf analysis function')
        return f

    def set_client(self):
        watchlist = ["ap.true_wind_speed", "ap.true_wind_angle", "gps.speed", "gps.track", "imu.heading", "sow.speed"]

        try:
            self.client = cypilotClient('localhost')
            self.client.connect(True)
            for item in watchlist:
                self.client.watch(item)
        except Exception as e:
            print(e)
            print("Fail to connect to server")
            raise ConnectionError from e

    def register(self, _type, name, *args, **kwargs):
        return self.client.register(_type(*(['perf.' + name] + list(args)), **kwargs))

    def retrieve_value(self):
        """Retrieve true wind speed and angle value and gps.speed
        """
        
        # these sensors may have different refresh rates
        # so multiple read are required to read all the values
        # as each individual sensor value is updated in real time
        
        # the timeout for this multiple sensors read should be
        # greater than the longest sensor period : 1.1 s allows
        # to use legacy NMEA sensor with 1 Hz rate
        
        rv_perf =  ["ap.true_wind_speed", "ap.true_wind_angle", "gps.speed"]
        rv_drift =  ["imu.heading", "sow.speed", "gps.track"]
        rv_list = rv_perf + rv_drift
        rv_values = {}
        rv_time = time.monotonic()
        
        while time.monotonic() - rv_time < 1.1 :
            self.data = self.client.receive(1)
            for v in rv_list :
                if v in self.data :
                    rv_values[v] = self.data[v]
            for v in rv_list :
                if v not in rv_values :
                    break
            else:
                self.gps_speed = rv_values["gps.speed"]
                self.wind_angle = rv_values["ap.true_wind_angle"]
                self.wind_speed = rv_values["ap.true_wind_speed"]
                self.heading = rv_values["imu.heading"]
                self.sow = rv_values["sow.speed"]
                self.track = rv_values["gps.track"]
                return True
        
        for v in rv_list :
            if v not in rv_values:
                print("Fail to analyse performance and compute drift, no {} data".format(v))
        return False

    def mean_value(self):
        #init parameter
        wind_angle = 0
        wind_speed = 0
        gps_speed = 0
        #append new value
        self.list_value.append((abs(self.wind_angle), self.wind_speed, self.gps_speed))
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

    def initialisation(self):
        self.client = object()

        self.list_value = []
        self.data = {}

        self.mean_time = 30

        self.wind_angle = 0
        self.wind_speed = 0
        self.gps_speed = 0

        self.mean_wind_speed = 0
        self.mean_wind_angle = 0
        self.mean_gps_speed = 0

        self.set_client()
        self.register(SensorValue, "target_spd")
        self.register(SensorValue, "polar_fract")
        self.register(SensorValue, "sail_advice")
        self.register(SensorValue, "drift_speed")
        self.register(SensorValue, "drift_direction")
        self.register(Property, "mean_time", self.mean_time)
        self.register(BooleanSetting, "quality_flag", False)

        l = self.saildef_data_extract()
        for item in l:
            self.register(EnumSetting, ("boat_config." + item), l[item][0], l[item])

    def analyse_perf(self):
        bsptgt = self.polar_f([self.mean_wind_angle],[self.mean_wind_speed])[0]
        sailadvice = self.sailect_f(self.mean_wind_angle, self.mean_wind_speed)
        self.client.set("perf.sail_advice", sailadvice)
        self.client.set("perf.target_spd", bsptgt)
        if bsptgt != 0:
            self.client.set("perf.polar_fract", (self.mean_gps_speed/bsptgt*100))

    def analyse_drift(self):
        # add calculation - track may be not defined
        drift_x = math.cos(math.radians(self.track))*self.gps_speed - math.cos(math.radians(self.heading))*self.sow
        drift_y = math.sin(math.radians(self.track))*self.gps_speed - math.sin(math.radians(self.heading))*self.sow
        drift_speed = math.sqrt(drift_x**2 + drift_y**2)
        # drift_dir = math.degrees(math.atan(drift_y/drift_x))
        drift_dir = math.degrees(math.atan(drift_y/(drift_x if drift_x != 0 else 0.001)))
        self.client.set("perf.drift_speed", drift_speed)
        self.client.set("perf.drift_direction", drift_dir)

    def tprocess(self):
        self.initialisation()
        print("Performance process started")
        while True:
            time.sleep(1)
            # check if every sensors needed run, if not, gain won't auto update
            if self.retrieve_value() :
                try:
                    self.mean_value()
                    self.analyse_perf()
                    self.analyse_drift()
                except (KeyError, AttributeError):
                    pass

if __name__ == "__main__":
    p = Perf()
    print(p.process.pid)
