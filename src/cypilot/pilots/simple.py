#!/usr/bin/env python
#
#   Copyright (C) 2017 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

#To do:
#        + Add overlay management
#        + Permit other source of speed

# pylint: disable=locally-disabled, missing-docstring, bare-except, broad-except

""" Simple algorythm to send angle to servo:
    Command = Gx(PxError + DxRotation + IxSumOfErrors + HxHeel + overlay )
              + RudderAngleOffset

    Could be use with GPS, TW, AW, Heading mode.
    In case of Ruder_mode: ap.heading_command will be send to servo

    Error =             Error beetween command and route, degree
    Rotation =          Rotation speed, dps
    SumOfError =        Sum of errors for a given time, degree
    Heel =              Heel angle, degree
    Overlay =           to permit the add of 2nd algorythm on overlay,
                        will be PID
    RudderAngleOffset = Rudder angle offset to moove the middle of rudder
                        angle ( for exemple in case of weather-helm)
    G =                 Coefficient to increase/decrease the steering angle,
                        need an option to link it to boat speed
                        G=(max(0.3, min(2, G/Boatspeed))
"""

from pilots.pilot import AutopilotPilot


class SimplePilot(AutopilotPilot):
    def __init__(self, ap, name="simple"):
        """
        Init of Simple Pilot,
        create PIDHGO
        Heritage of AutopilotPilot

        Args:
            ap (Autopilot object): autopilot which manage server with data
        """
        super(SimplePilot, self).__init__(name, ap)

        # create simple pid filter + heel correction
        self.gains = {}
        self.ap_gain('P', 1, 0, 5)
        # self.ap_gain('P', 1, 0, 10)
        self.ap_gain('I', 0, 0, 1)
        self.ap_gain('D', .3, 0, 1)
        self.ap_gain('H', 0.3, 0, 1)
        self.ap_gain('G', 6, 0, 40)
        self.ap_gain('O', 0, -10, 10)

        #need to add overlay PID
        # self.ap_gain('PO', .3, 0, 1)
        # self.ap_gain('I0', 0, 0, .05)
        # self.ap_gain('D0', .15, 0, .5)

    def process(self, reset):
        """
        Process of simple pilot which send the command to the servo:
        Command = Gx(PxError + DxRotation + IxSumOfErrors + HxHeel + overlay ) + RudderAngleOffset

        To do:
        + Add overlay management
        + Permit other source of speed

        Args:
            reset (Boolean): Not in use
        """
        #if super().process(reset) is False:
        #    return
        ap = self.ap
        # If rudder angle mode,don't use I, D and H; speed_correction = 0 and rudder_angle_offset = 0
        if ap.mode.value == 'rudder angle':
            command = ap.heading_command.value

        else:
            headingrate = ap.boatimu.sensor_values['headingrate'].value
            heel = ap.boatimu.sensor_values['roll'].value #need to chek the sign
            gain_values = {'P': ap.heading_error.value,
                           'I': ap.heading_error_int.value,
                           'D': headingrate,
                           'H': -heel
                          }
            #overlay gain_values
            #gain_values_overlay = {'P0': ap.heading_error.value,
                                    #'I0': ap.heading_error_int.value,
                                    #'D0': headingrate
                                    #}

            #speed correction of rudder angle or if there is no speed data from GPS
            if ap.speed_mode.value == 'none' or ap.pilots[self.name].gains['G']['apgain'].value == 0 or ap.mode.value == 'rudder angle':
                speed_correction = 1
            else:
                #speed = max(1, ap.sensors.gps.speed.value) #avoid division by zero
                speed = max(1, ap.client.values.values[ap.speed_mode.value].value)
                speed_correction = min(2, ap.pilots[self.name].gains['G']['apgain'].value/speed) #increase rudder angle if speed is low (max 2)
                speed_correction = max(0.3, speed_correction) # min 0.3

            #set rudder offset
            rudder_angle_offset = ap.pilots[self.name].gains['O']['apgain'].value

            #compute PID
            PID = self.ap_compute(gain_values)

            #compute PID_overlay
            #PID_overlay = (0 if not ap.mode_overlay.value else self.ap_compute(gain_values_overlay)

            #compute command in angle, to do: add PID_overlay
            command = speed_correction*(PID) + rudder_angle_offset


        if ap.enabled.value:
            #send command to servo, to be modified to be command in angle
            ap.servo.position_command.set(command)
            # print('Pilot command :',command)

    # need to add overlay possibility


pilot = SimplePilot
