#!/usr/bin/env python
#
#   Copyright (C) 2021 Cybele Services
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

import time
from struct import unpack
from threading import Thread
import re

import cypilot.pilot_path

import json
from client import cypilotClient
from sensors import init_source_priority
from kbhit import KBHit

from pilot_path import dprint as print # pylint: disable=redefined-builtin

try:
    from bluepy.btle import UUID, DefaultDelegate, Peripheral, ADDR_TYPE_RANDOM
except Exception as bpe:
    print('Bluepy not installed, except:', str(bpe))

BLE_CONFIG_PATH = cypilot.pilot_path.PILOT_DIR + 'cypilot_calypso.conf'
BLE_MAC_ADDRESS = 'c8:3a:cf:52:22:aa'

SOURCE_PRIORITY = {}

def calypso_uuid(val):
    return UUID(f"0000{val:04X}-0000-1000-8000-00805F9B34FB")

#=======================================================================
#            Calypso Data Service Class
#=======================================================================

DATA_SERVICE_UUID = 0x180D
PRINCIPAL_CHARACTERISTIC_UUID = 0x2A39
CCCD_UUID = 0x2902

E_PRINCIPAL_HANDLE = None

class DataService():
    serviceUUID = calypso_uuid(DATA_SERVICE_UUID)
    principal_char_uuid = calypso_uuid(PRINCIPAL_CHARACTERISTIC_UUID)

    def __init__(self, periph):
        self.periph = periph
        self.data_service = None
        self.principal_char = None
        self.principal_cccd = None

    def enable(self):
        """ Enables the class by finding the service and characteristics """
        global E_PRINCIPAL_HANDLE

        if self.data_service is None:
            self.data_service = self.periph.getServiceByUUID(self.serviceUUID)
        if self.principal_char is None:
            self.principal_char = self.data_service.getCharacteristics(self.principal_char_uuid)[0]
            E_PRINCIPAL_HANDLE = self.principal_char.getHandle()
            self.principal_cccd = self.principal_char.getDescriptors(forUUID=CCCD_UUID)[0]

    def set_principal_notification(self, state):
        if state:
            self.principal_cccd.write(b"\x01\x00", True)
        else:
            self.principal_cccd.write(b"\x00\x00", True)

#=======================================================================
#            PrincipalDelegate Class
#=======================================================================

CALYPSO_NOT_DATA = bytearray(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
CALYPSO_NOT_TIME = None

class PrincipalDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleNotification(self, cHandle, data):
        global CALYPSO_NOT_TIME, CALYPSO_NOT_DATA

        if cHandle == E_PRINCIPAL_HANDLE:
            CALYPSO_NOT_TIME = time.monotonic()
            CALYPSO_NOT_DATA = data

#=======================================================================
#            Calypso Class
#=======================================================================

class Calypso(Peripheral):
    """
    Calypso module. Instance the class and enable to get access to the Calypso Anemometer.
    The addr of your device has to be know, or can be found by using the hcitool command line
    tool, for example. Call "> sudo hcitool lescan" and your calypso's address should show up.
    """
    def __init__(self, addr):
        try:
            Peripheral.__init__(self, addr, addrType=ADDR_TYPE_RANDOM)
            self.data = DataService(self)
            self.error = None
        except Exception as e:
            self.data = None
            self.error = e
 
#=======================================================================
#            Ultrasonic Wind BLE Sensor
#=======================================================================

class uwble(object):
    def __init__(self, sensors=False):
        global SOURCE_PRIORITY
        SOURCE_PRIORITY = init_source_priority()
        self.sensors = sensors
        if not sensors:
            self.client = cypilotClient()
        else:
            server = sensors.client.server
            self.client = cypilotClient(server)
        self.debug = True
        self.initialized = False
        self.config = False
        self.active = False
        self.mac = BLE_MAC_ADDRESS
        self.calypso = None
        self.init()

    def init(self):
        try:
            f = open(BLE_CONFIG_PATH)
            self.config = f.read()
            # print('read uwble config: ', self.config)
            f.close()
            contents = json.loads(self.config)
            self.mac = contents['mac_address']
        except Exception as e:
            print('uwble failed to read config:', BLE_CONFIG_PATH, ' except:', str(e))
            self.config = False
        if 'ble' not in SOURCE_PRIORITY:
            print('Warning : "ble" not active (priority not defined in cypilot_sensors.conf)')
        else:
            self.active = True
            self.calypso_thread = Thread(target=self.bthread)
            self.calypso_thread.name = "bluepy_bthread"
            self.calypso_thread.daemon = True
            self.calypso_thread.start()

    def stop(self):
        self.active = False
        self.calypso_thread.join(1.0)

    def bthread(self):
        while self.active:
            while not self.initialized and self.active:
                self.calypso = Calypso(self.mac)
                if self.calypso.data:
                    self.calypso.setDelegate(PrincipalDelegate())
                    self.calypso.data.enable()
                    self.calypso.data.set_principal_notification(True)
                    self.initialized = True
                else:
                    if self.debug:
                        print('uwble failed to initialize BLE device :', self.calypso.error) 
                    time.sleep(10.0)
            try:
                if not self.calypso.waitForNotifications(1.0):
                    continue
            except AttributeError:
                self.initialized = False
            except Exception as e:
                if self.sensors:
                    print('uwble exception while waiting for notification:', str(e))
                self.initialized = False
        self.calypso.disconnect()
        del self.calypso

    def poll(self):
        if not self.initialized:
            return
        wind_speed, wind_direction, battery_level, temp_level, roll, pitch, ecompass = unpack('<HHBBBBH', CALYPSO_NOT_DATA)
        wind_speed_ms = wind_speed / 100
        wind_speed_kt = wind_speed_ms * 1.94384
        temp_level = temp_level - 100
        battery_level = battery_level * 10
        roll = roll - 90
        pitch = pitch - 90
        ecompass = 360 - ecompass
        data = {'direction': wind_direction, 'speed': wind_speed_kt, 'device': 'calypso'}
        if self.sensors:
            self.sensors.write('wind', data, 'ble')
        else:
            print(f"kt: {wind_speed_kt:.1f} m/s: {wind_speed_ms:.1f} dir: {wind_direction:.0f} heading: {ecompass:0.f}", end="\r")
            # print(f"   battery: {battery_lmevel:.1f} temperature: {temp_level:.0f} roll: {roll:.0f} pitch: {pitch:.0f}", end="\r")
            
def uwble_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    print('If you need to pair a Calypso BLE anemometer,\n'
          'use following command: \n'
          ' a : enter Calypso Anemometer MAC Address \n'
          ' c : print current configuration file \n'
          ' w : start wind measurement \n'
          ' s : stop wind measurement \n'
          ' q : quit \n')

    kbh = KBHit()
    uw = uwble()
    polling = False
    while True:
        #check if there is a entry, to permit appair mode
        if kbh.kbhit():
            k = kbh.getch()
            if k == 'q':
                exit()
            elif k == 'c':
                try:
                    print('Calypso BLE configuration file:')
                    f = open(BLE_CONFIG_PATH)
                    config = f.read()
                    print(config)
                    f.close()
                except Exception as e:
                    print('uwble failed to read config:', BLE_CONFIG_PATH, ' except:', str(e))
            elif k == 'a':
                uw.debug = False
                print('Enter the MAC Address of the Calypso wind sensor (example: c8:3a:cf:52:22:aa)')
                kbh.exit() # restore normal console behaviour with echo
                mac = input('MAC Address: ')
                uw.debug = True
                kbh.init() # switch back to non-echo mode
                if not re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", mac.lower()):
                    print("Invalid MAC Address : ", mac)
                else:
                    uw.stop()
                    time.sleep(1.0)
                    try:
                        f = open(BLE_CONFIG_PATH, 'w')
                        config = json.dumps({'mac_address': mac, 'poll_period': 0.01})
                        f.write(config)
                        print('uwble config has been written: ', config)
                        f.close()
                    except Exception as e:
                        print('uwble failed to write config:', BLE_CONFIG_PATH, ' except:', str(e))
                    uw.init()
            elif k == 'w':
                print('Start Wind Measurement ...')
                polling = True
            elif k == 's':
                print('Stop Wind Measurement ...')
                polling = False
        if polling:
            uw.poll()
            time.sleep(1.0)
            continue
        time.sleep(0.1)

if __name__ == '__main__':
    uwble_main()
