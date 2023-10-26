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

"""
Boat imu relies on BNO08X IMU devices with Hillcrest Laboratories firmware
"""

import time
import math

from adafruit_extended_bus import ExtendedI2C as I2C

import cypilot.pilot_path
import quaternion
from client import cypilotClient
from pilot_values import SensorValue, ResettableValue, EnumProperty, RangeProperty, Property
import pyjson

import devices.pilot_imu

from pilot_path import dprint as print # pylint: disable=redefined-builtin
from pilot_path import PILOT_DIR

def read_deviation():
    deviationfilename = PILOT_DIR + 'cypilot_deviation.conf'
    deviation_value = []

    # the deviation table provides deviation values for given headings
    # this deviation value is added to imu heading to compute true heading
    # note that this is not actually deviation : the values should also include the declinaison
    deviation_table = {}
    try:
        file = open(deviationfilename)
        deviation_table = pyjson.load(file)
        file.close()
    except:
        # Define default deviation table
        deviation_table = {'0':0,'30':0,'60':0,'90':0,'120':0,'150':0,'180':0,'210':0,'240':0,'270':0,'300':0,'330':0,'360':0}
        try:
            file = open(deviationfilename, 'w')
            json_deviation_table = pyjson.dumps(deviation_table, indent=4)
            file.write(json_deviation_table + '\n')
            file.close()
        except Exception as e:
            print('Exception writing default values to deviation table file:', deviationfilename, e)

    # use linear interpolation to compute value for headings from 0 to 360
    if not deviation_table:
        deviation_table['0'] = 0
    if '0' in deviation_table:
        deviation_table['360'] = deviation_table['0']
    elif '360' in deviation_table:
        deviation_table['0'] = deviation_table['360']
    else:
        h2 = int(list(deviation_table)[0])
        h1 = int(list(deviation_table)[-1])
        d2 = list(deviation_table.values())[0]
        d1 = list(deviation_table.values())[-1]
        d0 = (d2-d1)*(360-h1)/(360+h2-h1) + d1
        deviation_table['0'] = int(d0)
        deviation_table['360'] = deviation_table['0']
    for m in range(0,360):
        h1 = 0
        h2 = 360
        for s in deviation_table:
            h = int(s)
            if m >= h:
                h1 = max(h,h1)
            if m < h:
                h2 = min(h,h2)
        d1 = deviation_table[str(h1)]
        d2 = deviation_table[str(h2)]
        deviation_value.append(int((d2-d1)*(m-h1)/(h2-h1) + d1))

    return deviation_value

def readable_timespan(total):
    """readable_timespan : build readable time span

    Args:
        total (float): time value

    Returns:
        string: readable time value
    """
    mods = [('s', 1), ('m', 60), ('h', 60), ('d', 24), ('y', 365.24)]
    def loop(i, mod):
        if i == len(mods) or (int(total / (mods[i][1]*mod)) == 0 and i > 0):
            return ''
        if i < len(mods) - 1:
            div = mods[i][1]*mods[i+1][1]*mod
            t = int(total%int(div))
        else:
            t = total
        return loop(i+1, mods[i][1]*mod) + (('%d' + mods[i][0] + ' ') % (t/(mods[i][1]*mod)))
    return loop(0, 1)

class QuaternionValue(ResettableValue):
    """QuaternionValue Quaternion

    Args:
        name (string): name
        initial (float): initial value
    """
    def set(self, value):
        if value:
            value = quaternion.normalize(value)
        super(QuaternionValue, self).set(value)


class BoatIMU(object):
    """BoatIMU : Boat IMU on top of RTIMU

    Args:
            server
    """
    def __init__(self, client):
        self.client = client

        self.rate = self.register(EnumProperty, 'rate', 10, [10, 20], persistent=True)

        self.alignmentQ = self.register(QuaternionValue, 'alignmentQ', [1, 0, 0, 0], persistent=True)
        self.alignmentQ.last = False
        self.heading_off = self.register(RangeProperty, 'heading_offset', 0, -180, 180, persistent=True)
        self.heading_off.last = 3000 # invalid

        self.deviation = read_deviation()

        self.alignmentCounter = self.register(Property, 'alignmentCounter', 0)
        self.last_alignmentCounter = False
        self.alignmentPose = [0, 0, 0, 0]

        self.lasttimestamp = 0

        self.headingrate = self.heel = 0

        sensornames = ['accel_X', 'accel_Y', 'accel_Z', 'pitch', 'roll']
        sensornames += ['pitchrate', 'rollrate', 'headingrate', 'heel']
        directional_sensornames = ['heading']
        sensornames += directional_sensornames

        self.sensor_values = {}
        for name in sensornames:
            self.sensor_values[name] = self.register(SensorValue, name, directional=name in directional_sensornames)

        # quaternion needs to report many more decimal places than other sensors
        self.sensor_values['fusionQPose'] = self.register(SensorValue, 'fusionQPose', fmt='%.8f')

        # initialize IMU for direct access to the device data
        self.i2c = I2C(devices.pilot_imu.I2C_DEFAULT_BUS)
        self.imu = devices.pilot_imu.PilotIMU(i2c=self.i2c, rate=self.rate.value)
        time.sleep(0.1)

        self.last_imuread = time.monotonic() + 4 # ignore failed readings at startup

    def register(self, _type, name, *args, **kwargs):
        """register : register IMU object value on server under "imu.name"

        Args:
            _type (type): type of value
            name (string): registration name extension

        Returns:
            value: registered object value
        """
        value = _type(*(['imu.' + name] + list(args)), **kwargs)
        return self.client.register(value)

    def update_alignment(self, q):
        """update_alignment : update boat alignment

        Args:
            q (quaternion): alignment
        """
        a2 = 2*math.atan2(q[3], q[0])
        heading_offset = a2*180/math.pi
        off = self.heading_off.value - heading_offset
        o = quaternion.angvec2quat(off*math.pi/180, [0, 0, 1])
        self.alignmentQ.update(quaternion.normalize(quaternion.multiply(q, o)))

    def read(self):
        data = self.imu.getIMUData()

        self.last_imuread = time.monotonic()

        # alignment of the position vector to increase precision
        p_aligned = quaternion.multiply(data['fusionQPose'], self.alignmentQ.value)
        p_aligned = quaternion.normalize(p_aligned)
        data['roll'], data['pitch'], data['heading'] = map(math.degrees, quaternion.toeuler(p_aligned))

        # no alignment required for gyro if the installation alignment procedure has been completed
        # we use the gyro vector directly from the IMU as precision is sufficient for pitch/roll/heading rate
        data['rollrate'], data['pitchrate'], data['headingrate'] = map(math.degrees, data['gyro'])

        if data['heading'] < 0:
            data['heading'] += 360

        # apply deviation correction table on magnetic heading
        data['heading'] += self.deviation[int(data['heading'])]

        self.headingrate = data['headingrate']

        data['heel'] = self.heel = data['roll']*.03 + self.heel*.97

        data['accel_X'], data['accel_Y'], data['accel_Z'] = data['accel']

        # set sensors
        for sname, svalue in self.sensor_values.items():
            svalue.set(data[sname])

        # count down to alignment
        if self.alignmentCounter.value != self.last_alignmentCounter:
            self.alignmentPose = [0, 0, 0, 0]

        if self.alignmentCounter.value > 0:
            self.alignmentPose = list(map(lambda x, y: x + y, self.alignmentPose, p_aligned))
            self.alignmentCounter.set(self.alignmentCounter.value-1)

            if self.alignmentCounter.value == 0:
                self.alignmentPose = quaternion.normalize(self.alignmentPose)
                adown = quaternion.rotvecquat([0, 0, 1], quaternion.conjugate(self.alignmentPose))

                alignment = []
                alignment = quaternion.vec2vec2quat([0, 0, 1], adown)
                alignment = quaternion.multiply(self.alignmentQ.value, alignment)

                if alignment:
                    self.update_alignment(alignment)

            self.last_alignmentCounter = self.alignmentCounter.value

        # if alignment or heading offset changed:
        if self.heading_off.value != self.heading_off.last or self.alignmentQ.value != self.alignmentQ.last:
            self.update_alignment(self.alignmentQ.value)
            self.heading_off.last = self.heading_off.value
            self.alignmentQ.last = self.alignmentQ.value

def boatimu_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    from server import cypilotServer
    server = cypilotServer()
    client = cypilotClient(server)
    boatimu = BoatIMU(client)

    lastprint = 0
    while True:
        t0 = time.monotonic()
        server.poll()
        client.poll()
        boatimu.read()
        data = boatimu.imu.getIMUData()
        if t0-lastprint > 1:
            # pylint: disable=consider-using-f-string
            print(' Gyro (rad/sec): {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['gyro']))
            print(' FusionQPose: {:0.3f}, {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['fusionQPose']))
            print(' Acceleration (g): {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['accel']))
            print(' Gyro (rad/sec): {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['gyro']))
            print(' FusionQPose: {:0.3f}, {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['fusionQPose']))
            print('')
            lastprint = t0

if __name__ == '__main__':
    del print # disable cypilot trace
    boatimu_main()
