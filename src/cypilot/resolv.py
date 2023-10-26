#!/usr/bin/env python
#
#   Copyright (C) 2019 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

def resolv(angle, offset=0):
    while offset - angle > 180:
        angle += 360
    while offset - angle <= -180:
        angle -= 360
    return angle

def resolv360(angle, offset=0):
    angle = angle + offset
    while angle >= 360:
        angle -= 360
    while angle < 0:
        angle += 360
    return angle

def resolv180(angle, offset=0):
    angle = angle + offset
    while angle > 180:
        angle -= 360
    while angle <= -180:
        angle += 360
    return angle
