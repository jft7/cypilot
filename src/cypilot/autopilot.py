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

"""autopilot base handles reading from the imu (boatimu)
"""

import sys
import os
import math

import cypilot.pilot_path # pylint: disable=unused-import

from pilot_path import get_lock
get_lock('autopilot')

import servo
import tacking
import pilots
from perf import Perf
from sensors import Sensors
from pilot_version import STRVERSION
from resolv import resolv, resolv360, resolv180
from boatimu import BoatIMU
from pilot_values import time, Value, SensorValue, BooleanProperty, EnumProperty, RangeProperty, EnumSetting
from client import cypilotClient
from server import cypilotServer
from rc.receiver import RemoteControlClient

from pilot_path import (dprint as print, close_autopilot_log_pipe) # pylint: disable=redefined-builtin

def minmax(value, r):
    """minmax : adjust value in a range 0 to +/- rng
                ex: 'minmax( heading_error, 60)' adjust heading error to be in range -60 to +60)

    Args:
        value (integer): value
        rng (integer): range

    Returns:
        integer: value in the defined range
    """
    return min(max(value, -r), r)


def compute_true_wind(gps_speed, gps_track, wind_speed, wind_direction):
    """compute_true_wind : compute true wind value

    Args:
        gps_speed (integer): GPS speed
        gps_track (integer): GPS track
        wind_speed (integer): Wind speed
        wind_direction (integer): Wind direction / course made good (degrees)

    Returns:
        tupple: True wind dir, true wind speed
    """
    rwd = math.radians(wind_direction)
    rgpst = math.radians(gps_track)
    windv = wind_speed*math.sin(rwd), wind_speed*math.cos(rwd)
    gpsv = gps_speed*math.sin(rgpst), gps_speed*math.cos(rgpst)
    tws = math.hypot((windv[1]-gpsv[1]), (windv[0]-gpsv[0]))
    twd = math.degrees(math.atan2((windv[0]-gpsv[0]), (windv[1]-gpsv[1])))
    truewind = (twd, tws)
    return truewind

class ModeProperty(EnumProperty):
    """ModeProperty : Operating mode of Autopilot

        Args:
            name (string): Operating mode ('compass', 'gps', 'wind', 'true wind', 'rudder angle')
    """

    def __init__(self, name):
        self.ap = False
        super(ModeProperty, self).__init__(name, 'compass', [
            'compass', 'gps', 'wind', 'true wind', 'rudder angle'], persistent=True)

    def set(self, value):
        """set : Update the preferred operating mode when the mode changes from user

        Args:
            value (string): Operating mode ('compass', 'gps', 'wind', 'true wind', 'rudder angle')
        """
        # update the preferred mode when the mode changes from user
        if self.ap:
            self.ap.preferred_mode.update(value)
        self.set_internal(value)
        #add mode_overlay reset

    def set_internal(self, value):
        """set_internal : Update the operating mode (internal)

        Args:
            value (string): Operating mode ('compass', 'gps', 'wind', 'true wind', 'rudder angle')
        """
        super(ModeProperty, self).set(value)

class HeadingProperty(RangeProperty):
    """HeadingProperty

        Args:
            name
            mode
    """
    def __init__(self, name, mode):
        self.mode = mode
        super(HeadingProperty, self).__init__(name, 0, -180, 360)

    # +-180 for wind, true wind and rudder angle modes 0-360 for compass and gps modes
    def set(self, value):
        if self.mode.value in ['wind', 'true wind', 'rudder angle']:
            value = resolv180(value)
        elif self.mode.value in ['compass', 'gps']:
            value = resolv360(value)
        super(HeadingProperty, self).set(value)

class TimeStamp(SensorValue):
    def __init__(self):
        super(TimeStamp, self).__init__('timestamp', 0)
        self.info['type'] = 'TimeStamp' # not a sensor value to be scoped

class Autopilot(object):
    """Autopilot : Autopilot
    """

    def __init__(self):
        super(Autopilot, self).__init__()
        self.watchdog_device = False

        self.server = cypilotServer()
        self.client = cypilotClient(self.server)
        self.boatimu = BoatIMU(self.client)
        self.sensors = Sensors(self.client)
        self.servo = servo.Servo(self.client, self.sensors)
        self.remotecontrol = RemoteControlClient()
        self.perf = Perf()

        self.timestamp = self.client.register(TimeStamp())
        self.starttime = time.monotonic()

        self.version = self.register(Value, 'version', 'cypilot' + ' ' + STRVERSION)
        self.features = self.register(EnumSetting, 'features', 'basic', ['basic', 'advance', 'development'], persistent=True)
        
        self.mode = self.register(ModeProperty, 'mode')
        self.preferred_mode = self.register(Value, 'preferred_mode', 'compass')
        self.preferred_heading_command = self.register(HeadingProperty, 'preferred_heading_command', self.mode)
        self.lastmode = False
        self.mode.ap = self

        self.low_wind_limit = self.register(Value, 'low_wind_limit', 2)

        self.heading_command = self.register(HeadingProperty, 'heading_command', self.mode)
        self.enabled = self.register(BooleanProperty, 'enabled', False)
        self.lastenabled = False

        self.last_heading = False
        self.last_heading_off = self.boatimu.heading_off.value

        self.speed_mode = self.register(
            EnumSetting, 'speed_mode', 'gps.speed', ['gps.speed', 'sow.speed', 'none'], persistent=True)

        self.pilots = {}
        for pilot_type in pilots.DEFAULT:
            try:
                pilot = pilot_type(self)
                self.pilots[pilot.name] = pilot
            except Exception as e:
                print(f"Pilot [{pilot_type.__module__.split('.')[1]}] has not been loaded {e}'")

        pilot_names = list(self.pilots)
        print('Loaded Pilots:', pilot_names)
        self.pilot = self.register(
            EnumProperty, 'pilot', 'simple', pilot_names, persistent=True)

        # copy it to overlay
        self.heading = self.register(SensorValue, 'heading', directional=True)
        self.heading_error = self.register(SensorValue, 'heading_error')
        self.heading_error_int = self.register(
            SensorValue, 'heading_error_int')
        self.heading_error_int_time = time.monotonic()

        self.tack = tacking.Tack(self)
        self.wind_speed = self.register(
            Value, 'wind_speed', 0)
        self.wind_angle = self.register(
            SensorValue, 'wind_angle', initial=0, directional=True)
        self.wind_direction = self.register(
            SensorValue, 'wind_direction', initial=0, directional=True)
        self.wind_direction_smoothed = self.register(
            SensorValue, 'wind_direction_smoothed', initial=0, directional=True)
        self.true_wind_direction = self.register(
            SensorValue, 'true_wind_direction', initial=0, directional=True)

        self.wind_angle_smoothed = self.register(
            SensorValue, 'wind_angle_smoothed', directional=True)
        self.wind_speed_smoothed = self.register(
            Value, 'wind_speed_smoothed', 0)

        self.true_wind_angle = self.register(
            SensorValue, 'true_wind_angle', directional=True)
        self.true_wind_speed = self.register(
            Value, 'true_wind_speed', 0)

        self.smooth_factor_wind = self.register(
            RangeProperty, 'smooth_factor_wind', 0.3, 0.01, 1, persistent=True)

        self.wind_noise_reduction = self.register(
            BooleanProperty, 'wind_noise_reduction', False, persistent=True)
        self.wind_altitude =  self.register(
            Value, 'wind_altitude', 16, persistent=True)

        self.vmg = self.register(
            Value, 'vmg', 0)
        self.cmg = self.register(
            Value, 'cmg', 0)

        self.timings = self.register(SensorValue, 'timings', False)

        device = '/dev/watchdog0'
        try:
            self.watchdog_device = open(device, 'w')
        except:
            print('warning: failed to open special file', device, 'for writing')
            print('         cannot stroke the watchdog')

        self.server.poll()  # setup process before we switch main process to realtime
        print('autopilot process : ', os.getpid())
        if os.system(f"sudo chrt -pf 2 {os.getpid():d} 2>&1 > /dev/null"):
            print('warning, failed to make autopilot process realtime')

        self.lasttime = time.monotonic()

        # setup all processes to exit on any signal
        self.childprocesses = [self.sensors.nmea, self.sensors.gpsd, self.sensors.signalk, self.server, self.remotecontrol, self.perf]

        def cleanup(signal_number, frame=None):
            if signal_number == signal.SIGCHLD:
                pid = os.waitpid(-1, os.WNOHANG)
                sigchld = False
                for child in self.childprocesses:
                    if child.process and child.process.pid == pid:
                        sigchld = True
                        break
                if not sigchld:
                    return

            print('got signal', signal_number, 'cleaning up')
            if signal_number != 'atexit': # don't get this signal again
                signal.signal(signal_number, signal.SIG_IGN)

            while self.childprocesses:
                process = self.childprocesses.pop().process
                if process:
                    pid = process.pid
                    print('kill', pid, process)
                    try:
                        os.kill(pid, signal.SIGTERM) # get backtrace
                    except Exception as e:
                        print('kill failed', e)

            for pilot in self.pilots.values():
                while pilot.pid:
                    pid = pilot.pid.pop()
                    print('kill', pid, pilot)
                    try:
                        os.kill(pid, signal.SIGTERM) # get backtrace
                    except Exception as e:
                        print('kill failed', e)

            sys.stdout.flush()
            if signal_number != 'atexit':
                raise KeyboardInterrupt  # to get backtrace on all processes

        # unfortunately we occasionally get this signal,
        # some sort of timing issue where python doesn't realize the pipe
        # is broken yet, so doesn't raise an exception
        def printpipewarning(signal_number, frame):
            print('got SIGPIPE, ignoring')

        import signal
        for s in range(1, 16):
            if s == 13:
                signal.signal(s, printpipewarning)
            elif s != 9:
                signal.signal(s, cleanup)

        signal.signal(signal.SIGCHLD, cleanup)
        import atexit
        atexit.register(lambda: cleanup('atexit'))

    def __del__(self):
        print('closing autopilot')
        self.server.__del__()

        if self.watchdog_device:
            print('close watchdog')
            self.watchdog_device.write('V')
            self.watchdog_device.close()

        close_autopilot_log_pipe()

    def register(self, _type, name, *args, **kwargs):
        """register : register autopilot value on server

        Args:
            _type (type): type of value to register
            name (string): registration name

        Returns:
            value: value of registered item
        """
        return self.client.register(_type(*(['ap.' + name] + list(args)), **kwargs))

    def adjust_mode(self, pilot):
        """adjust_mode : change AutoPilot operating mode

        Args:
            pilot (AutopilotPilot): AutoPilot
        """
        # if the mode must change, keep the last preferred heading to auto come back
        newmode = pilot.best_mode(self.preferred_mode.value)
        if self.mode.value != newmode:
            if self.lastmode != newmode:
                if self.lastmode == self.preferred_mode.value:
                    self.preferred_heading_command.set(self.heading_command.value)
                    self.mode.set_internal(newmode)
                elif newmode == self.preferred_mode.value:
                    self.mode.set_internal(newmode)
                    self.heading_command.set(self.preferred_heading_command.value)
                    self.lastmode = newmode
                else:
                    self.mode.set_internal(newmode)

    def adjust_speed_mode(self):
        """adjust speed mode"""
        gps_source = self.sensors.gps.source.value
        sow_source = self.sensors.sow.source.value
        speed_mode = self.speed_mode.value
        if gps_source is None and sow_source is None and speed_mode != 'none':
            self.speed_mode.set('none')
        if gps_source is None and speed_mode == "gps.speed":
            self.speed_mode.set("sow.speed")
        elif sow_source is None and speed_mode == "sow.speed":
            self.speed_mode.set("gps.speed")

    def compute_wind(self):
        """compute_wind : compute difference between compass to gps and compass to wind
        """
        compass = self.boatimu.sensor_values['heading'].value
        roll = self.boatimu.sensor_values['roll'].value
        pitch = self.boatimu.sensor_values['pitch'].value
        rollrate = self.boatimu.sensor_values['rollrate'].value
        pitchrate = self.boatimu.sensor_values['pitchrate'].value
        smooth_factor_wind = self.smooth_factor_wind.value
        wind_noise_reduction = self.wind_noise_reduction.value
        altitude = self.wind_altitude.value
        ms_to_nds = 1.94384

        if self.sensors.wind.source.value != 'none':
            if self.sensors.wind.updated:
                self.sensors.wind.updated = False
                wind_speed = self.sensors.wind.speed.value
                wind_angle = self.sensors.wind.angle.value

                if wind_noise_reduction:
                    #remove wind from pitchrate/rollrate and then correct wind du to inclination of sensor
                    f_w = (math.cos(math.radians(wind_angle))*wind_speed + ms_to_nds*2*math.pi*altitude*(pitchrate/360))/math.cos(math.radians(min(45, pitch)))
                    l_w = (math.sin(math.radians(wind_angle))*wind_speed - ms_to_nds*2*math.pi*altitude*(rollrate/360))/math.cos(math.radians(min(45, roll)))
                    #f_w = (math.cos(math.radians(wind_angle))*wind_speed)/math.cos(math.radians(min(45, pitch)))
                    #l_w = (math.sin(math.radians(wind_angle))*wind_speed)/math.cos(math.radians(min(45, roll)))
                    wind_angle = math.degrees(math.atan2(l_w, f_w))
                    wind_speed = math.hypot(l_w, f_w)

                self.wind_speed.set(wind_speed)
                self.wind_angle.set(wind_angle)
                self.wind_direction.set(resolv360(compass, -wind_angle))
                self.wind_speed_smoothed.set(
                    (1-smooth_factor_wind)*self.wind_speed_smoothed.value + smooth_factor_wind*wind_speed
                    )
                wind_angle_smoothed = (1-smooth_factor_wind)*self.wind_angle_smoothed.value + smooth_factor_wind*wind_angle
                self.wind_angle_smoothed.set(resolv180(wind_angle_smoothed))#resolv180 probably unuse
                wind_direction = resolv360(compass, -wind_angle_smoothed)
                self.wind_direction_smoothed.set(wind_direction)

                if self.sensors.gps.source.value != 'none':
                    gps_speed = self.sensors.gps.speed.value
                    gps_track = self.sensors.gps.track.value
                    true_wind = compute_true_wind(gps_speed, gps_track, wind_speed,
                                                wind_direction)
                    true_wind_dir = resolv360(true_wind[0])
                    true_wind_speed = true_wind[1]
                    true_wind_angle = resolv180(compass, -true_wind_dir) # a vérifier le signe

                    self.true_wind_angle.set(
                        (1-smooth_factor_wind)*self.true_wind_angle.value + smooth_factor_wind*true_wind_angle
                        )
                    self.true_wind_speed.set(
                        (1-smooth_factor_wind)*self.true_wind_speed.value + smooth_factor_wind*true_wind_speed
                        )
                    self.true_wind_direction.set(
                        (1-smooth_factor_wind)*self.true_wind_direction.value + smooth_factor_wind*true_wind_dir
                        )

                else:
                    self.true_wind_angle.set(0)
                    self.true_wind_speed.set(0)
                    self.true_wind_direction.set(0)
        else:
            self.wind_speed.set(0)
            self.wind_angle.set(0)
            self.wind_direction.set(0)
            self.true_wind_angle.set(0)
            self.true_wind_speed.set(0)
            self.true_wind_direction.set(0)


    def compute_vmg(self):
        """Compute vmg from TWD, Compas and GPS Speed
        """
        if self.sensors.gps.source.value != 'none' and self.sensors.wind.source.value != 'none':
            gps_speed = self.sensors.gps.speed.value
            true_wind_direction = self.true_wind_direction.value
            compass = self.boatimu.sensor_values['heading'].value

            vmg = math.cos(math.radians(true_wind_direction - compass)) * gps_speed

            self.vmg.set(vmg)
            
        else:
            self.vmg.set(0)

    def compute_cmg(self):
        """Compute cmg from heading command, heading and GPS Speed
        """
        if self.sensors.gps.source.value != 'none':
            heading = self.heading.value
            heading_command = self.heading_command.value
            gps_speed = self.sensors.gps.speed.value

            cmg = math.cos(math.radians(heading_command - heading)) * gps_speed

            self.cmg.set(cmg)
        
        else:
            self.cmg.set(0)


    #Copy it to def compute_heading_error_overlay(self, t)
    def compute_heading_error(self, t):
        """compute_heading_error : compute heading error

        Args:
            ctime (float): current time in seconds since the Epoch
        """
        heading = self.heading.value
        ruddermode = 'rudder' in self.mode.value

        # keep same heading if mode changes except for autochange (keep last heading)
        if self.mode.value != self.lastmode:
            error = self.heading_error.value
            if ruddermode:
                self.heading_command.set(heading)
            else:
                self.heading_command.set(heading - error)
            self.lastmode = self.mode.value

        # compute heading error
        heading_command = self.heading_command.value

        # error +- 60 degrees
        err = minmax(resolv(heading - heading_command), 60)
        #set error
        self.heading_error.set(err)

        # compute integral for I gain
        dt = t - self.heading_error_int_time
        dt = min(dt, 1)
        self.heading_error_int_time = t
        self.heading_error_int.set(minmax(self.heading_error_int.value + self.heading_error.value/10*dt, 10))

    def iteration(self):
        """iteration : autopilot loop processing
        """

        # t0 : synchronous read of IMU values
        # -----------------------------------
        
        # boatimu.read() should return when fresh rotation vector is available
        t0 = time.monotonic()
        self.boatimu.read()
        
        # then do further autopilot processing
        
        # t1 : receive client messages
        # ----------------------------

        t1 = time.monotonic()
        msgs = self.client.receive()
        for msg, msgv in msgs.items():
            print('autopilot main process received:', msg, msgv)

        # t2 : poll sensors
        # -----------------

        t2 = time.monotonic()
        self.sensors.poll()

        # t3 : autopilot computations
        # ---------------------------

        t3 = time.monotonic()
        self.adjust_speed_mode()
        self.compute_wind()
        self.compute_vmg()
        pilot = self.pilots[self.pilot.value]  # select pilot
        self.adjust_mode(pilot)
        pilot.compute_heading()
        self.compute_cmg()

        # Process tack calculation before compute heading error
        self.tack.process()
        self.compute_heading_error(t0)

        # reset filters when autopilot is enabled
        reset = False
        if self.enabled.value != self.lastenabled:
            self.lastenabled = self.enabled.value
            if self.enabled.value:
                self.heading_error_int.set(0)
                reset = True

        # perform pilot specific calculation
        pilot.process(reset)

        # servo can only disengage under manual control
        self.servo.ap_engaged = self.enabled.value

        # t4 : poll servo
        # ---------------

        t4 = time.monotonic()
        self.servo.poll()

        # t5 : check consumed time
        # ------------------------

        t5 = time.monotonic()

        self.timings.set([t1-t0, t2-t1, t3-t2, t4-t3, t5-t4, t5-t1])
        self.timestamp.set(t1-self.starttime)

        if self.watchdog_device:
            self.watchdog_device.write('c')

        # imuboat time (t1-t0) is mainly sleeptime while waiting for next rotation vector
        
        period = 1/self.boatimu.rate.value
        imtime = t1-t0
        aptime = t5-t1
        if aptime > period :
            print(f"Autopilot processing time {aptime:.2f} > {period:.2f}: client/server={t2-t1:.2f}, sensors={t3-t2:.2f}, pilot={t4-t3:.2f}, servo={t5-t4:.2f}")
        if imtime > period * 1.5:
            print(f"Autopilot IMU report long delay, device seems too slow : delay={imtime:.2f}, IMU period={period:.2f}'")
        elif imtime < 0.02:
            print(f"Autopilot IMU report short delay, processor seems too busy : delay={imtime:.2f}, IMU period= {period:.2f}")


def autopilot_main():
    """main : main
    """
    ap = Autopilot()
    while True:
        ap.iteration()




if __name__ == '__main__':
    autopilot_main()
