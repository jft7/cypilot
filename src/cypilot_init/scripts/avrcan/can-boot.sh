# Upload firmware in CysBOX Atmega64m1 built-in gateway connected on port /dev/ttyUSB4
avrdude -C./avrdude.conf -v -patmega64m1 -cstk500 -P/dev/ttyUSB4 -Uflash:w:./optiboot_atmega64M1_16Mhz.hex:i -Ulock:w:0x0F:m

