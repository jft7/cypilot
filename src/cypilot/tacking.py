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

"""File wich manage tacking function
"""
import time
import cypilot.pilot_path
from pilot_values import EnumProperty, RangeSetting

from pilot_path import dprint as print # pylint: disable=redefined-builtin

class Tack(object):
    """Class wich manage tack function.
    To use, call Tack.process function
    """
    def __init__(self, ap):
        """Class Tack wich manage tacking update heading command at predefined rate

        Args:
            ap (autopilot object): main autopilot object
        """
        self.ap = ap

        # tacking states
        # none - not tacking, normal ap operation
        # begin - control application sets this to initiate tack
        # waiting - waiting delay seconds before beginning to tack
        # tacking - rudder is moving at tack rate until threshold
        self.state = self.register(EnumProperty, 'state', 'none', ['none', 'begin', 'waiting', 'tacking'])

        #parameter of tacking usage
        self.delay = self.register(RangeSetting, 'delay', 0, 0, 60, 'sec')
        self.angle = self.register(RangeSetting, 'angle', 100, 10, 180, 'deg')
        self.rate = self.register(RangeSetting, 'rate', 10, 1, 100, 'deg/s')
        self.direction = self.register(
            EnumProperty, 'direction', 'port', ['port', 'starboard'])

        #used to check if tack is allowed
        self.tack_allowed = False
        #used to fix angle/direction when tack start
        self.angle_used = self.angle.value
        self.direction_used = self.direction.value

        #timer parameter
        self.waiting_timer = time.monotonic()
        self.tacking_timer = time.monotonic()

        #counter to increment heading_command change
        self.counter = 0

        #lock to forbid new tack befor finishing tacking
        self.lock = False
        self.last_state = self.state.value #permit to come back to previous state if lock used



    def register(self, _type, name, *args, **kwargs):
        """ Register function"""
        return self.ap.client.register(_type(*(['ap.tack.' + name] + list(args)), **kwargs))

    def __tack_preparation(self):
        """Calculate tack angle if in wind mode and if tack is permitted
        """
        self.tack_allowed = False
        #set lock to True
        self.lock = True
        if self.ap.mode.value in ['true wind', 'wind']:
            if self.ap.heading_command.value > 0:
                if self.ap.heading_command.value < 60:
                    self.angle_used = 2*self.ap.heading_command.value
                    self.tack_allowed = True
                    self.direction_used = 'port'
                if self.ap.heading_command.value > 120:
                    self.angle_used = 2*(180-self.ap.heading_command.value)
                    self.tack_allowed = True
                    self.direction_used = 'starboard'

            elif self.ap.heading_command.value < 0:
                if self.ap.heading_command.value > -60:
                    self.angle_used = 2*abs(self.ap.heading_command.value)
                    self.tack_allowed = True
                    self.direction_used = 'starboard'
                if self.ap.heading_command.value < -120:
                    self.angle_used = 2*(180 + self.ap.heading_command.value)
                    self.tack_allowed = True
                    self.direction_used = 'port'

        elif self.ap.mode.value == "compass":
            self.tack_allowed = True
            self.direction_used = self.direction.value
            self.angle_used = self.angle.value

    def process(self):
        """ Function caled by ap every turn,
        check if tack is "begin", if yes launch tack"""
        # first check if state = "none"
        if self.state.value == "none":
            return


        if self.state.value == 'begin':
            #check if there is a lock and return to last_state if yes
            if self.lock:
                self.state.update(self.last_state)
                return

            #prepair tack with calculation, lock is set to True
            self.__tack_preparation()

            #if tack is not alowed, return to base state
            if self.tack_allowed is False:
                self.state.update('none')
                self.last_state = self.state.value
                self.lock = False #free the lock
                print("Tack not allowed in this mode/wind angle.")

            else: #go to waitig mode
                self.state.update('waiting')
                self.last_state = self.state.value
                self.waiting_timer = time.monotonic()

        if self.state.value == 'waiting':
            #check the delay
            if (time.monotonic() - self.waiting_timer) < self.delay.value:
                return
            else: # go to tacking, set tacking_timer and counter
                self.state.update('tacking')
                self.last_state = self.state.value
                self.counter = 0
                self.tacking_timer = time.monotonic()

        if self.state.value == 'tacking':
            #check ap.enabled or "rudder angle" mode to exit tack if not enabled
            if self.ap.enabled.value is False or self.ap.mode.value == "rudder angle":
                self.lock = False
                self.state.update('none')
                self.last_state = self.state.value
                return
            #check if timer reach 1/rate value if yes "increase" heading command by 1 degree
            if (time.monotonic() - self.tacking_timer) > (1/float(self.rate.value)):
                self.tacking_timer = time.monotonic()
                self.counter += 1
                if self.direction_used == 'port':
                    self.ap.heading_command.update(self.ap.heading_command.value - 1)
                if self.direction_used == 'starboard':
                    self.ap.heading_command.update(self.ap.heading_command.value + 1)
            #if counter reach angle_used, tack is finish, come back to base state
            if self.counter >= self.angle_used:
                self.lock = False
                self.state.update('none')
                self.last_state = self.state.value
                return



def tacking_main():
    """ Main function"""
    print('Version:', cypilot.pilot_path.STRVERSION)

if __name__ == '__main__':
    tacking_main()
