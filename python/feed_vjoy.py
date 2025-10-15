# -*- coding: utf-8 -*-
import json, socket, pyvjoy
UDP=("127.0.0.1",5005)
def map_axis(x): return int((x+1)*0.5*0x8000*2)   # [-1,1]→[0..65535]
def map_throttle(x): return int(x*0x8000*2)       # [0,1] →[0..65535]
j=pyvjoy.VJoyDevice(1)
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.bind(UDP)
print("[vJoy] Listening on", UDP)
while True:
    data,_=sock.recvfrom(2048); m=json.loads(data.decode())
    j.set_axis(pyvjoy.HID_USAGE_X, map_axis(m["yaw"]))
    j.set_axis(pyvjoy.HID_USAGE_Y, map_axis(m["altitude"]))
    j.set_axis(pyvjoy.HID_USAGE_Z, map_throttle(m["speed"]))
