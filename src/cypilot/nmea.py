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


# A separate process listens on port 20220 for tcp connections
# any NMEA and AIS data received can be relayed to all clients
#
# NMEA sentences are translated to be used for sensor inputs such as:
#  wind, gps, rudder
#
# inputs NMEA: wind, rudder, ...
# outputs NMEA: pitch, roll, and heading messages, wind, rudder

import os
import select
import time
import datetime
import socket
import multiprocessing
import fcntl
import serial

import cypilot.pilot_path
from client import cypilotClient
from pilot_values import Property
from nonblockingpipe import non_blocking_pipe
from bufferedsocket import LineBufferedNonBlockingSocket
from sensors import init_source_priority
import serials
from linebuffer import linebuffer

from pilot_path import dprint as print # pylint: disable=redefined-builtin

DEFAULT_PORT = 20220

# Talker Id used for internally generated NMEA messages :
#   - AG = Autopilot General for : IMU, Wind, Rudder
#   - GP = GPS for Global Positioning System
# We made these choice to ensur good compatibility with connected devices.
# Example: some VHF ASN can only receive GP messages for GPS positioning (Cobra Marine)
TALKER_IMU = 'AG'
TALKER_GPS = 'GP'
TALKER_WIND = 'AG'
TALKER_RUDDER = 'AG'

NMEA_TXPERIOD_IMU = 0.5
NMEA_TXPERIOD_GPS = 1.0
NMEA_TXPERIOD_WIND = 0.25
NMEA_TXPERIOD_RUDDER = 0.25

TIOCEXCL = 0x540C
SOURCE_PRIORITY = {}

def check_nmea_cksum(line):
    cksplit = line.split('*')
    try:
        return linebuffer.nmea_cksum(cksplit[0][1:]) == int(cksplit[1], 16)
    except:
        return False

def add_nmea_cksum(msg):
    msg = f"${msg}*{linebuffer.nmea_cksum(msg):02X}"
    return msg

def parse_nmea_gps(line):

    def degrees_minutes_to_decimal(n):
        n /= 100
        degrees = int(n)
        minutes = n - degrees
        return degrees + minutes*10/6

    if line[3:6] != 'RMC':
        return False

    try:
        data = line[7:len(line)-3].split(',')
        if data[1] == 'V':
            return False
        gps = {}

        timestamp = float(data[0]) if data[0] else 0

        lat = degrees_minutes_to_decimal(float(data[2]))
        if data[3] == 'S':
            lat = -lat

        lon = degrees_minutes_to_decimal(float(data[4]))
        if data[5] == 'W':
            lon = -lon

        speed = float(data[6]) if data[6] else 0
        gps = {'timestamp': timestamp, 'speed': speed, 'lat': lat, 'lon': lon}
        if data[7]:
            gps['track'] = float(data[7])

    except Exception as e:
        print('nmea failed to parse gps', line, e)
        return False

    return 'gps', gps


'''
   ** MWV - Wind Speed and Angle
   **
   **
   **
   ** $--MWV,x.x,a,x.x,a*hh<CR><LF>**
   ** Field Number:
   **  1) Wind Angle, 0 to 360 degrees
   **  2) Reference, R = Relative, T = True
   **  3) Wind Speed
   **  4) Wind Speed Units, K/M/N
   **  5) Status, A = Data Valid
   **  6) Checksum
'''


def parse_nmea_wind(line):
    if line[3:6] == 'VWR':
        data = line.split(',')
        msg = {}

        try:
            angle = float(data[1])
        except:
            return False  # require direction
        if data[2] == "L" and angle > 0:
            angle = 360.0 - angle
        msg['direction'] = angle

        try:
            speed = float(data[3])
            msg['speed'] = speed
        except Exception as e:
            print('nmea failed to parse wind', line, e)
            return False

        return 'wind', msg

    if line[3:6] == 'MWV':
        data = line.split(',')
        msg = {}

        try:
            msg['direction'] = float(data[1])
        except:
            return False  # require direction

        try:
            speed = float(data[3])
            speedunit = data[4]
            if speedunit == 'K':  # km/h
                speed *= .53995
            elif speedunit == 'M':  # m/s
                speed *= 1.94384
            msg['speed'] = speed
        except Exception as e:
            print('nmea failed to parse wind', line, e)
            return False

        return 'wind', msg

    return False

def parse_nmea_rudder(line):
    if line[3:6] != 'RSA':
        return False

    data = line.split(',')
    try:
        angle = float(data[1])
    except:
        angle = False

    return 'rudder', {'angle': angle}


def parse_nmea_apb(line):
    # also allow ap commands (should we allow via serial too??)
    '''
   ** APB - Autopilot Sentence "B"
   **                                         13    15
   **        1 2 3   4 5 6 7 8   9 10   11  12|   14|
   **        | | |   | | | | |   | |    |   | |   | |
   ** $--APB,A,A,x.x,a,N,A,A,x.x,a,c--c,x.x,a,x.x,a*hh<CR><LF>
   **
   **  1) Status
   **     V = LORAN-C Blink or SNR warning
   **     V = general warning flag or other navigation systems when a reliable
   **         fix is not available
   **  2) Status
   **     V = Loran-C Cycle Lock warning flag
   **     A = OK or not used
   **  3) Cross Track Error Magnitude
   **  4) Direction to steer, L or R
   **  5) Cross Track Units, N = Nautical Miles
   **  6) Status
   **     A = Arrival Circle Entered
   **  7) Status
   **     A = Perpendicular passed at waypoint
   **  8) Bearing origin to destination
   **  9) M = Magnetic, T = True
   ** 10) Destination Waypoint ID
   ** 11) Bearing, present position to Destination
   ** 12) M = Magnetic, T = True
   ** 13) Heading to steer to destination waypoint
   ** 14) M = Magnetic, T = True
   ** 15) Checksum
        '''
    if line[3:6] != 'APB':
        return False
    try:
        data = line[7:len(line)-3].split(',')
        isgp = line[1:3]
        if isgp != 'GP':
            mode = 'compass' if data[13] == 'M' else 'gps'
        else:
            mode = 'gps'
        track = float(data[12])
        xte = float(data[2])
        xte = min(xte, 0.15)  # maximum 0.15 miles
        if data[3] == 'L':
            xte = -xte
        return 'apb', {'mode': mode, 'track':  track, 'xte': xte, 'isgp': isgp}
    except Exception as e:
        print('exception parsing apb', e, line)
        return False

def parse_nmea_sow(line):
    '''
   ** VHW - Water speed and heading
   **
   **        1   2 3   4 5   6 7   8 9
   **        |   | |   | |   | |   | |
   ** $--VHW,x.x,T,x.x,M,x.x,N,x.x,K*hh<CR><LF>
   **
   ** Field Number:
   **  1) Degress True
   **  2) T = True
   **  3) Degrees Magnetic
   **  4) M = Magnetic
   **  5) Knots (speed of vessel relative to the water)
   **  6) N = Knots
   **  7) Kilometers (speed of vessel relative to the water)
   **  8) K = Kilometers
   **  9) Checksum
   ** LWY - Nautical Leeway Angle Measurement
   **
   **        1 2   3
   **        | |   |
   ** $--LWY,A,x.x*hh<CR><LF>
   **
   ** Field Number:
   **  1) A=Valid V=not valid
   **  2) Nautical Leeway Angle in degrees (positive indicates slippage to starboard)
   **  3) Checksum
    '''
    if line[3:6] == 'VHW':
        try:
            data = line.split(',')
            speed = float(data[5])
            return 'sow', {'speed': speed}
        except Exception as e:
            print('exception parsing vhw', e, line)

    elif line[3:6] == 'LWY':
        try:
            data = line.split(',')
            if data[1] == 'A':
                leeway = float(data[2])
                return 'sow', {'leeway': leeway}
        except Exception as e:
            print('exception parsing vhw', e, line)

    return False

NMEA_PARSERS = {'gps': parse_nmea_gps, 'wind': parse_nmea_wind,
                'rudder': parse_nmea_rudder, 'apb': parse_nmea_apb,
                'sow' : parse_nmea_sow }


class NMEASerialDevice(object):
    def __init__(self, path):
        self.device = serial.Serial(*path)
        self.path = path
        self.device.timeout = 0  # nonblocking
        fcntl.ioctl(self.device.fileno(), TIOCEXCL)
        self.b = linebuffer.LineBuffer(self.device.fileno())

    def readline(self):
        return self.b.readline_nmea()

    def close(self):
        self.device.close()
        
    def write(self,msg):
        self.device.write(msg.encode())

NMEASOCKETUID = 0

class NMEASocket(LineBufferedNonBlockingSocket):
    def __init__(self, connection, address):
        super(NMEASocket, self).__init__(connection, address)

        global NMEASOCKETUID
        self.uid = NMEASOCKETUID
        NMEASOCKETUID += 1
        self.nmea_client = None

    def readline(self):
        return self.b.readline_nmea()

class Nmea(object):
    def __init__(self, sensors):
        global SOURCE_PRIORITY
        SOURCE_PRIORITY = init_source_priority()
        self.client = sensors.client

        self.sensors = sensors
        self.nmea_bridge = nmeaBridge(self.client.server)
        self.process = self.nmea_bridge.process
        self.pipe = self.nmea_bridge.pipe_out
        self.sockets = False

        self.poller = select.poll()
        self.process_fd = self.pipe.fileno()
        self.poller.register(self.process_fd, select.POLLIN)

        self.device_fd = {}

        self.nmea_times = {'wind':0, 'rudder':0, 'imu':0, 'gps':0, 'sow':0}

        self.list_serials = serials.list_serials("nmea")
        self.devices = []
        self.devices_input_filter = {}
        self.devices_output_msgs = {}
        self.mdevices = {}

        for serial_device in self.list_serials:
            try:
                sdevice = NMEASerialDevice( (serial_device.path, serial_device.baudrate) )
            except Exception as e:
                print('failed to open', serial_device.path, 'for nmea data', e)
                continue
            self.devices.append(sdevice)
            fd = sdevice.device.fileno()
            self.device_fd[fd] = sdevice
            self.poller.register(fd, select.POLLIN)
            self.devices_input_filter[sdevice] = serial_device.input_filter
            self.devices_output_msgs[sdevice] = serial_device.output_msgs
            for nmea_msg in serial_device.output_msgs:
                if not nmea_msg in self.mdevices:
                    self.mdevices[nmea_msg] = [sdevice]
                else:
                    self.mdevices[nmea_msg].append(sdevice)

        self.start_time = time.monotonic()

    def __del__(self):
        #print('terminate nmea process')
        # self.process.terminate()
        pass

    def read_process_pipe(self):
        while True:
            msgs = self.pipe.recv()
            if not msgs:
                return
            if isinstance(msgs, str):
                if msgs == 'sockets':
                    self.sockets = True
                elif msgs == 'nosockets':
                    self.sockets = False
                elif msgs[:10] == 'lostsocket':
                    self.sensors.lostdevice(msgs[4:])
                else:
                    print('unhandled nmea pipe string', msgs)
            else:
                for name in msgs:
                    self.sensors.write(name, msgs[name], 'tcp')

    def read_serial_device(self, device, serial_msgs):
        t = time.monotonic()
        line = device.readline()
        if not line:
            return

        # AIS
        if line[0] == '!' :
            if self.sockets:
                self.pipe.send(line)
            return
        
        # NMEA
        nmea_name = line[:6]
        filter_msgs = self.devices_input_filter[device]
        if (filter_msgs != [] and nmea_name[3:] in filter_msgs) :
            return
        
        if self.sockets:
            dt = t - self.nmea_times[nmea_name] if nmea_name in self.nmea_times else 1
            if dt > .25:
                self.pipe.send(line)
                self.nmea_times[nmea_name] = t

        parsers = []

        # only process if
        # 1) current source is lower priority
        # 2) we do not have a source yet
        # 3) this the correct device for this data
        for name, parser in NMEA_PARSERS.items():
            name_device = self.sensors.sensors[name].device
            current_source = self.sensors.sensors[name].source.value
            if SOURCE_PRIORITY[current_source] > SOURCE_PRIORITY['serial'] or not name_device or name_device[2:] == device.path[0]:
                parsers.append(parser)

        # parse the nmea line, and update serial messages
        for parser in parsers:
            result = parser(line)
            if result:
                name, msg = result
                if name:
                    msg['device'] = line[1:3]+device.path[0]
                    serial_msgs[name] = msg
                break

    def poll(self):

        # 1- read nmea serial messages
        t1 = time.monotonic()
        serial_msgs = {}
        while True:
            events = self.poller.poll(0)
            if not events:
                break
            while events:
                event = events.pop()
                fd, flag = event
                if fd == self.process_fd:
                    if flag != select.POLLIN:
                        print('nmea got flag for process pipe:', flag)
                    else:
                        self.read_process_pipe()
                elif flag == select.POLLIN:
                    self.read_serial_device(self.device_fd[fd], serial_msgs)

        # 2- write messages to sensors
        t2 = time.monotonic()
        for name, msg in serial_msgs.items():
            self.sensors.write(name, msg, 'serial')

        # 3- encode IMU/GPS/WIND/RUDDER data and send messages to TCP and optionaly to serial ports
        t3 = time.monotonic()
        nt = time.monotonic()

        # Send IMU messages
        dt = nt - self.nmea_times['imu']
        values = self.client.values.values
        if dt > NMEA_TXPERIOD_IMU:
            # pitch and roll
            if self.sockets or 'XDR' in self.mdevices and 'imu.pitch' in values:
                pitch = values['imu.pitch'].value
                roll = values['imu.roll'].value
                if pitch and roll:
                    self.send_nmea((TALKER_IMU + 'XDR,A,%.3f,D,PTCH') % pitch)
                    self.send_nmea((TALKER_IMU + 'XDR,A,%.3f,D,ROLL') % roll)
            # heading
            if self.sockets or 'HDM' in self.mdevices and 'imu.heading' in values:
                heading = values['imu.heading'].value
                if heading:
                    self.send_nmea((TALKER_IMU + 'HDM,%.3f,M') % heading)
            self.nmea_times['imu'] = nt

        # Send GPS to sockets
        dt = nt - self.nmea_times['gps']
        if dt > NMEA_TXPERIOD_GPS:
            if self.sockets or 'RMC' in self.mdevices:
                lat = self.sensors.gps.lat.value
                lon = self.sensors.gps.lon.value
                speed = self.sensors.gps.speed.value
                track = self.sensors.gps.track.value
                if lat and lon:
                    today = datetime.datetime.today()
                    utc = datetime.datetime.utcnow().strftime("%H%M%S.%f")[:-4]
                    lat_min = (abs(lat) - abs(int(lat))) * 60
                    lon_min = (abs(lon) - abs(int(lon))) * 60
                    self.send_nmea((TALKER_GPS + 'RMC,%s,A,%02d%07.4f,%c,%03d%07.4f,%c,%.2f,%.2f,%02d%02d%02d,,,A') % ( \
                        utc, \
                        abs(lat), lat_min, 'N' if lat >= 0 else 'S', \
                        abs(lon), lon_min, 'E' if lat >= 0 else 'W', \
                        speed, (track if track > 0 else 360 + track), \
                        today.day, today.month, today.year % 100))
                    self.send_nmea((TALKER_GPS + 'GLL,%02d%07.4f,%c,%03d%07.4f,%c,%s,A') % ( \
                        abs(lat), lat_min, 'N' if lat >= 0 else 'S', \
                        abs(lon), lon_min, 'E' if lat >= 0 else 'W', \
                        utc ))
            self.nmea_times['gps'] = nt

        # Send wind messages
        dt = nt - self.nmea_times['wind']
        if dt > NMEA_TXPERIOD_WIND:
            if self.sockets or 'MWV' in self.mdevices:
                wind = self.sensors.wind
                direction = wind.direction.value
                speed = wind.speed.value
                if direction and speed:
                    self.send_nmea((TALKER_WIND + 'MWV,%.3f,R,%.3f,N,A') % (direction, speed))
            self.nmea_times['wind'] = nt

        # Send rudder messages
        dt = nt - self.nmea_times['rudder']
        if dt > NMEA_TXPERIOD_RUDDER:
            if self.sockets or 'RSA' in self.mdevices:
                angle = self.sensors.rudder.angle.value
                if angle:
                    self.send_nmea((TALKER_RUDDER + 'RSA,%.3f,A,,') % angle)
            self.nmea_times['rudder'] = nt

        # 4- check nmea poll time
        t4 = time.monotonic()
        if t4 - t1 > .1 and self.start_time - t1 > 1:
            print('nmea poll times', self.start_time-t1, t2-t1, t3-t2, t4-t3)

    def send_nmea(self, msg):
        # Complete message with header and checksum
        msg = f"${msg}*{linebuffer.nmea_cksum(msg):02X}"

        # Send messages to serial ports
        mtype = msg[3:6]
        if mtype in self.mdevices:
            for sdevice in self.mdevices[mtype]:
                try:
                    sdevice.write(msg + '\r\n')
                except Exception as e:
                    print('failed to send on serial port nmea message', mtype, e)
        # Send messages to TCP
        if self.sockets:
            self.pipe.send(msg)

class nmeaBridge(object):
    def __init__(self, server):
        self.client = cypilotClient(server)
        self.pipe, self.pipe_out = non_blocking_pipe('nmea pipe')
        self.process = multiprocessing.Process(target=self.nmea_process, daemon=True, name='nmeaBridge')
        self.process.start()
        self.client_socket = None
        self.nmea_client = None
        self.failed_nmea_client_time = 0
        self.msgs = None
        self.sockets = []
        self.server = None
        self.last_values = {}
        self.addresses = {}
        self.poller = None
        self.fd_to_socket = {}

    def setup(self):
        self.sockets = []

        self.nmea_client = self.client.register(Property('nmea.client', '', persistent=True))

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setblocking(0)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.client_socket = False

        port = DEFAULT_PORT
        while True:
            try:
                self.server.bind(('0.0.0.0', port))
                break
            except:
                print(f"nmea server on port {port:d}: bind failed.")
            time.sleep(1)
        print('listening on port', port, 'for nmea connections')

        self.server.listen(5)

        self.failed_nmea_client_time = 0
        self.last_values = {'gps.source': 'none', 'wind.source': 'none', 'rudder.source': 'none', 'apb.source': 'none', 'sow.source': 'none'}
        for name in self.last_values:
            self.client.watch(name)
        self.addresses = {}

        self.poller = select.poll()

        self.poller.register(self.server, select.POLLIN)
        self.fd_to_socket = {self.server.fileno(): self.server}

        self.poller.register(self.client.connection, select.POLLIN)
        self.fd_to_socket[self.client.connection.fileno()] = self.client

        self.poller.register(self.pipe, select.POLLIN)
        self.fd_to_socket[self.pipe.fileno()] = self.pipe

        self.msgs = {}

    def setup_watches(self, watch=True):
        watchlist = ['gps.source', 'wind.source', 'rudder.source', 'apb.source', 'sow.source']
        for name in watchlist:
            self.client.watch(name, watch)

    def receive_nmea(self, line, device):
        parsers = []

        # Optimization : avoid parsing sentences here that would be discarded
        # in the main process anyway because they are already handled by a source
        # with a higher priority than tcp
        tcp_priority = SOURCE_PRIORITY['tcp']
        for name, parser in NMEA_PARSERS.items():
            if SOURCE_PRIORITY[self.last_values[name + '.source']] >= tcp_priority:
                parsers.append(parser)

        for parser in parsers:
            result = parser(line)
            if result:
                name, msg = result
                msg['device'] = line[1:3] + device
                self.msgs[name] = msg
                return

    def new_socket_connection(self, connection, address):
        max_connections = 10
        if len(self.sockets) == max_connections:
            connection.close()
            print('nmea server has too many connections')
            return

        if not self.sockets:
            self.setup_watches()
            self.pipe.send('sockets')

        sock = NMEASocket(connection, address)
        self.sockets.append(sock)

        self.addresses[sock] = address
        fd = sock.socket.fileno()
        self.fd_to_socket[fd] = sock

        self.poller.register(sock.socket, select.POLLIN)
        return sock

    def socket_lost(self, sock, fd):
        if sock == self.client_socket:
            self.client_socket = False
        try:
            self.sockets.remove(sock)
        except:
            print('nmea sock not in sockets!')
            return

        self.pipe.send('lostsocket' + str(sock.uid))
        if not self.sockets:
            self.setup_watches(False)
            self.pipe.send('nosockets')

        try:
            self.poller.unregister(fd)
        except Exception as e:
            print('nmea failed to unregister socket', e)

        try:
            del self.fd_to_socket[fd]
        except Exception as e:
            print('nmea failed to remove fd', e)

        try:
            del self.addresses[sock]
        except Exception as e:
            print('nmea failed to remove address', e)

        sock.close()

    def connect_client(self):
        if ':' not in self.nmea_client.value:
            return
        host, port = self.nmea_client.value.split(':')
        port = int(port)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tc0 = time.monotonic()
            s.connect((host, port))
            print('connected to', host, port, 'in', time.monotonic() - tc0, 'seconds')
            self.client_socket = self.new_socket_connection(s, self.nmea_client.value)
            self.client_socket.nmea_client = self.nmea_client.value
        except Exception as e:
            print('nmea client failed to connect to', self.nmea_client.value, ':', e)
            self.client_socket = False

    def nmea_process(self):
        print('nmea process', os.getpid())
        self.setup()
        while True:
            timeout = 100 if self.sockets else 10000
            self.poll(timeout)

    def receive_pipe(self):
        while True:  # receive all messages in pipe
            msg = self.pipe.recv()
            if not msg:
                return
            # relay nmea message from server to all tcp sockets
            for sock in self.sockets:
                sock.write(msg + '\r\n')

    def poll(self, timeout=0):
        t0 = time.monotonic()
        events = self.poller.poll(timeout)

        t1 = time.monotonic()
        if t1-t0 > timeout:
            print('poll took too long in nmea process!')

        while events:
            fd, flag = events.pop()
            sock = self.fd_to_socket[fd]
            if flag & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                if sock == self.server:
                    print('nmea bridge lost server connection')
                    exit(2)
                if sock == self.pipe:
                    print('nmea bridge pipe to autopilot')
                    exit(2)
                self.socket_lost(sock, fd)
            elif sock == self.server:
                self.new_socket_connection(*self.server.accept())
            elif sock == self.pipe:
                self.receive_pipe()
            elif sock == self.client:
                pass  # wake from poll
            elif flag & select.POLLIN:
                if not sock.recvdata():
                    self.socket_lost(sock, fd)
                else:
                    while True:
                        line = sock.readline()
                        if not line:
                            break
                        self.receive_nmea(line, 'socket' + str(sock.uid))
                        # relay nmea message from incoming socket to all other tcp sockets
                        # this could be time consuming, we should make that optionnal (TBD)
                        for tsock in self.sockets:
                            if tsock != sock:
                                tsock.write(line + '\r\n')
            else:
                print('nmea bridge unhandled poll flag', flag)

        t2 = time.monotonic()

        # send any parsed nmea messages the server might care about
        if self.msgs:
            if self.pipe.send(self.msgs):
                self.msgs = {}

        t3 = time.monotonic()

        # receive cypilot messages
        cypilot_msgs = self.client.receive()
        for name, value in cypilot_msgs.items():
            self.last_values[name] = value

        t4 = time.monotonic()

        # flush sockets
        for sock in self.sockets:
            sock.flush()

        t5 = time.monotonic()

        # reconnect client tcp socket
        if self.client_socket:
            if self.client_socket.nmea_client != self.nmea_client.value:
                self.client_socket.socket.close()  # address has changed, close connection
        elif t5 - self.failed_nmea_client_time > 20:
            try:
                self.connect_client()
            except Exception as e:
                print('failed to create nmea socket as host:port', self.nmea_client.value, e)
                self.failed_nmea_client_time = t5

        t6 = time.monotonic()

        if t6-t1 > .1:
            print(f"NMEA process overtime {t6-t1:.2f} : poll={t1-t0:.2f}, event={t2-t1:.2f}, send={t3-t2:.2f}, receive={t4-t3:.2f}, flush={t5-t4:.2f}, connect={t6-t5:.2f}")

def nmea_main():
    print('Version:', cypilot.pilot_path.STRVERSION)


if __name__ == '__main__':
    nmea_main()
