/* Copyright (C) 2017 Sean D'Epagnier <seandepagnier@gmail.com>
 *
 * (C) Modified 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
 *
 * This Program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public
 * License as published by the Free Software Foundation; either
 * version 3 of the License, or (at your option) any later version.
 */

class LineBuffer {
public:
    LineBuffer(int _fd);
    const char *line();
    const char *line_nmea();
    bool recv();
    const char *readline_nmea();
private:
    bool next_nmea();
    bool readline_buf_nmea();
    int readline_buf();
    int fd;
    int b, pos, len;
    char buf[2][16384];
};
