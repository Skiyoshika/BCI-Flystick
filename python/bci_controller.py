# -*- coding: utf-8 -*-
"""BCI-Flystick Controller.

This module converts EEG samples streamed from an OpenBCI device into
multi-axis virtual joystick commands. It can operate either against a real
BrainFlow-compatible board or a fully synthetic generator that mimics the
spectral patterns required for offline development.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

import numpy as np
from scipy import signal

try:  # pragma: no cover - exercised via branch logic in tests
    from brainflow import BoardIds, BoardShim, BrainFlowInputParams
except ImportError:  # pragma: no cover - used in CI where brainflow may be missing
    BoardIds = None  # type: ignore
    BoardShim = None  # type: ignore
    BrainFlowInputParams = object  # type: ignore

# 使用绝对路径
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_MAP = os.path.join(BASE_DIR, "config", "channel_map.json")
CFG_SET = os.path.join(BASE_DIR, "config", "settings.yaml")
PROFILE_ENV_VAR = "BCI_FLYSTICK_PROFILE"


class ConfigError(RuntimeError):
    """配置文件不合法时抛出的异常"""


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _validate_channel_map(raw: Dict[str, Any]) -> Dict[str, Any]:
    _ensure(isinstance(raw, dict), "channel_map.json 必须是对象")

    serial = raw.get("serial_port")
    _ensure(isinstance(serial, str) and serial, "serial_port 必须为非空字符串")

    board_id = raw.get("board_id", "CYTON")
    _ensure(isinstance(board_id, (int, str)), "board_id 必须为整数或字符串")

    channels = raw.get("channels")
    _ensure(isinstance(channels, dict), "channels 必须为对象")
    required = {"C3", "C4", "Cz", "Oz"}
    missing = required.difference(channels or {})
    _ensure(not missing, f"channels 缺少键: {', '.join(sorted(missing))}")
    for name, idx in channels.items():
        _ensure(isinstance(idx, int) and idx >= 0, f"通道 {name} 必须为非负整数")

    return {
        "serial_port": serial,
        "board_id": board_id,
        "channels": {k: int(v) for k, v in channels.items()}
    }


def _validate_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    _ensure(isinstance(raw, dict), "settings.yaml 必须是映射")

    def _number(name: str, positive: bool = False, minimum: float | None = None,
                maximum: float | None = None) -> float:
        val = raw.get(name)
        _ensure(isinstance(val, (int, float)), f"{name} 必须为数字")
        if positive:
            _ensure(val > 0, f"{name} 必须大于 0")
        if minimum is not None:
            _ensure(val >= minimum, f"{name} 必须 >= {minimum}")
        if maximum is not None:
            _ensure(val <= maximum, f"{name} 必须 <= {maximum}")
        return float(val)

    sample_rate = _number("sample_rate", positive=True)
    notch = _number("notch", positive=True)
    window_sec = _number("window_sec", positive=True)
    hop_sec = _number("hop_sec", positive=True)
    _ensure(hop_sec <= window_sec, "hop_sec 不能大于 window_sec")
    ewma_alpha = _number("ewma_alpha", minimum=0.0, maximum=1.0)
    dead_band = _number("dead_band", minimum=0.0)
    calibration_sec = _number("calibration_sec", positive=True)

    bandpass = raw.get("bandpass")
    _ensure(isinstance(bandpass, (list, tuple)) and len(bandpass) == 2,
            "bandpass 必须为长度为 2 的列表")
    bp_lo, bp_hi = bandpass
    _ensure(isinstance(bp_lo, (int, float)) and isinstance(bp_hi, (int, float)),
            "bandpass 值必须为数字")
    _ensure(bp_lo < bp_hi, "bandpass 下限必须小于上限")

    gains = raw.get("gains") or {}
    _ensure(isinstance(gains, dict), "gains 必须为对象")
    if "throttle" not in gains and "speed" in gains:
        gains = dict(gains)
        gains["throttle"] = gains["speed"]
    gains_clean = {}
    for axis in ("yaw", "altitude", "throttle", "pitch"):
        val = gains.get(axis)
        _ensure(isinstance(val, (int, float)), f"gains.{axis} 必须为数字")
        _ensure(val >= 0, f"gains.{axis} 必须 >= 0")
        gains_clean[axis] = float(val)

    udp_target = raw.get("udp_target")
    _ensure(isinstance(udp_target, (list, tuple)) and len(udp_target) == 2,
            "udp_target 必须为 [host, port]")
    host, port = udp_target
    _ensure(isinstance(host, str) and host, "udp_target[0] 必须为主机字符串")
    _ensure(isinstance(port, int) and 0 < port < 65536, "udp_target[1] 必须为有效端口")

    return {
        "sample_rate": sample_rate,
        "bandpass": (float(bp_lo), float(bp_hi)),
        "notch": notch,
        "window_sec": window_sec,
        "hop_sec": hop_sec,
        "ewma_alpha": ewma_alpha,
        "dead_band": dead_band,
        "gains": gains_clean,
        "calibration_sec": calibration_sec,
        "udp_target": (host, port)
    }


BOARD_NAME_ALIASES = {
    "CYTON": "CYTON_BOARD",
    "CYTON_DAISY": "CYTON_DAISY_BOARD",
    "GANGLION": "GANGLION_BOARD",
    "SYNTHETIC": "SYNTHETIC_BOARD",
}


def resolve_board_id(board_id: Any) -> int:
    """根据配置中的 board_id 返回 BrainFlow 枚举值"""
    if isinstance(board_id, int):
        return board_id
    if isinstance(board_id, str):
        key = board_id.strip().upper()
        key = BOARD_NAME_ALIASES.get(key, key)
        if not key.endswith("_BOARD"):
            key = f"{key}_BOARD"
        if BoardIds is None:
            if key in ("SYNTHETIC", "SYNTHETIC_BOARD"):
                return -1
            raise ConfigError("BrainFlow 未安装，无法解析字符串 board_id")
        try:
            return BoardIds[key].value
        except KeyError as exc:
            raise ConfigError(f"不支持的 board_id: {board_id}") from exc
    raise ConfigError("board_id 必须为字符串或整数")


def load_cfg(map_path: str = CFG_MAP, settings_path: str = CFG_SET) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """加载并校验配置文件"""
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            raw_map = json.load(f)
        with open(settings_path, "r", encoding="utf-8") as f:
            raw_settings = yaml.safe_load(f)
    except FileNotFoundError as e:
        print(f"[ERROR] Config file not found: {e}")
        print(f"[INFO] Expected paths:")
        print(f"  - {map_path}")
        print(f"  - {settings_path}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        sys.exit(1)

    try:
        chmap = _validate_channel_map(raw_map)
        settings = _validate_settings(raw_settings)
    except ConfigError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    return chmap, settings


def load_runtime_profile() -> Dict[str, Any]:
    """Load optional runtime overrides provided by the setup wizard profile."""

    profile_path = os.environ.get(PROFILE_ENV_VAR)
    if not profile_path:
        return {}

    try:
        with open(profile_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"[WARN] Profile path from {PROFILE_ENV_VAR} not found: {profile_path}")
        return {}
    except json.JSONDecodeError as exc:
        print(f"[WARN] Failed to parse profile overrides: {exc}")
        return {}
    except Exception as exc:  # pragma: no cover - unexpected environment issues
        print(f"[WARN] Unexpected error loading profile overrides: {exc}")
        return {}

    if not isinstance(data, dict):
        print("[WARN] Profile overrides must be a JSON object, ignoring.")
        return {}

    return data

class Ewma:
    """指数加权移动平均滤波器"""
    def __init__(self, a):
        self.a, self.y = a, None

    def step(self, x):
        self.y = float(x) if self.y is None else self.a*float(x)+(1-self.a)*self.y
        return self.y


@dataclass(slots=True)
class FilterPipeline:
    """组合 notch + bandpass 滤波器，便于重复使用"""

    fs: float
    notch: float
    bp_lo: float
    bp_hi: float

    def __post_init__(self) -> None:
        nyq = self.fs * 0.5
        self._notch: tuple[np.ndarray, np.ndarray] | None = None
        if 0 < self.notch < nyq:
            q = 30.0
            w0 = self.notch / nyq
            self._notch = signal.iirnotch(w0, q)
        self._band: tuple[np.ndarray, np.ndarray] | None = None
        if 0 < self.bp_lo < self.bp_hi < nyq:
            self._band = signal.butter(4, [self.bp_lo / nyq, self.bp_hi / nyq], btype="band")

    def process(self, sig: np.ndarray) -> np.ndarray:
        data = np.asarray(sig, dtype=np.float64)
        if data.size == 0:
            return data
        if self._notch is not None and data.size > max(len(self._notch[0]), len(self._notch[1])):
            data = signal.filtfilt(*self._notch, data, method="gust")
        if self._band is not None and data.size > max(len(self._band[0]), len(self._band[1])):
            data = signal.filtfilt(*self._band, data, method="gust")
        return data


class MockBoard:
    """无需硬件的 EEG 数据模拟器."""

    def __init__(self, sample_rate: float, channel_order: Iterable[str]):
        self.sample_rate = float(sample_rate)
        self.channel_order = list(channel_order)
        self.channel_indices = {name: idx for idx, name in enumerate(self.channel_order)}
        self._t = 0.0
        self._rng = np.random.default_rng(42)
        self._running = False

    def prepare_session(self) -> None:  # pragma: no cover - trivial
        self._t = 0.0

    def start_stream(self, _buffer_size: int | None = None) -> None:  # pragma: no cover - trivial
        self._running = True

    def stop_stream(self) -> None:  # pragma: no cover - trivial
        self._running = False

    def release_session(self) -> None:  # pragma: no cover - trivial
        self._running = False

    def get_current_board_data(self, samples: int) -> np.ndarray:
        samples = max(0, int(samples))
        t = self._t + np.arange(samples) / self.sample_rate
        self._t += samples / self.sample_rate
        data = np.zeros((len(self.channel_order), samples), dtype=np.float64)

        c3 = self.channel_indices.get("C3")
        c4 = self.channel_indices.get("C4")
        cz = self.channel_indices.get("Cz")
        oz = self.channel_indices.get("Oz")
        if c3 is not None:
            data[c3, :] = 40e-6 + 5e-6 * np.sin(2 * np.pi * 0.2 * t)
        if c4 is not None:
            data[c4, :] = 40e-6 + 5e-6 * np.sin(2 * np.pi * 0.21 * t + 0.4)
        if cz is not None:
            data[cz, :] = 35e-6 + 6e-6 * np.sin(2 * np.pi * 0.18 * t + 1.2)
        if oz is not None:
            data[oz, :] = 30e-6 + 7e-6 * np.sin(2 * np.pi * 0.16 * t + 2.0)

        noise = 1.2e-6 * self._rng.standard_normal(data.shape)
        return data + noise


def bandpower(sig: np.ndarray, fs: float, f1: float, f2: float) -> float:
    """计算频段功率 (通过 Welch 谱)"""

    if sig.size == 0:
        return 0.0
    nperseg = min(max(128, int(fs)), sig.size)
    noverlap = int(nperseg * 0.5)
    freqs, psd = signal.welch(sig, fs=fs, nperseg=nperseg, noverlap=noverlap, window="hann")
    mask = (freqs >= f1) & (freqs <= f2)
    if not np.any(mask):
        return 0.0
    return float(np.trapz(psd[mask], freqs[mask]))

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BCI-Flystick controller")
    parser.add_argument("--mock", action="store_true", help="使用内置 EEG 模拟器 (无需硬件)")
    parser.add_argument("--udp-host", help="覆盖配置中的 UDP 主机")
    parser.add_argument("--udp-port", type=int, help="覆盖配置中的 UDP 端口")
    parser.add_argument("--duration", type=float, help="运行指定秒数后自动退出 (测试使用)")
    return parser.parse_args(argv)


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, value)))


def main(argv: list[str] | None = None) -> None:
    """主控制循环"""

    args = _parse_args(argv)
    board = None
    sock: socket.socket | None = None

    try:
        # ============ 1. 加载配置 ============
        chmap, cfg = load_cfg()
        ports = chmap["serial_port"]
        chs = chmap["channels"]
        board_id = resolve_board_id(chmap["board_id"])
        notch = cfg["notch"]
        bp_lo, bp_hi = cfg["bandpass"]
        win = cfg["window_sec"]
        hop = cfg["hop_sec"]
        alpha = cfg["ewma_alpha"]
        dead = cfg["dead_band"]
        gains = cfg["gains"]
        udp_target = cfg["udp_target"]

        if args.udp_host:
            udp_target = (args.udp_host, udp_target[1])
        if args.udp_port:
            udp_target = (udp_target[0], args.udp_port)

        runtime_profile = load_runtime_profile()
        invert_pitch = bool(runtime_profile.get("invert_pitch", False))
        throttle_scale_raw = runtime_profile.get("throttle_scale", 1.0)
        try:
            throttle_scale = float(throttle_scale_raw)
        except (TypeError, ValueError):
            throttle_scale = 1.0
        throttle_scale = float(max(0.1, min(5.0, throttle_scale)))
        if abs(throttle_scale - 1.0) > 1e-6 or invert_pitch:
            print(
                f"[PROFILE] Overrides → invert_pitch={invert_pitch}, throttle_scale={throttle_scale:.2f}"
            )

        MU = (8, 12)   # Mu 频段
        BE = (13, 30)  # Beta 频段
        AL = (8, 12)   # Alpha 频段

        use_mock = args.mock or board_id == -1 or BoardShim is None

        if use_mock:
            print("[INFO] Using mock EEG generator (offline mode)")
            board = MockBoard(cfg["sample_rate"], [k for k in ("C3", "C4", "Cz", "Oz") if k in chs])
            fs = cfg["sample_rate"]
            channel_indices = {name: board.channel_indices[name] for name in chs}
        else:
            if BoardShim is None or BrainFlowInputParams is object:
                raise RuntimeError("BrainFlow 未正确安装，无法连接真实设备")
            print(f"[INFO] Connecting to OpenBCI on {ports}...")
            params = BrainFlowInputParams()
            setattr(params, "serial_port", ports)
            board = BoardShim(board_id, params)
            if hasattr(BoardShim, "enable_dev_board_logger"):
                BoardShim.enable_dev_board_logger()
            try:
                board.prepare_session()
                board.start_stream(45000)
                print("[OK] OpenBCI connected successfully")
            except Exception as e:  # pragma: no cover - relies on hardware
                print(f"[ERROR] OpenBCI connection failed: {e}")
                print("[INFO] Troubleshooting:")
                print(f"  - Check device is connected to {ports}")
                print("  - Verify correct drivers are installed")
                print("  - Close other programs using the port")
                print("  - Try running with administrator/sudo privileges")
                sys.exit(1)

            fs = BoardShim.get_sampling_rate(board_id)
            if abs(cfg["sample_rate"] - fs) > 1e-3:
                print(f"[WARN] Config sample_rate={cfg['sample_rate']} 与硬件采样率 {fs} 不一致")
            eeg = BoardShim.get_eeg_channels(board_id)
            try:
                channel_indices = {name: eeg[idx] for name, idx in chs.items()}
            except IndexError as exc:
                raise RuntimeError("channel_map.json 中的索引超出硬件 EEG 通道范围") from exc

        required = {"C3", "C4", "Cz", "Oz"}
        missing = required.difference(channel_indices)
        if missing:
            raise RuntimeError(f"缺少必要通道映射: {', '.join(sorted(missing))}")

        filter_bank = FilterPipeline(fs, notch, bp_lo, bp_hi)

        # ============ 3. 初始化 UDP ============
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[INFO] UDP target: {udp_target}")

        # ============ 4. 基线校准 ============
        print(f"[INFO] Calibrating baseline ({cfg['calibration_sec']}s)...")
        print("       Keep relaxed and look straight ahead...")
        baseline_cz_total: list[float] = []
        baseline_cz_mu: list[float] = []
        baseline_cz_beta: list[float] = []
        baseline_oz_alpha: list[float] = []
        start = time.time()
        win_samp = int(win * fs)

        while time.time() - start < cfg["calibration_sec"]:
            time.sleep(0.2)
            data = board.get_current_board_data(win_samp)
            if data.shape[1] < win_samp:
                continue

            cz = filter_bank.process(data[channel_indices["Cz"], :])
            oz = filter_bank.process(data[channel_indices["Oz"], :])

            cz_mu = bandpower(cz, fs, *MU)
            cz_beta = bandpower(cz, fs, *BE)
            baseline_cz_total.append(cz_mu + cz_beta)
            baseline_cz_mu.append(cz_mu)
            baseline_cz_beta.append(cz_beta)
            baseline_oz_alpha.append(bandpower(oz, fs, *AL))

            elapsed = int(time.time() - start)
            remaining = max(0, int(cfg["calibration_sec"] - elapsed))
            print(f"       {elapsed}s / {cfg['calibration_sec']}s ({remaining}s remaining)", end="\r")

        B_CZ = float(np.median(baseline_cz_total) if baseline_cz_total else 1.0)
        B_CZ_MU = float(np.median(baseline_cz_mu) if baseline_cz_mu else 1.0)
        B_CZ_BE = float(np.median(baseline_cz_beta) if baseline_cz_beta else 1.0)
        B_OZ = float(np.median(baseline_oz_alpha) if baseline_oz_alpha else 1.0)
        print(f"\n[CAL] Baseline → Cz_total={B_CZ:.4f} μV², Cz_mu={B_CZ_MU:.4f} μV², Cz_beta={B_CZ_BE:.4f} μV², Oz_alpha={B_OZ:.4f} μV²")

        # ============ 5. 实时控制循环 ============
        sYaw = Ewma(alpha)
        sAlt = Ewma(alpha)
        sThr = Ewma(alpha)
        sPit = Ewma(alpha)
        hop_samp = int(max(1, hop * fs))
        print("[RUN] Streaming commands... (Press Ctrl+C to stop)")
        print("=" * 65)
        t_loop = time.time()

        while True:
            time.sleep(hop * 0.5)
            data = board.get_current_board_data(win_samp)
            if data.shape[1] < win_samp:
                continue

            c3 = filter_bank.process(data[channel_indices["C3"], :])
            c4 = filter_bank.process(data[channel_indices["C4"], :])
            cz = filter_bank.process(data[channel_indices["Cz"], :])
            oz = filter_bank.process(data[channel_indices["Oz"], :])

            pL_mu = bandpower(c3, fs, *MU)
            pL_be = bandpower(c3, fs, *BE)
            pR_mu = bandpower(c4, fs, *MU)
            pR_be = bandpower(c4, fs, *BE)
            pL = pL_mu + pL_be
            pR = pR_mu + pR_be
            li = (pR - pL) / (pR + pL + 1e-9)
            yaw = clamp(gains["yaw"] * sYaw.step(li))

            cz_mu = bandpower(cz, fs, *MU)
            cz_beta = bandpower(cz, fs, *BE)
            cz_total = cz_mu + cz_beta
            erd = (B_CZ - cz_total) / (B_CZ + 1e-9)
            alt = clamp(gains["altitude"] * sAlt.step(erd))

            pitch_raw = (cz_beta - B_CZ_BE) / (B_CZ_BE + 1e-9) - (cz_mu - B_CZ_MU) / (B_CZ_MU + 1e-9)
            pitch_value = gains["pitch"] * sPit.step(pitch_raw)
            if invert_pitch:
                pitch_value *= -1.0
            pitch = clamp(pitch_value)

            oz_alpha = bandpower(oz, fs, *AL)
            thr_raw = (B_OZ - oz_alpha) / (B_OZ + 1e-9)
            throttle_value = gains["throttle"] * sThr.step(thr_raw) * throttle_scale
            throttle = clamp(throttle_value)

            if abs(yaw) < dead:
                yaw = 0.0
            if abs(alt) < dead:
                alt = 0.0
            if abs(pitch) < dead:
                pitch = 0.0
            if abs(throttle) < dead:
                throttle = 0.0

            msg = {
                "yaw": round(yaw, 4),
                "altitude": round(alt, 4),
                "pitch": round(pitch, 4),
                "throttle": round(throttle, 4),
                "speed": round((throttle + 1.0) * 0.5, 4),
                "ts": time.time(),
            }
            sock.sendto(json.dumps(msg).encode("utf-8"), udp_target)

            print(
                f"Yaw={yaw:+.2f} | Alt={alt:+.2f} | Pitch={pitch:+.2f} | Throttle={throttle:+.2f}",
                end="\r",
            )

            if args.duration and time.time() - t_loop >= args.duration:
                print("\n[INFO] Duration reached, stopping...")
                break

    except KeyboardInterrupt:
        print("\n" + "=" * 65)
        print("[STOP] User interrupted")

    except Exception as e:  # pragma: no cover - unexpected paths
        print("\n" + "=" * 65)
        print(f"[ERROR] Unexpected error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        print("[CLEANUP] Releasing resources...")
        if board is not None:
            for name in ("stop_stream", "release_session"):
                meth = getattr(board, name, None)
                if callable(meth):
                    try:
                        meth()
                    except Exception:  # pragma: no cover - depends on backend
                        pass
            print("[OK] Board session closed")
        if sock is not None:
            sock.close()
        print("[EXIT] Goodbye!")


if __name__ == "__main__":
    main()
