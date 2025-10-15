# python/mock_bci_controller.py
# -*- coding: utf-8 -*-
# Mock BCI controller: generates synthetic 3-axis commands over UDP
import time, json, socket, math, random

UDP_TARGET = ("127.0.0.1", 5005)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("[MOCK] Sending synthetic Yaw/Altitude/Speed to", UDP_TARGET)
t0 = time.time()
while True:
    t = time.time() - t0
    # 平滑正弦 + 少许噪声
    yaw = 0.8 * math.sin(2*math.pi*0.2*t) + random.uniform(-0.05, 0.05)        # [-1,1]
    alt = 0.6 * math.sin(2*math.pi*0.13*t + 1.1) + random.uniform(-0.05, 0.05) # [-1,1]
    spd = 0.5 + 0.4 * (0.5*math.sin(2*math.pi*0.1*t + 2.2) + 0.5)               # [0,1]

    yaw = max(-1.0, min(1.0, yaw))
    alt = max(-1.0, min(1.0, alt))
    spd = max(0.0, min(1.0, spd))

    msg = {"yaw": round(yaw,4), "altitude": round(alt,4), "speed": round(spd,4), "ts": time.time()}
    sock.sendto(json.dumps(msg).encode("utf-8"), UDP_TARGET)
    print(msg)
    time.sleep(0.05)  # 20 Hz
