#!/usr/bin/env python
#
#   Copyright (C):
#           2021 Ladyada for Adafruit Industries
#           2021 Cybele Services (for use with cyPilot / CysBOX / CysPWR)
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

import time
import math
from adafruit_extended_bus import ExtendedI2C as I2C
from micropython import const

import cypilot.pilot_path
from kbhit import KBHit

# pylint: disable=unused-import,consider-using-f-string
from devices.cypilot_bno085 import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GAME_ROTATION_VECTOR,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_ROTATION_VECTOR,
    REPORT_ACCURACY_STATUS,
    _FRS_WRITE_DATA,
    _FRS_WRITE_REQUEST,
    _Q_POINT_30_SCALAR,
)
from devices.cypilot_bno085 import BNO08X_I2C, PacketError
from quaternion import normalize, toeuler

# from pilot_path import pilot_path_main
# pilot_path_main()

# Note : to measure the read time, be aware that if the read interval is
# greater than the report interval, several packets must be read and the
# total operation time could be much longer than a standard read time
# from autopilot loop.

# REPORT_INTERVAL = const(1000000)         # in microseconds = 1000ms
REPORT_INTERVAL = const(105000)         # in microseconds = 105ms
REPORT_INTERVAL_TARE = const(50000)     # in microseconds = 50ms

READ_INTERVAL = 0.5

def bno085_help():
    print('If you need to test or calibrate the IMU,\n'
          'use following command: \n'
          ' s : start reading IMU data \n'
          ' e : start reading IMU (Euler Angle only)\n'
          # ' t : execute tare procedure (first use)\n'
          # ' a : execute alignment procedure (user tare) \n'
          ' m : map device physical axis \n'
          ' c : calibrate \n'
          ' q : quit \n')

def bno085_read(alldata=True):
    print('Start reading IMU data - Press any key to stop')

    kbh = KBHit()
    i2c = I2C(3)
    bno = BNO08X_I2C(i2c)

    bno.report_interval = REPORT_INTERVAL

    while True:
        if kbh.kbhit():
            if kbh.getch() == 'q':
                return
        time.sleep(READ_INTERVAL)
        t0 = time.monotonic()
        # bno.process_available_packets()
        data = bno.getIMUData()
        t1 = time.monotonic()
        accel_x, accel_y, accel_z = bno.acceleration  # pylint:disable=no-member
        gyro_x, gyro_y, gyro_z = bno.gyro  # pylint:disable=no-member
        mag_x, mag_y, mag_z = bno.magnetic  # pylint:disable=no-member
        quat_i, quat_j, quat_k, quat_real = bno.quaternion  # pylint:disable=no-member
        t2 = time.monotonic()
        if alldata:
            # Data from device
            print('Data read from device:')
            
            print(f" Read time  for {bno._processed_count:d} packets : {t1-t0:0.3f} , {t2-t1:0.3f}") # pylint: disable=protected-access
            print(f" Acceleration > X: {accel_x:0.6f}  Y: {accel_y:0.6f} Z: {accel_z:0.6f}  m/s^2")
            print(f" Gyro         > X: {gyro_x:0.6f}  Y: {gyro_y:0.6f} Z: {gyro_z:0.6f} rads/s")
            print(f" Magnetometer > X: {mag_x:0.6f}  Y: {mag_y:0.6f} Z: {mag_z:0.6f} uT")
            print(f" Quaternion   > I: {quat_i:0.6f}  J: {quat_j:0.6f} K: {quat_k:0.6f}  Real: {quat_real:0.6f}")            
            print("")

            # Data ready for cypilot

            print('Data transmitted to pilot:')
            print(' Acceleration (g): {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['accel']))
            print(' Gyro (rad/sec): {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['gyro']))
            euler = map(math.degrees, data['fusionPose'])
            print(' FusionPose (deg): {:0.3f}, {:0.3f}, {:0.3f}'.format(*euler))
            print(' FusionQPose: {:0.3f}, {:0.3f}, {:0.3f}, {:0.3f}'.format(*data['fusionQPose']))
            print("")
            print("")
        else:
            euler = list(map(math.degrees, data['fusionPose']))
            if euler[2] < 0 :
                euler[2] += 360
            print(' FusionPose (deg): {:0.3f}, {:0.3f}, {:0.3f}         '.format(*euler), end='\r')

def bno085_tare():
    print('Execute first time tare procedure - Follow instructions')

    kbh = KBHit()
    i2c = I2C(3)
    bno = BNO08X_I2C(i2c)

    def kbcheck():
        time.sleep(0.1)
        bno.process_available_packets()
        if kbh.kbhit():
            return kbh.getch()
        else:
            return '-'

    # 1- Power on and activate the Rotation Vector Sensor
    bno.enable_feature(BNO_REPORT_ROTATION_VECTOR, REPORT_INTERVAL_TARE)

    # 2- Calibrate the magnetometer by rotating the device in figure 8
    print("Calibrate the magnetometer by rotating the device in a figure 8 until Accuracy Estimate is < 10°")
    print("(hit <space> to continue, q to quit)")
    print("")
    bno.enable_feature(BNO_REPORT_MAGNETOMETER, REPORT_INTERVAL_TARE)
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break
        accuracy = math.degrees(bno.accuracy_estimate)
        print("Magnetomer accuracy: %0.1f°" % (accuracy), end="\r")

    # 3- Calibrate the accelerometer by positionning the box
    print("Calibrate the accelerometer by positioning the device in 4-6 unique orientations and ensuring the device is stable for ~1s in each orientation")
    print("(hit <space> to continue, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break

    # 4- Set the device down for a few seconds so that the gyroscope ZRO can calibrate as well
    print("Set the device down for a few seconds so that the gyroscope ZRO can calibrate as well")
    print("(hit <space> to continue, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break

    # 5- Position the device so that your desired forward direction is pointed North and make sure the device is level
    print("Position the device so that your desired forward direction is pointed North and make sure the device is level")
    print("(hit <space> to continue and save tare settings, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break
        # quaternion
        q_x, q_y, q_z, q_w = bno.quaternion
        __, __, z = toeuler(normalize((q_w, q_y, q_x, -q_z)))
        print("  ---> Direction : %d°     " % (math.degrees(z)), end='\r')
        # print( bno.quaternion, end='     \r')

    # 6- Run Tare Now command and Persist Tare
    bno.send_command([0xF2, 0x00, 0x03, 0x00, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(1.0)
    bno.send_command([0xF2, 0x00, 0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(1.0)
    # bno.send_command([0xF4, 0x00, 0x00, 0x00, 0x3E, 0x2D, 0x00, 0x00])
    print("The current settings have been saved into the Sensor Orientation FRS config record")
    print("(hit q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return

def bno085_align():
    print('Execute user tare procedure (forward direction) - Follow instructions')

    kbh = KBHit()
    i2c = I2C(3)
    bno = BNO08X_I2C(i2c)

    def kbcheck():
        time.sleep(0.1)
        bno.process_available_packets()
        if kbh.kbhit():
            return kbh.getch()
        else:
            return '-'

    # 1- Power on and activate the Rotation Vector Sensor
    bno.enable_feature(BNO_REPORT_ROTATION_VECTOR, REPORT_INTERVAL_TARE)

    # 2- Calibrate the magnetometer by rotating the device in figure 8
    print("Calibrate the magnetometer by rotating the device in a figure 8 until Accuracy Estimate is < 10°")
    print("Set the device down for a few seconds so that the gyroscope ZRO can calibrate as well")
    print("(hit <space> to continue, q to quit)")
    print("")
    bno.enable_feature(BNO_REPORT_MAGNETOMETER, REPORT_INTERVAL_TARE)
    time.sleep(1.0)
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break
        accuracy = math.degrees(bno.accuracy_estimate)
        print("Magnetomer accuracy: %0.1f°" % (accuracy), end="\r")

    # 3- Position the device into your desired forward direction orientation
    print("Position the device into your desired forward direction orientation")
    print("(hit <space> to continue and save settings, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break
    bno.send_command([0xF2, 0x00, 0x03, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(1.0)
    bno.send_command([0xF2, 0x00, 0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(1.0)
    print("The current settings have been saved into the Sensor Orientation FRS config record")
    print("(hit q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return

def bno085_calibrate():
    print('Execute factory calibration - Follow instructions')

    kbh = KBHit()
    i2c = I2C(3)
    bno = BNO08X_I2C(i2c)

    def kbcheck():
        time.sleep(0.1)
        bno.process_available_packets()
        if kbh.kbhit():
            return kbh.getch()
        else:
            return '-'

    print("")
    print( "Clearing current calibration ...")
    bno.send_command([0xF2, 0x00, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(1.0)
    for _i in range(3):
        try:
            _packet = bno._read_packet() # pylint: disable=protected-access
        except PacketError:
            time.sleep(0.5)
    time.sleep(2.0)

    bno.begin_calibration()
    bno.enable_feature(BNO_REPORT_MAGNETOMETER, REPORT_INTERVAL_TARE)
    bno.enable_feature(BNO_REPORT_GAME_ROTATION_VECTOR, REPORT_INTERVAL_TARE)

    print("")
    print("Step 1 : Position the device in a relatively clean magnetic environment")
    print("Begin observing the Status bit of the Magnetic Field output")
    print("Rotate the device in a figure 8 until calibration quality is high")
    print("(hit <space> to continue, q to quit)")
    print("")   
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break
        calibration_status = bno.calibration_status
        print("Magnetometer Calibration quality: %s, (%d)        " % (REPORT_ACCURACY_STATUS[calibration_status], calibration_status), end='\r')
    print("")

    print("")
    print("Step 2 : Perform the accelerometer calibration")
    print("Calibrate the accelerometer by positioning the device in 4-6 unique orientations")
    print("Ensure the device is stable for ~1s in each orientation")
    print("(hit <space> to continue, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break
        
    print("")
    print("Step 3 : Perform the gyroscope calibration")
    print("Set the device down on a stationary surface for ~2-3 seconds to calibrate the gyroscope")
    print("(hit <space> to continue, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break

    print("")
    print("Step 4 : Perform the magnetometer calibration motions")
    print("Rotate the device ~180° and back to the beginning position in each axis (roll, pitch, yaw)")
    print("Rotation speed should be about 2 seconds per axis")
    print("(hit <space> to continue and save calibration data, q to quit)")
    print("")
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            bno.save_calibration_data()
            print("Calibration data saved")
            break

    print("Calibration done")

# mapping quaternion : (Qx, Qy, Qz, Qw)
_MAPPING_QUATERNION = {
    ('e', 'n', 'u'):(0, 0, 0, 1),
    ('n', 'w', 'u'):(0, 0, 0.707, 0.707),
    ('w', 's', 'u'):(0, 0, 1, 0),
    ('s', 'e', 'u'):(0, 0, -0.707, 0.707),
    ('e', 's', 'd'):(0, -1, 0, 0),
    ('n', 'e', 'd'):(-0.707, -0.707, 0, 0),
    ('w', 'n', 'd'):(-1, 0, 0, 0),
    ('s', 'w', 'd'):(-0.707,0.707,0,0),
    ('u', 's', 'e'):(0, -0.707, 0.707, 0),
    ('n', 'u', 'e'):(-0.5, -0.5, 0.5, 0.5),
    ('d', 'n', 'e'):(-0.707, 0, 0, 0.707),
    ('s', 'd', 'e'):(-0.5, 0.5, -0.5, 0.5),
    ('u', 'n', 'w'):(-0.707, 0, 0, -0.707),
    ('n', 'd', 'w'):(-0.5, -0.5, -0.5, -0.5),
    ('d', 's', 'w'):(0, -0.707, -0.707, 0),
    ('s', 'u', 'w'):(0.5, -0.5, -0.5, 0.5),
    ('u', 'e', 'n'):(-0.5, -0.5, 0.5, -0.5),
    ('w', 'u', 'n'):(-0.707, 0, 0.707, 0),
    ('d', 'w', 'n'):(-0.5, 0.5, 0.5, 0.5),
    ('e', 'd', 'n'):(0, -0.707, 0, -0.707),
    ('u', 'w', 's'):(0.5, -0.5, 0.5, 0.5),
    ('w', 'd', 's'):(-0.707, 0, -0.707, 0),
    ('d', 'e', 's'):(-0.5, -0.5, -0.5, 0.5),
    ('e', 'u', 's'):(0, -0.707, 0, 0.707),
}

_MAPPING_AXIS = {'n':'North', 'e':'East', 's':'South', 'w':'West', 'u':'Up', 'd':'Down'}

def bno085_map():
    print('Enter mapping orientation of the BNO08X - Follow instructions\n'\
          'For each BNO physical axis, select mount alignment using n/e/s/w/u/d keys:\n'\
          'n -> North, e -> East, s -> South, w -> West, u -> Up, d -> Down\n'\
          '\n'\
          'CysBOX Built-in BNO08X IMU:\n'\
          ' - s w d : horizontal mount on floor, right side of the box towards the bow\n'\
          ' - n e d : horizontal mount on floor, left side of the box towards the bow\n'\
          ' - s e u : horizontal mount on ceiling, right side of the box towards the bow\n'\
          ' - n w u : horizontal mount on ceiling, left side of the box towards the bow\n'\
          ' - n u e : vertical mount on starboard, left side of the box towards the bow\n'\
          ' - s u w : vertical mount on port, right side of the box towards the bow\n'\
          '\n'\
          'IMU Adafruit BNO08X on Stemma slot #1:\n'\
          ' - e n u : horizontal mount on floor, right side of the box towards the bow\n'\
          ' - w s u : horizontal mount on floor, left side of the box towards the bow\n'\
          ' - w n d : horizontal mount on ceiling, right side of the box towards the bow\n'\
          ' - e s d : horizontal mount on ceiling, left side of the box towards the bow\n'\
          ' - d s w : vertical mount on starboard, left side of the box towards the bow\n'\
          ' - d n e : vertical mount on port, right side of the box towards the bow\n'\
          '...\n'\
          '\n')

    kbh = KBHit()

    def get_alignment(axis):
        while True:
            print('Enter BNO %s physical axis alignment (n/e/s/w/u/d) or q to quit' % axis)
            k = kbh.getch()
            if k in _MAPPING_AXIS:
                alignment = _MAPPING_AXIS[k]
                print('BNO %s Axis is aligned %s' %(axis, alignment))
                return k
            elif k == 'q':
                return k

    bno_x = get_alignment('X')
    if bno_x == 'q':
        return
    bno_y = get_alignment('Y')
    if bno_y == 'q':
        return
    bno_z = get_alignment('Z')
    if bno_z == 'q':
        return

    try:
        orientation = _MAPPING_QUATERNION[(bno_x, bno_y, bno_z)]
    except:
        print('Error: BNO physical axis mapping not supported', (bno_x, bno_y, bno_z))
        return

    i2c = I2C(3)
    bno = BNO08X_I2C(i2c)
    time.sleep(0.1)
    bno.process_available_packets()

    print("Hit <space> to continue and save mapping data, q to quit")
    print("")

    # bno.send_command([0xF2, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    # bno.send_command([0xF2, 0x00, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    # for _i in range(3):
    #    try:
    #        _packet = bno._read_packet()
    #    except PacketError:
    #       time.sleep(0.5)
    # time.sleep(2.0)
    bno.process_available_packets()

    while True:
        if kbh.kbhit():
            k = kbh.getch()
            if k == 'q':
                return
            elif k == ' ':
                if bno.set_orientation(orientation):
                    print("Physical orientation set : ", (bno_x, bno_y, bno_z))
                    print("Please run calibration procedure now")
                else:
                    print("Error, can't set physical orientation : ",(bno_x, bno_y, bno_z))
                # bno.send_command([0xF4, 0x00, 0x00, 0x00, 0x3e, 0x2d, 0x00, 0x00])
                return
        bno.process_available_packets()
        time.sleep(0.1)

def bno085_init():
    print('Reinitialize device - Follow instructions')

    kbh = KBHit()
    i2c = I2C(3)
    bno = BNO08X_I2C(i2c)

    def kbcheck():
        time.sleep(0.1)
        bno.process_available_packets()
        if kbh.kbhit():
            return kbh.getch()
        else:
            return '-'

    print("(hit <space> to continue, q to quit)")
    print("")   
    while True:
        k = kbcheck()
        if k == 'q':
            return
        elif k == ' ':
            break

    # bno.send_command([0xF2, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    bno.send_command([0xF2, 0x00, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(1.0)
    for _i in range(3):
        try:
            _packet = bno._read_packet() # pylint: disable=protected-access
        except PacketError:
            time.sleep(0.5)
    time.sleep(2.0)

def bno085_main():
    print('Version:', cypilot.pilot_path.STRVERSION)

    bno085_help()
    kbh = KBHit()

    print("")
    print("Warning: calibration must be done when mapping of the axis are changed")
    print("")
    while True:
        #check if there is a entry, to allow test and calibration
        if kbh.kbhit():
            k = kbh.getch()
            if k == 'q':
                exit()
            elif k == 's':
                bno085_read()
            elif k == 'e':
                bno085_read(alldata=False)
#            elif k == 'i':
#                bno085_init()
#            elif k == 't':
#                bno085_tare()
#            elif k == 'a':
#                bno085_align()
            elif k == 'm':
                bno085_map()
            elif k == 'c':
                bno085_calibrate()
            bno085_help()
        time.sleep(0.1)

if __name__ == '__main__':
    bno085_main()
