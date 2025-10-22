import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from feed_uinput import m01, m11  # type: ignore
from feed_vjoy import normalize, _extract_axes, _fill_missing_axes  # type: ignore


def test_normalize_range() -> None:
    assert normalize(-1.5) == 0
    assert normalize(-1.0) == 0
    assert normalize(0.0) == 16384
    assert normalize(1.0) == 32767
    # Values outside [-1, 1] but within the vJoy range are passed through.
    assert normalize(1.5) == 2
    assert normalize(50000) == 32767


def test_extract_axes_standard_payload() -> None:
    payload = {
        "yaw": -0.4,
        "altitude": 0.25,
        "throttle": 0.5,
        "pitch": -1.0,
    }
    axes = _extract_axes(payload)
    assert axes["yaw"] == normalize(payload["yaw"])
    assert axes["roll"] == normalize(payload["altitude"])
    assert axes["altitude"] == normalize(payload["altitude"])
    assert axes["throttle"] == normalize(payload["throttle"])
    assert axes["pitch"] == normalize(payload["pitch"])


def test_extract_axes_with_aliases() -> None:
    payload = {
        "X": 1.0,
        "Y": 0.25,
        "Z": -0.5,
        "RX": 0.75,
        "speed": 0.6,
    }
    axes = _extract_axes(payload)
    assert axes["roll"] == normalize(1.0)
    assert axes["pitch"] == normalize(-0.5)
    assert axes["throttle"] == normalize(0.25)
    assert axes["yaw"] == normalize(0.75)


def test_extract_axes_speed_fallback() -> None:
    payload = {"speed": 0.6}
    axes = _extract_axes(payload)
    assert axes["throttle"] == normalize(0.6)


def test_fill_missing_axes_defaults_to_neutral() -> None:
    neutral = {axis: normalize(0.0) for axis in ("throttle", "roll", "pitch", "yaw")}
    last_known = dict(neutral)

    update = {
        "yaw": normalize(0.25),
        "roll": None,
        "throttle": normalize(-1.0),
        "pitch": None,
    }

    filled, missing = _fill_missing_axes(update, last_known, neutral)

    assert filled["yaw"] == normalize(0.25)
    assert filled["roll"] == neutral["roll"]
    assert filled["throttle"] == normalize(-1.0)
    assert filled["pitch"] == neutral["pitch"]
    assert missing == ["roll", "pitch"]
    # Ensure last_known was updated for axes with new readings and fallback
    assert last_known["yaw"] == normalize(0.25)
    assert last_known["roll"] == neutral["roll"]


def test_uinput_mappings() -> None:
    assert m11(-1.5) == 0
    assert m11(0.0) == 32767
    assert m11(2.0) == 65535
    assert m01(-0.1) == 0
    assert m01(0.4) == int(0.4 * 65535)
    assert m01(2.0) == 65535
