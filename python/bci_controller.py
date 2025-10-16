# -*- coding: utf-8 -*-
"""
BCI-Flystick Controller
Real-time EEG to virtual joystick converter
"""
import time, json, socket, os, yaml, sys
from typing import Dict, Any, Tuple

import numpy as np
from brainflow import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter, FilterTypes, WindowOperations

# 使用绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_MAP = os.path.join(BASE_DIR, "config", "channel_map.json")
CFG_SET = os.path.join(BASE_DIR, "config", "settings.yaml")


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
    gains_clean = {}
    for axis in ("yaw", "altitude", "speed"):
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

class Ewma:
    """指数加权移动平均滤波器"""
    def __init__(self, a): 
        self.a, self.y = a, None
    
    def step(self, x):
        self.y = float(x) if self.y is None else self.a*float(x)+(1-self.a)*self.y
        return self.y

def bandpower(sig, fs, f1, f2):
    """计算频段功率"""
    psd = DataFilter.get_psd_welch(sig, int(fs/2), int(fs/4), fs, WindowOperations.HANNING.value)
    return DataFilter.get_band_power(psd, f1, f2)

def prep(sig, fs, notch, bp_lo, bp_hi):
    """预处理信号：陷波 + 带通滤波"""
    DataFilter.perform_bandstop(sig, fs, notch, 4.0, 2, FilterTypes.BUTTERWORTH.value, 0)
    DataFilter.perform_bandpass(sig, fs, bp_lo, bp_hi, 4, FilterTypes.BUTTERWORTH.value, 0)

def main():
    """主控制循环"""
    board = None
    sock = None
    
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
        kY, kH, kS = cfg["gains"]["yaw"], cfg["gains"]["altitude"], cfg["gains"]["speed"]
        udp_target = cfg["udp_target"]

        MU = (8, 12)   # Mu 频段
        BE = (13, 30)  # Beta 频段
        AL = (8, 12)   # Alpha 频段

        # ============ 2. 初始化 OpenBCI ============
        print(f"[INFO] Connecting to OpenBCI on {ports}...")
        params = BrainFlowInputParams()
        params.serial_port = ports
        board = BoardShim(board_id, params)
        BoardShim.enable_dev_board_logger()
        
        try:
            board.prepare_session()
            board.start_stream(45000)
            print("[OK] OpenBCI connected successfully")
        except Exception as e:
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

        # ============ 3. 初始化 UDP ============
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[INFO] UDP target: {udp_target}")

        # ============ 4. 基线校准 ============
        print(f"[INFO] Calibrating baseline ({cfg['calibration_sec']}s)...")
        print("       Keep relaxed and look straight ahead...")
        B_CZ, B_OZ = [], []
        t0 = time.time()
        
        while time.time() - t0 < cfg["calibration_sec"]:
            time.sleep(0.2)
            data = board.get_current_board_data(int(win * fs))
            if data.shape[1] < int(win * fs):
                continue
            
            cz = data[eeg[chs["Cz"]], :]
            oz = data[eeg[chs["Oz"]], :]
            prep(cz, fs, notch, bp_lo, bp_hi)
            prep(oz, fs, notch, bp_lo, bp_hi)
            B_CZ.append(bandpower(cz, fs, *MU) + bandpower(cz, fs, *BE))
            B_OZ.append(bandpower(oz, fs, *AL))
            
            # 显示进度
            elapsed = int(time.time() - t0)
            remaining = cfg["calibration_sec"] - elapsed
            print(f"       {elapsed}s / {cfg['calibration_sec']}s ({remaining}s remaining)", end="\r")

        B_CZ = float(np.median(B_CZ) if B_CZ else 1.0)
        B_OZ = float(np.median(B_OZ) if B_OZ else 1.0)
        print(f"\n[CAL] Baseline → Cz={B_CZ:.4f} μV², Oz={B_OZ:.4f} μV²")

        # ============ 5. 实时控制循环 ============
        sYaw, sAlt, sSpd = Ewma(alpha), Ewma(alpha), Ewma(alpha)
        hop_samp = int(hop * fs)
        win_samp = int(win * fs)
        print("[RUN] Streaming commands... (Press Ctrl+C to stop)")
        print("=" * 50)
        
        while True:
            time.sleep(hop * 0.5)
            data = board.get_current_board_data(win_samp)
            
            if data.shape[1] < win_samp:
                continue

            # 提取通道
            c3 = data[eeg[chs["C3"]], :]
            c4 = data[eeg[chs["C4"]], :]
            cz = data[eeg[chs["Cz"]], :]
            oz = data[eeg[chs["Oz"]], :]

            # 预处理
            for s in (c3, c4, cz, oz):
                prep(s, fs, notch, bp_lo, bp_hi)

            # === Yaw: C3/C4 lateralization ===
            pL = bandpower(c3, fs, *MU) + bandpower(c3, fs, *BE)
            pR = bandpower(c4, fs, *MU) + bandpower(c4, fs, *BE)
            li = (pR - pL) / (pR + pL + 1e-9)
            yaw = max(-1.0, min(1.0, kY * sYaw.step(li)))

            # === Altitude: Cz ERD ===
            cz_mb = bandpower(cz, fs, *MU) + bandpower(cz, fs, *BE)
            erd = (B_CZ - cz_mb) / (B_CZ + 1e-9)
            alt = max(-1.0, min(1.0, kH * sAlt.step(erd)))

            # === Speed: Oz alpha suppression ===
            oz_a = bandpower(oz, fs, *AL)
            spd = max(0.0, min(1.0, kS * sSpd.step((B_OZ - oz_a) / (B_OZ + 1e-9))))

            # 死区处理
            if abs(yaw) < dead: 
                yaw = 0.0
            if abs(alt) < dead: 
                alt = 0.0

            # 发送 UDP
            msg = {
                "yaw": round(yaw, 4),
                "altitude": round(alt, 4),
                "speed": round(spd, 4),
                "ts": time.time()
            }
            sock.sendto(json.dumps(msg).encode(), udp_target)
            
            # 显示状态
            print(f"Yaw={yaw:+.2f} | Alt={alt:+.2f} | Spd={spd:.2f}", end="\r")

    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("[STOP] User interrupted")
    
    except Exception as e:
        print("\n" + "=" * 50)
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # ============ 清理资源 ============
        print("[CLEANUP] Releasing resources...")
        if board:
            try:
                board.stop_stream()
                board.release_session()
                print("[OK] OpenBCI disconnected")
            except:
                pass
        if sock:
            sock.close()
        print("[EXIT] Goodbye!")

if __name__ == "__main__":
    main()
