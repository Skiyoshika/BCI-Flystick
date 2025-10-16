import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import bci_controller  # type: ignore
from bci_controller import load_cfg, resolve_board_id


def _write_files(tmp_path: Path, channel_map: dict, settings: dict) -> tuple[str, str]:
    map_path = tmp_path / "channel_map.json"
    settings_path = tmp_path / "settings.yaml"
    map_path.write_text(json.dumps(channel_map), encoding="utf-8")
    settings_path.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding="utf-8")
    return str(map_path), str(settings_path)


def test_load_cfg_success(tmp_path: Path) -> None:
    map_cfg = {
        "serial_port": "COM9",
        "board_id": "cyton",
        "channels": {"C3": 0, "C4": 1, "Cz": 2, "Oz": 3},
    }
    settings_cfg = {
        "sample_rate": 250,
        "bandpass": [1.0, 40.0],
        "notch": 50.0,
        "window_sec": 1.0,
        "hop_sec": 0.5,
        "ewma_alpha": 0.3,
        "dead_band": 0.05,
        "gains": {"yaw": 1.0, "altitude": 1.0, "speed": 1.0},
        "calibration_sec": 10,
        "udp_target": ["127.0.0.1", 6000],
    }

    map_path, settings_path = _write_files(tmp_path, map_cfg, settings_cfg)
    chmap, cfg = load_cfg(map_path, settings_path)

    assert chmap["serial_port"] == "COM9"
    assert chmap["channels"]["C4"] == 1
    assert cfg["sample_rate"] == 250.0
    assert cfg["bandpass"] == (1.0, 40.0)
    assert cfg["udp_target"] == ("127.0.0.1", 6000)


def test_resolve_board_id_alias() -> None:
    assert resolve_board_id("cyton") == bci_controller.BoardIds.CYTON_BOARD.value


def test_load_cfg_invalid_channels(tmp_path: Path) -> None:
    map_cfg = {
        "serial_port": "COM9",
        "board_id": "CYTON",
        "channels": {"C3": 0, "C4": 1},
    }
    settings_cfg = {
        "sample_rate": 250,
        "bandpass": [1.0, 40.0],
        "notch": 50.0,
        "window_sec": 1.0,
        "hop_sec": 0.5,
        "ewma_alpha": 0.3,
        "dead_band": 0.05,
        "gains": {"yaw": 1.0, "altitude": 1.0, "speed": 1.0},
        "calibration_sec": 10,
        "udp_target": ["127.0.0.1", 6000],
    }

    map_path, settings_path = _write_files(tmp_path, map_cfg, settings_cfg)

    with pytest.raises(SystemExit):
        load_cfg(map_path, settings_path)


def test_validate_settings_missing_gain(tmp_path: Path) -> None:
    map_cfg = {
        "serial_port": "COM9",
        "board_id": "CYTON",
        "channels": {"C3": 0, "C4": 1, "Cz": 2, "Oz": 3},
    }
    settings_cfg = {
        "sample_rate": 250,
        "bandpass": [1.0, 40.0],
        "notch": 50.0,
        "window_sec": 1.0,
        "hop_sec": 0.5,
        "ewma_alpha": 0.3,
        "dead_band": 0.05,
        "gains": {"yaw": 1.0, "altitude": 1.0},
        "calibration_sec": 10,
        "udp_target": ["127.0.0.1", 6000],
    }

    map_path, settings_path = _write_files(tmp_path, map_cfg, settings_cfg)

    with pytest.raises(SystemExit):
        load_cfg(map_path, settings_path)
