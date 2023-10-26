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

import math
import time

import cypilot.pilot_path
from pilot_values import SensorValue, Value, EnumProperty, RangeProperty, BooleanProperty
from sensors import Sensor

from pilot_path import dprint as print # pylint: disable=redefined-builtin

class Rudder(Sensor):
    def __init__(self, client):
        super(Rudder, self).__init__(client, 'rudder')

        self.angle = self.register(SensorValue, 'angle')
        self.speed = self.register(SensorValue, 'speed')
        self.last = 0
        self.last_time = time.monotonic()
        self.offset = self.register(Value, 'offset', 0.0, persistent=True)
        self.scale = self.register(Value, 'scale', 100.0, persistent=True)
        self.nonlinearity = self.register(Value, 'nonlinearity', 0.0, persistent=True)
        self.range = self.register(RangeProperty, 'range', 45, 10, 100, persistent=True)
        self.calibrated = self.register(BooleanProperty, 'calibrated', False, persistent=True)

        self.calibration_state = self.register(EnumProperty, 'calibration_state', 'idle', [
            'idle', 'reset', 'centered', 'starboard range', 'port range'])
        self.calibration_raw = {}

        self.lastrange = 0
        self.minmax = -.5, .5
        self.raw = 0
        
        self.data_list = [self.angle, self.speed]

    # calculate minimum and maximum raw rudder value in the range -0.5 to 0.5
    def update_minmax(self):
        scale = self.scale.value
        offset = self.offset.value
        range_ = float(self.range.value)
        self.lastrange = self.range.value
        if self.calibrated.value:
            self.minmax = (-range_ - offset)/scale, (range_ - offset)/scale
        else:
            self.minmax = -.5, .5

    def calibration(self, command):
        if command == 'reset':
            self.nonlinearity.update(0.0)
            self.scale.update(100.0)
            self.offset.update(0.0)
            self.calibration_raw = {}
            self.calibrated.update(False)
            self.update_minmax()
            return

        elif command == 'centered':
            true_angle = 0
        elif command == 'port range':
            true_angle = self.range.value
        elif command == 'starboard range':
            true_angle = -self.range.value
        else:
            print('unhandled rudder_calibration', command)
            return

        # raw range 0 to 1
        self.calibration_raw[command] = {'raw': self.raw, 'rudder': true_angle}

        scale = self.scale.value
        offset = self.offset.value
        nonlinearity = self.nonlinearity.value

        # rudder = (nonlinearity * raw + scale) * raw + offset
        p = []
        for c in ['starboard range', 'centered', 'port range']:
            if c in self.calibration_raw:
                p.append(self.calibration_raw[c])

        # we need 3 points to estimate nonlinearity scale and offset
        if len(p) < 3:
            print('need 3 points to calibrate rudder', self.calibration_raw)
            return

        # compute scale, offset and nonlinearity
        rudder0, rudder1, rudder2 = p[0]['rudder'], p[1]['rudder'], p[2]['rudder']
        raw0, raw1, raw2 = p[0]['raw'], p[1]['raw'], p[2]['raw']

        if min(abs(raw1 - raw0), abs(raw2 - raw0), abs(raw2 - raw1)) > .001:
            scale = (rudder2 - rudder0)/(raw2 - raw0)
            offset = rudder0 - scale*raw0
            nonlinearity = (rudder1 - scale*raw1 - offset) / \
                (raw0-raw1)/(raw2-raw1)
        else:
            print('bad rudder calibration', self.calibration_raw)
            del self.calibration_raw[command]
            return

        if abs(scale) <= .01:
            # bad update, trash an other reading
            print('bad servo rudder calibration', scale, nonlinearity)
            while len(self.calibration_raw) > 1:
                for c, r in self.calibration_raw.items():
                    if c != command:
                        del r
                        break
            return

        self.offset.update(offset)
        self.scale.update(scale)
        self.nonlinearity.update(nonlinearity)
        self.calibrated.update(True)
        self.update_minmax()

    def invalid(self):
        # return type(self.angle.value) == type(False)
        return (isinstance(self.angle.value, type(False)) or self.angle.value is None)

    def poll(self):
        if self.calibrated.value and self.lastrange != self.range.value:
            # warning: do not allow to change range if not in calibration procedure
            self.range.update(self.lastrange)

        if self.calibration_state.value != 'idle':
            # perform calibration
            self.calibration(self.calibration_state.value)
            self.calibration_state.set('idle')

    def raw2angle(self, raw):
        scale = self.scale.value
        offset = self.offset.value
        nlin = self.nonlinearity.value
        mn = self.minmax[0]
        mx = self.minmax[1]

        angle = round(scale*raw + offset + nlin*(mn-raw)*(mx-raw), 2)
        return angle

    def angle2raw(self, angle):
        scale = self.scale.value
        offset = self.offset.value
        nlin = self.nonlinearity.value
        mn = self.minmax[0]
        mx = self.minmax[1]

        a = nlin
        b = scale - nlin*(mn+mx)
        c = offset - angle + nlin*mn*mx
        d = b*b - a*c*4
        r = 0

        if a != 0 and d >= 0:
            r = (-b -math.sqrt(d))/(2*a)
            if r < -0.5 or r > 0.5:
                r = (-b +math.sqrt(d))/(2*a)

        if r < -0.5 or r > 0.5:
            r = 0

        return r

    def update(self, data):
        if not data:
            self.angle.update(False)
            return

        self.raw = data['angle']
        if math.isnan(self.raw):
            self.angle.update(False)
            return

        angle = self.raw2angle(self.raw)
        self.angle.set(angle)

        self.angle2raw(angle)

        t = time.monotonic()
        dt = t - self.last_time

        if dt > 1:
            dt = 1
        if dt > 0:
            speed = (self.angle.value - self.last) / dt
            self.last_time = t
            self.last = self.angle.value
            self.speed.set(speed if self.speed.value is None else .9*self.speed.value + .1*speed)

    def reset(self):
        self.angle.set(False)

def rudder_main():
    print('Version:', cypilot.pilot_path.STRVERSION)

if __name__ == '__main__':
    rudder_main()
