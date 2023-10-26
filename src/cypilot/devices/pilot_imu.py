#!/usr/bin/env python
#
#   Copyright (C):
#           2021 Cybele Services
#
# Published under MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""
`pilot_imu`
=======================================================================================

Detect IMU devices
Supported IMU:
- Hillcrestlabs BNO080/085/86 - best performance achieved with BNO085 (2021-09-25)

Bosch BNO055 - No longer supported : some problems mainly due to autocalibration feature may occur while sailing

These devices are inertial measurement unit modules with sensor fusion
"""

import time
from micropython import const
from adafruit_extended_bus import ExtendedI2C as I2C
from adafruit_bus_device.i2c_device import I2CDevice

import cypilot.pilot_path # pylint: disable=unused-import
from devices.cypilot_bno085 import BNO08X_I2C, BNO08X_DEFAULT_ADDRESS

from pilot_path import dprint as print # pylint: disable=redefined-builtin

# These IMU devices use clock stretching option of I2C bus
# so with Raspberry PI, i2c-gpio must be used to comply with I2C standard
# Insert following line in /boot/config.txt file:
# dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=02,i2c_gpio_scl=03,i2c_gpio_delay_us=1
I2C_DEFAULT_BUS = const(3)

class NOIMU:
    def __init__(self, i2c=0, rate=10):
        super().__init__()
        self.rate = rate
        self.readtime = time.monotonic()

    def getIMUData(self):
        """Get IMU Data """
        now = time.monotonic()
        sleep = (1 / self.rate) - (now - self.readtime)
        if sleep > 0:
            time.sleep( sleep )
        self.readtime = now
               
        IMUData = {}
        # acceleration
        IMUData['accel'] = (0, 0, 0)
        # gyro
        IMUData['gyro'] = (0, 0, 0)
        # quaternion
        IMUData['fusionQPose'] = (0, 0, 0, 0)
        # euler angles
        IMUData['fusionPose'] = (0, 0, 0)
        return IMUData

def detect_IMU(address):
    data_buffer = bytearray(4)
    try:
        i2c = I2C(3)
        bus_device_obj = I2CDevice(i2c, address)
        with bus_device_obj as i2c:
            i2c.readinto(data_buffer)
        return True
    except Exception as e:
        print(e)
        return False

if detect_IMU(BNO08X_DEFAULT_ADDRESS):
    print("Using Hillcrestlabs BNO08X IMU device")
    PilotIMU = BNO08X_I2C
else:
    print("No IMU device available")
    PilotIMU = NOIMU
