#!/bin/bash

# 2020 JF/ED / Cybele Services (cf@cybele-sailing.com)
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

# reboot now
echo ""
sleep 1
read -p "Reboot now(y/n) ?" RESP
if [ "$RESP" = "y" ]; then
    echo "Rebooting now ..."
    sleep 2
    sudo reboot
else
    echo "Warning : you will have to reboot before using autopîlot"
fi

echo ""
read -p "Done - Enter return to exit" RESP


