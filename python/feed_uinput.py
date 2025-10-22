# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import socket
import sys

try:
    import uinput  # type: ignore
except ImportError:  # pragma: no cover - tested via branch logic
    uinput = None


def _require_uinput() -> None:
    if uinput is None:
        print("[ERROR] python-uinput not installed!")
        print("Install with: pip install python-uinput")
        sys.exit(1)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge BCI UDP commands into a Linux uinput joystick")
    parser.add_argument("--host", default=DEFAULT_HOST, help="UDP host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to bind (default: 5005)")
    return parser.parse_args(argv)

def m01(x):
    return int(max(0, min(1, x)) * 65535)

def m11(x):
    return int((max(-1, min(1, x)) + 1) * 0.5 * 65535)

def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    _require_uinput()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 0)
        except OSError:
            pass
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    try:
        sock.bind((args.host, args.port))
        print(f"[OK] Listening on {(args.host, args.port)}")
    except OSError as e:
        print(f"[ERROR] Failed to bind: {e}")
        sys.exit(1)

    axes = [
        uinput.ABS_X + (0, 65535, 0, 0),
        uinput.ABS_Y + (0, 65535, 0, 0),
        uinput.ABS_Z + (0, 65535, 0, 0),
        uinput.ABS_RX + (0, 65535, 0, 0),
    ]

    try:
        with uinput.Device(axes, name="BCI-Flystick") as dev:
            print("[OK] Virtual joystick created")
            while True:
                try:
                    data, _ = sock.recvfrom(2048)
                    m = json.loads(data.decode())
                    if not all(k in m for k in ["yaw", "altitude"]):
                        continue
                    throttle = m.get("throttle")
                    if throttle is None:
                        throttle = 2 * float(m.get("speed", 0.0)) - 1.0
                    pitch = float(m.get("pitch", 0.0))
                    dev.emit(uinput.ABS_X, m11(throttle), syn=False)
                    dev.emit(uinput.ABS_Y, m11(m["yaw"]), syn=False)
                    dev.emit(uinput.ABS_Z, m11(m["altitude"]), syn=False)
                    dev.emit(uinput.ABS_RX, m11(pitch), syn=True)
                except json.JSONDecodeError:
                    continue
    except PermissionError:
        print("[ERROR] Run with: sudo python python/feed_uinput.py")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[STOP]")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
