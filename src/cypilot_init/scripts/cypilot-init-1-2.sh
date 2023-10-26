#!/bin/bash

# 2020 JF/ED / Cybele Services (cf@cybele-sailing.com)
# Tested with CysBOX/CysPWR hardware fitted with Pi4-4GB/OS64b

echo "Install Signal-K server"

cd "$(dirname "$0")"

# Install dependencies
echo ""
echo "-----------------------------------------------------------"
sleep 1
read -p "Install signal-k dependencies ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : signal-K dependencies"
    # curl -sL https://deb.nodesource.com/setup_16.x | sudo -E bash -
    # sudo apt-get install -y nodejs
    cd /tmp
    NODEJS_VERSION="v16.17.0"
    wget "https://nodejs.org/dist/"$NODEJS_VERSION"/node-"$NODEJS_VERSION"-linux-arm64.tar.gz"
    tar -xzf "node-"$NODEJS_VERSION"-linux-arm64.tar.gz"
    if test -d "node-"$NODEJS_VERSION"-linux-arm64"
    then
        cd "node-"$NODEJS_VERSION"-linux-arm64"
        sudo cp -R * /usr/local/
    else
        echo "******** Error installing node.js ! *********"
    fi
    sudo apt install -y libnss-mdns avahi-utils libavahi-compat-libdnssd-dev
fi

# Install signal-k server
echo ""
echo "-----------------------------------------------------------"
sleep 1
read -p "Install signal-k server ? (y/n) " RESP
if [ "$RESP" = "y" ]; then
    echo "Installing : signal-K server"
    # stop signalk server
    sudo systemctl stop signalk.socket
    sudo systemctl stop signalk.service
    sudo npm install -g npm@latest
    # added the following line to deal with error which sometimes occurs ...("npm ERR! code ENOTEMPTY")
    sudo npm i --package-lock-only signalk-server
    sudo npm i -g signalk-server
    echo ""
    echo ""
    echo "Now, we can setup signalk-server for our boat ..."
    echo ""
    echo ">>>> When asked for the port to be used for signal-K web service, select port 3000"
    sudo signalk-server-setup
fi

echo ""
read -p "Done - Enter return to exit" RESP
