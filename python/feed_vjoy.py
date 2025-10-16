# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import socket
import sys

try:
    import pyvjoy  # type: ignore
except ImportError:  # pragma: no cover - tested via branch logic
    pyvjoy = None


def _require_pyvjoy() -> None:
    if pyvjoy is None:
        print("[ERROR] pyvjoy not installed!")
        print("Install with: pip install pyvjoy")
        sys.exit(1)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge BCI UDP commands into a vJoy/ViGEm device")
    parser.add_argument("--host", default=DEFAULT_HOST, help="UDP host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to bind (default: 5005)")
    parser.add_argument("--device-id", type=int, default=1, help="vJoy device ID to control (default: 1)")
    return parser.parse_args(argv)

def map_axis(x: float) -> int:
    """将 [-1, 1] 映射到 [0, 65535] 并防止溢出"""

    val = (float(x) + 1.0) * 0.5 * 65535
    return max(0, min(65535, int(val)))


def map_throttle(x: float) -> int:
    """将 [-1, 1] 映射到 [0, 65535] 并防止溢出"""

    return map_axis(x)
def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    _require_pyvjoy()
    # 检查 vJoy 驱动
    try:
        j = pyvjoy.VJoyDevice(args.device_id)
        print(f"[OK] vJoy Device {args.device_id} connected")
    except Exception as e:
        print(f"[ERROR] vJoy driver not found: {e}")
        print("\nPlease install vJoy:")
        print("  1. Download from: https://sourceforge.net/projects/vjoystick/")
        print("  2. Install the driver")
        print("  3. Restart this script")
        sys.exit(1)

    # 绑定 UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Allow multiple UDP consumers (e.g. dashboard + joystick bridge) to
    # listen on the same localhost port when running on Windows. Without this
    # Windows raises WinError 10048 as soon as the second process binds.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        # Ensure the more restrictive exclusive mode stays disabled so the
        # reuse flag above takes effect on Windows.
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
        print(f"[ERROR] Failed to bind UDP port: {e}")
        print("  - Try closing feed_uinput.py if running")
        sys.exit(1)

    print("[RUN] Waiting for BCI commands...")

    try:
        while True:
            data, _ = sock.recvfrom(2048)
            try:
                m = json.loads(data.decode())
                if not all(k in m for k in ["yaw", "altitude"]):
                    continue
                throttle_val = m.get("throttle")
                if throttle_val is None:
                    throttle_val = 2 * float(m.get("speed", 0.0)) - 1.0
                pitch_val = float(m.get("pitch", 0.0))
                j.set_axis(pyvjoy.HID_USAGE_X, map_axis(m["yaw"]))
                j.set_axis(pyvjoy.HID_USAGE_Y, map_axis(m["altitude"]))
                j.set_axis(pyvjoy.HID_USAGE_Z, map_throttle(throttle_val))
                if hasattr(pyvjoy, "HID_USAGE_RX"):
                    j.set_axis(pyvjoy.HID_USAGE_RX, map_axis(pitch_val))
            except json.JSONDecodeError:
                continue
    except KeyboardInterrupt:
        print("\n[STOP] User interrupted")
    finally:
        sock.close()
        print("[EXIT] Goodbye!")

if __name__ == "__main__":
    main()
