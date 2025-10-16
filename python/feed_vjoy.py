# -*- coding: utf-8 -*-
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
UDP = ("127.0.0.1", 5005)

def map_axis(x: float) -> int:
    """将 [-1, 1] 映射到 [0, 65535] 并防止溢出"""

    val = (float(x) + 1.0) * 0.5 * 65535
    return max(0, min(65535, int(val)))


def map_throttle(x: float) -> int:
    """将 [-1, 1] 映射到 [0, 65535] 并防止溢出"""

    return map_axis(x)
def main():
    _require_pyvjoy()
    # 检查 vJoy 驱动
    try:
        j = pyvjoy.VJoyDevice(1)
        print("[OK] vJoy Device 1 connected")
    except Exception as e:
        print(f"[ERROR] vJoy driver not found: {e}")
        print("\nPlease install vJoy:")
        print("  1. Download from: https://sourceforge.net/projects/vjoystick/")
        print("  2. Install the driver")
        print("  3. Restart this script")
        sys.exit(1)

    # 绑定 UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(UDP)
        print(f"[OK] Listening on {UDP}")
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
