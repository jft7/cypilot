#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (support@netcys.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#

# pylint: disable=unused-import, no-member, wildcard-import, unused-wildcard-import

try:
    import orjson
    from orjson import loads
    # from orjson import loads
    def dumps(obj,indent=0):
        if indent == 0:
            jstr = orjson.dumps(obj).decode()
        else:
            jstr = orjson.dumps(obj,option=orjson.OPT_INDENT_2).decode()
        return jstr
            
    def load(file):
        return orjson.loads(file.read())
    
    def dump(obj,file,indent=0):
        file.write( dumps(obj,indent) )
        
except Exception as e:
    print('WARNING: python orjson library failed, performance may be affected', e)
    import json
    from json import *
