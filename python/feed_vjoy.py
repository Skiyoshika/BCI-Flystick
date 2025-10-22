# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from collections.abc import Mapping
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    import pyvjoy  # type: ignore
except ImportError:  # pragma: no cover - tested via branch logic
    pyvjoy = None

try:  # pragma: no cover - optional dependency guard
    from pyvjoy._sdk import RelinquishVJD  # type: ignore
except Exception:  # pragma: no cover - only triggered when pyvjoy absent
    RelinquishVJD = None  # type: ignore

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005
AXIS_MAX = 32767
AXIS_ORDER = ("throttle", "roll", "pitch", "yaw")


def _require_pyvjoy() -> None:
    if pyvjoy is None:
        print("[ERROR] pyvjoy not installed!")
        print("Install with: pip install pyvjoy")
        sys.exit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bridge BCI UDP commands into a vJoy/ViGEm device"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="UDP host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to bind (default: 5005)")
    parser.add_argument("--device-id", type=int, default=1, help="vJoy device ID to control (default: 1)")
    return parser.parse_args(argv)


def normalize(value: Any) -> Optional[int]:
    """Auto-normalise joystick axis values to the vJoy range.

    Supported input ranges:

    * ``[-1, 1]`` – centred values (primary BCI output)
    * ``[0, 1]`` – already normalised values
    * integers within ``[0, AXIS_MAX]`` – passed through with clamping
    """

    if value is None:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if -1.1 <= numeric <= 1.1:
        scaled = (numeric * 0.5 + 0.5) * AXIS_MAX
    elif -0.1 <= numeric <= 1.1:
        # Treat values in [0, 1] (with small tolerance) as already normalised.
        scaled = numeric * AXIS_MAX
    else:
        scaled = numeric

    clamped = max(0, min(AXIS_MAX, int(round(scaled))))
    return clamped


def _first_match(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _extract_axes(payload: Mapping[str, Any]) -> Dict[str, Optional[int]]:
    """Pick out joystick axes from a telemetry payload.

    The controller now broadcasts the canonical fields ``throttle``, ``roll``,
    ``pitch`` and ``yaw``. For compatibility with older payload shapes we
    accept a few aliases (e.g. ``altitude`` for roll, ``x``/``y``/``z`` for the
    primary axes, and ``speed`` as a throttle substitute). All lookups are
    case-insensitive. The aliases also mirror the historical axis order so
    legacy consumers that still rely on ``x``/``y``/``z`` continue to function
    despite the updated joystick binding (Y → throttle, X → roll, Z → pitch,
    RX → yaw).
    """

    lowered = {k.lower(): v for k, v in payload.items()}

    throttle_value = normalize(
        _first_match(lowered, ("throttle", "y", "speed"))
    )
    roll_value = normalize(
        _first_match(lowered, ("roll", "altitude", "x"))
    )
    pitch_value = normalize(
        _first_match(lowered, ("pitch", "z", "elevator"))
    )
    yaw_value = normalize(
        _first_match(lowered, ("yaw", "rx", "rz", "ry", "rudder"))
    )

    axes: Dict[str, Optional[int]] = {
        "throttle": throttle_value,
        "roll": roll_value,
        "pitch": pitch_value,
        "yaw": yaw_value,
    }

    # Maintain legacy compatibility for consumers that still expect an
    # ``altitude`` reading by mirroring the roll signal when the payload does
    # not explicitly include it.
    axes["altitude"] = roll_value

    return axes


def _fill_missing_axes(
    axes: Mapping[str, Optional[int]],
    last_known: Dict[str, int],
    fallback: Mapping[str, int],
) -> Tuple[Dict[str, int], list[str]]:
    """Replace missing axis readings with the last known values.

    Parameters
    ----------
    axes:
        Newly parsed axis values, where ``None`` indicates the payload did not
        provide an updated reading for that axis.
    last_known:
        Mutable mapping of the most recent values pushed to vJoy.  The mapping
        is updated in-place so subsequent payloads can continue from the latest
        readings.
    fallback:
        Default values used whenever an axis reading is missing.  Typically
        this will be the neutral joystick position for each axis so that stale
        values do not linger when telemetry drops individual fields.

    Returns
    -------
    Tuple[Dict[str, int], list[str]]
        A tuple containing the axis dictionary with missing entries replaced
        as well as the list of axis names that required a fallback.  The list
        is ordered according to the iteration order of ``last_known`` so the
        logging remains stable for users diagnosing telemetry issues.
    """

    filled: Dict[str, int] = {}
    missing: list[str] = []
    for name, previous in list(last_known.items()):
        value = axes.get(name)
        if value is None:
            value = fallback.get(name, previous)
            missing.append(name)
        last_known[name] = value
        filled[name] = value
    return filled, missing


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    _require_pyvjoy()

    try:
        j = pyvjoy.VJoyDevice(args.device_id)
        print(f"[INFO] Connected to vJoy device #{args.device_id}")
    except Exception as exc:
        print(f"[ERROR] Failed to connect to vJoy device #{args.device_id}: {exc}")
        print("\nPlease install vJoy:")
        print("  1. Download from: https://sourceforge.net/projects/vjoystick/")
        print("  2. Install the driver")
        print("  3. Restart this script")
        sys.exit(1)

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
        print(f"[INFO] Listening on UDP {(args.host, args.port)}")
    except OSError as exc:
        print(f"[ERROR] Failed to bind UDP port: {exc}")
        print("  - Try closing feed_uinput.py if running")
        sys.exit(1)

    print("[INFO] Waiting for BCI UDP telemetry...")

    packet_counter = 0
    last_report_time = time.time()

    neutral_axes = {axis: normalize(0.0) for axis in AXIS_ORDER}
    current_axes = dict(neutral_axes)

    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)
            except OSError as exc:
                print(f"[ERROR] UDP socket error: {exc}")
                time.sleep(0.5)
                continue

            packet_counter += 1

            try:
                payload = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                print("[WARN] Received non-JSON UDP payload")
                continue

            if not isinstance(payload, Mapping):
                print("[WARN] Ignoring UDP packet with unexpected structure")
                continue

            axes = _extract_axes(payload)
            axes, missing = _fill_missing_axes(axes, current_axes, neutral_axes)
            if missing:
                print(
                    "[WARN] Missing axis data for: "
                    + ", ".join(missing)
                    + " (using last known values)"
                )

            try:
                j.set_axis(pyvjoy.HID_USAGE_X, axes["roll"])
                j.set_axis(pyvjoy.HID_USAGE_Y, axes["throttle"])
                j.set_axis(pyvjoy.HID_USAGE_Z, axes["pitch"])
                usage_rx = getattr(
                    pyvjoy,
                    "HID_USAGE_RX",
                    getattr(pyvjoy, "HID_USAGE_RZ", pyvjoy.HID_USAGE_Y),
                )
                j.set_axis(usage_rx, axes["yaw"])
            except pyvjoy.vJoyException as exc:  # type: ignore[attr-defined]
                print(f"[ERROR] vJoy update failed: {exc}")
                time.sleep(0.5)
                continue
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[ERROR] Unexpected vJoy error: {exc}")
                time.sleep(0.5)
                continue

            now = time.time()
            elapsed = now - last_report_time
            if elapsed >= 1.0:
                rate = packet_counter / max(elapsed, 1e-9)
                print(
                    f"[INFO] {rate:5.1f} pkt/s | Throttle={axes['throttle']:5d} "
                    f"Roll={axes['roll']:5d} Pitch={axes['pitch']:5d} Yaw={axes['yaw']:5d}"
                )
                packet_counter = 0
                last_report_time = now
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user, shutting down...")
    finally:
        try:
            sock.close()
        finally:
            if RelinquishVJD is not None:
                try:
                    RelinquishVJD(args.device_id)
                    print(f"[INFO] Released vJoy device #{args.device_id}")
                except Exception as exc:
                    print(f"[WARN] Failed to relinquish vJoy device: {exc}")


if __name__ == "__main__":
    main()
