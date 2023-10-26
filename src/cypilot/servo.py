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

import math
import sys
import time
import fcntl
import serial

import cypilot.pilot_path
from client import cypilotClient
from pilot_values import Value, Property, SensorValue, RangeSetting, RangeProperty, ResettableValue, BooleanValue, StringValue
import serials
from kbhit import KBHit

from pilot_path import dprint as print # pylint: disable=locally-disabled, redefined-builtin

PILOT_DIR = cypilot.pilot_path.PILOT_DIR

# these are not defined in python module
TIOCEXCL = 0x540C
TIOCNXCL = 0x540D

class ServoFlags(Value):

    # Motor Driver Flags values:
    SYNC                    = 0b00000001 << 0
    OVERTEMP_FAULT          = 0b00000010 << 0
    OVERCURRENT_FAULT       = 0b00000100 << 0
    ENGAGED                 = 0b00001000 << 0
    INVALID                 = 0b00010000 << 0
    PORT_PIN_FAULT          = 0b00100000 << 0
    STARBOARD_PIN_FAULT     = 0b01000000 << 0
    BADVOLTAGE_FAULT        = 0b10000000 << 0

    MIN_RUDDER_FAULT        = 0b00000001 << 8
    MAX_RUDDER_FAULT        = 0b00000010 << 8
    CURRENT_RANGE           = 0b00000100 << 8 # only for compatibility
    BAD_FUSES               = 0b00001000 << 8
    REBOOTED                = 0b10000000 << 8

    DRIVER_MASK             = 0b1111111111111111

    # Servo Flags values:
    PORT_OVERCURRENT_FAULT      = 0b00000001 << 16
    STARBOARD_OVERCURRENT_FAULT = 0b00000010 << 16
    DRIVER_TIMEOUT              = 0b00000100 << 16
    SATURATED                   = 0b00001000 << 16

    def __init__(self, name):
        super(ServoFlags, self).__init__(name, 0)

    def get_str(self):
        ret = ""
        if self.value & self.SYNC:
            ret += 'SYNC '
        if self.value & self.OVERTEMP_FAULT:
            ret += 'OVERTEMP_FAULT '
        if self.value & self.OVERCURRENT_FAULT:
            ret += 'OVERCURRENT_FAULT '
        if self.value & self.ENGAGED:
            ret += 'ENGAGED '
        if self.value & self.INVALID:
            ret += 'INVALID '
        if self.value & self.PORT_PIN_FAULT:
            ret += 'PORT_PIN_FAULT '
        if self.value & self.STARBOARD_PIN_FAULT:
            ret += 'STARBOARD_PIN_FAULT '
        if self.value & self.BADVOLTAGE_FAULT:
            ret += 'BADVOLTAGE_FAULT '
        if self.value & self.MIN_RUDDER_FAULT:
            ret += 'MIN_RUDDER_FAULT '
        if self.value & self.MAX_RUDDER_FAULT:
            ret += 'MAX_RUDDER_FAULT '
        if self.value & self.BAD_FUSES:
            ret += 'BAD_FUSES '
        if self.value & self.PORT_OVERCURRENT_FAULT:
            ret += 'PORT_OVERCURRENT_FAULT '
        if self.value & self.STARBOARD_OVERCURRENT_FAULT:
            ret += 'STARBOARD_OVERCURRENT_FAULT '
        if self.value & self.DRIVER_TIMEOUT:
            ret += 'DRIVER_TIMEOUT '
        if self.value & self.SATURATED:
            ret += 'SATURATED '
        if self.value & self.REBOOTED:
            ret += 'REBOOTED'
        return ret

    def get_msg(self):
        return '"' + self.get_str().strip() + '"'

    def setbit(self, bit, t=True):
        if t:
            self.update(self.value | bit)
        else:
            self.update(self.value & ~bit)

    def clearbit(self, bit):
        self.setbit(bit, False)

    def port_overcurrent_fault(self):
        self.update((self.value | ServoFlags.PORT_OVERCURRENT_FAULT)
                    & ~ServoFlags.STARBOARD_OVERCURRENT_FAULT)

    def starboard_overcurrent_fault(self):
        self.update((self.value | ServoFlags.STARBOARD_OVERCURRENT_FAULT)
                    & ~ServoFlags.PORT_OVERCURRENT_FAULT)


class ServoTelemetry(object):
    FLAGS = 1
    CURRENT = 2
    VOLTAGE = 4
    SPEED = 8
    POSITION = 16
    CONTROLLER_TEMP = 32
    MOTOR_TEMP = 64
    RUDDER = 128
    EEPROM = 256
    VERSION_FIRMWARE = 512

# a property which records the time when it is updated

class TimedProperty(Property):
    def __init__(self, name):
        super(TimedProperty, self).__init__(name, 0)
        self.time = 0

    def set(self, value):
        self.time = time.monotonic()
        return super(TimedProperty, self).set(value)


class TimeoutSensorValue(SensorValue):
    def __init__(self, name):
        super(TimeoutSensorValue, self).__init__(name, False, fmt='%.3f')

    def set(self, value):
        self.time = time.monotonic()
        super(TimeoutSensorValue, self).set(value)

    def timeout(self):
        if self.value and time.monotonic() - self.time > 8:
            self.set(False)

# range setting bounded pairs, don't let max setting below min setting, and ensure max is at least min

class MinRangeSetting(RangeSetting):
    def __init__(self, name, initial, min_value, max_value, units, minvalue, **kwargs):
        self.minvalue = minvalue
        minvalue.maxvalue = self
        super(MinRangeSetting, self).__init__(
            name, initial, min_value, max_value, units, **kwargs)

    def set(self, value):
        if value < self.minvalue.value:
            value = self.minvalue.value
        super(MinRangeSetting, self).set(value)


class MaxRangeSetting(RangeSetting):
    def __init__(self, name, initial, min_value, max_value, units, **kwargs):
        self.maxvalue = None
        super(MaxRangeSetting, self).__init__(
            name, initial, min_value, max_value, units, **kwargs)

    def set(self, value):
        if self.maxvalue and value > self.maxvalue.value:
            self.maxvalue.set(value)
        super(MaxRangeSetting, self).set(value)


class Servo(object):
    def __init__(self, client, sensors):
        self.client = client
        self.sensors = sensors
        self.lastdir = 0  # doesn't matter
        self.device = None
        self.lastpolltime = 0

        self.version_firmware = self.register(Value,'version_firmware',0)

        self.position_command = self.register(TimedProperty, 'position_command')
        self.command = self.register(TimedProperty, 'command')

        self.faults = self.register(ResettableValue, 'faults', 0, persistent=True)

        # power usage
        self.voltage = self.register(SensorValue, 'voltage')
        self.current = self.register(SensorValue, 'current')
        self.current.lasttime = time.monotonic()
        self.controller_temp = self.register(TimeoutSensorValue, 'controller_temp')
        self.motor_temp = self.register(TimeoutSensorValue, 'motor_temp')

        self.engaged = self.register(BooleanValue, 'engaged', False)
        self.max_current = self.register(RangeSetting, 'max_current', 7, 0, 60, 'amps')
        self.current.factor = self.register(RangeProperty, 'current.factor', 1, 0.8, 1.2, persistent=True)
        self.current.offset = self.register(RangeProperty, 'current.offset', 0, -1.2, 1.2, persistent=True)
        self.voltage.factor = self.register(RangeProperty, 'voltage.factor', 1, 0.8, 1.2, persistent=True)
        self.voltage.offset = self.register(RangeProperty, 'voltage.offset', 0, -1.2, 1.2, persistent=True)
        self.max_controller_temp = self.register(RangeProperty, 'max_controller_temp', 60, 45, 80, persistent=True)
        self.max_motor_temp = self.register(RangeProperty, 'max_motor_temp', 60, 30, 80, persistent=True)

        self.max_slew_speed = self.register(MaxRangeSetting, 'max_slew_speed', 18, 0, 100, '')
        self.max_slew_slow = self.register(MinRangeSetting, 'max_slew_slow', 28, 0, 100, '', self.max_slew_speed)

        self.brake = self.register(RangeSetting, 'brake', 1, 1, 20, '%')
        self.gain = self.register(RangeProperty, 'gain', 1, -10, 10, persistent=True)
        self.period = self.register(RangeSetting, 'period', .4, .1, 3, 'sec')
        self.amphours = self.register(ResettableValue, 'amp_hours', 0, persistent=True)
        self.watts = self.register(SensorValue, 'watts')

        self.speed = self.register(SensorValue, 'speed')
        self.speed.min = self.register(MaxRangeSetting, 'speed.min', 100, 0, 100, '%')
        self.speed.max = self.register(MinRangeSetting, 'speed.max', 100, 0, 100, '%', self.speed.min)

        self.position = self.register(SensorValue, 'position')
        self.position.set(0)

        self.rawcommand = self.register(SensorValue, 'raw_command')

        self.use_eeprom = self.register(BooleanValue, 'use_eeprom', True, persistent=True)

        self.position.amphours = 0

        self.disengaged = True
        self.ap_engaged = False
        self.force_engaged = False

        self.last_zero_command_time = self.command_timeout = time.monotonic()
        self.driver_timeout_start = 0

        self.state = self.register(StringValue, 'state', 'none')

        self.controller = self.register(StringValue, 'controller', 'none')
        self.flags = self.register(ServoFlags, 'flags')

        self.driver = False
        self.raw_command(0)

    def register(self, _type, name, *args, **kwargs):
        return self.client.register(_type(*(['servo.' + name] + list(args)), **kwargs))

    def send_command(self):
        t = time.monotonic()
        dp = t - self.position_command.time
        dc = t - self.command.time

        if dp < dc and not self.sensors.rudder.invalid():
            timeout = 10  # position command will expire after 10 seconds
            if time.monotonic() - self.position_command.time > timeout:
                #print('servo position_command timeout', time.monotonic() - self.position_command.time)
                self.command.set(0)
                self.raw_command(0)
            else:
                self.disengaged = False
                if abs(self.position.value - self.position_command.value) < 0.5:
                    self.command.set(0)
                else:
                    self.do_position_command(self.position_command.value)
                    return
        elif self.command.value and not self.fault():
            timeout = 1  # command will expire after 1 second
            if time.monotonic() - self.command.time > timeout:
                #print('servo command timeout', time.monotonic() - self.command.time)
                self.command.set(0)
            self.disengaged = False

        self.do_command(self.command.value)

    def do_position_command(self, position):

        # disengage if autopilot not enabled and "force_engaged" is not required, or driver fault
        if not self.ap_engaged and not self.force_engaged \
                or self.fault() \
                or (self.flags.value & (ServoFlags.PORT_OVERCURRENT_FAULT | ServoFlags.BADVOLTAGE_FAULT | ServoFlags.OVERTEMP_FAULT)):
            self.disengaged = True
            self.raw_command(0)
            return

        raw = self.sensors.rudder.angle2raw(position)
        self.raw_angle(raw)

    def do_command(self, speed):

        # if not moving or faulted stop
        if not speed or self.fault():
            if not self.ap_engaged and time.monotonic() - self.command_timeout > self.period.value*3:
                self.disengaged = True
            self.raw_command(0)
            return

        speed *= self.gain.value # apply gain
        # prevent moving the wrong direction if flags set
        if self.flags.value & (ServoFlags.PORT_OVERCURRENT_FAULT | ServoFlags.MAX_RUDDER_FAULT) and speed > 0 or \
           self.flags.value & (ServoFlags.STARBOARD_OVERCURRENT_FAULT | ServoFlags.MIN_RUDDER_FAULT) and speed < 0:
            self.raw_command(0)
            return  # abort

        # clear faults from overcurrent if moved sufficiently the other direction
        rudder_range = self.sensors.rudder.range.value
        if self.position.value < .9*rudder_range:
            self.flags.clearbit(ServoFlags.PORT_OVERCURRENT_FAULT)
        if self.position.value > -.9*rudder_range:
            self.flags.clearbit(ServoFlags.STARBOARD_OVERCURRENT_FAULT)

        min_speed = self.speed.min.value/100.0  # convert percent to 0-1
        max_speed = self.speed.max.value/100.0

        # ensure it is in range
        min_speed = min(min_speed, max_speed)

        # clamp to max speed
        speed = min(max(speed, -max_speed), max_speed)
        self.speed.set(speed)

        # use fixed speed calibration values [.2,.8]
        if speed == 0:
            self.raw_command(0)
            return
        command = .2 + abs(speed)*.8
        if speed < 0:
            command = -command
        self.raw_command(command)

    def raw_command(self, command):

        self.rawcommand.set(command)
        if command <= 0:
            if command < 0:
                self.state.update('reverse')
                self.lastdir = -1
            else:
                self.speed.set(0)
                self.state.update('idle')
        else:
            self.state.update('forward')
            self.lastdir = 1

        t = time.monotonic()
        if command == 0:
            # only send at .2 seconds when command is zero for more than a second
            if t > self.command_timeout + 1 and t - self.last_zero_command_time < .2:
                return
            self.last_zero_command_time = t
        else:
            self.command_timeout = t

        if self.driver:
            if self.disengaged:  # keep sending disengage to keep sync
                self.send_driver_params()
                self.driver.disengage()
            else:
                mul = 1
                if self.flags.value & ServoFlags.PORT_OVERCURRENT_FAULT or \
                   self.flags.value & ServoFlags.STARBOARD_OVERCURRENT_FAULT:  # allow more current to "unstuck" ram
                    mul = 2
                self.send_driver_params(mul)
                self.driver.command(command)

                # detect driver timeout if commanded without measuring current
                if self.current.value:
                    self.flags.clearbit(ServoFlags.DRIVER_TIMEOUT)
                    self.driver_timeout_start = 0
                elif command:
                    if self.driver_timeout_start:
                        if time.monotonic() - self.driver_timeout_start > 1:
                            self.flags.setbit(ServoFlags.DRIVER_TIMEOUT)
                    else:
                        self.driver_timeout_start = time.monotonic()

    def raw_angle(self, angle):
        if self.driver:
            if self.disengaged:  # keep sending disengage to keep sync
                self.send_driver_params()
                self.driver.disengage()
            else:
                self.send_driver_params()
                self.driver.angle(angle)

    def reset(self):
        if self.driver:
            self.driver.reset()

    def close_driver(self):
        #print('servo lost connection')
        self.controller.update('none')
        self.sensors.rudder.update(False)
        self.device.close()
        self.driver = False

    def send_driver_params(self, mul=1):
        uncorrected_max_current = max(
            0, self.max_current.value - self.current.offset.value) / self.current.factor.value
        minmax = self.sensors.rudder.minmax
        self.driver.params(mul * uncorrected_max_current,
                           minmax[0], minmax[1],
                           self.max_current.value,
                           self.max_controller_temp.value,
                           self.max_motor_temp.value,
                           self.sensors.rudder.range.value,
                           self.sensors.rudder.offset.value,
                           self.sensors.rudder.scale.value,
                           self.sensors.rudder.nonlinearity.value,
                           self.max_slew_speed.value,
                           self.max_slew_slow.value,
                           self.current.factor.value,
                           self.current.offset.value,
                           self.voltage.factor.value,
                           self.voltage.offset.value,
                           self.speed.min.value,
                           self.speed.max.value,
                           self.gain.value,
                           self.brake.value)

    def poll(self):
        if not self.driver:
            list_serials = serials.list_serials("servo")
            if list_serials:
                device_path = list_serials[0].path
                baud = list_serials[0].baudrate
                print('servo probe', device_path, baud, time.monotonic())
                try:
                    device = serial.Serial(device_path, baud)
                except Exception as e:
                    print('failed to open servo on:', device_path, e)
                    return

                try:
                    device.timeout = 0  # nonblocking
                    fcntl.ioctl(device.fileno(), TIOCEXCL)  # exclusive
                except Exception as e:
                    print('failed set nonblocking/exclusive', e)
                    device.close()
                    return
                from arduino_servo.arduino_servo import ArduinoServo

                self.driver = ArduinoServo(device.fileno())
                self.send_driver_params()
                self.device = device
                self.device.path = device_path
                self.lastpolltime = time.monotonic()

        if not self.driver:
            return

        result = self.driver.poll()
        if result == -1:
            print('servo lost')
            self.close_driver()
            return
        t = time.monotonic()
        if result == 0:
            d = t - self.lastpolltime
            if d > 4:
                #print('servo timeout', d)
                self.close_driver()
        else:
            self.lastpolltime = t

            if self.controller.value == 'none':
                device_path = [self.device.port, self.device.baudrate]
                print('arduino servo found on', device_path)
                self.controller.set('Servo')
                self.driver.command(0)

        if result & ServoTelemetry.VOLTAGE:
            # apply correction
            corrected_voltage = self.voltage.factor.value*self.driver.voltage
            corrected_voltage += self.voltage.offset.value
            self.voltage.set(round(corrected_voltage, 3))

        if result & ServoTelemetry.CONTROLLER_TEMP:
            self.controller_temp.set(self.driver.controller_temp)
        if result & ServoTelemetry.MOTOR_TEMP:
            self.motor_temp.set(self.driver.motor_temp)
        if result & ServoTelemetry.RUDDER:
            if self.driver.rudder:
                if math.isnan(self.driver.rudder):  # rudder no longer valid
                    if self.sensors.rudder.source.value == 'servo':
                        self.sensors.lostsensor(self.sensors.rudder)
                else:
                    data = {'angle': self.driver.rudder, 'timestamp': t,
                            'device': self.device.path}
                    self.sensors.write('rudder', data, 'servo')
        if result & ServoTelemetry.CURRENT:
            # apply correction
            corrected_current = self.current.factor.value*self.driver.current
            if self.driver.current:
                corrected_current = max(
                    0, corrected_current + self.current.offset.value)

            self.current.set(round(corrected_current, 3))
            # integrate power consumption
            dt = t - self.current.lasttime
            self.current.lasttime = t
            if self.current.value:
                amphours = self.current.value*dt/3600
                self.amphours.set(self.amphours.value + amphours)
            lp = .003*dt  # 5 minute time constant to average wattage
            self.watts.set((1-lp)*self.watts.value + lp *
                           self.voltage.value*self.current.value)

        if result & ServoTelemetry.FLAGS:
            # self.max_current.set_max(40 if self.driver.flags & ServoFlags.CURRENT_RANGE else 20)
            flags = self.flags.value & ~ServoFlags.DRIVER_MASK | self.driver.flags

            # if rudder angle comes from serial or tcp, may need to set these flags
            # to prevent rudder movement
            angle = self.sensors.rudder.angle.value
            if angle:  # note, this is ok here for both False, 0 and None
                if abs(angle) > self.sensors.rudder.range.value and self.sensors.rudder.calibrated.value:
                    if angle > 0:
                        flags |= ServoFlags.MAX_RUDDER_FAULT
                    else:
                        flags |= ServoFlags.MIN_RUDDER_FAULT
            self.flags.update(flags)
#            self.engaged.update(bool(self.driver.flags) & ServoFlags.ENGAGED)
            self.engaged.update(bool(self.driver.flags & ServoFlags.ENGAGED)) # CYS

        if result & ServoTelemetry.EEPROM and self.use_eeprom.value:  # occurs only once after connecting
            self.max_current.set(self.driver.max_current)
            self.max_controller_temp.set(self.driver.max_controller_temp)
            self.max_motor_temp.set(self.driver.max_motor_temp)
            self.max_slew_speed.set(self.driver.max_slew_speed)
            self.max_slew_slow.set(self.driver.max_slew_slow)
            self.sensors.rudder.scale.set(self.driver.rudder_scale)
            self.sensors.rudder.nonlinearity.set(self.driver.rudder_nonlinearity)
            self.sensors.rudder.offset.set(self.driver.rudder_offset)
            self.sensors.rudder.range.set(self.driver.rudder_range)
            self.sensors.rudder.update_minmax()
            self.current.factor.set(self.driver.current_factor)
            self.current.offset.set(self.driver.current_offset)
            self.voltage.factor.set(self.driver.voltage_factor)
            self.voltage.offset.set(self.driver.voltage_offset)
            self.speed.min.set(self.driver.min_speed)
            self.speed.max.set(self.driver.max_speed)
            self.gain.set(self.driver.gain)
            self.brake.set(self.driver.rudder_brake)

        if result & ServoTelemetry.VERSION_FIRMWARE:
            self.version_firmware.set(self.driver.version_firmware)

        if self.fault():
            if not self.flags.value & ServoFlags.PORT_OVERCURRENT_FAULT and \
               not self.flags.value & ServoFlags.STARBOARD_OVERCURRENT_FAULT:
                self.faults.set(self.faults.value + 1)

            # if overcurrent then fault in the direction traveled
            # this prevents moving further in this direction
            if self.flags.value & ServoFlags.OVERCURRENT_FAULT:
                if self.lastdir > 0:
                    self.flags.port_overcurrent_fault()
                elif self.lastdir < 0:
                    self.flags.starboard_overcurrent_fault()

            self.reset()  # clear fault condition

        # update position from rudder feedback
        if not self.sensors.rudder.invalid():
            self.position.set(self.sensors.rudder.angle.value)

        self.send_command()
        self.controller_temp.timeout()
        self.motor_temp.timeout()

    def fault(self):
        if not self.driver:
            return False
        return self.driver.fault()

def test(device_path):
    from arduino_servo.arduino_servo import ArduinoServo
    print('probing arduino servo on', device_path)
    while True:
        try:
            device = serial.Serial(device_path, 38400)
            break
        except Exception as e:
            print(e)
            time.sleep(.5)

    device.timeout = 0  # nonblocking
    fcntl.ioctl(device.fileno(), TIOCEXCL)  # exclusive
    driver = ArduinoServo(device.fileno())
    # t0 = time.monotonic()
    for _ in range(1000):
        r = driver.poll()
        if r:
            print('arduino servo detected')
            exit(0)
        time.sleep(.1)
    exit(1)


def servo_main():
    for i, arg in enumerate(sys.argv):
        if arg == '-t':
            if len(sys.argv) < i + 2:
                print('device needed for option -t')
                exit(1)
            test(sys.argv[i+1])

    print('cypilot Servo')
    from server import cypilotServer
    server = cypilotServer()
    client = cypilotClient(server)

    from sensors import Sensors  # for rudder feedback
    sensors = Sensors(client)
    servo = Servo(client, sensors)
    servo.force_engaged = True # allow position command with autopilot not engaged

    period = .1
    lastt = time.monotonic()

    kb = KBHit()

    while True:

        if kb.kbhit():
            k = kb.getch()
            if k == ' ':
                if servo.controller.value != 'none':
                    # print('voltage:', servo.voltage.value, 'current', servo.current.value, 'ctrl temp', servo.controller_temp.value,
                    #      'motor temp', servo.motor_temp.value, 'rudder pos', sensors.rudder.angle.value, 'flags', servo.flags.get_str())
                    print('Status : rudder angle', sensors.rudder.angle.value, 'flags', servo.flags.get_str())
            elif k == '=':
                print('Servo command : ', 0)
                servo.command.set(0)
            elif k == '+':
                print('Servo command : ', 0.1)
                servo.command.set(0.1)
            elif k == '-':
                print('Servo command : ', -0.1)
                servo.command.set(-0.1)
            elif k == 'c':
                print('Servo position command : ', 0)
                servo.position_command.set(0)
            elif k == 'p':
                print('Servo position command : ', 20)
                servo.position_command.set(20)
            elif k == 's':
                print('Servo position command : ', -20)
                servo.position_command.set(-20)
            elif k == 'e':
                print('Servo position command out of range : ', 80)
                servo.position_command.set(80)
            elif k == 'q':
                print('Exiting')
                break
            else:
                print('Use keyboard key to send servo command:\n'
                      'space : display servo status\n'
                      '= : stop rudder motion\n'
                      '+ : move rudder to startboard\n'
                      '- : move rudder to port\n'
                      'c : set rudder position to 0\n'
                      'p : set rudder position to +20\n'
                      's : set rudder position to -20\n'
                      'e : set rudder position out of range\n'
                      'q : quit\n')

        servo.poll()
        sensors.poll()
        client.poll()
        server.poll()

        dt = period - time.monotonic() + lastt
        if dt > 0 and dt < period:
            time.sleep(dt)
            lastt += period
        else:
            lastt = time.monotonic()


if __name__ == '__main__':
    servo_main()
