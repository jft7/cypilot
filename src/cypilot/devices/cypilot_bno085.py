#!/usr/bin/env python
#
#   Copyright (C):
#           2020 Bryan Siepert for Adafruit Industries
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

# pylint: disable=invalid-name, too-many-lines, consider-using-f-string

"""
`cypilot_bno08x`
================================================================================

Helper library for the Hillcrest Laboratories BNO08x IMUs

"""

import time

from struct import unpack_from, pack_into
from collections import namedtuple

from micropython import const
from adafruit_bus_device.i2c_device import I2CDevice

from quaternion import normalize, toeuler

import RPi.GPIO as gpio

from pilot_path import dprint as print # pylint: disable=redefined-builtin

# TODO: Remove on release
from .debug_bno085 import channels, reports

# TODO: shorten names
# Channel 0: the SHTP command channel
BNO_CHANNEL_SHTP_COMMAND = const(0)
BNO_CHANNEL_EXE = const(1)
_BNO_CHANNEL_CONTROL = const(2)
_BNO_CHANNEL_INPUT_SENSOR_REPORTS = const(3)
_BNO_CHANNEL_WAKE_INPUT_SENSOR_REPORTS = const(4)
_BNO_CHANNEL_GYRO_ROTATION_VECTOR = const(5)

_GET_FEATURE_REQUEST = const(0xFE)
_SET_FEATURE_COMMAND = const(0xFD)
_GET_FEATURE_RESPONSE = const(0xFC)
_BASE_TIMESTAMP = const(0xFB)

_TIMESTAMP_REBASE = const(0xFA)

_SHTP_REPORT_PRODUCT_ID_RESPONSE = const(0xF8)
_SHTP_REPORT_PRODUCT_ID_REQUEST = const(0xF9)

_FRS_WRITE_REQUEST = const(0xF7)
_FRS_WRITE_DATA = const(0xF6)
_FRS_WRITE_RESPONSE = const(0xF5)

_FRS_READ_REQUEST = const(0xF4)
_FRS_READ_RESPONSE = const(0xF3)

_COMMAND_REQUEST = const(0xF2)
_COMMAND_RESPONSE = const(0xF1)

# DCD/ ME Calibration commands and sub-commands
_SAVE_DCD = const(0x6)
_ME_CALIBRATE = const(0x7)
_ME_CAL_CONFIG = const(0x00)
_ME_GET_CAL = const(0x01)

# Calibrated Acceleration (m/s2)
BNO_REPORT_ACCELEROMETER = const(0x01)
# Calibrated gyroscope (rad/s).
BNO_REPORT_GYROSCOPE = const(0x02)
# Magnetic field calibrated (in µTesla). The fully calibrated magnetic field measurement.
BNO_REPORT_MAGNETOMETER = const(0x03)
# Linear acceleration (m/s2). Acceleration of the device with gravity removed
BNO_REPORT_LINEAR_ACCELERATION = const(0x04)
# Rotation Vector
BNO_REPORT_ROTATION_VECTOR = const(0x05)
BNO_REPORT_GAME_ROTATION_VECTOR = const(0x08)

BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR = const(0x09)

BNO_REPORT_STEP_COUNTER = const(0x11)

BNO_REPORT_RAW_ACCELEROMETER = const(0x14)
BNO_REPORT_RAW_GYROSCOPE = const(0x15)
BNO_REPORT_RAW_MAGNETOMETER = const(0x16)
BNO_REPORT_SHAKE_DETECTOR = const(0x19)

BNO_REPORT_STABILITY_CLASSIFIER = const(0x13)
BNO_REPORT_ACTIVITY_CLASSIFIER = const(0x1E)
BNO_REPORT_GYRO_INTEGRATED_ROTATION_VECTOR = const(0x2A)
# TODOz:
# Calibrated Acceleration (m/s2)
# Euler Angles (in degrees?)
# CALIBRATION
# RAW ACCEL, MAG, GYRO # Sfe says each needs the non-raw enabled to work

_DEFAULT_REPORT_INTERVAL = const(100000)  # in microseconds = 100ms
_MAGNETOMETER_REPORT_INTERVAL = const(1000000) # only used for configuration testing
_QUAT_READ_TIMEOUT = 0.500  # timeout in seconds
_PACKET_READ_TIMEOUT = 2.000  # timeout in seconds
_FEATURE_ENABLE_TIMEOUT = 2.0
_DEFAULT_TIMEOUT = 2.0
_BNO08X_CMD_RESET = const(0x01)
_QUAT_Q_POINT = const(14)
_BNO_HEADER_LEN = const(4)

_Q_POINT_30_SCALAR = 2 ** (30 * -1)
_Q_POINT_14_SCALAR = 2 ** (14 * -1)
_Q_POINT_12_SCALAR = 2 ** (12 * -1)
# _Q_POINT_10_SCALAR = 2 ** (10 * -1)
_Q_POINT_9_SCALAR = 2 ** (9 * -1)
_Q_POINT_8_SCALAR = 2 ** (8 * -1)
_Q_POINT_4_SCALAR = 2 ** (4 * -1)

_GYRO_SCALAR = _Q_POINT_9_SCALAR
_ACCEL_SCALAR = _Q_POINT_8_SCALAR
_QUAT_SCALAR = _Q_POINT_14_SCALAR
_GEO_QUAT_SCALAR = _Q_POINT_12_SCALAR
_MAG_SCALAR = _Q_POINT_4_SCALAR

_REPORT_LENGTHS = {
    _SHTP_REPORT_PRODUCT_ID_RESPONSE: 16,
    _GET_FEATURE_RESPONSE: 17,
    _COMMAND_RESPONSE: 16,
    _SHTP_REPORT_PRODUCT_ID_RESPONSE: 16,
    _BASE_TIMESTAMP: 5,
    _TIMESTAMP_REBASE: 5,
    _FRS_READ_RESPONSE: 16,
    _FRS_WRITE_RESPONSE: 4,
}
# these raw reports require their counterpart to be enabled
_RAW_REPORTS = {
    BNO_REPORT_RAW_ACCELEROMETER: BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_RAW_GYROSCOPE: BNO_REPORT_GYROSCOPE,
    BNO_REPORT_RAW_MAGNETOMETER: BNO_REPORT_MAGNETOMETER,
}
_AVAIL_SENSOR_REPORTS = {
    BNO_REPORT_ACCELEROMETER: (_Q_POINT_8_SCALAR, 3, 10),
    BNO_REPORT_GYROSCOPE: (_Q_POINT_9_SCALAR, 3, 10),
    BNO_REPORT_MAGNETOMETER: (_Q_POINT_4_SCALAR, 3, 10),
    BNO_REPORT_LINEAR_ACCELERATION: (_Q_POINT_8_SCALAR, 3, 10),
    BNO_REPORT_ROTATION_VECTOR: (_Q_POINT_14_SCALAR, 4, 14),
    BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR: (_Q_POINT_12_SCALAR, 4, 14),
    BNO_REPORT_GAME_ROTATION_VECTOR: (_Q_POINT_14_SCALAR, 4, 12),
    BNO_REPORT_STEP_COUNTER: (1, 1, 12),
    BNO_REPORT_SHAKE_DETECTOR: (1, 1, 6),
    BNO_REPORT_STABILITY_CLASSIFIER: (1, 1, 6),
    BNO_REPORT_ACTIVITY_CLASSIFIER: (1, 1, 16),
    BNO_REPORT_RAW_ACCELEROMETER: (1, 3, 16),
    BNO_REPORT_RAW_GYROSCOPE: (1, 3, 16),
    BNO_REPORT_RAW_MAGNETOMETER: (1, 3, 16),
}
_INITIAL_REPORTS = {
    BNO_REPORT_ACTIVITY_CLASSIFIER: {
        "Tilting": -1,
        "most_likely": "Unknown",
        "OnStairs": -1,
        "On-Foot": -1,
        "Other": -1,
        "On-Bicycle": -1,
        "Still": -1,
        "Walking": -1,
        "Unknown": -1,
        "Running": -1,
        "In-Vehicle": -1,
    },
    BNO_REPORT_STABILITY_CLASSIFIER: "Unknown",
    BNO_REPORT_ROTATION_VECTOR: (0.0, 0.0, 0.0, 0.0),
    BNO_REPORT_GAME_ROTATION_VECTOR: (0.0, 0.0, 0.0, 0.0),
    BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR: (0.0, 0.0, 0.0, 0.0),
}

_ENABLED_ACTIVITIES = (
    0x1FF  # All activities; 1 bit set for each of 8 activities, + Unknown
)

DATA_BUFFER_SIZE = const(512)  # data buffer size. obviously eats ram
PacketHeader = namedtuple(
    "PacketHeader",
    [
        "channel_number",
        "sequence_number",
        "data_length",
        "packet_byte_count",
    ],
)

REPORT_ACCURACY_STATUS = [
    "Accuracy Unreliable",
    "Low Accuracy",
    "Medium Accuracy",
    "High Accuracy",
]


class PacketError(Exception):
    """Raised when the packet couldnt be parsed"""

    pass  # pylint:disable=unnecessary-pass


def _elapsed(start_time):
    return time.monotonic() - start_time


############ PACKET PARSING ###########################
def _parse_sensor_report_data(report_bytes):
    """Parses reports with only 16-bit fields"""
    data_offset = 4  # this may not always be true
    report_id = report_bytes[0]
    scalar, count, _report_length = _AVAIL_SENSOR_REPORTS[report_id]
    if report_id in _RAW_REPORTS:
        # raw reports are unsigned
        format_str = "<H"
    else:
        format_str = "<h"
    results = []

    if report_id == BNO_REPORT_ROTATION_VECTOR or report_id == BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR:
        accuracy = unpack_from("<h", report_bytes, offset=12)[0] * _Q_POINT_12_SCALAR
    else:
        accuracy = unpack_from("<B", report_bytes, offset=2)[0]
        accuracy &= 0b11

    for _offset_idx in range(count):
        total_offset = data_offset + (_offset_idx * 2)
        raw_data = unpack_from(format_str, report_bytes, offset=total_offset)[0]
        scaled_data = raw_data * scalar
        results.append(scaled_data)
    results_tuple = tuple(results)

    return (results_tuple, accuracy)


def _parse_step_couter_report(report_bytes):
    return unpack_from("<H", report_bytes, offset=8)[0]


def _parse_stability_classifier_report(report_bytes):
    classification_bitfield = unpack_from("<B", report_bytes, offset=4)[0]
    return ["Unknown", "On Table", "Stationary", "Stable", "In motion"][
        classification_bitfield
    ]


# report_id
# feature_report_id
# feature_flags
# change_sensitivity
# report_interval
# batch_interval_word
# sensor_specific_configuration_word
def _parse_get_feature_response_report(report_bytes):
    return unpack_from("<BBBHIII", report_bytes)


# 0 Report ID = 0x1E
# 1 Sequence number
# 2 Status
# 3 Delay
# 4 Page Number + EOS
# 5 Most likely state
# 6-15 Classification (10 x Page Number) + confidence
def _parse_activity_classifier_report(report_bytes):
    activities = [
        "Unknown",
        "In-Vehicle",  # look
        "On-Bicycle",  # at
        "On-Foot",  # all
        "Still",  # this
        "Tilting",  # room
        "Walking",  # for
        "Running",  # activities
        "OnStairs",
    ]

    end_and_page_number = unpack_from("<B", report_bytes, offset=4)[0]
    # last_page = (end_and_page_number & 0b10000000) > 0
    page_number = end_and_page_number & 0x7F
    most_likely = unpack_from("<B", report_bytes, offset=5)[0]
    confidences = unpack_from("<BBBBBBBBB", report_bytes, offset=6)

    classification = {}
    classification["most_likely"] = activities[most_likely]
    for idx, raw_confidence in enumerate(confidences):
        confidence = (10 * page_number) + raw_confidence
        activity_string = activities[idx]
        classification[activity_string] = confidence
    return classification


def _parse_shake_report(report_bytes):
    shake_bitfield = unpack_from("<H", report_bytes, offset=4)[0]
    return (shake_bitfield & 0x111) > 0


def parse_sensor_id(buffer):
    """Parse the fields of a product id report"""
    if not buffer[0] == _SHTP_REPORT_PRODUCT_ID_RESPONSE:
        raise AttributeError("Wrong report id for sensor id: %s" % hex(buffer[0]))

    sw_major = unpack_from("<B", buffer, offset=2)[0]
    sw_minor = unpack_from("<B", buffer, offset=3)[0]
    sw_patch = unpack_from("<H", buffer, offset=12)[0]
    sw_part_number = unpack_from("<I", buffer, offset=4)[0]
    sw_build_number = unpack_from("<I", buffer, offset=8)[0]

    return (sw_part_number, sw_major, sw_minor, sw_patch, sw_build_number)


def _parse_command_response(report_bytes):

    # CMD response report:
    # 0 Report ID = 0xF1
    # 1 Sequence number
    # 2 Command
    # 3 Command sequence number
    # 4 Response sequence number
    # 5 R0-10 A set of response values. The interpretation of these values is specific
    # to the response for each command.
    report_body = unpack_from("<BBBBB", report_bytes)
    response_values = unpack_from("<BBBBBBBBBBB", report_bytes, offset=5)
    return (report_body, response_values)


def _insert_command_request_report(command, buffer, next_sequence_number, command_params=None):
    if command_params and len(command_params) > 9:
        raise AttributeError(
            "Command request reports can only have up to 9 arguments but %d were given"
            % len(command_params)
        )
    for _i in range(12):
        buffer[_i] = 0
    buffer[0] = _COMMAND_REQUEST
    buffer[1] = next_sequence_number
    buffer[2] = command
    if command_params is None:
        return

    for idx, param in enumerate(command_params):
        buffer[3 + idx] = param


def _report_length(report_id):
    if report_id < 0xF0:  # it's a sensor report
        return _AVAIL_SENSOR_REPORTS[report_id][2]

    return _REPORT_LENGTHS[report_id]


def _separate_batch(packet, report_slices):
    # get first report id, loop up its report length
    # read that many bytes, parse them
    next_byte_index = 0
    while next_byte_index < packet.header.data_length:
        report_id = packet.data[next_byte_index]
        required_bytes = _report_length(report_id)

        unprocessed_byte_count = packet.header.data_length - next_byte_index

        # handle incomplete remainder
        if unprocessed_byte_count < required_bytes:
            raise RuntimeError("Unprocessable Batch bytes", unprocessed_byte_count)
        # we have enough bytes to read
        # add a slice to the list that was passed in
        # print("Receive report %d with sequence %d" % (report_id, sequence))
        report_slice = packet.data[next_byte_index : next_byte_index + required_bytes]
        report_slices.insert(0, [report_slice[0], report_slice])
        next_byte_index = next_byte_index + required_bytes

# class Report:
#     _buffer = bytearray(DATA_BUFFER_SIZE)
#     _report_obj = Report(_buffer)

#     @classmethod
#     def get_report(cls)
#         return cls._report_obj


class Packet:
    """A class representing a Hillcrest LaboratorySensor Hub Transport packet"""

    def __init__(self, packet_bytes):
        self.header = self.header_from_buffer(packet_bytes)
        data_end_index = self.header.data_length + _BNO_HEADER_LEN
        self.data = packet_bytes[_BNO_HEADER_LEN:data_end_index]

    def __str__(self):

        length = self.header.packet_byte_count
        outstr = "\n\t\t********** Packet *************\n"
        outstr += "DBG::\t\t HEADER:\n"

        outstr += "DBG::\t\t Data Len: %d\n" % (self.header.data_length)
        outstr += "DBG::\t\t Channel: %s (%d)\n" % (
            channels[self.channel_number],
            self.channel_number,
        )
        if self.channel_number in [_BNO_CHANNEL_CONTROL, _BNO_CHANNEL_INPUT_SENSOR_REPORTS,]:
            if self.report_id in reports:
                outstr += "DBG::\t\t \tReport Type: %s (0x%x)\n" % (reports[self.report_id], self.report_id,)
            else:
                outstr += "DBG::\t\t \t** UNKNOWN Report Type **: %s\n" % hex(
                    self.report_id
                )

            if (self.report_id > 0xF0 and len(self.data) >= 6 and self.data[5] in reports):
                outstr += "DBG::\t\t \tSensor Report Type: %s(%s)\n" % (reports[self.data[5]], hex(self.data[5]),)

            if (self.report_id == 0xFC and len(self.data) >= 6 and self.data[1] in reports):
                outstr += "DBG::\t\t \tEnabled Feature: %s(%s)\n" % (
                    reports[self.data[1]],
                    hex(self.data[5]),
                )
        outstr += "DBG::\t\t Sequence number: %s\n" % self.header.sequence_number
        outstr += "\n"
        outstr += "DBG::\t\t Data:"

        for idx, packet_byte in enumerate(self.data[:length]):
            packet_index = idx + 4
            if (packet_index % 4) == 0:
                outstr += "\nDBG::\t\t[0x{:02X}] ".format(packet_index)
            outstr += "0x{:02X} ".format(packet_byte)
        outstr += "\n"
        outstr += "\t\t*******************************\n"

        return outstr

    @property
    def report_id(self):
        """The Packet's Report ID"""
        return self.data[0]

    @property
    def channel_number(self):
        """The packet channel"""
        return self.header.channel_number

    @classmethod
    def header_from_buffer(cls, packet_bytes):
        """Creates a `PacketHeader` object from a given buffer"""
        packet_byte_count = unpack_from("<H", packet_bytes)[0]
        packet_byte_count &= ~0x8000
        channel_number = unpack_from("<B", packet_bytes, offset=2)[0]
        sequence_number = unpack_from("<B", packet_bytes, offset=3)[0]
        data_length = max(0, packet_byte_count - 4)

        header = PacketHeader(
            channel_number, sequence_number, data_length, packet_byte_count
        )
        return header

    @classmethod
    def is_error(cls, header):
        """Returns True if the header is an error condition"""

        if header.channel_number > 5:
            return True
        if header.packet_byte_count == 0xFFFF and header.sequence_number == 0xFF:
            return True
        return False


class BNO08X:  # pylint: disable=too-many-instance-attributes, too-many-public-methods
    """Library for the BNO08x IMUs from Hillcrest Laboratories

    :param ~busio.I2C i2c_bus: The I2C bus the BNO08x is connected to.

    """

    def __init__(self, reset=None, rate=10, debug=False, sh_debug=False):
        self._debug = debug
        self.sh_debug = sh_debug
        self._reset = reset
        self._dbg("********** __init__ *************")
        self._data_buffer = bytearray(DATA_BUFFER_SIZE)
        self._command_buffer = bytearray(12)
        self._packet_slices = []

        # TODO: this is wrong there should be one per channel per direction
        self._sequence_number = [0, 0, 0, 0, 0, 0]
        self._two_ended_sequence_numbers = {
            "send": {},  # holds the next seq number to send with the report id as a key
            "receive": {},
        }
        self._dcd_saved_at = -1
        self._me_calibration_started_at = -1
        self._calibration_complete = False
        self._magnetometer_accuracy = 0
        self._accuracy_estimate = 3.141593
        self._processed_count = 0
        self._wait_for_initialize = True
        self._init_complete = False
        self._id_read = False
        self._frs_status = 0
        self._report_rotation = False
        self.rate = rate
        self.report_interval = int((1 / rate)*1000000) # report interval (uS)
        self.report_timeout = int(self.report_interval/1000 + 20) # report timeout (mS) - irq gpio mode
        self.report_polling = (1 / rate) / 10 # report polling perod (S) - polling mode
        # for saving the most recent reading when decoding several packets
        self._readings = {}
        self.initialize()

    def initialize(self):
        """Initialize the sensor"""
        self.hard_reset()
        self.soft_reset()
        time.sleep(1.0)
        self._check_id()
        # enable reports
        self.enable_feature(BNO_REPORT_MAGNETOMETER, _MAGNETOMETER_REPORT_INTERVAL)
        self.enable_feature(BNO_REPORT_ACCELEROMETER, self.report_interval)
        self.enable_feature(BNO_REPORT_ROTATION_VECTOR, self.report_interval)
        self.enable_feature(BNO_REPORT_GYROSCOPE, self.report_interval)

    def send_command(self, data):
        """Send a packet to device"""
        self._send_packet(_BNO_CHANNEL_CONTROL, data)

    def process_available_packets(self):
        """Process all available packets before reading data from IMU """
        self._process_available_packets()

    def getIMUData(self):
        """Get IMU Data """
        t0 = time.monotonic()
        while True:
            ##############
            # Begin / TODO: check CysBOX hardware version
            # IMU interrupt is usable only with CysBOX hardware version >= 3 using buily-in BNO085
            #
            # In this case, it's better to wait for gpio edge as follow:
            # gpio.wait_for_edge(BNO08X_DEFAULT_GPIO, gpio.FALLING, timeout=self.report_timeout)
            # while gpio.input(BNO08X_DEFAULT_GPIO) == 0:
            #    self._process_available_packets()
            #
            self._processed_count = 0
            while self._processed_count == 0:
                self._process_available_packets()
                if self._processed_count != 0:
                    break
                else:
                    time.sleep(self.report_polling)
            # End / TODO
            ############
            tw = time.monotonic() - t0
            if self._report_rotation is True:
                # print("IMU - Rotation vector receive, reports number and time : ", self._processed_count, tw)
                break
            elif tw > self.report_timeout*2 :
                print("IMU - Error, rotation report timeout : ", tw)
            else:
                # print("IMU - Read reports number and time : ", self._processed_count, tw)
                continue

        IMUData = {}       
        # acceleration
        x, y, z = self.acceleration
        IMUData['accel'] = (y, x, -z)
        # gyro
        x, y, z = self.gyro
        IMUData['gyro'] = (y, x, -z)
        # quaternion
        q_x, q_y, q_z, q_w = self.quaternion
        q = normalize((q_w, q_y, q_x, -q_z))
        IMUData['fusionQPose'] = q
        # euler angles
        x, y, z = toeuler(q)
        IMUData['fusionPose'] = (x, y, z)

        return IMUData

    @property
    def magnetic(self):
        """A tuple of the current magnetic field measurements on the X, Y, and Z axes"""
        # self._process_available_packets()  # decorator?
        try:
            return self._readings[BNO_REPORT_MAGNETOMETER]
        except KeyError:
            raise RuntimeError("No magfield report found, is it enabled?") from None

    @property
    def quaternion(self):
        """A quaternion representing the current rotation vector"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_ROTATION_VECTOR]
        except KeyError:
            raise RuntimeError("No quaternion report found, is it enabled?") from None

    @property
    def geomagnetic_quaternion(self):
        """A quaternion representing the current geomagnetic rotation vector"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR]
        except KeyError:
            raise RuntimeError(
                "No geomag quaternion report found, is it enabled?"
            ) from None

    @property
    def game_quaternion(self):
        """A quaternion representing the current rotation vector expressed as a quaternion with no
        specific reference for heading, while roll and pitch are referenced against gravity. To
        prevent sudden jumps in heading due to corrections, the `game_quaternion` property is not
        corrected using the magnetometer. Some drift is expected"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_GAME_ROTATION_VECTOR]
        except KeyError:
            raise RuntimeError(
                "No game quaternion report found, is it enabled?"
            ) from None

    @property
    def steps(self):
        """The number of steps detected since the sensor was initialized"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_STEP_COUNTER]
        except KeyError:
            raise RuntimeError("No steps report found, is it enabled?") from None

    @property
    def linear_acceleration(self):
        """A tuple representing the current linear acceleration values on the X, Y, and Z
        axes in meters per second squared"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_LINEAR_ACCELERATION]
        except KeyError:
            raise RuntimeError("No lin. accel report found, is it enabled?") from None

    @property
    def acceleration(self):
        """A tuple representing the acceleration measurements on the X, Y, and Z
        axes in meters per second squared"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_ACCELEROMETER]
        except KeyError:
            raise RuntimeError("No accel report found, is it enabled?") from None

    @property
    def gyro(self):
        """A tuple representing Gyro's rotation measurements on the X, Y, and Z
        axes in radians per second"""
        # self._process_available_packets()
        try:
            return self._readings[BNO_REPORT_GYROSCOPE]
        except KeyError:
            raise RuntimeError("No gyro report found, is it enabled?") from None

    @property
    def shake(self):
        """True if a shake was detected on any axis since the last time it was checked

        This property has a "latching" behavior where once a shake is detected, it will stay in a
        "shaken" state until the value is read. This prevents missing shake events but means that
        this property is not guaranteed to reflect the shake state at the moment it is read
        """
        # self._process_available_packets()
        try:
            shake_detected = self._readings[BNO_REPORT_SHAKE_DETECTOR]
            # clear on read
            if shake_detected:
                self._readings[BNO_REPORT_SHAKE_DETECTOR] = False
            return shake_detected
        except KeyError:
            raise RuntimeError("No shake report found, is it enabled?") from None

    @property
    def stability_classification(self):
        """Returns the sensor's assessment of it's current stability, one of:

        * "Unknown" - The sensor is unable to classify the current stability
        * "On Table" - The sensor is at rest on a stable surface with very little vibration
        * "Stationary" -  The sensor’s motion is below the stable threshold but\
        the stable duration requirement has not been met. This output is only available when\
        gyro calibration is enabled
        * "Stable" - The sensor’s motion has met the stable threshold and duration requirements.
        * "In motion" - The sensor is moving.

        """
        # self._process_available_packets()
        try:
            stability_classification = self._readings[BNO_REPORT_STABILITY_CLASSIFIER]
            return stability_classification
        except KeyError:
            raise RuntimeError(
                "No stability classification report found, is it enabled?"
            ) from None

    @property
    def activity_classification(self):
        """Returns the sensor's assessment of the activity that is creating the motions\
        that it is sensing, one of:

        * "Unknown"
        * "In-Vehicle"
        * "On-Bicycle"
        * "On-Foot"
        * "Still"
        * "Tilting"
        * "Walking"
        * "Running"
        * "On Stairs"

        """
        # self._process_available_packets()
        try:
            activity_classification = self._readings[BNO_REPORT_ACTIVITY_CLASSIFIER]
            return activity_classification
        except KeyError:
            raise RuntimeError(
                "No activity classification report found, is it enabled?"
            ) from None

    @property
    def raw_acceleration(self):
        """Returns the sensor's raw, unscaled value from the accelerometer registers"""
        # self._process_available_packets()
        try:
            raw_acceleration = self._readings[BNO_REPORT_RAW_ACCELEROMETER]
            return raw_acceleration
        except KeyError:
            raise RuntimeError(
                "No raw acceleration report found, is it enabled?"
            ) from None

    @property
    def raw_gyro(self):
        """Returns the sensor's raw, unscaled value from the gyro registers"""
        # self._process_available_packets()
        try:
            raw_gyro = self._readings[BNO_REPORT_RAW_GYROSCOPE]
            return raw_gyro
        except KeyError:
            raise RuntimeError("No raw gyro report found, is it enabled?") from None

    @property
    def raw_magnetic(self):
        """Returns the sensor's raw, unscaled value from the magnetometer registers"""
        # self._process_available_packets()
        try:
            raw_magnetic = self._readings[BNO_REPORT_RAW_MAGNETOMETER]
            return raw_magnetic
        except KeyError:
            raise RuntimeError("No raw magnetic report found, is it enabled?") from None

    def begin_calibration(self):
        """Begin the sensor's self-calibration routine"""
        # start calibration for accel, gyro, and mag
        self._send_me_command(
            [
                1,  # calibrate accel
                1,  # calibrate gyro
                1,  # calibrate mag
                _ME_CAL_CONFIG,
                0,  # calibrate planar acceleration
                0,  # 'on_table' calibration
                0,  # reserved
                0,  # reserved
                0,  # reserved
            ]
        )
        self._calibration_complete = False

    @property
    def calibration_status(self):
        """Get the status of the self-calibration"""
        self._send_me_command(
            [
                0,  # calibrate accel
                0,  # calibrate gyro
                0,  # calibrate mag
                _ME_GET_CAL,
                0,  # calibrate planar acceleration
                0,  # 'on_table' calibration
                0,  # reserved
                0,  # reserved
                0,  # reserved
            ]
        )
        return self._magnetometer_accuracy

    @property
    def accuracy_estimate(self):
        """Get the latest accuracy estimate of rotation vector report"""
        return self._accuracy_estimate

    def _send_me_command(self, subcommand_params):

        start_time = time.monotonic()
        local_buffer = self._command_buffer
        _insert_command_request_report(
            _ME_CALIBRATE,
            self._command_buffer,  # should use self._data_buffer :\ but send_packet don't
            self._get_report_seq_id(_COMMAND_REQUEST),
            subcommand_params,
        )
        self._send_packet(_BNO_CHANNEL_CONTROL, local_buffer)
        self._increment_report_seq(_COMMAND_REQUEST)
        while _elapsed(start_time) < _DEFAULT_TIMEOUT:
            self._process_available_packets()
            if self._me_calibration_started_at > start_time:
                break

    def save_calibration_data(self):
        """Save the self-calibration data"""
        # send a DCD save command
        start_time = time.monotonic()
        local_buffer = bytearray(12)
        _insert_command_request_report(
            _SAVE_DCD,
            local_buffer,  # should use self._data_buffer :\ but send_packet don't
            self._get_report_seq_id(_COMMAND_REQUEST),
        )
        self._send_packet(_BNO_CHANNEL_CONTROL, local_buffer)
        self._increment_report_seq(_COMMAND_REQUEST)
        while _elapsed(start_time) < _DEFAULT_TIMEOUT:
            self._process_available_packets()
            if self._dcd_saved_at > start_time:
                return
        raise RuntimeError("Could not save calibration data")

    ############### private/helper methods ###############
    # # decorator?
    def _process_available_packets(self, max_packets=None):
        self._report_rotation = False
        processed_count = 0
        while True:
            if max_packets and processed_count > max_packets:
                return
            try:
                new_packet = self._read_packet()
            except PacketError:
                continue
            if new_packet.header.data_length == 0:
                break
            self._handle_packet(new_packet)
            processed_count += 1
        self._processed_count = processed_count
        self._dbg("")
        self._dbg(" ** DONE! **")

    def _wait_for_packet_type(self, channel_number, report_id=None, timeout=5.0):
        if report_id:
            report_id_str = " with report id %s" % hex(report_id)
        else:
            report_id_str = ""
        self._dbg("** Waiting for packet on channel", channel_number, report_id_str)
        start_time = time.monotonic()
        while _elapsed(start_time) < timeout:
            new_packet = self._wait_for_packet()

            if new_packet.channel_number == channel_number:
                if report_id:
                    if new_packet.report_id == report_id:
                        return new_packet
                else:
                    return new_packet
            if new_packet.channel_number not in (BNO_CHANNEL_EXE, BNO_CHANNEL_SHTP_COMMAND,):
                self._dbg("passing packet to handler for de-slicing")
                self._handle_packet(new_packet)

        raise RuntimeError("Timed out waiting for a packet on channel", channel_number)

    def _wait_for_packet(self, timeout=_PACKET_READ_TIMEOUT):
        start_time = time.monotonic()
        while _elapsed(start_time) < timeout:
            new_packet = self._read_packet()
            if new_packet.header.data_length != 0:
                return new_packet
        raise RuntimeError("Timed out waiting for a packet")

    def _update_sequence_number(self, header):
        self._sequence_number[header.channel_number] = header.sequence_number
        # print("New packet -> Length, Header channel and sequence : ", header.data_length, header.channel_number, header.sequence_number)

    def _handle_packet(self, packet):
        # split out reports first
        try:
            _separate_batch(packet, self._packet_slices)
            while self._packet_slices:
                self._process_report(*self._packet_slices.pop())
        except Exception as error:
            print(packet)
            raise error

    def _handle_control_report(self, report_id, report_bytes):
        if report_id == _SHTP_REPORT_PRODUCT_ID_RESPONSE:
            (
                sw_part_number,
                sw_major,
                sw_minor,
                sw_patch,
                sw_build_number,
            ) = parse_sensor_id(report_bytes)
            self._dbg("FROM PACKET SLICE:")
            self._dbg("*** Part Number: %d" % sw_part_number)
            self._dbg("*** Software Version: %d.%d.%d" % (sw_major, sw_minor, sw_patch))
            self._dbg("\tBuild: %d" % (sw_build_number))
            self._dbg("")

        if report_id == _GET_FEATURE_RESPONSE:
            get_feature_report = _parse_get_feature_response_report(report_bytes)
            _report_id, feature_report_id, *_remainder = get_feature_report
            self._readings[feature_report_id] = _INITIAL_REPORTS.get(
                feature_report_id, (0.0, 0.0, 0.0)
            )

        if report_id == _COMMAND_RESPONSE:
            self._handle_command_response(report_bytes)

        if report_id == _FRS_WRITE_RESPONSE:
            self._frs_status = report_bytes[1]

    def _handle_command_response(self, report_bytes):
        (report_body, response_values) = _parse_command_response(report_bytes)

        (
            _report_id,
            _seq_number,
            command,
            _command_seq_number,
            _response_seq_number,
        ) = report_body

        # status, accel_en, gyro_en, mag_en, planar_en, table_en, *_reserved) = response_values
        command_status, *_rest = response_values

        if command == _ME_CALIBRATE and command_status == 0:
            self._me_calibration_started_at = time.monotonic()

        if command == _SAVE_DCD:
            if command_status == 0:
                self._dcd_saved_at = time.monotonic()
            else:
                raise RuntimeError("Unable to save calibration data")

    def _process_report(self, report_id, report_bytes):
        if report_id >= 0xF0:
            self._handle_control_report(report_id, report_bytes)
            return
        self._dbg("\tProcessing report:", reports[report_id])
        if self._debug:
            outstr = ""
            for idx, packet_byte in enumerate(report_bytes):
                packet_index = idx
                if (packet_index % 4) == 0:
                    outstr += "\nDBG::\t\t[0x{:02X}] ".format(packet_index)
                outstr += "0x{:02X} ".format(packet_byte)
            self._dbg(outstr)
            self._dbg("")

        if report_id == BNO_REPORT_STEP_COUNTER:
            self._readings[report_id] = _parse_step_couter_report(report_bytes)
            return

        if report_id == BNO_REPORT_SHAKE_DETECTOR:
            shake_detected = _parse_shake_report(report_bytes)
            # shake not previously detected - auto cleared by 'shake' property
            try:
                if not self._readings[BNO_REPORT_SHAKE_DETECTOR]:
                    self._readings[BNO_REPORT_SHAKE_DETECTOR] = shake_detected
            except KeyError:
                pass
            return

        if report_id == BNO_REPORT_STABILITY_CLASSIFIER:
            stability_classification = _parse_stability_classifier_report(report_bytes)
            self._readings[BNO_REPORT_STABILITY_CLASSIFIER] = stability_classification
            return

        if report_id == BNO_REPORT_ACTIVITY_CLASSIFIER:
            activity_classification = _parse_activity_classifier_report(report_bytes)
            self._readings[BNO_REPORT_ACTIVITY_CLASSIFIER] = activity_classification
            return

        sensor_data, accuracy = _parse_sensor_report_data(report_bytes)
        self._readings[report_id] = sensor_data
        if report_id == BNO_REPORT_MAGNETOMETER:
            self._magnetometer_accuracy = accuracy
        elif report_id == BNO_REPORT_ROTATION_VECTOR or report_id == BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR:
            self._accuracy_estimate = accuracy
            self._report_rotation = True
        

    # TODO: Make this a Packet creation
    @staticmethod
    def _get_feature_enable_report(feature_id, report_interval=_DEFAULT_REPORT_INTERVAL, sensor_specific_config=0):
        set_feature_report = bytearray(17)
        set_feature_report[0] = _SET_FEATURE_COMMAND
        set_feature_report[1] = feature_id
        pack_into("<I", set_feature_report, 5, report_interval)
        pack_into("<I", set_feature_report, 13, sensor_specific_config)

        return set_feature_report

    # TODO: add docs for available features
    # TODO2: I think this should call an fn that imports all the bits for the given feature
    # so we're not carrying around  stuff for extra features
    def enable_feature(self, feature_id, report_interval=_DEFAULT_REPORT_INTERVAL):
        """Used to enable a given feature of the BNO08x"""
        self._dbg("\n********** Enabling feature id:", feature_id, "**********")

        if feature_id == BNO_REPORT_ACTIVITY_CLASSIFIER:
            set_feature_report = self._get_feature_enable_report(
                feature_id, report_interval=report_interval, sensor_specific_config=_ENABLED_ACTIVITIES
            )
        else:
            set_feature_report = self._get_feature_enable_report(feature_id, report_interval=report_interval)

        feature_dependency = _RAW_REPORTS.get(feature_id, None)
        # if the feature was enabled it will have a key in the readings dict
        if feature_dependency and feature_dependency not in self._readings:
            self._dbg("Enabling feature depencency:", feature_dependency)
            self.enable_feature(feature_dependency)

        self._dbg("Enabling", feature_id)
        self._send_packet(_BNO_CHANNEL_CONTROL, set_feature_report)

        start_time = time.monotonic()  # 1

        while _elapsed(start_time) < _FEATURE_ENABLE_TIMEOUT:
            self._process_available_packets(max_packets=10)
            if feature_id in self._readings:
                return
        raise RuntimeError("Was not able to enable feature", feature_id)

    def _check_id(self):
        self._dbg("\n********** READ ID **********")
        if self._id_read:
            return True
        data = bytearray(2)
        data[0] = _SHTP_REPORT_PRODUCT_ID_REQUEST
        data[1] = 0  # padding
        self._dbg("\n** Sending ID Request Report **")
        self._send_packet(_BNO_CHANNEL_CONTROL, data)
        self._dbg("\n** Waiting for packet **")
        # _a_ packet arrived, but which one?
        while True:
            self._wait_for_packet_type(
                _BNO_CHANNEL_CONTROL, _SHTP_REPORT_PRODUCT_ID_RESPONSE
            )
            sensor_id = self._parse_sensor_id()
            if sensor_id:
                self._id_read = True
                return True
            self._dbg("Packet didn't have sensor ID report, trying again")

        return False

    def _parse_sensor_id(self):
        if not self._data_buffer[4] == _SHTP_REPORT_PRODUCT_ID_RESPONSE:
            return None

        sw_major = self._get_data(2, "<B")
        sw_minor = self._get_data(3, "<B")
        sw_patch = self._get_data(12, "<H")
        sw_part_number = self._get_data(4, "<I")
        sw_build_number = self._get_data(8, "<I")

        self._dbg("")
        self._dbg("*** Part Number: %d" % sw_part_number)
        self._dbg("*** Software Version: %d.%d.%d" % (sw_major, sw_minor, sw_patch))
        self._dbg(" Build: %d" % (sw_build_number))
        self._dbg("")
        # Print Product Id
        print("*** BNO08X / Software Version: %d.%d.%d" % (sw_major, sw_minor, sw_patch))
        print("*** BNO08X / Build: %d" % (sw_build_number))
        # TODO: this is only one of the numbers!
        return sw_part_number

    def _dbg(self, *args, **kwargs):
        if self._debug:
            print("DBG::\t\t", *args, **kwargs)

    def _get_data(self, index, fmt_string):
        # index arg is not including header, so add 4 into data buffer
        data_index = index + 4
        return unpack_from(fmt_string, self._data_buffer, offset=data_index)[0]

    def hard_reset(self):
        """Hardware reset the sensor to an initial unconfigured state"""
        if not self._reset:
            return
        import digitalio

        self._reset.direction = digitalio.Direction.OUTPUT
        self._reset.value = True
        time.sleep(0.01)
        self._reset.value = False
        time.sleep(0.01)
        self._reset.value = True
        time.sleep(0.01)

    def soft_reset(self):
        """Reset the sensor to an initial unconfigured state"""
        self._dbg("Soft resetting...", end="")
        data = bytearray(1)
        data[0] = 1
        _seq = self._send_packet(BNO_CHANNEL_EXE, data)
        time.sleep(1.0)

        for _i in range(3):
            try:
                _packet = self._read_packet()
            except PacketError:
                time.sleep(0.5)

        self._dbg("OK!")
        # all is good!

    def _send_packet(self, channel, data):
        print("Error : _send_packet Not implemented")
        return 0

    def _read_packet(self):
        print("Error : _read_packet Not implemented")
        return Packet((0, 0, 0, 0))

    def _increment_report_seq(self, report_id):
        current = self._two_ended_sequence_numbers.get(report_id, 0)
        self._two_ended_sequence_numbers[report_id] = (current + 1) % 256

    def _get_report_seq_id(self, report_id):
        return self._two_ended_sequence_numbers.get(report_id, 0)

    def set_orientation(self, orientation):
        qx = int(orientation[0] / _Q_POINT_30_SCALAR)
        qy = int(orientation[1] / _Q_POINT_30_SCALAR)
        qz = int(orientation[2] / _Q_POINT_30_SCALAR)
        qw = int(orientation[3] / _Q_POINT_30_SCALAR)
        # FRS Write Request
        frs = bytearray(6)
        frs[0] = _FRS_WRITE_REQUEST
        frs[1] = 0 # reserved
        frs[2] = 4 # length LSB
        frs[3] = 0 # length MSB
        frs[4] = 0x3E # FRS Type LSB
        frs[5] = 0x2D # FRS Type MSB
        if self._send_frs(frs) != 4:
            return False
        # FRS Write Data Request #1
        frs = bytearray(12)
        frs[0] = _FRS_WRITE_DATA
        frs[1] = 0 # reserved
        frs[2] = 0 # offset LSB
        frs[3] = 0 # offset MSB
        pack_into("<l", frs, 4, qx)
        pack_into("<l", frs, 8, qy)
        if self._send_frs(frs) != 0:
            return False
        # FRS Write Data Request #2
        frs[2] = 2 # offset LSB
        frs[3] = 0 # offset MSB
        pack_into("<l", frs, 4, qz)
        pack_into("<l", frs, 8, qw)
        if self._send_frs(frs) != 3:
            return False
        return True

    def _send_frs(self, frs):
        self._send_packet(_BNO_CHANNEL_CONTROL, frs)
        start_time = time.monotonic()
        self._frs_status = 0
        while  _elapsed(start_time) < _DEFAULT_TIMEOUT:
            self._process_available_packets(max_packets=10)
            if self._frs_status == 0 or self._frs_status == 3 or self._frs_status == 4:
                return self._frs_status
        return False

"""

    Subclass of `adafruit_bno08x.BNO08X` to use I2C

"""

BNO08X_DEFAULT_ADDRESS = const(0x4A)
BNO08X_DEFAULT_GPIO = const(24)

class BNO08X_I2C(BNO08X):
    """Library for the BNO08x IMUs from Hillcrest Laboratories

    :param ~busio.I2C i2c_bus: The I2C bus the BNO08x is connected to.

    """

    def __init__(self, i2c, rate=10, reset=None, address=BNO08X_DEFAULT_ADDRESS, debug=False):
        self.bus_device_obj = I2CDevice(i2c, address)
        super().__init__(reset, rate, debug)
        # activate IMU irq input
        gpio.setmode(gpio.BCM)
        gpio.setup(BNO08X_DEFAULT_GPIO, gpio.IN, pull_up_down=gpio.PUD_UP)

    def _send_packet(self, channel, data):
        data_length = len(data)
        write_length = data_length + 4

        pack_into("<H", self._data_buffer, 0, write_length)
        self._data_buffer[2] = channel
        self._data_buffer[3] = self._sequence_number[channel]
        for idx, send_byte in enumerate(data):
            self._data_buffer[4 + idx] = send_byte
        packet = Packet(self._data_buffer)
        self._dbg("Sending packet:")
        self._dbg(packet)
        # protocol debug:
        if self.sh_debug:
            print("Sending packet:")
            print(packet)
        with self.bus_device_obj as i2c:
            i2c.write(self._data_buffer, end=write_length)

        self._sequence_number[channel] = (self._sequence_number[channel] + 1) % 256
        return self._sequence_number[channel]

    # returns packet if available data was read
    # the sensor will always tell us how much there is, so no need to track it ourselves

    def _read_packet(self):
        with self.bus_device_obj as i2c:
            i2c.readinto(self._data_buffer, end=4)  # this is expecting a header?
        new_packet = Packet(self._data_buffer)

        header = new_packet.header
        self._update_sequence_number(header)

        if header.data_length != 0:
            self._dbg(
                "channel",
                header.channel_number,
                "has",
                header.packet_byte_count,
                "bytes available to read",
            )
            self._dbg("trying to read", header.packet_byte_count, "bytes")
            if header.packet_byte_count > DATA_BUFFER_SIZE:
                self._data_buffer = bytearray(header.packet_byte_count)
                self._dbg(
                    "!!!!!!!!!!!! ALLOCATION: increased _data_buffer to bytearray(%d) !!!!!!!!!!!!! "
                    % header.packet_byte_count
                )
            with self.bus_device_obj as i2c:
                i2c.readinto(self._data_buffer, end=header.packet_byte_count)

            new_packet = Packet(self._data_buffer)
            self._update_sequence_number(new_packet.header)

            if self.sh_debug and header.channel_number == _BNO_CHANNEL_CONTROL:
                print("Received packet:")
                print(new_packet)

        return new_packet
