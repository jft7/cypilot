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

import socket
import select
import sys
import os
import time
import heapq

import cypilot.pilot_path
import pyjson
from bufferedsocket import LineBufferedNonBlockingSocket
from pilot_values import Value

from pilot_path import dprint as print # pylint: disable=redefined-builtin
from pilot_path import PILOT_DIR

DEFAULT_PORT = 23322
CLIENT_CONNECT_RETRY_TIME = 1
CLIENT_CONNECT_MAX_DELAY = 20


class Watch():
    def __init__(self, value, period):
        self.value = value
        self.period = period
        self.time = time.monotonic() + period

class ClientWatch(Value):
    def __init__(self, values, client):
        super().__init__('watch', {})
        self.values = values
        self.client = client

    def set(self, value):
        for name in value:
            val = self.values[name]
            period = value[name]
            if period is False:
                val.watch = False
            else:
                if period is True:
                    period = 0
                if not val.watch or val.watch.period > period:
                    self.client.send(name + '=' + val.get_msg() + '\n') # initial send
                val.watch = Watch(val, period)
                val.pwatch = True

class ClientValues(Value):
    def __init__(self, client):
        self.value = False
        super(ClientValues, self).__init__('values', False)
        self.client = client
        self.values = {'values': self}
        self.values['watch'] = ClientWatch(self.values, client)
        self.wvalues = {}
        self.pqwatches = []

    def set(self, value):
        if self.value is False:
            self.value = value
        else:
            for name in value:
                self.value[name] = value[name]

    def send_watches(self):
        t0 = time.monotonic()
        while self.pqwatches:
            if t0 < self.pqwatches[0][0]:
                break # no more are ready
            __, __, watch = heapq.heappop(self.pqwatches)
            if watch.value.watch == watch:
                self.client.send(watch.value.name + '=' + watch.value.get_msg() + '\n')
                watch.time += watch.period
                if watch.time < t0:
                    watch.time = t0
                watch.value.pwatch = True # can watch again once updated

    def insert_watch(self, watch):
        heapq.heappush(self.pqwatches, (watch.time, time.monotonic(), watch))

    def register(self, value):
        if value.name in self.values:
            print('warning, registering existing value:', value.name)
        self.wvalues[value.name] = value.info
        self.values[value.name] = value

    def get_msg(self):
        ret = pyjson.dumps(self.wvalues)
        if "must be real number, not NoneType" in ret:
            print('TRIGGER')
        self.wvalues = {}
        return ret

    def onconnected(self):
        for name, value in self.values.items():
            if name != 'values' and name != 'watch':
                self.wvalues[name] = value.info

class cypilotClient(object):
    def __init__(self, host=False):
        self.values = ClientValues(self)
        self.watches = {}
        self.wwatches = {}
        self.received = []
        self.last_values_list = False
        self.poller_in_progress = None

        if host and not isinstance(host, type('')):
            # host is the server object
            self.server = host
            self.connection = host.pipe()
            self.poller = select.poll()
            fd = self.connection.fileno()
            if fd:
                self.poller.register(fd, select.POLLIN)
                self.values.onconnected()
            return

        config = {}
        self.configfilename = PILOT_DIR + 'cypilot_client.conf'

        try:
            file = open(self.configfilename)
            config = pyjson.loads(file.readline())
            file.close()

        except Exception as e:
            print('failed to read config file:', self.configfilename, e)
            config = {}

        if host:
            if ':' in host:
                i = host.index(':')
                config['host'] = host[:i]
                config['port'] = host[i+1:]
            else:
                config['host'] = host
        if 'host' not in config:
            config['host'] = '127.0.0.1'

        if 'port' not in config:
            config['port'] = DEFAULT_PORT
        self.config = config

        self.connection = False # connect later
        self.connection_in_progress = False

    def onconnected(self):
        # print('connected to cypilot server', time.time())
        self.last_values_list = False

        # write config if connection succeeds
        try:
            file = open(self.configfilename, 'w')
            file.write(pyjson.dumps(self.config) + '\n')
            file.close()
            self.write_config = False
        except IOError:
            print('failed to write config file:', self.configfilename)
        except Exception as e:
            print('Exception writing config file:', self.configfilename, e)

        self.connection = LineBufferedNonBlockingSocket(self.connection_in_progress, self.config['host'])
        self.connection_in_progress = False
        self.poller = select.poll()
        self.poller.register(self.connection.socket, select.POLLIN)
        self.wwatches = {}
        for name, value in self.watches.items():
            self.wwatches[name] = value # resend watches

        self.values.onconnected()

    def poll(self, timeout=0):
        if not self.connection:
            if self.connection_in_progress:
                events = self.poller_in_progress.poll(0)
                if events:
                    __, flag = events.pop()
                    if not flag & select.POLLOUT:
                        # hung hup
                        self.connection_in_progress.close()
                        self.connection_in_progress = False
                        return

                    self.onconnected()
                return
            else:
                if not self.connect(False):
                    time.sleep(timeout)
                return

        # inform server of any watches we have changed
        if self.wwatches:
            self.connection.write('watch=' + pyjson.dumps(self.wwatches) + '\n')
            #print('watch', watches, self.wwatches, self.watches)
            self.wwatches = {}

        # send any delayed watched values
        self.values.send_watches()

        if self.connection.fileno():
            # flush output
            self.connection.flush()
            try:
                events = self.poller.poll(int(1000 * timeout))
            except Exception as e:
                print('exception polling', e, os.getpid())
                self.disconnect()
                return

            if not events:
                return # no data ready

            __, flag = events.pop()
            if not (flag & select.POLLIN) or (self.connection and not self.connection.recvdata()):
                # other flags indicate disconnect
                self.disconnect() # recv returns 0 means connection closed
                return

        # read incoming data line by line
        while True:
            # t0 = time.monotonic()
            line = self.connection.readline()
            if not line:
                return
            try:
                name, data = line.rstrip().split('=', 1)
                data = str(data).replace("'", '"')
                if name == 'error':
                    print('server error:', data)
                    continue
                value = pyjson.loads(data)
            except ValueError as e:
                print('client value error:', line, e)
                continue

            except Exception as e:
                print('invalid message from server:', line, e)
                raise Exception(e) from e # pylint: disable=broad-exception-raised

            if name in self.values.values: # did this client register this value
                self.values.values[name].set(value)
            else:
                self.received.append((name, value)) # remote value

    # polls at least as long as timeout
    def disconnect(self):
        if self.connection:
            self.connection.close()
        self.connection = False

    def connect(self, sync=False):

        ret = False
        mxt = CLIENT_CONNECT_MAX_DELAY/CLIENT_CONNECT_RETRY_TIME

        if self.connection:
            print('warning, client already has connection')
            self.disconnect()

        while (not ret) and (mxt != 0):
            try:
                host_port = self.config['host'], self.config['port']
                self.connection_in_progress = False
                self.connection_in_progress = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                self.connection_in_progress.settimeout(1) # set to 0 ?
                self.connection_in_progress.connect(host_port)
            except OSError as e:
                import errno
                if e.args[0] is errno.EINPROGRESS:
                    self.poller_in_progress = select.poll()
                    self.poller_in_progress.register(self.connection_in_progress.fileno(), select.POLLOUT)
                    print('warning, waiting for connection in progress')
                    ret = True
                    break
                self.connection_in_progress = False
                if e.args[0] is not errno.ECONNREFUSED:
                    print(f'connect failed to {host_port} : {e}')
                if not sync:
                    break
                else:
                    mxt = mxt-1
                    time.sleep(CLIENT_CONNECT_RETRY_TIME)
                    # print("connect retry")
                    continue
            ret = True
            self.onconnected()
        return ret

    def receive_single(self):
        if self.received:
            ret = self.received[0]
            self.received = self.received[1:]
            return ret
        return False

    def receive(self, timeout=0):
        self.poll(timeout)
        ret = {}
        for msg in self.received:
            name, value = msg
            ret[name] = value
        self.received = []
        return ret

    def send(self, msg):
        if self.connection:
            self.connection.write(msg)

    def set(self, name, value):
        # quote strings
        if isinstance(value, type('')) :
            value = '"' + value + '"'
        elif isinstance(value, bool):
            value = 'true' if value else 'false'
        self.send(name + '=' + str(value) + '\n')

    def watch(self, name, value=True):
        if name in self.watches: # already watching
            if value is False:
                del self.watches[name]
                self.wwatches[name] = value
                return
            elif self.watches[name] is value:
                return # same watch ignore
        elif value is False:
            return # already not watching

        self.watches[name] = value
        self.wwatches[name] = value

    def clear_watches(self):
        for name in self.watches:
            self.wwatches[name] = False
        self.watches = {}

    def register(self, value):
        self.values.register(value)
        value.client = self
        return value

    def get_values(self):
        if self.values.value:
            return self.values.value
        return {}

    def list_values(self, timeout=0):
        self.watch('values')
        t0, dt, ret = time.monotonic(), timeout, self.values.value
        while not ret and dt >= 0:
            self.poll(dt)
            ret = self.values.value
            dt = timeout - (time.monotonic()-t0)
        if self.last_values_list == ret:
            return False
        self.last_values_list = ret
        return ret

    def info(self, name):
        return self.values.value[name]

def cypilot_client_from_args(values, period=True, host=False):
    client = cypilotClient(host)
    if not client.connect(False):
        print('failed to connect to', host)
        exit(1)

    # set any value specified with path=value
    watches = {}
    sets = False
    for arg in values:
        if '=' in arg:
            name, value = arg.split('=', 1)
            try: # make string if it won't load
                pyjson.loads(value)
            except:
                value = pyjson.dumps(value)

            client.send(name + '=' + value + '\n')
            sets = True
            watches[name] = True
        else:
            name = arg
            watches[name] = period

    if sets:
        client.poll(1)

    for name, watch in watches.items():
        client.watch(name, watch)

    return client

# Simple test client for an autopilot server

def client_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    import signal
    def quit_(sign, frame):
        exit(0)
    signal.signal(signal.SIGINT, quit_)

    if '-h' in sys.argv:
        print('usage', sys.argv[0], '[-s host] -i -c -h [NAME[=VALUE]]...')
        print('eg:', sys.argv[0], '-i imu.heading')
        print('   ', sys.argv[0], 'servo.max_slew_speed=10')
        print('-s', 'set the host or ip address')
        print('-i', 'print info about each value type')
        print('-c', 'continuous watch')
        print('-h', 'show this message')
        exit(0)

    args = list(sys.argv)[1:]
    host = 'localhost'
    if '-s' in args:
        i = args.index('-s')
        host = args[i+1]
        args = args[:i+1] + args[i+2:]

    continuous = '-c' in args
    info = '-i' in args

    watches = []
    for arg in args:
        if arg[0] != '-':
            watches.append(arg)

    period = True if continuous else 10
    client = cypilot_client_from_args(watches, period, host)
    
    if client.watches: # retrieve all values
        watches = list(client.watches)
        if info:
            client.list_values(10)
    else:
        watches = list(client.list_values(10))
        if not watches:
            print('failed to retrieve value list!')
            exit(1)
        for name in watches:
            client.watch(name, period)

    if not continuous:
        values = {}
        t0 = time.monotonic()
        while len(values) < len(watches):
            dt = time.monotonic() - t0
            if dt > 10:
                print('timeout retrieving', len(watches) - len(values), 'values')
                for name in watches:
                    if not name in values:
                        print('missing', name)
                break

            client.poll(.1)
            msgs = client.receive()
            for name, value in msgs.items():
                values[name] = value

        names = sorted(values)
        for name in names:
            if info:
                print(name, client.info(name), '=', values[name])
            else:
                maxlen = 76
                result = name + ' = ' + str(values[name])
                if len(result) > maxlen:
                    result = result[:maxlen] + ' ...'
                print(result)
    else:
        while True:
            client.poll(1)
            msg = client.receive_single()
            while msg:
                name, data = msg
                if info:
                    print(name, client.info(name), '=', data)
                else:
                    print(name, '=', data)
                msg = client.receive_single()

if __name__ == '__main__':
    del print # disable cypilot trace
    client_main()
