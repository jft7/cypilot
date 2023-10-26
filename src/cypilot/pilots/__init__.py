# import all scripts in this directory

# pylint: disable=locally-disabled, missing-docstring, bare-except, broad-except

import sys
import os
import importlib

import pilot_path

DEFAULT = []

for module in os.listdir(os.path.dirname(__file__)):
    if module == '__init__.py' or module[-3:] != '.py' or module.startswith('.'):
        continue
    if module == 'pilot.py':
        continue
    # to add an algorythm without auto-detecting it, add this lines:
    #if module == 'name_of_your_file.py':
    #    continue

    try:
        mod = importlib.import_module('pilots.'+module[:-3])
    except Exception as e1:
        try:
            mod = importlib.import_module(module[:-3])
        except Exception as e2:
            print('ERROR loading', module, e1, ' ', e2)
            continue

    try:
        DEFAULT.append(mod.pilot)
    except:
        pass
