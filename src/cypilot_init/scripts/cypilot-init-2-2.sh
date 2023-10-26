#!/bin/bash

# 2020 JF/ED / Cybele Services (cf@cybele-sailing.com)
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

echo "Initialize configuration (warning: files will be overwritten)"
echo ""
echo "Copying : cypilot default configuration files"

if [ -s /proc/device-tree/hat/product ]
then
    product="$(tr -d '\0' </proc/device-tree/hat/product)"
fi
if [ -s /proc/device-tree/hat/product_id ]
then
    product_id="$(tr -d '\0' </proc/device-tree/hat/product_id)"
fi
if [ -s /proc/device-tree/hat/product_ver ]
then
    product_ver="$(tr -d '\0' </proc/device-tree/hat/product_ver)"
fi

echo ""
if [ "$product_id" = "0x9599" ]
then
    echo "CysBOX hardware detected:"
    echo "    - Product Name    : "$product
    echo "    - Product Id      : "$product_id
    echo "    - Product Version : "$product_ver
else
    echo "No CysBOX hardware detected"
fi
echo ""


cd "$(dirname "$0")"

cp -rT ./files/pi4-64/home ~/.
sudo cp -rT ./files/pi4-64/etc /etc

echo ""
read -p "Install new /boot/config.txt ? (y/n) " RESP
if [ "$RESP" = "y" ]
then
    read -p "Enter CysBOX Hardware Version (1/3) : " VER
    config="config-cysbox-v"$VER.txt

    if ! [ -s ./files/pi4-64/boot/$config ]
    then
        echo "No CysBOX config file for this hardware version ($config)"
    else
        read -p "Confirm $config ? (y/n) " RESP
        if [ "$RESP" = "y" ]
        then
	    echo "Installing : "$config
            sudo cp /boot/config.txt /boot/config.save
            sudo cp ./files/pi4-64/boot/$config /boot/config.txt
            echo "System will have to reboot to take the changes into account"
        fi
    fi
fi

echo ""
read -p "Done - Enter return to exit" RESP




