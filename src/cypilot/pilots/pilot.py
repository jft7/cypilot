#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
#
# (C) 2019 Sean D'Epagnier (pypilot)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

import cypilot.pilot_path # pylint: disable=unused-import

from pilot_values import RangeProperty, SensorValue


class AutopilotGain(RangeProperty):
    def __init__(self, *cargs):
        super(AutopilotGain, self).__init__(*cargs, persistent=True)
        self.info['AutopilotGain'] = True


class AutopilotPilot(object):
    def __init__(self, name, ap):
        super(AutopilotPilot, self).__init__()
        self.name = name
        self.ap = ap
        self.gains = {}
        self.pid = []
        self.counter = 0
        # self.frequency = self.register(RangeProperty, "period", 1, 1, 20)

    def process(self, reset):
        #self.counter += 1
        #if self.counter >= self.ap.client.values.values['ap.pilot.' + self.name + '.period'].value:
        #    self.counter = 0
        #else:
        #    return False
        pass


    def register(self, _type, name, *args, **kwargs):
        return self.ap.client.register(_type(*(['ap.pilot.' + self.name + '.' + name] + list(args)), **kwargs))

    def ap_gain(self, name, default, min_val, max_val, compute=None):
        if compute is None:
            def compute_(value):
                return value * self.gains[name]['apgain'].value
            compute = compute_
        self.gains[name] = {'apgain': self.register(AutopilotGain, name, default, min_val, max_val),
                            'sensor': self.register(SensorValue, name+'gain'),
                            'compute': compute}

    def ap_compute(self, gain_values):
        command = 0
        for gain in self.gains:
            if gain in gain_values.keys():
                value = gain_values[gain]
                gains = self.gains[gain]
                gains['sensor'].set(gains['compute'](value))
                command += gains['sensor'].value
        return command

    def compute_heading(self):
        #to add overlay without break the code, check if ap.mode_overlay.value
        #and compute ap.heading_overlay.set in function
        ap = self.ap
        compass = ap.boatimu.sensor_values['heading'].value
        gps = ap.sensors.gps.track.value

        if ap.mode.value == 'true wind':
            ap.heading.set(ap.true_wind_angle.value)
        elif ap.mode.value == 'wind':
            ap.heading.set(ap.wind_angle_smoothed.value)
        elif ap.mode.value == 'gps':
            ap.heading.set(gps)
        elif ap.mode.value == 'compass':
            ap.heading.set(compass)
        elif ap.mode.value == 'rudder angle':
            rudder = ap.client.values.values['rudder.angle'].value
            ap.heading.set(int(rudder))
        #forexemple:
        #if ap.mode_overlay == 'wind':
        #    wind = resolv(ap.wind_compass_offset.value - compass)
        #    ap.heading_overlay.set(wind)

    # return new mode if sensors don't support it
    def best_mode(self, mode):
        sensors = self.ap.sensors
        nowind = sensors.wind.source.value == 'none' #or sensors.wind.speed.value < self.ap.low_wind_limit.value
        nogps = sensors.gps.source.value == 'none' or sensors.gps.speed.value < 1 #and? or?
        #add nocompass switch to wind

        if mode == 'true wind':  # for true wind, need both wind and gps
            if nowind:
                return 'compass'
            if nogps:
                return 'wind'
        if mode == 'wind' and nowind:
            return 'compass'
        elif mode == 'gps' and nogps:
            return 'compass'
        return mode
