#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

""" Version information
"""

import os
import sys

__version__ = '1.1.0'

PILOTPATH = os.path.dirname(os.path.abspath(__file__))
STRVERSION = __version__

def pilot_version_main():
    print('Git V4 - Version:', STRVERSION, 'Pilot path:', PILOTPATH)
    for entry in sys.path:
        print(entry)

if __name__ == '__main__':
    pilot_version_main()
