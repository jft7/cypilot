#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
#
# (C) 2020 Sean D'Epagnier (pypilot)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

import time
import socket
import multiprocessing
import requests
import random

import cypilot.pilot_path
from nonblockingpipe import non_blocking_pipe
import pyjson
from client import cypilotClient
from pilot_values import Property, RangeProperty
from sensors import init_source_priority

from pilot_path import dprint as print # pylint: disable=redefined-builtin

SOURCE_PRIORITY = {}
SIGNALK_PRIORITY = 1
RADIANS = 3.141592653589793/180
METERS_S = 0.5144456333854638

# provide bi-directional translation of these keys
SIGNALK_TABLE = {'wind': {('environment.wind.speedApparent', METERS_S): 'speed',
                          ('environment.wind.angleApparent', RADIANS): 'direction'},
                 'gps': {('navigation.courseOverGroundTrue', RADIANS): 'track',
                         ('navigation.speedOverGround', METERS_S): 'speed',
                         ('navigation.position', 1): {'latitude': 'lat', 'longitude': 'lon'}},
                 'rudder': {('steering.rudderAngle', RADIANS): 'angle'},
                 'apb': {('steering.autopilot.target.headingTrue', RADIANS): 'track'},
                 'imu': {('navigation.headingMagnetic', RADIANS): 'heading',
                         ('navigation.attitude', RADIANS): {'pitch': 'pitch', 'roll': 'roll', 'yaw': 'heading'}}}

TOKEN_PATH = cypilot.pilot_path.PILOT_DIR + 'signalk-token'

def debug(*args):
    #print(*args)
    pass

class signalk(object):
    def __init__(self, sensors=False):
        self.active = False
        self.initialized = False
        self.process = None

        global SOURCE_PRIORITY, SIGNALK_PRIORITY
        SOURCE_PRIORITY = init_source_priority()
        if 'signalk' not in SOURCE_PRIORITY:
            print('Warning : "signalk" not active (priority not defined in cypilot_sensors.conf)')
            return
        else:
            self.active = True
            SIGNALK_PRIORITY = SOURCE_PRIORITY['signalk']

        self.sensors = sensors
        if not sensors:
            self.client = cypilotClient()
        else:
            server = sensors.client.server
            self.client = cypilotClient(server)

        self.initialized = False
        self.missingzeroconfwarned = False
        self.signalk_access_url = False
        self.last_access_request_time = 0

        self.token = None
        self.last_values = {}
        self.signalk_msgs = {}
        self.signalk_msgs_skip = {}
        self.period = None
        self.uid = None
        self.signalk_host_port = False
        self.signalk_ws_url = False
        self.ws_ = False

        self.subscribed = {}
        self.subscriptions = []
        self.signalk_values = {}

        self.signalk_last_msg_time = {}
        self.last_sources = {}

        # store certain values across parsing invocations to ensure
        # all of the keys are filled with the latest data
        self.last_values_keys = {}

        if self.sensors:
            self.sensors_pipe, self.sensors_pipe_out = non_blocking_pipe('signalk pipe')
            self.process = multiprocessing.Process(target=self.signalk_process, daemon=True, name='signalk')
            self.process.start()

    def setup(self):
        try:
            f = open(TOKEN_PATH)
            self.token = f.read()
            print('read token', self.token)
            f.close()
        except Exception as e:
            print('signalk failed to read token:', TOKEN_PATH, ' except:', str(e))
            self.token = False

        try:
            from zeroconf import ServiceBrowser, Zeroconf
        except Exception as e:
            if not self.missingzeroconfwarned:
                print(f'signalk: failed to import zeroconf, autodetection not possible, {e}')
                print('try pip3 install zeroconf or apt install python3-zeroconf')
                self.missingzeroconfwarned = True
            time.sleep(20)
            return

        self.last_values = {}
        self.last_sources = {}
        self.signalk_last_msg_time = {}

        # store certain values across parsing invocations to ensure
        # all of the keys are filled with the latest data
        self.last_values_keys = {}
        for __, sensor_table in SIGNALK_TABLE.items():
            for signalk_path_conversion, cypilot_path in sensor_table.items():
                signalk_path, __ = signalk_path_conversion
                if isinstance(cypilot_path, type({})): # single path translates to multiple cypilot
                    self.last_values_keys[signalk_path] = {}

        self.period = self.client.register(RangeProperty('signalk.period', .5, .1, 2, persistent=True))
        self.uid = self.client.register(Property('signalk.uid', 'cypilot', persistent=True))

        self.signalk_host_port = False
        self.signalk_ws_url = False
        self.ws_ = False

        class Listener:
            def __init__(self, signalk_):
                self.signalk = signalk_
                self.name_type = False

            def remove_service(self, zeroconf, type_, name):
                print('signalk zeroconf service removed', name, type_)
                if self.name_type == (name, type_):
                    self.signalk.signalk_host_port = False
                    self.signalk.disconnect_signalk()
                    print('signalk server lost')

            def add_service(self, zeroconf, type_, name):
                print('signalk zeroconf service add', name, type_)
                self.name_type = name, type_
                info = zeroconf.get_service_info(type_, name)
                if not info:
                    return
                for name, value in info.properties.items():
                    if name.decode() == 'swname' and value.decode() == 'signalk-server':
                        try:
                            host_port = socket.inet_ntoa(
                                info.addresses[0]) + ':' + str(info.port)
                        except:
                            host_port = socket.inet_ntoa(info.address) + ':' + str(info.port)
                        self.signalk.signalk_host_port = host_port
                        print('signalk server found', host_port)

            def update_service(self, zeroconf, type_, name):
                """Callback for state updates, which we ignore for now."""

        zeroconf = Zeroconf()
        listener = Listener(self)
        ServiceBrowser(zeroconf, "_http._tcp.local.", listener)
        # zeroconf.close()
        if not self.signalk_host_port:
            self.signalk_host_port = '127.0.0.1:3000'
            print('signalk server not found, using localhost server')
        self.initialized = True

    def probe_signalk(self):
        print('signalk probe...', self.signalk_host_port)

        try:
            r = requests.get('http://' + self.signalk_host_port + '/signalk')
            contents = pyjson.loads(r.content)
            self.signalk_ws_url = contents['endpoints']['v1']['signalk-ws'] + '?subscribe=none'
        except Exception as e:
            print('failed to retrieve/parse data from', self.signalk_host_port, e)
            time.sleep(5)
            return
        print('signalk found', self.signalk_ws_url)

    def request_access(self):
        if self.signalk_access_url:
            dt = time.monotonic() - self.last_access_request_time
            if dt < 10:
                return
            self.last_access_request_time = time.monotonic()
            try:
                r = requests.get(self.signalk_access_url)
                contents = pyjson.loads(r.content)
                print('signalk see if token is ready', self.signalk_access_url, contents)
                if contents['state'] == 'COMPLETED':
                    if 'accessRequest' in contents:
                        access = contents['accessRequest']
                        if access['permission'] == 'APPROVED':
                            self.token = access['token']
                            print('signalk received token', self.token)
                            try:
                                f = open(TOKEN_PATH, 'w')
                                f.write(self.token)
                                f.close()
                            except Exception as e:
                                print(f'signalk failed to store token ({e}) {TOKEN_PATH}')
                    else:
                        self.signalk_access_url = False
            except Exception as e:
                print('signalk error requesting access', e)
                self.signalk_access_url = False
            return

        try:
            def random_number_string(n):
                if n == 0:
                    return ''
                return str(int(random.random()*10)) + random_number_string(n-1)

            if self.uid.value == 'cypilot':
                self.uid.set('cypilot-' + random_number_string(11))
            r = requests.post('http://' + self.signalk_host_port + '/signalk/v1/access/requests', data={"clientId":self.uid.value, "description": "cypilot"})

            contents = pyjson.loads(r.content)
            print('signalk post', contents)
            if contents['statusCode'] == 202 or contents['statusCode'] == 400:
                self.signalk_access_url = 'http://' + self.signalk_host_port + contents['href']
                print('signalk request access url', self.signalk_access_url)
        except Exception as e:
            print('signalk error requesting access', e)
            self.signalk_ws_url = False

    def connect_signalk(self):
        try:
            from websocket import create_connection
        except Exception as e:
            print('signalk cannot create connection:', e)
            print('try pip3 install websocket-client or apt install python3-websocket')
            self.signalk_host_port = False
            return

        self.subscribed = {}
        for sensor in list(SIGNALK_TABLE):
            self.subscribed[sensor] = False
        self.subscriptions = []  # track signalk subscriptions
        self.signalk_values = {}
        try:
            self.ws_ = create_connection(self.signalk_ws_url, header={'Authorization': 'JWT ' + self.token})
            self.ws_.settimeout(0)  # nonblocking
        except Exception as e:
            print('signalk failed to connect', e)
            self.token = False

    def poll(self):
        if self.active:
            msg = self.sensors_pipe_out.recv()
            while msg:
                sensor, data = msg
                self.sensors.write(sensor, data, 'signalk')
                msg = self.sensors_pipe_out.recv()
        
    def signalk_process(self):
        time.sleep(6)
        while True:
            time.sleep(.1)
            if not self.active:
                continue

            if not self.initialized:
                self.setup()
                continue

            self.client.poll(1)
            if not self.signalk_host_port:
                continue # waiting for signalk to detect

            if not self.signalk_ws_url:
                self.probe_signalk()
                continue

            if not self.token:
                self.request_access()
                continue

            if not self.ws_:
                self.connect_signalk()
                if not self.ws_:
                    continue
                print('signalk connected to', self.signalk_ws_url)
                # setup cypilot watches
                watches = ['imu.heading', 'imu.roll', 'imu.pitch', 'timestamp']
                for watch in watches:
                    self.client.watch(watch, self.period.value)
                for sensor in SIGNALK_TABLE:
                    self.client.watch(sensor+'.source')
                continue

            # at this point we have a connection
            # read all messages from cypilot
            while True:
                msg = self.client.receive_single()
                if not msg:
                    break
                debug('signalk cypilot msg', msg)
                name, value = msg
                if name == 'timestamp':
                    self.send_signalk()
                    self.last_values = {}

                if name.endswith('.source'):
                    # update sources
                    for sensor in SIGNALK_TABLE:
                        source_name = sensor + '.source'
                        if name == source_name:
                            self.update_sensor_source(sensor, value)
                        self.last_sources[name[:-7]] = value
                else:
                    self.last_values[name] = value

            while True:
                try:
                    msg = self.ws_.recv()
                    # print('signalk received', msg)
                except:
                    break
                self.receive_signalk(msg)

            # convert received signalk values into sensor inputs if possible
            for sensor, sensor_table in SIGNALK_TABLE.items():
                for source, values in self.signalk_values.items():
                    data = {}
                    for signalk_path_conversion, cypilot_path in sensor_table.items():
                        signalk_path, signalk_conversion = signalk_path_conversion
                        if signalk_path in values:
                            try:
                                value = values[signalk_path]
                                if isinstance(cypilot_path, type({})): # single path translates to multiple cypilot
                                    for signalk_key, cypilot_key in cypilot_path.items():
                                        data[cypilot_key] = value[signalk_key] / signalk_conversion
                                else:
                                    data[cypilot_path] = value / signalk_conversion
                            except Exception as e:
                                print('Exception converting signalk->cypilot', e, self.signalk_values)
                                break
                        elif signalk_conversion != 1: # don't require fields with conversion of 1
                            break  # missing fields?  skip input this iteration
                    else:
                        for signalk_path_conversion in sensor_table:
                            signalk_path, signalk_conversion = signalk_path_conversion
                            if signalk_path in values:
                                del values[signalk_path]
                        # all needed sensor data is found
                        data['device'] = source
                        if self.sensors_pipe:
                            self.sensors_pipe.send([sensor, data])
                        else:
                            print('signalk received', sensor, data)
                        break

    def send_signalk(self):
        # see if we can produce any signalk output from the data we have read
        updates = []
        for sensor, sensor_table in SIGNALK_TABLE.items():
            if sensor != 'imu' and (not sensor in self.last_sources or SOURCE_PRIORITY[self.last_sources[sensor]] >= SIGNALK_PRIORITY):
                #debug('signalk skip send from priority', sensor)
                continue

            for signalk_path_conversion, cypilot_path in sensor_table.items():
                signalk_path, signalk_conversion = signalk_path_conversion
                if isinstance(cypilot_path, type({})):  # single path translates to multiple cypilot
                    keys = self.last_values_keys[signalk_path]
                    # store keys we need for this signalk path in dictionary
                    for signalk_key, cypilot_key in cypilot_path.items():
                        key = sensor+'.'+cypilot_key
                        if key in self.last_values:
                            keys[key] = self.last_values[key]

                    # see if we have the keys needed
                    v = {}
                    for signalk_key, cypilot_key in cypilot_path.items():
                        key = sensor+'.'+cypilot_key
                        if not key in keys:
                            break
                        v[signalk_key] = keys[key]*signalk_conversion
                    else:
                        updates.append({'path': signalk_path, 'value': v})
                        self.last_values_keys[signalk_path] = {}
                else:
                    key = sensor+'.'+cypilot_path
                    if key in self.last_values:
                        v = self.last_values[key]*signalk_conversion
                        updates.append({'path': signalk_path, 'value': v})

        if updates:
            # send signalk updates
            msg = {'updates': [{'$source': 'cypilot', 'values': updates}]}
            debug('signalk updates', msg)
            try:
                self.ws_.send(pyjson.dumps(msg)+'\n')
            except Exception as e:
                print('signalk failed to send', e)
                self.disconnect_signalk()

    def disconnect_signalk(self):
        if self.ws_:
            self.ws_.close()
        self.ws_ = False
        self.client.clear_watches()  # don't need to receive cypilot data

    def receive_signalk(self, msg):
        try:
            data = pyjson.loads(msg)
        except:
            print('signalk failed to parse msg:', msg)
            return
        if 'updates' in data:
            updates = data['updates']
            for update in updates:
                source = 'unknown'
                if 'source' in update:
                    source = update['source']['talker']
                elif '$source' in update:
                    source = update['$source']
                if 'timestamp' in update:
                    timestamp = update['timestamp']
                if not source in self.signalk_values:
                    self.signalk_values[source] = {}
                for value in update['values']:
                    path = value['path']
                    if path in self.signalk_last_msg_time:
                        if self.signalk_last_msg_time[path] == timestamp:
                            debug('signalk skip duplicate timestamp', source, path, timestamp)
                            continue
                        self.signalk_values[source][path] = value['value']
                    else:
                        debug('signalk skip initial message', source, path, timestamp)
                    self.signalk_last_msg_time[path] = timestamp

    def update_sensor_source(self, sensor, source):
        priority = SOURCE_PRIORITY[source]
        watch = priority < SIGNALK_PRIORITY # translate from cypilot -> signalk
        if watch:
            watch = self.period.value
        for signalk_path_conversion, cypilot_path in SIGNALK_TABLE[sensor].items():
            if isinstance(cypilot_path, type({})):
                for __, cypilot_key in cypilot_path.items():
                    cypilot_path = sensor + '.' + cypilot_key
                    if cypilot_path in self.last_values:
                        del self.last_values[cypilot_path]
                    self.client.watch(cypilot_path, watch)
            else:
                # remove any last values from this sensor
                cypilot_path = sensor + '.' + cypilot_path
                if cypilot_path in self.last_values:
                    del self.last_values[cypilot_path]
                self.client.watch(cypilot_path, watch)
        subscribe = priority >= SIGNALK_PRIORITY

        # prevent duplicating subscriptions
        if self.subscribed[sensor] == subscribe:
            return
        self.subscribed[sensor] = subscribe

        if not subscribe:
            # signalk can't unsubscribe by path!?!?!
            subscription = {'context': '*', 'unsubscribe': [{'path': '*'}]}
            debug('signalk unsubscribe', subscription)
            self.ws_.send(pyjson.dumps(subscription)+'\n')

        signalk_sensor = SIGNALK_TABLE[sensor]
        if subscribe: # translate from signalk -> cypilot
            subscriptions = []
            for signalk_path_conversion in signalk_sensor:
                signalk_path, __ = signalk_path_conversion
                if signalk_path in self.signalk_last_msg_time:
                    del self.signalk_last_msg_time[signalk_path]
                subscriptions.append(
                    {'path': signalk_path, 'minPeriod': self.period.value*1000, 'format': 'delta', 'policy': 'instant'})
            self.subscriptions += subscriptions
        else:
            # remove this subscription and resend all subscriptions
            debug('signalk remove subs', signalk_sensor, self.subscriptions)
            subscriptions = []
            for subscription in self.subscriptions:
                for signalk_path_conversion in signalk_sensor:
                    signalk_path, __ = signalk_path_conversion
                    if subscription['path'] == signalk_path:
                        break
                else:
                    subscriptions.append(subscription)
            self.subscriptions = subscriptions
            self.signalk_last_msg_time = {}

        subscription = {'context': 'vessels.self'}
        subscription['subscribe'] = subscriptions
        debug('signalk subscribe', subscription)
        self.ws_.send(pyjson.dumps(subscription)+'\n')

def signalk_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    sk = signalk()
    sk.signalk_process()

if __name__ == '__main__':
    signalk_main()
