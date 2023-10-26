from setuptools import setup, Extension

linebuffer_module = Extension('_linebuffer',
                              sources=['src/cypilot/linebuffer/linebuffer.cpp',
                                       'src/cypilot/linebuffer/linebuffer.i'],
                              extra_compile_args=['-Wno-unused-result'],
                              swig_opts=['-c++']
                              )

arduino_servo_module = Extension('_arduino_servo',
                                 sources=['src/cypilot/arduino_servo/arduino_servo.cpp',
                                          'src/cypilot/arduino_servo/arduino_servo_eeprom.cpp', 'src/cypilot/arduino_servo/arduino_servo.i'],
                                 extra_compile_args=['-Wno-unused-result'],
                                 swig_opts=['-c++']
                                 )


from setuptools import setup, Extension
from distutils.command.build import build

class build_alt_order(build):
    def __init__(self, *args):
        super().__init__(*args)
        self.sub_commands = [('build_ext', build.has_ext_modules), ('build_py', build.has_pure_modules)]

if __name__ == "__main__":
    setup(ext_modules=[arduino_servo_module, linebuffer_module])
