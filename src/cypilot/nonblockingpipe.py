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
import time
import os

import cypilot.pilot_path
import pyjson
from linebuffer import linebuffer

from pilot_path import dprint as print # pylint: disable=redefined-builtin

class PipeNonBlockingPipeEnd(object):
    def __init__(self, r, w, name, recvfailok, sendfailok):
        self.name = name
        self.r, self.w = r, w
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        self.b = linebuffer.LineBuffer(r)
        self.pollout = select.poll()
        self.pollout.register(self.w, select.POLLOUT)
        self.recvfailok = recvfailok
        self.sendfailok = sendfailok

    def fileno(self):
        return self.r

    def close(self):
        os.close(self.r)
        os.close(self.w)

    def recvdata(self):
        return self.b.recv()

    def readline(self):
        return self.b.line()

    def recv(self, timeout=0):
        self.recvdata()
        line = self.b.line()
        if not line:
            return
        try:
            d = pyjson.loads(line.rstrip())
            return d
        except Exception as e:
            print('failed to decode data socket!', self.name, e)
            print('line', line)
        return False

    def flush(self):
        pass

    def write(self, data):
        if not self.pollout.poll(0):
            if not self.sendfailok:
                print('failed write', self.name)
        t0 = time.time()
        os.write(self.w, data.encode())
        t1 = time.time()
        if t1-t0 > .024:
            print('too long write pipe', t1-t0, self.name, len(data))

    def send(self, value, block=False):
        if not self.pollout.poll(0):
            if not self.sendfailok:
                print('failed send', self.name)
        t0 = time.time()
        try:
            data = pyjson.dumps(value) + '\n'
            os.write(self.w, data.encode())
            t1 = time.time()
            self.flush()
            t2 = time.time()
            if t2-t0 > .024:
                print('too long send nonblocking pipe',
                      t1-t0, t2-t1, self.name, len(data))
            return True
        except Exception as e:
            if not self.sendfailok:
                print('failed to encode data pipe!', self.name, e)
            return False

def non_blocking_pipe(name, recvfailok=True, sendfailok=False):
    r0, w0 = os.pipe()
    r1, w1 = os.pipe()
    return PipeNonBlockingPipeEnd(r0, w1, name+'[0]', recvfailok, sendfailok), PipeNonBlockingPipeEnd(r1, w0, name+'[1]', recvfailok, sendfailok)

def nonblockingpipe_main():
    print('Version:', cypilot.pilot_path.STRVERSION)

if __name__ == '__main__':
    nonblockingpipe_main()
