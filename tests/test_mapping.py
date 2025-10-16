import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from feed_uinput import m01, m11  # type: ignore
from feed_vjoy import map_axis, map_throttle  # type: ignore


def test_map_axis_range() -> None:
    assert map_axis(-1.5) == 0
    assert map_axis(0.0) == 32767
    assert map_axis(1.5) == 65535


def test_map_throttle_range() -> None:
    assert map_throttle(-1.5) == 0
    assert map_throttle(0.0) == 32767
    assert map_throttle(0.75) == map_axis(0.75)


def test_uinput_mappings() -> None:
    assert m11(-1.5) == 0
    assert m11(0.0) == 32767
    assert m11(2.0) == 65535
    assert m01(-0.1) == 0
    assert m01(0.4) == int(0.4 * 65535)
    assert m01(2.0) == 65535
