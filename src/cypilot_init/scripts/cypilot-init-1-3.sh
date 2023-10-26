#!/bin/bash

# 2020 JF/ED / Cybele Services (cf@cybele-sailing.com)
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

cd "$(dirname "$0")"

echo "Install ther utilities and tools"

# Check CysDev directory
if ! test -d ~/CysDev
then
    mkdir ~/CysDev
    echo "Mkdir CysDev directory"
fi

# Install vscode
echo "-----------------------------------------------------------"
sleep 1
read -p "Install Visual Studio Code ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : Visual Studio Code"
    sudo apt-get -y install gnome-keyring
    sudo apt install -y code
    sleep 1
    read -p "Install Visual Studio Code recommended extensions ? (y/n) " RESP
    if [ "$RESP" = "y" ]; then
        echo "Installing : Visual Studio Code recommended extensions"
        code --install-extension GitHub.vscode-pull-request-github
        code --install-extension KevinRose.vsc-python-indent
        code --install-extension kopub.pydocstring
        code --install-extension mhutchie.git-graph
        code --install-extension ms-python.python
        code --install-extension ms-python.vscode-pylance
        code --install-extension ms-toolsai.jupyter
        code --install-extension ms-toolsai.jupyter-keymap
        code --install-extension ms-toolsai.jupyter-renderers
        code --install-extension ms-vscode.cpptools
        code --install-extension njpwerner.autodocstring
        code --install-extension reddevil.pythondoc
        code --install-extension spadin.remote-x11
        code --install-extension spadin.remote-x11-ssh
        code --install-extension tht13.python
    fi
fi

# Install CYS GitHub configuration
echo "-----------------------------------------------------------"
sleep 1
read -p "Install CYS GitHub configuration ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : CYS GitHub configuration"
    if ! test -d ~/CysDev/cypilot
    then
        mkdir ~/CysDev/cypilot
        echo "Mkdir CysDev/cypilot directory"
    fi
    if ! test -d ~/CysDev/cypilot/.git
    then
        mkdir ~/CysDev/cypilot/.git
        echo "Mkdir CysDev/cypilot/.git directory"
    fi
    cp ~/CysDev/cypilot/src/cypilot_init/scripts/files/pi4-64/git/config ~/CysDev/cypilot/.git/config
fi


# Install libreoffice
echo "-----------------------------------------------------------"
sleep 1
read -p "Install libreoffice ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : libreoffice"
    sudo apt-get -y install libreoffice
fi

# Install AVRDUDE
echo "-----------------------------------------------------------"
sleep 1
read -p "Install AVRDUDE tool (to flash ATMEGA NMEA2K Gateway) ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : AVRDUDE tool"
    sudo apt-get -y install avrdude
fi

# Install DTC Compiler
echo "-----------------------------------------------------------"
sleep 1
read -p "Install DTC compiler (to compile Hat configuation memory) ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : DTC compiler"
    sudo apt-get -y install device-tree-compiler
fi

echo ""
read -p "Done - Enter return to exit" RESP


