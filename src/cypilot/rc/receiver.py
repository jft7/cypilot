""" RC module"""

import time
import board
import busio
import digitalio
import RPi.GPIO as gpio
import adafruit_rfm69
# from getmac import get_mac_address as gma

import cypilot.pilot_path
from client import cypilotClient
from kbhit import KBHit

from pilot_path import dprint as print # pylint: disable=locally-disabled, redefined-builtin

# pylint: disable=protected-access, bare-except

class RadioControl():
    """ Class which manage the radio chip manipulation """
    def __init__(self, RADIO_FREQ_MHZ=434.0, TX_POWER=12, FQ_DEVIATION=19200, BITRATE=9600, DEBUG=False):
        # parameter used by function
        self._order = None
        self._encryption_key_init = (
            b"\x01\x02\x03\x04\x05\x06\x07\x08\x01\x02\x03\x04\x05\x06\x07\x08"
        )
        self._encryption_key = self.__get_key()
        self._debug = DEBUG

        #parameter used to init the radio chip
        cs_pin = digitalio.DigitalInOut(board.CE1)
        reset = digitalio.DigitalInOut(board.D26)
        rfm69_g0 = 25

        #callback/interrupt definition
        gpio.setmode(gpio.BCM)
        gpio.setup(rfm69_g0, gpio.IN, pull_up_down=gpio.PUD_DOWN)  # activate input
        gpio.add_event_detect(rfm69_g0, gpio.RISING, bouncetime=50)
        gpio.add_event_callback(rfm69_g0, self.__callback)

        #definition of SPI
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

        #radio init
        try:
            self.radio = adafruit_rfm69.RFM69(spi, cs_pin, reset, RADIO_FREQ_MHZ)
        except:
            self.radio = None
            return
        self.radio = adafruit_rfm69.RFM69(spi, cs_pin, reset, RADIO_FREQ_MHZ)
        self.radio.encryption_key = self._encryption_key
        self.radio.tx_power = TX_POWER
        self.radio.frequency_deviation = FQ_DEVIATION
        self.radio.bitrate = BITRATE

        # From RadioHead:
        # - CONFIG_GFSK (RH_RF69_DATAMODUL_DATAMODE_PACKET | RH_RF69_DATAMODUL_MODULATIONTYPE_FSK | RH_RF69_DATAMODUL_MODULATIONSHAPING_FSK_BT1_0)
        #     = (0x00|0x00|0x01)
        #     = 0x01
        # - CONFIG_WHITE (RH_RF69_PACKETCONFIG1_PACKETFORMAT_VARIABLE | RH_RF69_PACKETCONFIG1_DCFREE_WHITENING | RH_RF69_PACKETCONFIG1_CRC_ON | RH_RF69_PACKETCONFIG1_ADDRESSFILTERING_NONE)
        #     = (0x80|0x40|0x10|0x00)
        #     = 0xd0

        # Register initialization from RadioHead table:
        # 02,            03,   04,   05,   06,   19,   1a, 37
        # CONFIG_GFSK, 0x3e, 0x80, 0x00, 0x52, 0xf4, 0xf5, CONFIG_WHITE (GFSK_Rb2Fd5)
        self.radio._write_u8(0x02, 0x01) # CONFIG_GFSK
        self.radio._write_u8(0x03, 0x3e)
        self.radio._write_u8(0x04, 0x80)
        self.radio._write_u8(0x05, 0x00)
        self.radio._write_u8(0x06, 0x52)
        self.radio._write_u8(0x19, 0xf4)
        self.radio._write_u8(0x1a, 0xf5)
        self.radio._write_u8(0x37, 0xd0) # CONFIG_WHITE

        #start listening
        self.radio.listen()

    def __get_key(self):
        """ Define encryption key from MAC address"""
        # mac = gma().replace(":", "") + "0000"
        # return bytes(mac, 'utf-8')
        """ Define encryption key from CPU identifier"""
        try:
            f = open('/proc/cpuinfo', 'r')
            for line in f:
                if line[0:6] == 'Serial':
                    cpu_id = line[-17:-1]
            f.close()
        except:
            cpu_id = "0000000000000000"
        return bytes(cpu_id, 'utf-8')

    def __callback(self, channel):
        """ Interrupt callback function, update self._order from packet receive,
        return channel """
        packet = self.radio.receive()
        rssi = str(self.radio.last_rssi)
        if packet is not None:
            self._order = int.from_bytes(packet, byteorder='little', signed='true')
            print(str(self._order))
            if self._debug:
                print("RSSI: " + rssi)
                #print("Chip Temp: " + str(self.radio.temperature))
                #print("Frequency: " + str(self.radio.frequency_mhz))
                #print("Operation mode: " + str(self.radio.operation_mode))
                #print("TX Power: " + str(self.radio.tx_power))
                #print("Bitrate: " + str(self.radio.bitrate))
                #print("Frequency deviation: " + str(self.radio.frequency_deviation))
        return channel

    def appair_mode(self):
        """ Switch encryption key to self._encryption_key_init"""
        self.radio.encryption_key = self._encryption_key_init

    def transmit_mode(self):
        """ Switch encryption key to self._encryption_key"""
        self.radio.encryption_key = self._encryption_key

    def send_appair_key(self):
        """ Appair function """
        print("Sending appair key")
        self.radio.send(self._encryption_key)
        self.radio.encryption_key = self._encryption_key
        print("Returned to transmit mode")

    @property
    def order(self):
        """ get function """
        return self._order

    @order.deleter
    def order(self):
        """ del function"""
        self._order = None

class RemoteControl(object):
    """Remote Class from jft7"""
    def __init__(self):
        self.last_msg = {}
        self.last_msg['ap.enabled'] = False
        self.last_msg['ap.heading_command'] = 0
        self.client = cypilotClient('localhost')
        self.client.connect(False)
        self.watchlist = [
            'ap.enabled',
            'ap.heading_command',
            'ap.mode'
            ]
        for name in self.watchlist:
            self.client.watch(name)

    def heading(self, value):
        """ Define new heading"""
        new_heading = self.last_msg['ap.heading_command'] + value
        self.client.set('ap.heading_command', new_heading)
        return new_heading

    def tack(self, direction):
        """ Tack command if ap enabled
            Argument [string]: direction"""
        #need to be tested
        if self.last_msg['ap.enabled']:
            if self.last_msg['ap.mode'] in ['gps', 'rudder angle']:
                print("No remote auto tack in this mode")
                return
            else:
                self.client.set('ap.tack.direction', direction)
                print("Tack/jibe to ", direction)
                self.client.set('ap.tack.state', 'begin')
        else:
            print("please engage AP before auto tacking")

    def change_mode(self):
        """ Change mode beetween 'wind', 'true wind', 'compass'.
            If previous mode was 'gps', go to 'compass'
        """
        if self.last_msg['ap.mode'] in ['gps', 'true wind', 'rudder angle']:
            self.client.set('ap.mode', 'compass')
            print("Change mode to 'compass")
        elif self.last_msg['ap.mode'] == 'compass':
            self.client.set('ap.mode', 'wind')
            print("Change mode to 'wind")
        elif self.last_msg['ap.mode'] == 'wind':
            self.client.set('ap.mode', 'true wind')
            print("Change mode to 'true wind")


    def engage(self):
        """ Engage command"""
        if self.last_msg['ap.enabled']:
            print("Set AP OFF")
            #self.client.set('servo.command', 0)
            self.client.set('ap.enabled', False)
        else:
            print("Set AP ON")
            try:
                self.client.set('ap.heading_command', self.last_msg['ap.heading'])
            except KeyError as error:
                print("No key ", error, ". Keep the last ap.heading_command.")

            self.client.set('ap.enabled', True)
            return self.last_msg['ap.heading_command']

    def poll(self):
        """ Poll command"""
        msgs = self.client.receive()
        for name, value in msgs.items():
            self.last_msg[name] = value

        # receive heading once per second if autopilot is not enabled
        self.client.watch(
            'ap.heading', False if self.last_msg['ap.enabled'] else 1)

class RemoteControlClient(RemoteControl):
    """
    RemoteControlClient
    """
    def __init__(self, multi_processing=True, sleep_time=0.2):
        super(RemoteControlClient, self).__init__()

        self.remote = None
        self.radio = None
        self.sleep = sleep_time

        if multi_processing:
            import multiprocessing
            self.process = multiprocessing.Process(target=self.tprocess, daemon=True, name='RemoteControl')
            self.process.start()
        else:
            self.remote = RemoteControl()
            self.radio = RadioControl()

    def init(self):
        self.remote = RemoteControl()
        self.radio = RadioControl()

    def tprocess(self):
        """
        RC Process
        """
        self.init()
        print('RC Poll Period ', self.sleep)
        while True:
            time.sleep(self.sleep)
            self.poll()

    def poll(self):
        """
        RC Poll
        """
        #check if there is new data
        self.remote.poll()
        # if there is new order from radio remote, apply change to server
        if self.radio.order is not None:
            if self.radio.order == 0:
                self.remote.engage()
            if self.radio.order in [-10, -1, 1, 10]:
                heading_command = self.remote.heading(self.radio.order)
                print('Heading command : ', heading_command)
            if self.radio.order in [-11, 11]:
                if self.radio.order < 0:
                    print("Tack to port")
                    self.remote.tack("port")
                else:
                    print("Tack to starboard")
                    self.remote.tack("starboard")
            if self.radio.order == 20:
                print("Someone ask for key")
                self.radio.send_appair_key()
            if self.radio.order == 30:
                print("Change AP Mode")
                self.remote.change_mode()
            del self.radio.order

def remote_main(sleep_time=0.2):
    """ Main remote"""
    print('Version:', cypilot.pilot_path.STRVERSION)
    print('Use CysBoxRC key to control.\n'
          'If you need to appair a new device,\n'
          'use following command: \n'
          ' y : enter in appair mode \n'
          ' n : return to transmit mode \n'
          ' d : debug \n'
          ' r : RSSI measure \n'
          ' q : quit \n')

    rc = RemoteControlClient(multi_processing=False)
    kbh = KBHit()

    # print('Raspberry serial number : ', str(rc.radio._encryption_key))

    while True:
        #check if there is a entry, to permit appair mode
        if kbh.kbhit():
            k = kbh.getch()
            if k == 'q':
                exit()
            if rc.radio.radio:
                if k == 'y':
                    rc.radio.appair_mode()
                    print("Appair mode")
                if k == 'n':
                    rc.radio.transmit_mode()
                    print("Transmit mode")
                if k == 'd':
                    rc.radio._debug = not rc.radio._debug
                    if rc.radio._debug:
                        print('Debug mode ON')
                    else:
                        print('Debug mode OFF')
                if k == 'r':
                    rc.radio.radio.operation_mode = adafruit_rfm69.STANDBY_MODE
                    rc.radio.radio.idle()
                    rc.radio.radio._write_u8(0x29, 0xff)
                    rc.radio.radio.listen()
                    time.sleep(1.0)
                    rssi = str(rc.radio.radio.rssi)
                    print("RSSI: " + rssi)
                    rc.radio.radio.idle()
                    rc.radio.radio._write_u8(0x29, 0xe4)
                    rc.radio.radio.listen()
            else:
                print('No RF Radio device')

        #waiting time
        time.sleep(sleep_time)

        #check if there is new data
        rc.poll()

if __name__ == '__main__':
    del print # disable cypilot trace
    remote_main(0.2)
