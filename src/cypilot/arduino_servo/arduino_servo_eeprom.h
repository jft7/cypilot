/* Copyright (C) 2019 Sean D'Epagnier <seandepagnier@gmail.com>
 *
 * (C) Modified 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
 * Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b
 * 
 * This Program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public
 * License as published by the Free Software Foundation; either
 * version 3 of the License, or (at your option) any later version.
 * 
 */

// This structure is stored in eeprom memory
// The CysPWR processor shares these parameters with the cypilot driver
// so ascending compatibility is ensured by reading signature at the end
// of the structure:
// - new parameters must be added just before signature
// - no longer used parameters must be initialized to default value

// When new parameters are added, signature value is updated in order
// CysPWR firmware knows about parameter validity.

#define CYSPOWER_SIGNATURE "cysv03"

struct arduino_servo_data {
    // Servo data - version 'cysv01'
    uint16_t max_current, max_controller_temp, max_motor_temp;
    uint8_t rudder_range;
    int16_t rudder_offset;
    int16_t rudder_scale;
    int16_t rudder_nonlinearity;
    uint8_t max_slew_speed, max_slew_slow;
    uint8_t current_factor, voltage_factor;
    uint8_t current_offset, voltage_offset;
    uint8_t min_speed, max_speed;
    uint16_t gain;
    // Servo data _ version 'cysv03'
    uint16_t rudder_brake;
    // ...
    // Signature
    char signature[6]; // changes if eeprom format changes,
                       // put at end so it's written last
} __attribute__((packed)) ;

class arduino_servo_eeprom
{
public:
    arduino_servo_eeprom();
    
    double get_max_current();
    void set_max_current(double max_current);
    double get_max_controller_temp();
    void set_max_controller_temp(double max_controller_temp);
    double get_max_motor_temp();
    void set_max_motor_temp(double max_motor_temp);
    double get_rudder_range();
    void set_rudder_range(double rudder_range);
    double get_rudder_offset();
    void set_rudder_offset(double rudder_offset);
    double get_rudder_scale();
    void set_rudder_scale(double rudder_scale);
    double get_rudder_nonlinearity();
    void set_rudder_nonlinearity(double rudder_nonlinearity);
    double get_max_slew_speed();
    void set_max_slew_speed(double max_slew_speed);
    double get_max_slew_slow();
    void set_max_slew_slow(double max_slew_slow);

    double get_current_factor();
    void set_current_factor(double current_factor);
    double get_current_offset();
    void set_current_offset(double current_offset);

    double get_voltage_factor();
    void set_voltage_factor(double voltage_factor);
    double get_voltage_offset();
    void set_voltage_offset(double voltage_offset);

    double get_min_speed();
    void set_min_speed(double min_speed);
    double get_max_speed();
    void set_max_speed(double max_speed);

    double get_gain();
    void set_gain(double gain);
    
    double get_rudder_brake();
    void set_rudder_brake(double rudder_brake);
    
    int need_read(uint8_t *end=0);
    int need_write();
    bool initial();
    void value(uint8_t addr, uint8_t val);
    uint8_t data(uint8_t addr) { return ((uint8_t*)&local)[addr]; }

    arduino_servo_data local; // local version of servo data
    bool initial_read; // false until all data read from arduino
    
private:
    arduino_servo_data arduino; // data retrieved from arduino
    uint8_t verified[sizeof arduino]; // boolean for if data is valid
};
