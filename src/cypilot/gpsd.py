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

import os
import multiprocessing
import time
import socket
import select
import serial

import cypilot.pilot_path
from nonblockingpipe import non_blocking_pipe
from bufferedsocket import LineBufferedNonBlockingSocket
import serials
# import serialprobe
import pyjson

from pilot_path import dprint as print # pylint: disable=redefined-builtin

# Sent messages
UBX_RATE_1HZ = b'\xB5\x62\x06\x08\x06\x00\xE8\x03\x01\x00\x01\x00\x01\x39'
UBX_RATE_5HZ = b'\xB5\x62\x06\x08\x06\x00\xC8\x00\x01\x00\x01\x00\xDE\x6A'
UBX_RATE_10HZ = b'\xB5\x62\x06\x08\x06\x00\x64\x00\x01\x00\x01\x00\x7A\x12'
UBX_PRT_ASYN0 = b'\xB5\x62\x06\x00\x14\x00\x01\x00\x00\x00\xC0\x08\x00\x00\x80\x25\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x88\x6B' # disable serial port
UBX_PRT_USB0 = b'\xB5\x62\x06\x00\x14\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\x00\x03\x00\x00\x00\x00\x00\x23\xAE' # disable NMEA on USB
UBX_PRT_USB1 = b'\xB5\x62\x06\x00\x14\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\x00\x03\x00\x00\x00\x00\x00\x23\xAE' # enable UBX and NMEA on USB

# Received messages
UBX_ACK_ACK = b'\xB5\x62\x05\x01\x02\x00'

def ubx_send(ser, cmd, ack=False):
    ser.flushInput()
    ser.write(cmd)
    if ack:
        answer = ser.read(256)
        if UBX_ACK_ACK in answer:
            return True
    return False

def gps_json_loads(line):
    try:
        return pyjson.loads(line)
    except:
        pass
    act = '"activated"'
    i = line.index(act)
    j = line.index('Z', i)
    line = line[:i]+act+':"'+line[i+12:j+1]+'"'+line[j+1:]
    return pyjson.loads(line)

def gpsd_restart():
    list_serials = serials.list_serials("gps")
    if list_serials:
        device = list_serials[0].path
        baud = list_serials[0].baudrate
        os.system('sudo killall -9 gpsd')
        os.system('sudo systemctl stop gpsd.socket')
        try:
            ser = serial.Serial(device, baud, timeout=0.5)
            ubx_send(ser, UBX_PRT_USB0, True)
            time.sleep(.5)
            if ubx_send(ser, UBX_PRT_ASYN0, True):
                print("GPS Async port disabled")
            if ubx_send(ser, UBX_RATE_5HZ, True):
                print("GPS Rate changed to 5Hz")
            if ubx_send(ser, UBX_PRT_USB1, True):
                print("GPS USB port enabled for UBX and NMEA")
            print('gpsd: restart device ', device)
            os.system('sudo gpsd ' + device + ' -F /var/run/gpsd.sock')
        except:
            print('gpsd: unable to restart device ', device)

class gpsProcess(multiprocessing.Process):
    def __init__(self):
        # split pipe ends
        self.pipe, pipe = non_blocking_pipe('gps_pipe')
        super(gpsProcess, self).__init__(target=self.gps_process, args=(pipe,), daemon=True)
        self.devices = []
        self.gpsd_socket = None
        self.gpsconnecttime = 0
        self.poller = None
        gpsd_restart()

    def connect(self):
        time.sleep(2)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('127.0.0.1', 2947))
            self.poller.register(sock, select.POLLIN)
            sock.settimeout(0)
            sock.send('?WATCH={"enable":true,"json":true};'.encode())
            self.gpsd_socket = LineBufferedNonBlockingSocket(sock, 'gpsd')
            self.gpsconnecttime = time.monotonic()
            self.devices = []
            print('gpsd connected')
        # except socket.error:
        except ConnectionRefusedError:
            print('gpsd failed to connect')
            self.gpsd_socket = False
            time.sleep(30)
        except Exception as e:
            self.gpsd_socket = False
            print('exception connecting to gps', e)
            time.sleep(60)

    def disconnect(self):
        print('gpsd disconnected')
        self.poller.unregister(self.gpsd_socket.socket)
        self.gpsd_socket.close()
        self.gpsd_socket = False
        self.devices = []

    def read_pipe(self, pipe):
        while True:
            device = pipe.recv()
            if not device:
                break
            if self.gpsd_socket and not self.devices:
                # gpsd: no devices
                list_serials = serials.list_serials("gps")
                if list_serials:
                    device = list_serials[0].path
                if os.system('timeout -s KILL 30 gpsctl ' + device + ' 2> /dev/null'):
                    gpsd_restart()
                else:
                    print('gpsd probe OK')
                self.devices = [device]
            # always reply with devices when asked to probe
            print('GPSD send devices', self.devices)
            pipe.send({'devices': self.devices})

    def parse_gpsd(self, msg, pipe):
        if not 'class' in msg:
            return False  # unrecognized

        ret = False
        cls = msg['class']
        if cls == 'DEVICES':
            self.devices = []
            for dev in msg['devices']:
                self.devices.append(dev['path'])
            ret = True
        elif cls == 'DEVICE':
            device = msg['path']
            if msg['activated']:
                if not device in self.devices:
                    self.devices.append(device)
                    ret = True
            else:
                print('gpsd deactivated', device, self.devices)
                if device in self.devices:
                    self.devices.remove(device)
                    ret = True
        elif cls == 'TPV':
            if msg['mode'] == 3:
                fix = {'speed': 0}
                for key in ['track', 'speed', 'lat', 'lon', 'device']:
                    if key in msg:
                        fix[key] = msg[key]
                fix['speed'] *= 1.944  # knots
                device = msg['device']
                if not device in self.devices:
                    self.devices.append(device)
                    ret = True
                pipe.send(fix, False)
        return ret

    def gps_process(self, pipe):
        print('gps process', os.getpid())
        self.gpsd_socket = False
        self.poller = select.poll()
        while True:
            self.read_pipe(pipe)
            if not self.gpsd_socket:
                self.connect()
                continue

            events = self.poller.poll(1000)
            if not events:
                if self.gpsconnecttime and time.monotonic() - self.gpsconnecttime > 10:
                    print('gpsd timeout from lack of data')
                    self.disconnect()
                continue

            self.gpsconnecttime = False
            __, flag = events.pop()
            if flag & select.POLLIN and self.gpsd_socket.recvdata():
                while True:
                    line = self.gpsd_socket.readline()
                    if not line:
                        break
                    try:
                        if self.parse_gpsd(gps_json_loads(line), pipe):
                            pipe.send({'devices': self.devices})
                    except Exception as e:
                        print('gpsd received invalid message', line, e)
            else:  # gpsd connection lost
                self.disconnect()
                pipe.send({'devices': self.devices})


class gpsd(object):
    def __init__(self, sensors):
        self.sensors = sensors
        self.devices = False  # list of devices used by gpsd, or False if not connected

        self.process = gpsProcess()
        self.process.start()

        read_only = select.POLLIN | select.POLLHUP | select.POLLERR
        self.poller = select.poll()
        self.poller.register(self.process.pipe.fileno(), read_only)

    def read(self):
        data = self.process.pipe.recv()
        while data:
            if 'devices' in data:
                print('GPSD devices', data['devices'])
                if self.devices and not data['devices']:
                    self.sensors.lostgpsd()
                self.devices = data['devices']
            else:
                self.sensors.write('gps', data, 'gpsd')
            data = self.process.pipe.recv()

    def poll(self):
        while True:
            events = self.poller.poll(0)
            if not events:
                break
            while events:
                event = events.pop()
                __, flag = event
                if flag == select.POLLIN:
                    self.read()
        return


def gps_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    list_serials = serials.list_serials("gps")
    if list_serials:
        device = list_serials[0].path
        print('Using GPS Device : ', device)

if __name__ == '__main__':
    gps_main()
