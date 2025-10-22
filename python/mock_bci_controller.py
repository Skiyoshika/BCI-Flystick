# python/mock_bci_controller.py
# -*- coding: utf-8 -*-
# Mock BCI controller: generates synthetic 3-axis commands over UDP
import time, json, socket, math, random, os
from typing import Iterable, List, Tuple

def _split_target_spec(spec: str) -> List[str]:
    parts: List[str] = []
    for entry in spec.replace(";", ",").split(","):
        value = entry.strip()
        if value:
            parts.append(value)
    return parts


def _parse_target_entries(entries: Iterable[str], default_host: str) -> List[Tuple[str, int]]:
    targets: List[Tuple[str, int]] = []
    for entry in entries:
        host_part, sep, port_part = entry.rpartition(":")
        if sep:
            host = host_part.strip() or default_host
            port_text = port_part.strip()
        else:
            host = default_host
            port_text = entry.strip()
        if not host:
            continue
        try:
            port = int(port_text, 10)
        except ValueError:
            continue
        if not (0 < port < 65536):
            continue
        targets.append((host, port))
    return targets


def _deduplicate_targets(targets: Iterable[Tuple[str, int]]) -> List[Tuple[str, int]]:
    seen: set[Tuple[str, int]] = set()
    unique: List[Tuple[str, int]] = []
    for host, port in targets:
        key = (host, port)
        if key in seen:
            continue
        unique.append(key)
        seen.add(key)
    return unique


UDP_PRIMARY = ("127.0.0.1", 5005)
env_spec = os.environ.get("BCI_FLYSTICK_UDP_FANOUT", "")
extras = _parse_target_entries(_split_target_spec(env_spec), UDP_PRIMARY[0]) if env_spec else []
UDP_TARGETS = _deduplicate_targets([UDP_PRIMARY, *extras])
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("[MOCK] Sending synthetic Yaw/Altitude/Speed to:")
for host, port in UDP_TARGETS:
    print(f"    - {(host, port)}")
t0 = time.time()
while True:
    t = time.time() - t0
    # 平滑正弦 + 少许噪声
    yaw = 0.8 * math.sin(2*math.pi*0.2*t) + random.uniform(-0.05, 0.05)        # [-1,1]
    alt = 0.6 * math.sin(2*math.pi*0.13*t + 1.1) + random.uniform(-0.05, 0.05) # [-1,1]
    pitch = 0.5 * math.sin(2*math.pi*0.17*t + 0.7) + random.uniform(-0.05, 0.05)
    thr = 0.7 * math.sin(2*math.pi*0.11*t + 2.2) + random.uniform(-0.05, 0.05)

    yaw = max(-1.0, min(1.0, yaw))
    alt = max(-1.0, min(1.0, alt))
    pitch = max(-1.0, min(1.0, pitch))
    thr = max(-1.0, min(1.0, thr))

    msg = {
        "yaw": round(yaw, 4),
        "altitude": round(alt, 4),
        "pitch": round(pitch, 4),
        "throttle": round(thr, 4),
        "speed": round((thr + 1.0) * 0.5, 4),
        "ts": time.time(),
    }
    encoded = json.dumps(msg).encode("utf-8")
    for target in UDP_TARGETS:
        sock.sendto(encoded, target)
    print(msg)
    time.sleep(0.05)  # 20 Hz
