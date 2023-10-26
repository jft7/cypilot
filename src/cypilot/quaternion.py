#!/usr/bin/env python
#
#   Copyright (C) 2016 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

import math

import cypilot.pilot_path
import vector

def angvec2quat(angle_, v):
    n = vector.norm(v)
    if n == 0:
        fac = 0
    else:
        fac = math.sin(angle_/2) / n

    return [math.cos(angle_/2), v[0]*fac, v[1]*fac, v[2]*fac]

def angle(q):
    return 2*math.acos(q[0])

def vec2vec2quat(a, b):
    n = vector.cross(a, b)
    fac = vector.dot(a, b) / vector.norm(a) / vector.norm(b)
    # protect against possible slight numerical errors
    fac = min(max(fac, -1), 1)

    ang = math.acos(fac)
    return angvec2quat(ang, n)

def multiply(q1, q2):
    return [q1[0]*q2[0] - q1[1]*q2[1] - q1[2]*q2[2] - q1[3]*q2[3],
            q1[0]*q2[1] + q1[1]*q2[0] + q1[2]*q2[3] - q1[3]*q2[2],
            q1[0]*q2[2] - q1[1]*q2[3] + q1[2]*q2[0] + q1[3]*q2[1],
            q1[0]*q2[3] + q1[1]*q2[2] - q1[2]*q2[1] + q1[3]*q2[0]]

# take a vector and quaternion, and rotate the vector by the quaternion
def rotvecquat(v, q):
    w = [0, v[0], v[1], v[2]]
    r = [q[0], -q[1], -q[2], -q[3]]
    return multiply(multiply(q, w), r)[1:]

def toeuler(q):
    roll = math.atan2(2.0 * (q[2] * q[3] + q[0] * q[1]),
                      1 - 2.0 * (q[1] * q[1] + q[2] * q[2]))
    pitch = math.asin(min(max(2.0 * (q[0] * q[2] - q[1] * q[3]), -1), 1))
    heading = math.atan2(2.0 * (q[1] * q[2] + q[0] * q[3]),
                         1 - 2.0 * (q[2] * q[2] + q[3] * q[3]))
    return roll, pitch, heading

def toquaternion(roll, pitch, heading):
    rsin = math.sin(roll/2)
    rcos = math.cos(roll/2)
    psin = math.sin(pitch/2)
    pcos = math.cos(pitch/2)
    hsin = math.sin(heading/2)
    hcos = math.cos(heading/2)

    qw = rcos * pcos * hcos + rsin * psin * hsin
    qx = rsin * pcos * hcos - rcos * psin * hsin
    qy = rcos * psin * hcos + rsin * pcos * hsin
    qz = rcos * pcos * hsin - rsin * psin * hcos

    return [qw, qx, qy, qz]

def conjugate(q):
    return [q[0], -q[1], -q[2], -q[3]]

def normalize(q):
    total = 0
    for v in q:
        total += v*v
    d = math.sqrt(total)
    if d != 0:
        return [q[0] / d, q[1] / d, q[2] / d, q[3] / d]
    else:
        return q

def quaternion_main():
    print('Version:', cypilot.pilot_path.STRVERSION)
    euler = (10.0, 20.0, 330.0)
    print("Euler: ", euler)
    euler = [math.radians(angle) for angle in euler]
    roll, pitch, heading = euler
    quaternion = toquaternion(roll, pitch, heading)
    print("Quaternion: ", quaternion)
    euler = toeuler(quaternion)
    euler = [math.degrees(angle) for angle in euler]
    print("Quaternion to euler: ", euler)

if __name__ == '__main__':
    quaternion_main()
