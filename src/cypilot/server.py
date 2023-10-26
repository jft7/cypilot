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

import select
import socket
import time
import numbers
import os
import heapq

import cypilot.pilot_path # pylint: disable=unused-import
from nonblockingpipe import non_blocking_pipe
from bufferedsocket import LineBufferedNonBlockingSocket
import pyjson

from pilot_path import dprint as print # pylint: disable=redefined-builtin
from pilot_path import PILOT_DIR

DEFAULT_PORT = 23322
MAX_CONNECTIONS = 30
DEFAULT_PERSISTENT_PATH = PILOT_DIR + 'cypilot.conf'
SERVER_PERSISTENT_PERIOD = 60  # store data every 60 seconds

class Watch(object):
    def __init__(self, value, connection, period):
        self.value = value
        self.connections = [connection]
        self.period = period
        self.time = 0


class cypilotValue(object):
    def __init__(self, values, name, info=None, connection=False, msg=False):
        if info is None:
            info = {}
        self.server_values = values
        self.name = name
        self.info = info
        self.lasttime = time.monotonic()
        self.connection = connection
        self.watching = False

        self.awatches = []  # all watches
        self.pwatches = []  # periodic watches limited in period
        self.msg = msg

    def get_msg(self):
        return self.msg

    def set(self, msg, connection):
        t0 = time.monotonic()
        if self.connection == connection:
            # received new value from owner, inform watchers
            self.msg = msg

            if self.awatches:
                watch = self.awatches[0]
                if watch.period == 0:
                    for connection in watch.connections:
                        connection.write(msg)

                for watch in self.pwatches:
                    if t0 >= watch.time:
                        watch.time = t0
                    if watch.connections:  # only insert if there are connections
                        self.server_values.insert_watch(watch)
                self.pwatches = []

        elif self.connection:  # inform owner of change if we are not owner
            if 'writable' in self.info and self.info['writable']:
                __, data = msg.rstrip().split('=', 1)
                pyjson.loads(data)  # validate data
                self.connection.write(msg)
                self.msg = False
            else:  # inform key can not be set arbitrarily
                connection.write('error='+self.name+' is not writable\n')

    def remove_watches(self, connection):
        for watch in self.awatches:
            if connection in watch.connections:
                watch.connections.remove(connection)
                if not watch.connections:
                    self.awatches.remove(watch)
                    self.calculate_watch_period()
                break

    def calculate_watch_period(self):
        # find minimum watch period from all watches
        watching = False
        if 'persistent' in self.info and self.info['persistent']:
            watching = SERVER_PERSISTENT_PERIOD
        for watch in self.awatches:
            if watch.connections == 0:
                print('ERROR no connections in watch')  # should never hit
            if watching is False or watch.period < watching:
                watching = watch.period

        if watching is not self.watching:
            self.watching = watching
            if watching == 0:
                watching = True
            if self.connection:
                self.connection.cwatches[self.name] = watching
                if watching is False:
                    self.msg = None  # server no longer tracking value

    def unwatch(self, connection, recalc):
        for watch in self.awatches:
            if connection in watch.connections:
                watch.connections.remove(connection)
                if not watch.connections:
                    self.awatches.remove(watch)
                    if recalc and watch.period is self.watching:
                        self.calculate_watch_period()
                return True
        return False

    def watch(self, connection, period):
        if connection == self.connection:
            connection.write('error=can not add watch for own value: ' + self.name + '\n')
            return

        if period is False:  # period is False: remove watch
            if not self.unwatch(connection, True):
                # inform client there was no watch
                connection.write('error=cannot remove unknown watch for ' + self.name + '\n')
            return

        if period is True:
            period = 0  # True is same as a period of 0, for continuous watch

        # unwatch by removing
        watching = self.unwatch(connection, False)

        if not watching and self.msg and period >= self.watching:
            connection.write(self.get_msg())  # initial retrieval

        for watch in self.awatches:
            if watch.period == period:  # already watching at this rate, add connection
                watch.connections.append(connection)
                if period > self.watching:  # only need to update if period is relaxed
                    self.calculate_watch_period()
                break
        else:
            # need a new watch for this unique period
            watch = Watch(self, connection, period)
            if period == 0:  # make sure period 0 is always at start of list
                self.awatches.insert(0, watch)
            else:
                self.awatches.append(watch)
            self.calculate_watch_period()
            if period:
                self.pwatches.append(watch)


class ServerWatch(cypilotValue):
    def __init__(self, values):
        super(ServerWatch, self).__init__(values, 'watch')

    def set(self, msg, connection):
        name, data = msg.rstrip().split('=', 1)
        watches = pyjson.loads(data)
        values = self.server_values.values
        for name in watches:
            if not name in values:
                # watching value not yet registered, add it so we can watch it
                values[name] = cypilotValue(self.server_values, name)
            values[name].watch(connection, watches[name])

class ServerValues(cypilotValue):
    def __init__(self, server):
        super(ServerValues, self).__init__(self, 'values')
        self.values = {'values': self, 'watch': ServerWatch(self)}
        self.internal = list(self.values)
        self.pipevalues = {}
        self.msg = 'new'
        self.load()
        self.pqwatches = []  # priority queue of watches
        self.last_send_watches = 0
        self.persistent_timeout = time.monotonic() + SERVER_PERSISTENT_PERIOD

    def get_msg(self):
        if not self.msg or self.msg == 'new':
            msg = 'values={'
            notsingle = False          
            for name,value in self.values.items():
                if name in self.internal:
                    continue
                info = value.info
                if not info:  # placeholders that are watched
                    continue
                if notsingle:
                    msg += ','
                msg += '"' + name + '":' + pyjson.dumps(info)
                notsingle = True
            self.msg = msg + '}\n'
        return self.msg

    def sleep_time(self):
        # sleep until the first value in heap is ready
        if not self.pqwatches:
            return None
        return self.pqwatches[0][0] - time.monotonic()

    def send_watches(self):
        t0 = time.monotonic()
        while self.pqwatches:
            if t0 < self.pqwatches[0][0]:
                break  # no more are ready
            __, __, watch = heapq.heappop(self.pqwatches)
            if not watch.connections:
                continue  # forget this watch
            msg = watch.value.get_msg()
            if msg:
                for connection in watch.connections:
                    connection.write(msg)

            watch.time += watch.period
            if watch.time < t0:
                watch.time = t0
            # put back on value periodic watch list
            watch.value.pwatches.append(watch)

    def insert_watch(self, watch):
        heapq.heappush(self.pqwatches, (watch.time, time.monotonic(), watch))

    def remove(self, connection):
        for __, value in self.values.items():
            if value.connection == connection:
                value.connection = False
                continue
            value.remove_watches(connection)

    def set(self, msg, connection):
        name, data = msg.rstrip().split('=', 1)
        values = pyjson.loads(data)
        for name in values:
            info = values[name]
            if name in self.values:
                value = self.values[name]
                if value.connection:
                    connection.write('error=value already held: ' + name + '\n')
                    continue
                value.connection = connection
                value.info = info  # update info
                value.watching = False
                if value.msg:
                    connection.write(value.get_msg())  # send value
                value.calculate_watch_period()
                self.msg = 'new'
                continue

            value = cypilotValue(self, name, info, connection)
            if 'persistent' in info and info['persistent']:
                value.calculate_watch_period()
                if name in self.persistent_data:
                    v = self.persistent_data[name]
                    if isinstance(v, numbers.Number):
                        v = float(v)  # convert any numeric to floating point
                    value.set(v, connection)  # set persistent value

            self.values[name] = value
            self.msg = 'new'

        msg = False  # inform watching clients of updated values
        for watch in self.awatches:
            for c in watch.connections:
                if c != connection:
                    if not msg:
                        msg = 'values=' + pyjson.dumps(values) + '\n'
                    c.write(msg)

    def handle_request(self, msg, connection):
        name, __ = msg.split('=', 1)
        if not name in self.values:
            connection.write('error=invalid unknown value: ' + name + '\n')
            return
        self.values[name].set(msg, connection)

    def handle_pipe_request(self, msg, connection):
        name, __ = msg.split('=', 1)
        if not name in self.values:
            connection.write('error=invalid unknown value: ' + name + '\n')
            return
        self.values[name].set(msg, connection)

    def load_file(self, f):
        line = f.readline()
        while line:
            name, __ = line.split('=', 1)
            self.persistent_data[name] = line
            if name in self.values:
                value = self.values[name]
                if value.connection:
                    print('does this ever hit?? ,.wqiop pasm2;')
                    value.connection.write(line)

            self.values[name] = cypilotValue(self, name, msg=line)

            line = f.readline()
        f.close()

    def load(self):
        self.persistent_data = {}
        try:
            self.load_file(open(DEFAULT_PERSISTENT_PATH))
        except Exception as el:
            try:
                print(f'load persistent data failed ({el}), attempt to load backup data')
                self.load_file(open(DEFAULT_PERSISTENT_PATH + '.bak'))
                return
            except Exception as eb:
                print(f'backup data failed as well ({eb})')
            return

        # backup persistent_data if it loaded with success
        file = open(DEFAULT_PERSISTENT_PATH + '.bak', 'w')
        for data in self.persistent_data.values():
            file.write(data)
        file.close()

    def store(self):
        self.persistent_timeout = time.monotonic() + SERVER_PERSISTENT_PERIOD
        need_store = False
        for name, value in self.values.items():
            if value.msg is False or 'persistent' not in value.info or not value.info['persistent']:
                continue
            if not name in self.persistent_data or value.msg != self.persistent_data[name]:
                self.persistent_data[name] = value.msg
                need_store = True

        if not need_store:
            return
        name = ''
        try:
            file = open(DEFAULT_PERSISTENT_PATH, 'w')
            for name, data in self.persistent_data.items():
                file.write(data)
            file.close()
        except Exception as e:
            print('failed to write', name, DEFAULT_PERSISTENT_PATH, e)


class cypilotServer(object):
    def __init__(self):
        self.pipes = []
        self.initialized = False
        self.process = False
        self.server_socket = None
        self.port = None
        self.sockets = []
        self.fd_to_pipe = {}
        self.fd_to_connection = {}
        self.values = None
        self.poller = None

    def pipe(self):
        if self.initialized:
            print('direct pipe clients must be created before the server is run')
            exit(0)

        pipe0, pipe1 = non_blocking_pipe('cypilotServer pipe' + str(len(self.pipes)))
        self.pipes.append(pipe1)
        return pipe0

    def run(self):
        print('cypilotServer process', os.getpid())
        # if server is in a separate process
        self.init()
        while True:
            dt = self.values.sleep_time()
            t0 = time.monotonic()
            self.poll(dt)
            pt = time.monotonic() - t0
            #print('times', pt, dt)
            st = .04 - pt
            if st > 0:
                time.sleep(st)

    def init_process(self):
        import multiprocessing
        self.process = multiprocessing.Process(target=self.run, daemon=True, name='cypilotServer')
        self.process.start()

    def init(self):
        self.process = 'main process'
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setblocking(0)
        self.server_socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.port = DEFAULT_PORT
        self.sockets = []
        self.fd_to_pipe = {}

        self.values = ServerValues(self)

        while True:
            try:
                self.server_socket.bind(('0.0.0.0', self.port))
                print('cypilot_server: bind successfull')
                break
            except:
                print('cypilot_server: bind failed; already running a server?')
                time.sleep(3)

        # listen for tcp sockets
        self.server_socket.listen(5)
        fd = self.server_socket.fileno()
        self.fd_to_connection = {fd: self.server_socket}
        self.poller = select.poll()
        self.poller.register(fd, select.POLLIN)

        # setup direct pipe clients
        print('server setup has', len(self.pipes), 'pipes')
        for pipe in self.pipes:
            fd = pipe.fileno()
            self.poller.register(fd, select.POLLIN)
            self.fd_to_connection[fd] = pipe
            self.fd_to_pipe[fd] = pipe
            # server always watches client values
            pipe.cwatches = {'values': True}

        self.initialized = True

    def __del__(self):
        if not self.initialized:
            return
        self.values.store()
        self.server_socket.close()
        for socket_ in self.sockets:
            socket_.close()
        for pipe in self.pipes:
            pipe.close()

    def remove_socket(self, socket_):
        print('server, remove socket', socket_.address)
        self.sockets.remove(socket_)

        found = False
        for fd, sk in self.fd_to_connection.items():
            if socket_ == sk:
                del sk
                self.poller.unregister(fd)
                found = True
                break

        if not found:
            print('server error: socket not found in fd_to_connection')

        socket_.close()
        self.values.remove(socket_)

    def poll(self, timeout=0):
        # server is in subprocess
        if self.process != 'main process':
            if not self.process:
                self.init_process()
            return

        t0 = time.monotonic()
        if t0 >= self.values.persistent_timeout:
            self.values.store()
            dt = time.monotonic() - t0
            if dt > .1:
                print('persistent store took too long!', time.monotonic() - t0)
                return

        if timeout:
            timeout *= 1000  # milliseconds

        timeout = .1
        events = self.poller.poll(timeout)
        while events:
            event = events.pop()
            fd, flag = event

            connection = self.fd_to_connection[fd]
            if connection == self.server_socket:
                connection, address = connection.accept()
                if len(self.sockets) == MAX_CONNECTIONS:
                    print('cypilot server: max connections reached!!!',
                          len(self.sockets))
                    self.remove_socket(self.sockets[0])  # dump first socket??
                socket_ = LineBufferedNonBlockingSocket(connection, address)
                print('server add socket', socket_.address)

                self.sockets.append(socket_)
                fd = socket_.fileno()
                # server always watches client values
                socket_.cwatches = {'values': True}

                self.fd_to_connection[fd] = socket_
                self.poller.register(fd, select.POLLIN)
            elif flag & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                if not connection in self.sockets:
                    print('internal pipe closed, server exiting')
                    exit(0)
                self.remove_socket(connection)
            elif flag & select.POLLIN:
                if fd in self.fd_to_pipe:
                    if not connection.recvdata():
                        continue
                    line = connection.readline()  # shortcut since poll indicates data is ready
                    while line:
                        self.values.handle_pipe_request(line, connection)
                        line = connection.readline()

                    continue
                if not connection.recvdata():
                    self.remove_socket(connection)
                    continue
                while True:
                    line = connection.readline()
                    if not line:
                        break
                    try:
                        self.values.handle_request(line, connection)
                    except Exception as e:
                        connection.write('error=invalid request: ' + line)
                        try:
                            print('invalid request from connection', e, line)
                        except Exception as e2:
                            print('invalid request has malformed string', e, e2)

        # send periodic watches
        self.values.send_watches()

        # send watches
        for connection in self.sockets + self.pipes:
            if connection.cwatches:
                connection.write(
                    'watch=' + pyjson.dumps(connection.cwatches) + '\n')
                connection.cwatches = {}

        # flush all sockets
        for socket_ in self.sockets:
            socket_.flush()
        while True:
            for socket_ in self.sockets:
                if not socket_.socket:
                    print('server socket closed from flush!!')
                    self.remove_socket(socket_)
                    break
            else:
                break

        for pipe in self.pipes:
            pipe.flush()

def server_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    server = cypilotServer()
    from client import cypilotClient
    from pilot_values import Value, Property
    client1 = cypilotClient(server)  # direct pipe to server
    clock = client1.register(Value('clock', 0))
    # test1 = client1.register(Property('test', 1234))
    print('client values1', client1.values)
    client1.watch('test2', 10)

    client2 = cypilotClient('localhost')  # tcp socket connection
    test2 = client2.register(Property('test2', [1, 2, 3, 4], persistent=True))
    client2.watch('clock', 1)

    client3 = cypilotClient('localhost')
    client3.watch('clock', 3)

    def print_msgs(name, msgs):
        for msg in msgs:
            print(name, msg, msgs[msg])

    print('cypilot demo server')
    t00 = t0 = time.monotonic()
    while True:
        server.poll()
        print_msgs('client1', client1.receive())
        print_msgs('client2', client2.receive())
        print_msgs('client3', client3.receive())

        time.sleep(.04)
        dt = time.monotonic() - t0
        if dt > .01:
            clock.set(time.monotonic()-t00)
            t0 += .01
            test2.set(123)

if __name__ == '__main__':
    server_main()
