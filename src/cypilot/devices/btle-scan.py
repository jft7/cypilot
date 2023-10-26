# run as root (sudo)
# or setcap as follow:
# sudo setcap cap_net_raw+e      <PATH>/bluepy-helper
# sudo setcap cap_net_admin+eip  <PATH>/bluepy-helper

from bluepy.btle import Scanner
 
scanner = Scanner()
devices = scanner.scan(10.0)
 
for device in devices:
    print("DEV = {} RSSI = {}".format(device.addr, device.rssi))