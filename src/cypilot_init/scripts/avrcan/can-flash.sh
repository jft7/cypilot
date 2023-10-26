# Upload firmware in CysBOX Atmega64m1 built-in gateway connected on port /dev/ttyACM0
avrdude -C./avrdude.conf -v -patmega64m1 -carduino -P/dev/ttyAMA0 -b57600 -D -Uflash:w:./nmea2000gw.hex:i
