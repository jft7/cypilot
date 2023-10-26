#!/usr/bin/env python
#
#   Copyright (C) 2019 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

#   Modified (C) 2020 JF for Cybele Services (jf@netcys.com)

# pylint: disable=locally-disabled, missing-docstring, bare-except, broad-except, invalid-name, global-statement

from signal import SIGTERM
import sys
import os
from threading import Timer
from time import monotonic
import subprocess

from flask import Flask, render_template, request

from flask_socketio import SocketIO, Namespace, emit

import cypilot.pilot_path # pylint: disable=unused-import
from client import cypilotClient
import json

from pilot_path import PILOT_DIR

cypilot_web_port = 8000

if len(sys.argv) > 1:
    try:
        cypilot_web_port = int(sys.argv[1])
    except:
        print('using default port of', cypilot_web_port)
else:
    filename = PILOT_DIR+'web.conf'
    try:
        file = open(filename, 'r')
        config = json.loads(file.readline())
        if 'port' in config:
            cypilot_web_port = config['port']
        file.close()
    except:
        print('using default port of', cypilot_web_port)

# Set this variable to 'threading', 'eventlet' or 'gevent' to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on installed packages.
async_mode = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)

DEFAULT_PORT = 21311

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode, cypilot_web_port=cypilot_web_port)

browser = None
def open_browser():
    global browser
    browser = subprocess.Popen(['/usr/bin/chromium-browser', '--app=http://localhost:8000'])
    print(browser)

autopilot = None

def run_autopilot():
    global autopilot
    autopilot_path = os.path.dirname(os.path.abspath(__file__)) + '/../ui/qt_autopilot.py'
    autopilot = subprocess.Popen(['python3', autopilot_path], stdout=subprocess.DEVNULL)
    print(autopilot)

class cyPilotWeb(Namespace):
    def __init__(self, name):
        super().__init__(name)
        socketio.start_background_task(target=self.background_thread)
        self.clients = {}

    def background_thread(self):
        print('processing clients')
        global autopilot
        t0 = monotonic()
        while True:
            socketio.sleep(.25)
            sys.stdout.flush() # update log
            sids = list(self.clients)
            for sid in sids:
                if not sid in self.clients:
                    print('client was removed')
                    continue # was removed

                client = self.clients[sid]
                values = client.list_values()
                if values:
                    #print('values', values)
                    socketio.emit('cypilot_values', json.dumps(values), room=sid)
                if not client.connection:
                    socketio.emit('cypilot_disconnect', room=sid)
                    if ((autopilot is None) or (autopilot.poll() is not None)):
                        run_autopilot()
                msgs = client.receive()
                if msgs:
                    # convert back to json (format is nicer)
                    socketio.emit('cypilot', json.dumps(msgs), room=sid)
            if((browser is None) or (browser.poll() is not None)):
                if monotonic() - t0 > 8:
                    # kill autopilot process and exit
                    # WARNING : at the moment, we kill the autopilot process on exit, regardless if any other client is connected !!!
                    if autopilot:
                        autopilot.send_signal(SIGTERM)
                    exit()

    def on_cypilot(self, message):
        #print('message', message)
        self.clients[request.sid].send(message + '\n')

    def on_ping(self):
        emit('pong')

    def on_connect(self):
        print('Client connected', request.sid)
        client = cypilotClient()
        self.clients[request.sid] = client

    def on_disconnect(self):
        print('Client disconnected', request.sid)
        client = self.clients[request.sid]
        client.disconnect()
        del self.clients[request.sid]

socketio.on_namespace(cyPilotWeb(''))


def main():
    path = os.path.dirname(__file__)
    os.chdir(os.path.abspath(path))
    port = cypilot_web_port



    Timer(3, open_browser).start() # delayed start, give e.g. web server time to launch

    while True:
        try:
            socketio.run(app, debug=False, host='0.0.0.0', port=port)
            break
        except PermissionError as e:
            print('failed to run socket io on port', port, e)
            port += 8000 - 80
            print('trying port', port)

    browser.kill()

if __name__ == '__main__':
    main()
