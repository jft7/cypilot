#!/usr/bin/env python
#
# 2020 JF/ED / Cybele Services (cf@cybele-sailing.com)
#
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

""" Raspberry PI4 Initialization
"""

# pylint: disable=locally-disabled, missing-docstring, bare-except, broad-except, unused-import

# /etc/xdg/menus/lxde-pi-applications.menu
# command : xdg-desktop-menu

import os
import sys
#local import of desktop_entry_lib to fix terminal key problem in v2.0 of desktop-entry-lib package
#if fixed in future version of the library, just remove desktop_entry_lib.py from current directory
from desktop_entry_lib import DesktopEntry
from consolemenu import *
from consolemenu.items import *

IPATH = os.path.dirname(__file__)
PPATH = os.path.dirname(IPATH)
EPATH = os.path.realpath(sys.executable)
HOME = os.environ['HOME']
DESKTOP = HOME + '/Desktop'

if "/src/" in IPATH :
    TITLE1 = "Cypilot Initialization : DEVELOPMENT"
    TITLE2 = "Cypilot Installation : DEVELOPMENT"
else:
    TITLE1 = "Cypilot Initialization"
    TITLE2 = "Cypilot Installation"

def make_menu_shortcut(name, comment, exec=None, script=None, terminal=False, desktop=True, desktop_folder=None, menu=False):
    app_entry = DesktopEntry()
    app_entry.Name.default_text = name
    app_entry.Comment.default_text = comment
    app_entry.Type = "Application"
    app_entry.Terminal = terminal
    app_entry.Icon = IPATH + '/icons/Logo_CYS_sailing.jpg'
    if exec:
        app_entry.Exec = exec
    elif script:
        app_entry.Exec = EPATH + ' ' + PPATH + '/cypilot/' + script + '.py'
    else:
        return
    if desktop:
        target_dir = DESKTOP
        if desktop_folder:
            target_dir = DESKTOP + '/' +desktop_folder
            try:
                os.mkdir( target_dir )
            except FileExistsError:
                pass
        app_entry.write_file(target_dir + '/' + name + '.desktop')
    if menu:
        try:
            os.mkdir( HOME + '/.cypilot' )
        except FileExistsError:
            pass
        try:
            os.mkdir( HOME + '/.cypilot/menu' )
        except FileExistsError:
            pass
        app_entry_file = HOME + '/.cypilot/menu/cypilot_menu_' + name + '.desktop'
        dir_entry_file = HOME + '/.cypilot/menu/cypilot_menu.directory'
        app_entry.write_file(app_entry_file)
        dir_entry = DesktopEntry()
        dir_entry.Name.default_text = 'Cypilot'
        dir_entry.Comment.default_text = 'Autopilot'
        dir_entry.Type = 'Directory'
        dir_entry.Icon = IPATH + '/icons/Logo_CYS_sailing.jpg'
        dir_entry.write_file(dir_entry_file)
        os.system( 'xdg-desktop-menu install --novendor ' + dir_entry_file + ' ' + app_entry_file )

def make_menu_shortcuts():
    print('Create menu entries')
    # Autopilot main process
    make_menu_shortcut('ApRun', 'ApRun', script='ui/qt_autopilot', desktop_folder='CypilotTools', terminal=False, menu=True)
    # Qt Control dialog
    make_menu_shortcut('ApControl', 'AP Control UI', script='ui/qt_autopilot_control', desktop_folder='CypilotTools', terminal=False)
    make_menu_shortcut('ApControl', 'AP Control UI', script='ui/qt_autopilot_control', terminal=False, desktop=True, menu=True)
    # Qt Calibration dialog
    make_menu_shortcut('ApCalibration', 'AP Calibration UI', script='ui/qt_autopilot_calibration', desktop_folder='CypilotTools', menu=True, terminal=False)
    # Qt Configuration dialog
    make_menu_shortcut('ApConfiguration', 'AP Configuration UI', script='ui/qt_autopilot_client', desktop_folder='CypilotTools', menu=True, terminal=False)
    # Qt Autotune Wizard
    make_menu_shortcut('AutotuneWizard', 'Autotune Wizard', script='ui/autotune_wizard', desktop_folder='CypilotTools', menu=True, terminal=False)
    # Qt Dashboard
    make_menu_shortcut('Dashboard', 'Dashboard', script='ui/dashboard', desktop_folder='CypilotTools', menu=True, terminal=False)
    # Qt Learning Manager
    make_menu_shortcut('Learning_GUI', 'Learning GUI', script='pilots/learningmanager/learninggui_v2', desktop_folder='CypilotTools', menu=True, terminal=False)
    make_menu_shortcut('Learning_Terminal', 'Learning Terminal', script='pilots/learningmanager/learningmanager_v2', desktop_folder='CypilotTools', menu=True, terminal=True)
    # Remote Control
    make_menu_shortcut('RC', 'Remote Control', script='rc/receiver', desktop_folder='CypilotTools', menu=True, terminal=True)
    # Web UI
    make_menu_shortcut('WebUI', 'Web UI', script='web/web', desktop_folder='CypilotTools', menu=True, terminal=False)
    # Add Autostart command
    os.system('mkdir /home/pi/.config/autostart 2>/dev/null')
    os.system('sudo cp $HOME/Desktop/CypilotTools/ApRun.desktop $HOME/.config/autostart/ApRun.desktop')

def install_signal_k_server():
    os.system(IPATH + '/scripts/cypilot-init-1-2.sh')
    make_menu_shortcut('SignalK', 'Signal-K Server', exec='/usr/bin/chromium-browser http://127.0.0.1:3000/admin/#/dashboard', terminal=False, desktop=True, menu=True)

def init_pi_menu():
    menu2 = ConsoleMenu(TITLE2, "Complete Autopilot installation : select operation to be done")
    menu1 = ConsoleMenu(TITLE1, "Autopilot initialization : select operation to be done")

    menu1_item1 = SubmenuItem("Complete Autopilot installation", menu2, menu1)
    menu1_item2 = FunctionItem("Install Signal-K server (optional)", install_signal_k_server)
    menu1_item3 = CommandItem("Install miscellaneous development tools (optional)", IPATH + '/scripts/cypilot-init-1-3.sh')
    menu1_item4 = CommandItem("Reboot",  IPATH + '/scripts/install-reboot.sh')

    menu2_item1 = CommandItem("Install required packages",  IPATH + '/scripts/cypilot-init-2-1.sh')
    menu2_item2 = CommandItem("Initialize configuration (warning: files will be overwritten)", IPATH + '/scripts/cypilot-init-2-2.sh')
    menu2_item3 = FunctionItem("Create menu entries", make_menu_shortcuts)

    menu1.append_item(menu1_item1)
    menu1.append_item(menu1_item2)
    menu1.append_item(menu1_item3)
    menu1.append_item(menu1_item4)

    menu2.append_item(menu2_item1)
    menu2.append_item(menu2_item2)
    menu2.append_item(menu2_item3)

    menu1.show()

if __name__ == '__main__':
    init_pi_menu()
