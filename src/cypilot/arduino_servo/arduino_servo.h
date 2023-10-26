/* Copyright (C) 2018 Sean D'Epagnier <seandepagnier@gmail.com>
 *
 * This Program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public
 * License as published by the Free Software Foundation; either
 * version 3 of the License, or (at your option) any later version.
 * 
 * Modified (C) 2020 JF for Cybele Services (jf@netcys.com)
 *
 *   Support CysBOX/CysPWR dedicated hardened hardware
 */

#include "arduino_servo_eeprom.h"

class ArduinoServo
{
    enum Telemetry {FLAGS= 1, CURRENT = 2, VOLTAGE = 4, SPEED = 8, POSITION = 16, CONTROLLER_TEMP = 32, MOTOR_TEMP = 64, RUDDER = 128, EEPROM = 256, VERSION_FIRMWARE = 512};
    enum {SYNC=1, OVERTEMP_FAULT=2, OVERCURRENT_FAULT=4, ENGAGED=8, INVALID=16*1, PORT_PIN_FAULT=16*2, STARBOARD_PIN_FAULT=16*4};
public:
    ArduinoServo(int _fd);

    void command(double command);
    void angle(double angle);
    void reset();
    void disengage();
    void reprogram();
    int poll();
    bool fault();
    void params(double _raw_max_current, double _rudder_min, double _rudder_max, double _max_current, double _max_controller_temp, double _max_motor_temp, double _rudder_range, double _rudder_offset, double _rudder_scale, double _rudder_nonlinearity, double _max_slew_speed, double _max_slew_slow, double _current_factor, double _current_offset, double _voltage_factor, double _voltage_offset, double _min_speed, double _max_speed, double _gain, double _rudder_brake);

    // firmware version
    int version_firmware;

    // sensors
    double voltage, current, controller_temp, motor_temp, rudder;

    // parameters
    double raw_max_current;
    double rudder_min, rudder_max;

    // eeprom settings (some are parameters)
    double max_current, max_controller_temp, max_motor_temp;
    double rudder_range, rudder_offset, rudder_scale, rudder_nonlinearity;
    double max_slew_speed, max_slew_slow;
    double current_factor, current_offset, voltage_factor, voltage_offset;

    double min_speed, max_speed;
    double gain;
    double rudder_brake;
    
    int flags;

private:
    void send_value(uint8_t command, uint16_t value);
    void send_params();
    void raw_command(uint16_t value);
    void raw_angle(uint16_t value);
    int process_packet(uint8_t *in_buf);
    int in_sync_count;
    uint8_t in_buf[1024];
    int in_buf_len;
    int fd;
    int out_sync;
    int params_set;
    int packet_count;

    int nosync_count, nosync_data;

    arduino_servo_eeprom eeprom;
    int eeprom_read;
};
