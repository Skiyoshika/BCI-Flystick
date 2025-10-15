# -*- coding: utf-8 -*-
import json, socket, time, uinput
UDP=("127.0.0.1",5005)
AX=[uinput.ABS_X + (0,65535,0,0), uinput.ABS_Y + (0,65535,0,0), uinput.ABS_Z + (0,65535,0,0)]
def m01(x): return int(max(0,min(1,x))*65535)
def m11(x): return int((max(-1,min(1,x))+1)*0.5*65535)
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.bind(UDP)
with uinput.Device(AX, name="BCI-Flystick") as dev:
    print("[uinput] Joystick ready:", dev)
    while True:
        data,_=sock.recvfrom(2048); m=json.loads(data.decode())
        dev.emit(uinput.ABS_X, m11(m["yaw"]), syn=False)
        dev.emit(uinput.ABS_Y, m11(m["altitude"]), syn=False)
        dev.emit(uinput.ABS_Z, m01(m["speed"]), syn=True)
