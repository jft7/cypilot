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

import json
from json import JSONEncoder

import cypilot.pilot_path

from pilot_path import dprint as print # pylint: disable=locally-disabled, redefined-builtin, wrong-import-order

PILOT_DIR = cypilot.pilot_path.PILOT_DIR

class SerialDevice:
    def __init__(self, path, baudrate=9600, protocol="nmea", description="", input_filter=None, output_msgs=None):
        if not input_filter:
            input_filter = []
        if not output_msgs:
            output_msgs = []
        self.path = path                    # device path
        self.baudrate = baudrate            # baud rate
        self.protocol = protocol            # protocol : nmea,gps,servo
        self.input_filter = input_filter    # list of received messages to be filtered out (empty list : no message)
        self.output_msgs = output_msgs      # list of messages to be transmitted (empty list : no message)
        self.description = description      # description

class SerialDeviceEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__

def init_serials():
    serialfilename = PILOT_DIR + 'cypilot_serial.conf'
    serial_config = []
    try:
        file = open(serialfilename)
        json_serial_configuration = json.load(file)
        for serial_device in json_serial_configuration:
            serial_config.append( SerialDevice( **serial_device ) )
        file.close()
    except: # pylint: disable=broad-except
        # Define default serial ports configuration
        serial_config = [SerialDevice("/dev/ttyUSB0", 4800, "nmea", "NKE Display Output"),
                         SerialDevice("/dev/ttyUSB1", 38400, "nmea", "Vesper AIS Input"),
                         SerialDevice("/dev/ttyUSB2", 38400, "servo", "CysPWR Rudder Servo Input/Output"),
                         SerialDevice("/dev/ttyUSB3", 4800, "nmea", "NKE TopLine Input/VHF ASN GPS Output", output_msgs=["RMC","GLL"]),
                         SerialDevice("/dev/ttyUSB4", 115200, "nmea", "CysBOX NMEA2000 GW Input/output"),
                         SerialDevice("/dev/ttyACM0", 115200, "gps", "CysBOX U-Blox GPS Input/Output")]
        try:
            file = open(serialfilename, 'w')
            json_serial_configuration = json.dumps(serial_config, cls=SerialDeviceEncoder, indent=4)
            file.write(json_serial_configuration + '\n')
            file.close()
        except Exception as e: # pylint: disable=broad-except
            print('Exception writing default values to serial configuration file:', serialfilename, e)
    return serial_config

def list_serials(protocol):
    serial_config = init_serials()
    list_serial = []
    for serial_device in serial_config:
        if isinstance(serial_device,SerialDevice) and  serial_device.protocol == protocol:
            list_serial.append(serial_device)
    return list_serial

if __name__ == '__main__':
    print("Testing serial configuration")
    print(" NMEA:")
    for d in list_serials("nmea"):
        print("     Path : ",d.path)
