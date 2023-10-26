#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
#
# (C) 2020 Sean D'Epagnier (pypilot)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

import time
import math

import cypilot.pilot_path
import pyjson

from pilot_path import dprint as print # pylint: disable=redefined-builtin

class Value(object):
    """Value : value

    Args:
        name (string): name
        initial (float): initial value
    """

    def __init__(self, name, initial, **kwargs):
        self.name = name
        self.value = False
        self.watch = None
        self.client = None
        self.pwatch = False
        self.set(initial)

        self.info = {'type': 'Value'}
        # if persistent argument make the server store/load this value regularly
        if 'persistent' in kwargs and kwargs['persistent']:
            self.info['persistent'] = True

    def update(self, value):
        if isinstance(value, tuple):
            value = list(value)
        if self.value != value:
            self.set(value)

    def get_msg(self):
        if isinstance(self.value, str):
            return '"' + self.value + '"'
        return str(self.value)

    def set(self, value):
        if isinstance(value, tuple):
            value = list(value)
        self.value = value
        if self.watch:
            if self.watch.period == 0:  # and False:   # disable immediate
                self.client.send(self.name+'='+self.get_msg()+'\n')

            elif self.pwatch:
                t0 = time.monotonic()
                if t0 >= self.watch.time:
                    self.watch.time = t0  # watch already expired, increment time
                self.client.values.insert_watch(self.watch)
                self.pwatch = False


class JSONValue(Value):
    def get_msg(self):
        return pyjson.dumps(self.value)


def round_value(value, fmt):
    if isinstance(value, list):
        ret = '['
        if value:
            ret += round_value(value[0], fmt)
            for item in value[1:]:
                ret += ', ' + round_value(item, fmt)
        return ret + ']'
    elif isinstance(value, bool):
        if value:
            return 'true'
        return 'false'
    elif value is None:
        return 'null'
    try:
        if math.isnan(value):
            return '"nan"'
        return fmt % value
    except Exception as e:
        return str(e)


class RoundedValue(Value):
    def get_msg(self):
        return round_value(self.value, '%.3f')


class StringValue(Value):
    """Value : value

    Args:
        name (string): name
        initial (float): initial value
    """

    def get_msg(self):
        if isinstance(self.value, bool):
            strvalue = 'true' if self.value else 'false'
        else:
            strvalue = '"' + self.value + '"'
        return strvalue


class SensorValue(Value):
    def __init__(self, name, initial=False, fmt='%.3f', **kwargs):
        super().__init__(name, initial, **kwargs)
        self.directional = 'directional' in kwargs and kwargs['directional']
        self.fmt = fmt  # round to 3 places unless overrideen

        self.info['type'] = 'SensorValue'
        if self.directional:
            self.info['directional'] = True

    def get_msg(self):
        value = self.value
        if isinstance(value, tuple()):
            value = list(value)
        return round_value(value, self.fmt)


class Property(Value):
    """Property : Value that may be modified by external clients

    Args:
        name (string): name
        initial (float): initial value
    """

    def __init__(self, name, initial, **kwargs):
        super().__init__(name, initial, **kwargs)
        self.info['writable'] = True


class ResettableValue(Property):
    """ResettableValue : Value that may be modified by external clients

    Args:
        name (string): name
        initial (float): initial value
    """

    def __init__(self, name, initial, **kwargs):
        self.initial = initial
        super().__init__(name, initial, **kwargs)
        self.info['type'] = 'ResettableValue'

    def set(self, value):
        if not value:
            value = self.initial  # override value
        super().set(value)


class RangeProperty(Property):
    """RangeProperty : Value that may be modified by external clients with range limits

    Args:
        name (string): name
        initial (float): initial value
        min_value (float): min value
        max_value (float): max value
    """

    def __init__(self, name, initial, min_value, max_value, **kwargs):
        self.min_value = min_value
        self.max_value = max_value
        if initial < min_value or initial > max_value:
            print('invalid initial value for range property', name, initial)
        super().__init__(name, initial, **kwargs)

        self.info['type'] = 'RangeProperty'
        self.info['min'] = self.min_value
        self.info['max'] = self.max_value

    def get_msg(self):
        return f"{self.value:.4f}"

    def set(self, value):
        try:
            value = float(value)  # try to convert to number
        except:
            return  # ignore invalid value
        if value >= self.min_value and value <= self.max_value:
            super().set(value)

    def set_max(self, max_value):
        if self.value > max_value:
            self.value = max_value
        self.max_value = max_value

class RangeSetting(RangeProperty):
    """RangeSetting : Range property that is persistent and specifies the units

    Args:
        name (string): name
        initial (float): initial value
        min_value (float): min value
        max_value (float): max value
        units (string): units
    """
    def __init__(self, name, initial, min_value, max_value, units):
        self.units = units
        super().__init__(name, initial, min_value, max_value, persistent=True)
        self.info['type'] = 'RangeSetting'
        self.info['units'] = self.units

class EnumProperty(Property):
    def __init__(self, name, initial, choices, **kwargs):
        self.choices = choices
        super().__init__(name, initial, **kwargs)
        self.info['type'] = 'EnumProperty'
        self.info['choices'] = self.choices

    def set(self, value):
        for choice in self.choices:
            try:  # accept floating point equivilent, 10.0 is 10
                if float(choice) != float(value):
                    continue
            except:
                if str(choice) != str(value):
                    continue
            super().set(value)
            return
        print('invalid set', self.name, '=', value)

class EnumSetting(EnumProperty):
    def __init__(self, name, initial, choices, **kwargs):
        super().__init__(name, initial, choices, **kwargs)
        self.info['type'] = 'EnumSetting'

class BooleanValue(Value):
    def get_msg(self):
        return 'true' if self.value else 'false'

class BooleanProperty(BooleanValue):
    def __init__(self, name, initial, **kwargs):
        super().__init__(name, initial, **kwargs)
        self.info['writable'] = True
        self.info['type'] = 'BooleanProperty'

    def set(self, value):
        super().set(bool(value))
        
class BooleanSetting(BooleanProperty):
    def __init__(self, name, initial, **kwargs):
        super().__init__(name, initial, **kwargs)
        self.info['type'] = 'BooleanSetting'

def pilot_values_main():
    print('Version:', cypilot.pilot_path.STRVERSION)

if __name__ == '__main__':
    pilot_values_main()
