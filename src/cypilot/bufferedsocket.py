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
import select
import os

import cypilot.pilot_path

from pilot_path import dprint as print # pylint: disable=redefined-builtin

from linebuffer import linebuffer

class LineBufferedNonBlockingSocket:
    def __init__(self, connection, address):
        connection.setblocking(0)
        self.b = linebuffer.LineBuffer(connection.fileno())

        self.socket = connection
        self.address = address
        self.out_buffer = ''

        self.pollout = select.poll()
        self.pollout.register(connection, select.POLLOUT)
        self.sendfail_msg = 1
        self.sendfail_cnt = 0

    def fileno(self):
        if self.socket:
            return self.socket.fileno()
        return 0

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = False

    def recvdata(self):
        return self.b.recv()

    def readline(self):
        return self.b.line()

    def write(self, data):
        self.out_buffer += data
        if len(self.out_buffer) > 65536:
            print('overflow in cypilot socket', self.address, len(self.out_buffer), os.getpid())
            self.out_buffer = ''
            self.close()

    def flush(self):
        if not self.out_buffer:
            return

        try:
            if not self.pollout.poll(0):
                if self.sendfail_cnt >= self.sendfail_msg:
                    print('cypilot socket failed to send to', self.address, self.sendfail_cnt)
                    self.sendfail_msg *= 10
                self.sendfail_cnt += 1

                if self.sendfail_cnt > 100:
                    self.socket.close()
                    return

            t0 = time.monotonic()
            count = self.socket.send(self.out_buffer.encode())
            t1 = time.monotonic()

            if t1-t0 > .03:
                print('socket send took too long!?!?', self.address, t1-t0, len(self.out_buffer))
            if count < 0:
                print('socket send error', self.address, count)
                self.socket.close()
            self.out_buffer = self.out_buffer[count:]
        except Exception as e:
            print('cypilot socket exception', self.address, e, os.getpid(), self.socket)
            self.close()

def bufferedsocket_main():
    print('Version:', cypilot.pilot_path.STRVERSION)

if __name__ == '__main__':
    bufferedsocket_main()
