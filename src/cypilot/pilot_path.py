#!/usr/bin/env python
#
# (C) 2020-2023 JF/ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

""" Update system path to cover misc cases (run, test, debug, lint, ...)

    Import this file after system imports and before autopilot application imports
"""

import os
import sys
import io
import inspect
import json
import socket


SFILE = os.path.abspath(__file__)

# attempt to identify main python file
try:
    MFILE = os.path.abspath(sys.modules['__main__'].__file__)
except:
    MFILE = SFILE

# update path to support different configurations : installed package and development source tree
if "local/bin" in MFILE:
    # running an installed cypilot package
    MFILE = SFILE
SPATH = MFILE.rsplit("/cypilot", 1)[0]+"/cypilot"

# cypilot, cypilot/cypilot, cypilot/ui, cypilot/rc, ...
for dn in next(os.walk(SPATH))[1] :
    dp = os.path.join(SPATH, dn)
    if os.path.isfile(dp + "/__init__.py") and dp not in sys.path :
        sys.path.insert(0, dp)
while SPATH in sys.path :
    sys.path.remove(SPATH)
sys.path.insert(0, SPATH)

try:
    import pilot_version
except ImportError:
    print("Can't import pilot version file")
    print(sys.path)

STRVERSION = pilot_version.STRVERSION
PILOT_DIR = os.getenv('HOME') + '/.cypilot/'

try:
    os.mkdir(PILOT_DIR)
except FileExistsError:
    pass

""" Manage log information

    Logs can be written to a named pipe to be used by the autopîlot dialog
    The named pipe AUTOPILOT_LOG_PIPE must be created by the autopîlot dialog : if it doesn't exist, logs are written to stdout
"""

AUTOPILOT_LOG_PIPE = '/tmp/autopilot_log_pipe'
AUTOPILOT_LOG_FIFO = None

if os.path.exists(AUTOPILOT_LOG_PIPE):
    try:
        AUTOPILOT_LOG_FIFO = os.open(AUTOPILOT_LOG_PIPE, os.O_RDWR | os.O_NONBLOCK)
    except:
        pass

def close_autopilot_log_pipe():
    if os.path.exists(AUTOPILOT_LOG_PIPE):
        os.unlink(AUTOPILOT_LOG_PIPE)

""" Create a lock to avoid launching a new script when script with same name is already running

    For Linux system, it is atomic and avoids the problem of having lock files lying around if your process gets sent a SIGKILL
"""

def get_lock(process_name,sysexit=True):
    get_lock._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) # pylint: disable=protected-access

    try:
        # The null byte (\0) means the socket is created 
        # in the abstract namespace instead of being created 
        # on the file system itself.
        # Works only in Linux
        get_lock._lock_socket.bind('\0' + process_name)  # pylint: disable=protected-access
        dprint('get the lock : ', process_name)
    except socket.error:
        if sysexit:
            dprint('lock exists : ', process_name)
            sys.exit()
        else:
            return False
    return True

""" Print log to stdout or named pipe

    Include script name, and custom log message
    Support message filtering as defined by configuration file : cypilot_dprint.conf

"""

DPRINT_ALLOWED = []
DPRINT_EXCLUDED = []
DPRINT_UNIQ = True
DPRINT_LINE = ''

def init_dprint_filter():
    global DPRINT_ALLOWED
    global DPRINT_EXCLUDED
    global DPRINT_UNIQ

    dprintfilename = PILOT_DIR + 'cypilot_dprint.conf'
    dprintconfig = {}
    try:
        file = open(dprintfilename)
        dprintconfig = json.load(file)
        file.close()
        DPRINT_UNIQ = bool(dprintconfig['uniq'])
        DPRINT_ALLOWED = list(dprintconfig['allowed'])
        DPRINT_EXCLUDED = list(dprintconfig['excluded'])
    except: # pylint: disable=broad-except
        DPRINT_UNIQ = True
        DPRINT_ALLOWED = ['any']
        DPRINT_EXCLUDED = ['none']
        try:
            file = open(dprintfilename, 'w')
            dprintconfig['uniq'] = DPRINT_UNIQ
            dprintconfig['allowed'] = DPRINT_ALLOWED
            dprintconfig['excluded'] = DPRINT_EXCLUDED
            file.write(json.dumps(dprintconfig, indent=4) + '\n')
            file.close()
        except Exception as e: # pylint: disable=broad-except
            print('Exception writing default values to dprint filter:', dprintfilename, e)
    return

def dprint(*args, **kwargs):
    global DPRINT_LINE
    
    frame_info = inspect.stack()[1]
    caller = frame_info[1].split('/')[-1].split('.')[0]
    info = f"{caller:<16}" + " > " + " ".join(map(str, args))
    if not DPRINT_ALLOWED :
        init_dprint_filter()
    if ('any' in DPRINT_ALLOWED and not caller in DPRINT_EXCLUDED) or (caller in DPRINT_ALLOWED):
        if AUTOPILOT_LOG_FIFO:
            sio = io.StringIO()
            print(info, **kwargs, file=sio)
            dprint_line = bytes(sio.getvalue(),'utf-8')
            if not DPRINT_UNIQ or dprint_line != DPRINT_LINE:
                DPRINT_LINE = dprint_line
                os.write(AUTOPILOT_LOG_FIFO, dprint_line)
        else:
            print(info, **kwargs)
        # who was the caller of the caller ?
        # frame_info = inspect.stack()[2]
        # print("   called from : + ",frame_info[1].split('/')[-1].split('.')[0]," line:", frame_info[2], " function:", frame_info[3])
        # print("   Main: ", MFILE, " - This: ", SFILE)

def pilot_path_main():
    print('Version:', pilot_version.STRVERSION, 'Pilot path:', pilot_version.PILOTPATH)
    for entry in sys.path:
        print(entry)
    print( 'Main: ', MFILE, ' - This: ', SFILE)

if __name__ == '__main__':
    pilot_path_main()
