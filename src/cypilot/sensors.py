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

import time
import pyjson

import cypilot.pilot_path

from pilot_values import StringValue, SensorValue, RangeSetting, RangeProperty
from resolv import resolv

from gpsd import gpsd

from pilot_path import dprint as print # pylint: disable=redefined-builtin
from pilot_path import PILOT_DIR

SOURCE_PRIORITY = {}

def init_source_priority():
    global SOURCE_PRIORITY
    # favor lower priority sources
    SOURCE_PRIORITY = {'gpsd': 1, 'servo': 1, 'ble': 1, 'serial': 2, 'tcp': 3, 'signalk': 4, 'none': 5}

    sensorsource = {}
    sensorsfilename = PILOT_DIR + 'cypilot_sensors.conf'
    try:
        file = open(sensorsfilename)
        sensorsource = pyjson.load(file)
        file.close()
        SOURCE_PRIORITY = dict(sensorsource['priority'])
    except Exception as e: # pylint: disable=broad-except
        print('failed to read sensor source file:', sensorsfilename, e)
        try:
            file = open(sensorsfilename, 'w')
            sensorsource['priority'] = SOURCE_PRIORITY
            file.write(pyjson.dumps(sensorsource, indent=4) + '\n')
            file.close()
        except Exception as ew: # pylint: disable=broad-except
            print('Exception writing default values to sensor source file:', sensorsfilename, ew)
    return SOURCE_PRIORITY

class Sensor(object):
    def __init__(self, client, name):
        self.source = client.register(StringValue(name + '.source', 'none'))
        self.lastupdate = 0
        self.device = None
        self.name = name
        self.client = client
        self.data_list = []

    def write(self, data, source):
        if SOURCE_PRIORITY[self.source.value] < SOURCE_PRIORITY[source]:
            return False

        # if there are more than one device for a source at the same priority,
        # we only use data from one rather than randomly switching between the two
        if SOURCE_PRIORITY[self.source.value] == SOURCE_PRIORITY[source] and data['device'] != self.device:
            return False

        #timestamp = data['timestamp'] if 'timestamp' in data else time.monotonic()-self.starttime
        self.update(data)

        if self.source.value != source:
            print('found', self.name, 'on', source, data['device'])
            self.source.set(source)
            self.device = data['device']
        self.lastupdate = time.monotonic()

        return True

    def reset(self):
        raise RuntimeError('reset should be overloaded')

    def update(self, data):
        raise RuntimeError('update should be overloaded')

    def register(self, _type, name, *args, **kwargs):
        return self.client.register(_type(*([self.name + '.' + name] + list(args)), **kwargs))


class Wind(Sensor):
    def __init__(self, client):
        super(Wind, self).__init__(client, 'wind')

        self.direction = self.register(
            SensorValue, 'direction', directional=True)
        self.angle = self.register(
            SensorValue, 'angle', directionnal=True)
        self.speed = self.register(SensorValue, 'speed')
        self.offset = self.register(
            RangeSetting, 'offset', 0, -180, 180, 'deg')
        self.coef = self.register(
            RangeSetting, 'coefficient', 100, 0, 200, '%')
        
        self.updated = False
        
        self.data_list = [self.direction, self.angle, self.speed]

    def update(self, data):
        if 'direction' in data:
            # direction is from -180 to 180
            self.direction.set(resolv(data['direction'] + self.offset.value))
            self.angle.set(-self.direction.value)
            self.updated = True
        if 'speed' in data:
            self.speed.set(data['speed'] * self.coef.value/100)
            self.updated = True

    def reset(self):
        self.direction.set(False)
        self.speed.set(False)


class APB(Sensor):
    def __init__(self, client):
        super(APB, self).__init__(client, 'apb')
        self.track = self.register(SensorValue, 'track', directional=True)
        self.xte = self.register(SensorValue, 'xte')
        # 300 is 30 degrees for 1/10th mile
        self.gain = self.register(
            RangeProperty, 'xte.gain', 300, 0, 3000, persistent=True)
        self.last_time = time.monotonic()
        
        self.data_list = [self.track, self.xte]

    def reset(self):
        self.xte.update(0)

    def update(self, data):
        t = time.monotonic()
        if t - self.last_time < .5:  # only accept apb update at 2hz
            return

        self.last_time = t
        self.track.update(data['track'])
        self.xte.update(data['xte'])

         # ignore message if autopilot is not enabled
        if not self.client.values.values['ap.enabled'].value:
            return

        mode = self.client.values.values['ap.mode']
        if mode.value != data['mode']:
            # for GPAPB, ignore message on wrong mode
            if data['isgp'] != 'GP':
                mode.set(data['mode'])
            else:
                return
                # APB is from GP with no gps mode selected so exit

        command = data['track'] + self.gain.value*data['xte']
        print("apb command", command, data)

        heading_command = self.client.values.values['ap.heading_command']
        if abs(heading_command.value - command) > .1:
            heading_command.set(command)


class gps(Sensor):
    def __init__(self, client):
        super(gps, self).__init__(client, 'gps')
        self.last_time = time.monotonic()
        self.track = self.register(SensorValue, 'track', directional=True)
        self.speed = self.register(SensorValue, 'speed')
        self.lat = self.register(SensorValue, 'lat', fmt='%.11f')
        self.lon = self.register(SensorValue, 'lon', fmt='%.11f')
        self.data_list = [self.track, self.speed, self.lat, self.lon]

    def update(self, data):
        # CYS +
        self.last_time = time.monotonic()
        if 'speed' in data:
            self.speed.set(data['speed'])
        # CYS -
        if 'track' in data:
            self.track.set(data['track'])
        if 'lat' in data and 'lon' in data:
            self.lat.set(data['lat'])
            self.lon.set(data['lon'])

    def reset(self):
        self.track.set(False)
        self.speed.set(False)

class sow(Sensor):
    def __init__(self, client):
        super(sow, self).__init__(client, 'sow')
        self.speed = self.register(SensorValue, 'speed')
        self.coef = self.register(RangeSetting, 'coefficient', 100, 0, 200, '%') 
        self.data_list = [self.speed]

    def update(self, data):
        if 'speed' in data:
            self.speed.set(data['speed'] * self.coef.value/100)

    def reset(self):
        self.speed.set(False)

class Sensors(object):
    def __init__(self, client):
        from rudder import Rudder
        from nmea import Nmea
        from signalk import signalk
        from devices.ble_calypso import uwble

        self.client = client

        # sensors priority
        global SOURCE_PRIORITY
        SOURCE_PRIORITY = init_source_priority()

        # services that can receive sensor data
        self.nmea = Nmea(self)
        self.signalk = signalk(self)
        self.gpsd = gpsd(self)
        self.uwble = uwble(self)

        # actual sensors supported
        self.gps = gps(client)
        self.wind = Wind(client)
        self.rudder = Rudder(client)
        self.apb = APB(client)
        self.sow = sow(client)

        self.sensors = {'gps': self.gps, 'wind': self.wind, 'rudder': self.rudder, 'apb': self.apb, 'sow': self.sow}

    def poll(self):
        t0 = time.monotonic()
        self.nmea.poll()
        t1 = time.monotonic()
        self.signalk.poll()
        t2 = time.monotonic()
        self.uwble.poll()
        t3 = time.monotonic()
        self.gpsd.poll()
        t4 = time.monotonic()
        self.rudder.poll()
        t5 = time.monotonic()

        if t5-t0 >= 0.05:
            print(f"Sensor overtime {t5-t0:.2f} > 0.05: nmea={t1-t0:.2f}, signalk={t2-t1:.2f}, uwble={t3-t2:.2f}, gpsd={t4-t3:.2f}, rudder={t5-t4:.2f}")

        # timeout sources
        t = time.monotonic()
        for __, sensor in self.sensors.items():
            if sensor.source.value == 'none':
                continue
            if t - sensor.lastupdate > 8:
                self.lostsensor(sensor)

    def lostsensor(self, sensor):
        print('sensor', sensor.name, 'lost',
              sensor.source.value, sensor.device)
        sensor.source.set('none')
        for item in sensor.data_list:
            item.set(None)
        sensor.reset()
        sensor.device = None

    def lostgpsd(self):
        if self.gps.source.value == 'gpsd':
            self.lostsensor(self.gps)

    def write(self, sensor, data, source):
        if not sensor in self.sensors:
            print('unknown data parsed!', sensor)
            return
        self.sensors[sensor].write(data, source)

    def lostdevice(self, device):
        # optional routine  useful when a device is
        # unplugged to skip the normal data timeout
        for __, sensor in self.sensors.items():
            if sensor.device and sensor.device[2:] == device:
                self.lostsensor(sensor)


def sensors_main():
    print('Version:', cypilot.pilot_path.STRVERSION)

    from server import cypilotServer
    from client import cypilotClient
    server = cypilotServer()
    client = cypilotClient(server)
    sensors = Sensors(client)

    while True:
        server.poll()
        client.poll()
        sensors.poll()
        time.sleep(1.0)

if __name__ == '__main__':
    sensors_main()
