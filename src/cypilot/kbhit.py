#!/usr/bin/env python
#
# (C) 2020 JF/ED for Cybele Services (cf@cybele-sailing.com)
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b


import sys
import termios
import atexit
from select import select
import time

class KBHit:

    def __init__(self):
        '''Creates a KBHit object that you can call to do various keyboard things.'''
        # Save the terminal settings
        self.fd = sys.stdin.fileno()
        self.new_term = termios.tcgetattr(self.fd)
        self.old_term = termios.tcgetattr(self.fd)

        # New terminal setting unbuffered
        self.init()

        # Support normal-terminal reset at exit
        atexit.register(self.exit)

    def init(self):
        ''' New terminal setting unbuffered
        '''
        self.new_term[3] = self.new_term[3] & ~termios.ICANON & ~termios.ECHO
        termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)

    def exit(self):
        ''' Resets to normal terminal.
        '''
        termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

    def getch(self):
        ''' Returns a keyboard character after kbhit() has been called.
        '''
        return sys.stdin.read(1)

    def kbhit(self):
        ''' Returns True if keyboard character was hit, False otherwise.
        '''
        dr, __, __ = select([sys.stdin], [], [], 0)
        return dr != []


if __name__ == '__main__':
    KB = KBHit()
    while True:
        if KB.kbhit(): #If a key is pressed:
            K_IN = KB.getch() #Detect what key was pressed
            print("You pressed ", K_IN, "!") #Do something
            if K_IN == 'q':
                KB.exit()
                exit()
            elif K_IN == 't':
                KB.exit()
                T = input("Enter string : ")
                print("You entered :", T)
                KB.init()
        time.sleep(0.01)
