# cypilot

This is a much modified version of the original pypilot software created by Sean D'Epagnier
under the terms of the GNU General Public License as published by the Free Software Foundation
(version 3 of the License or any later version)

(C) 2020-2023 Cybele Services (cf@cybele-sailing.com)

Designed for:

   - Support of CysBOX/CysPWR dedicated hardened hardware and CysRC remote control unit
   (see doc/Img and https://cybele-sailing.com)

   - Support of latest IMU devices with built-in fusion (RTIMULib2 is no longer used) : BNO085/BNO086 from HillCrest Labs is recommended
   (use BNO08X with HillCrest labs/CEVA firmware, original Bosch BNO055 no longer supported)

   - New specific pilot algorithms with auto-tune, auto-learning, ...

   - QT Dialogs

   - ...

Work in progress, to test this software:

   - install software as described hereafter

   - run autopilot UI using the __ApControl__ menu or desktop shorcut, or invoking "autopilot" or "autopilot_web" from command line
      This will automatically launch an autopilot server and the __ApControl__ UI.
      Note that the Autopilot server is now launched at startup: when it is running, click on black triangle down icon in the taskbar to open the trace window, or to hide/stop it.

   - optionally run a client in another terminal window ("cypilot_calibration","cypilot_client",...)

   See "Running Autopilot" hereafter for details.

___

# How to Install the cypilot package:

This is the basic installation for Autopilot standard user.

## 1) install package

This is a complete suggested installation procedure for basic users.

The minimal system configuration is as follow:
- RaspBerry PI4 (recommended memory : 8GB)
- OS version : Raspberry Pi OS 64-bit (bullseye)
- Kernel : 6.1.29 (GPIO I2C problems occured when using default 6.1.21 kernel)

While pip alone is sufficient to install from pre-built binary archives, up to date copies of the setuptools and wheel projects are useful to ensure you can also install from source archives:

__sudo python3 -m pip install --upgrade pip setuptools wheel__

Download __wheel file__ from https://cybele-sailing.com/software-package

Install __cypilot__ from wheel file:

__sudo pip3 install cypilot-1.0.0-cp39-cp39-linux_aarch64.whl__

note: to uninstall = __sudo pip3 uninstall cypilot==1.0.0__

## 2) complete installation

After package has been installed, installation must be completed using the __cypilot_init__ command:

__cypilot_init__

At least, select __-1- Complete Autopilot Installation__ from main menu, then from the opened submenu:
- step __-1 Install required packages__
- step __-2 Initialize configuration__
- step __-3 Create menu entries__
- then __-4 Return to main menu__

Reboot by selecting __-4-__ in the main menu.

To install __signal-k__ server, select step __-2-__ from main menu, install __signal-k dependancies__,
then when installing __signal-k server__, choose all default settings:
__default location__, __update__ or start from scratch, any __vessel name__, __MMSI__ (if you have one), do not use port 80 (use __default port 3000__), __do not enable SSL__

## 3) customize configuration to match your boat specifications

Update the configuration files which are located in $HOME/.cypilot directory:
   - NMEA, COM, ... ports assignment
   - sensor priorities
   - ...

Calibrate IMU (mounting position, gyro, heading, ...) using __cypilot_calibration__ utility.

See detailed documentation in the doc directory.

___

# Running Autopilot:

## 1- Using Raspberry PI GUI:

Run __Autopilot UI__ from Raspberry pi Menu : __AutoPilot > ApControl__
or
Double-click __ApControl__ UI icon on PI desktop

The following menu shortcuts are installed ("Cypilot menu", desktop, and/or "Cypilot Tools" folder):

   - Shortcuts to QT dialogs:

      - __ApCalibration__ : QT calibration menu (command line : __cypilot_calibration__)
      - __ApConfiguration__ : QT generic configuration client menu (command line : __cypilot_config__)
      - __ApControl__ : QT main autopilot dialog menu (command line : __autopilot__)
      - __ApRun__ : run autopilot server (command line : __cypilot__)
      - __AutotuneWizard__ : Autotune configuration dialog (same as longpress on Autotune button in __ApControl__ dialog)
      - __DashBoard__ : Dashboard utility
      - __Learning_GUI__ : learning manager GUI (in development)

   - Shortcuts to terminal windows:

      - __Learning_Terminal__ : learning manager terminal (in development)
      - __RC__ : Remote-control test and configuration terminal (command line : __cypilot_rc__)

   - Web browser:

      - __SignalK__ : SignalK
      - __WebUI__ : Autopilot control

## 2- Using Web UI:

Run __Autopilot Web UI__ from Raspberry pi Menu : __AutoPilot > Web UI__

When the UI or the Web UI is started, if no active server is detected, the Autopilot server is automatically launched, and it is closed on UI termination.
When the Web UI is started, a local Chromium Web Browser is launched in kiosk mode, and the Autopilot can be controled from any Wifi browser at address __http://cysbox-4:8000__
The Remote Control device can be used to control the Autopilot as soon as the Autopilot server is running.

## 3- Using command line:

### 1- Running Autopilot servers (only one executes at a time)

These server scripts can be run as tests:

__cypilot__             -- run the complete autopilot server : main pilot processes, sensors,
                       servo communication, remote control receiver, ...
                       The debug trace is displayed on the console windows.
                       * useful for testing the complete Autopilot server


Instead of running the complete autopilot these scripts provide a server with specific functionality:

__cypilot_boatimu__     -- run imu specific to boat motions
                       * useful for testing the imu (gyros) or even just reading gyros
                      
__cypilot_sensors__     -- convert and multiplex nmea0183 data
                       reads nmea0183 from serial ports or from tcp connections, and multiplexes
                       the output to tcp port 20220 by default
                       * convert and multiplex nmea0183 data

__cypilot_servo__       -- use to test or verify a working motor controller is detected,
                       * can be used to control the servo

### 2- Running Autopilot clients (run as many of these to connect to a server):

__autopilot__           -- Raspberry PI GUI to command autopilot (if not active, Autopilot server is launched)

__autopilot_web__       -- Autopilot Web UI (Chromium started in kiosk mode, and if not active, Autopilot server is launched)

__cypilot_calibration__ -- run Autopilot calibration dialog (IMU alignment, rudder calibration, settings)

__cypilot_config__      -- allow simple access to Autopilot current data

### 3- Test and configuration scripts

__cypilot_version__     -- display software version

__cypilot_bno085__      -- test and configure BNO085 IMU

__cypilot_ble__         -- test and configure Calypso Anemometer

___

# How to Prepare system for development:

This is a complete suggested installation procedure for developers

## 1) clone project from github

We advise to use our common directory structure, so to clone git to /home/pi/CysDev/cypilot

## 2) install package

While pip alone is sufficient to install from pre-built binary archives, up to date copies of the setuptools and wheel projects are useful to ensure you can also install from source archives:

__sudo python3 -m pip install --upgrade pip setuptools wheel__

Use wheel distribution from the dist directory __/home/pi/CysDev/cypilot/dist__

__cd /home/pi/CysDev/cypilot/dist__

__sudo pip3 install *.whl__

## 3) complete installation from development environment

To install with menu shortcuts pointing to development files, just run __python3 cypilot_init.py__ from the development environment.
At least, select __-1-__ from main menu, then step __-1,2,3-__ from the opened submenu, and __-4-__ to reboot.

__cd /home/pi/CysDev/cypilot/src/cypilot_init__

__python3 cypilot_init.py__

To build C extensions (linebuffer, servo, ...) in the development source tree:

__cd /home/pi/CysDev/cypilot__

__python3 setup.py build_ext__

To install __signal-k__ server, select step __-2-__ from main menu, install __signal-k dependancies__,
then when installing __signal-k server__, choose all default settings:
__default location__, __update__ or start from scratch, any __vessel name__, __MMSI__ (if you have one), do not use port 80 (use __default port 3000__), __do not enable SSL__

## 4) How to Build a complete package:

The development environment must have been installed (see "Prepare system for development" just before)

### 1) install build if not already done

__sudo pip3 install --upgrade build__

### 2) build

__cd /home/pi/CysDev/cypilot__

Optionaly clean previous build:

__rm -r build__
__rm -r dist__

Build package:

__python3 -m build . --wheel__

The built package is in dist repertory : __cypilot-1.0.0-cp39-cp39-linux_aarch64.whl__


