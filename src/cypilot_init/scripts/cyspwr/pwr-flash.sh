# Upload firmware in CysPWR module connected on port /dev/ttyUSB2
avrdude -C./avrdude.conf -v -patmega64m1 -carduino -P/dev/ttyUSB2 -b57600 -D -Uflash:w:./motor-cys.hex:i
