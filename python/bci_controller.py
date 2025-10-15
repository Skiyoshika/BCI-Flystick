# -*- coding: utf-8 -*-
import time, json, socket, math, os, yaml, sys
import numpy as np
from brainflow import BoardShim, BrainFlowInputParams, BoardIds, DataFilter, FilterTypes, WindowFunctions

# 使用绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_MAP = os.path.join(BASE_DIR, "config", "channel_map.json")
CFG_SET = os.path.join(BASE_DIR, "config", "settings.yaml")

def load_cfg():
    """加载配置文件，包含错误处理"""
    try:
        with open(CFG_MAP, "r", encoding="utf-8") as f:
            m = json.load(f)
        with open(CFG_SET, "r", encoding="utf-8") as f:
            s = yaml.safe_load(f)
        return m, s
    except FileNotFoundError as e:
        print(f"[ERROR] Config file not found: {e}")
        print(f"[INFO] Expected paths:")
        print(f"  - {CFG_MAP}")
        print(f"  - {CFG_SET}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        sys.exit(1)

class Ewma:
    def __init__(self, a): self.a, self.y = a, None
    def step(self, x):
        self.y = float(x) if self.y is None else self.a*float(x)+(1-self.a)*self.y
        return self.y

def bandpower(sig, fs, f1, f2):
    psd = DataFilter.get_psd_welch(sig, int(fs/2), int(fs/4), fs, WindowFunctions.HANNING.value)
    return DataFilter.get_band_power(psd, f1, f2)

def prep(sig, fs, notch, bp_lo, bp_hi):
    DataFilter.perform_bandstop(sig, fs, notch, 4.0, 2, FilterTypes.BUTTERWORTH.value, 0)
    DataFilter.perform_bandpass(sig, fs, bp_lo, bp_hi, 4, FilterTypes.BUTTERWORTH.value, 0)

def main():
    """主控制循环"""
    board = None
    sock = None
    
    try:
        # 1. 加载配置
        chmap, cfg = load_cfg()
    ports = chmap["serial_port"]
    chs = chmap["channels"]
    sr = cfg["sample_rate"]; notch = cfg["notch"]; bp_lo, bp_hi = cfg["bandpass"]
    win = cfg["window_sec"]; hop = cfg["hop_sec"]; alpha = cfg["ewma_alpha"]; dead = cfg["dead_band"]
    kY, kH, kS = cfg["gains"]["yaw"], cfg["gains"]["altitude"], cfg["gains"]["speed"]
    udp_target = tuple(cfg["udp_target"])

    MU=(8,12); BE=(13,30); AL=(8,12)

    # 2. 初始化 OpenBCI
        print(f"[INFO] Connecting to OpenBCI on {ports}...")
        params = BrainFlowInputParams()
        params.serial_port = ports
        board = BoardShim(BoardIds.CYTON_BOARD.value, params)
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
    fs = BoardShim.get_sampling_rate(BoardIds.CYTON_BOARD.value)
    eeg = BoardShim.get_eeg_channels(BoardIds.CYTON_BOARD.value)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("[INFO] Calibrating baseline...")
    B_CZ, B_OZ = [], []; t0=time.time()
    while time.time()-t0 < cfg["calibration_sec"]:
        time.sleep(0.2)
        data = board.get_current_board_data(int(win*fs))
        if data.shape[1] < int(win*fs): continue
        cz = data[eeg[chs["Cz"]], :]; oz = data[eeg[chs["Oz"]], :]
        prep(cz, fs, notch, bp_lo, bp_hi); prep(oz, fs, notch, bp_lo, bp_hi)
        B_CZ.append(bandpower(cz, fs, *MU)+bandpower(cz, fs, *BE))
        B_OZ.append(bandpower(oz, fs, *AL))
    B_CZ = float(np.median(B_CZ) if B_CZ else 1.0)
    B_OZ = float(np.median(B_OZ) if B_OZ else 1.0)
    print(f"[CAL] B_CZ={B_CZ:.4f}, B_OZ={B_OZ:.4f}")

    sYaw, sAlt, sSpd = Ewma(alpha), Ewma(alpha), Ewma(alpha)
    hop_samp=int(hop*fs); win_samp=int(win*fs)
    print("[RUN] Streaming…")
    while True:
        time.sleep(hop*0.5)
        data = board.get_current_board_data(win_samp)
        if data.shape[1] < win_samp: continue
        c3=data[eeg[chs["C3"]],:]; c4=data[eeg[chs["C4"]],:]; cz=data[eeg[chs["Cz"]],:]; oz=data[eeg[chs["Oz"]],:]
        for s in (c3,c4,cz,oz): prep(s, fs, notch, bp_lo, bp_hi)

        pL = bandpower(c3, fs, *MU)+bandpower(c3, fs, *BE)
        pR = bandpower(c4, fs, *MU)+bandpower(c4, fs, *BE)
        li = (pR - pL) / (pR + pL + 1e-9)
        yaw = max(-1.0, min(1.0, kY * sYaw.step(li)))

        cz_mb = bandpower(cz, fs, *MU)+bandpower(cz, fs, *BE)
        erd = (B_CZ - cz_mb) / (B_CZ + 1e-9)
        alt = max(-1.0, min(1.0, kH * sAlt.step(erd)))

        oz_a = bandpower(oz, fs, *AL)
        spd = max(0.0, min(1.0, kS * sSpd.step((B_OZ - oz_a)/(B_OZ+1e-9))))

        if abs(yaw) < dead: yaw = 0.0
        if abs(alt) < dead: alt = 0.0
        msg = {"yaw": round(yaw,4),"altitude":round(alt,4),"speed":round(spd,4),"ts":time.time()}
        sock.sendto(json.dumps(msg).encode(), udp_target)
        print(msg)

except KeyboardInterrupt:
        print("\n[STOP] User interrupted")
    
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
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
