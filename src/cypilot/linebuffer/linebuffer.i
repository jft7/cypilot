/* File: linebuffer.i */
%module linebuffer

%{
#include <stdlib.h>
#include <string.h>
#include "linebuffer.h"
%}

%include <pybuffer.i>
%pybuffer_string(const char* msg)

%inline %{
int nmea_cksum(char *msg) {
    int value = 0;
    size_t len = strlen(msg);
    for(int i=0; i<len; i++)
        value ^= msg[i];
    return value;
}
%}

class LineBuffer {
public:
    LineBuffer(int _fd);

    const char *line();
    const char *line_nmea();
    bool recv();
    const char *readline_nmea();
};
