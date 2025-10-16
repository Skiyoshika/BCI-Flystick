# BCI-Flystick  
### OpenBCI-based Real-Time EEG → Virtual Joystick Bridge for Drone & Flight Simulation Control

---

## Overview

**BCI-Flystick** is an open-source framework that converts real-time EEG signals from the **OpenBCI Cyton** board into a **four-axis virtual joystick**.
It decodes **motor-imagery (μ/β)** and **visual-attention (α/SSVEP)** patterns to control yaw, altitude, pitch and throttle, enabling brain-driven flight in drone simulators or robotic testbeds.

> • **Yaw (left/right rotation)** ← C3/C4 μβ lateralization
> • **Altitude (up/down)** ← Cz μβ ERD intensity
> • **Pitch (nose up/down)** ← Cz μ vs β balance dynamics
> • **Throttle (accelerate/decelerate)** ← Oz α power decrease or SSVEP frequency response

---

## Key Features

| Feature | Description |
|----------|-------------|
| **EEG Acquisition** | Real-time data streaming from OpenBCI Cyton (8 channels) |
| **Signal Processing** | μ/β ERD for motor imagery and α/SSVEP for attention control |
| **Virtual Joystick Output** | vJoy (Windows) or uinput (Linux) creates a USB joystick device |
| **Offline Development** | Built-in mock EEG board & BrainFlow synthetic mode for hardware-free testing |
| **Live Telemetry Dashboard** | Terminal UI visualises yaw/altitude/pitch/throttle in real time |
| **Simulator Integration** | Works with PX4 SITL + QGroundControl, Mission Planner, AirSim, VelociDrone |
| **Config-Driven Design** | JSON + YAML for channel mapping and parameter tuning |
| **Extensible Architecture** | Python feature extraction + Rust receiver for low-latency control |

---

## System Architecture
```text
EEG (C3, C4, Cz, Oz)
        ↓    
   OpenBCI Cyton 
        ↓      
  BrainFlow SDK (Python)
        ↓        
 Feature Extraction (μ, β, α, SSVEP) 
        ↓      
  UDP Stream (Yaw, Alt, Pitch, Throttle)
        ↓       
 Virtual Joystick (vJoy / uinput) 
        ↓       
 Drone Simulator / Game Engine
```
## Installation & Setup
1️⃣ Clone Repository
```bash
git clone https://github.com/Skiyoshika/BCI-Flystick.git
cd BCI-Flystick
```
2️⃣ Setup Python Environment
```bash
python -m venv .venv
source .venv/bin/activate                # macOS / Linux
& .\.venv\Scripts\Activate.ps1          # Windows PowerShell
\\.venv\Scripts\activate.bat           # Windows CMD
pip install -r python/requirements.txt
```

> ℹ️ **PowerShell Tip:** If PowerShell opens `Activate.ps1` in an editor instead of running it, make sure the command starts with the call operator `&` (for example `& .\.venv\Scripts\Activate.ps1`).
3️⃣ Run the guided setup wizard (optional but recommended)
```bash
python -m python.main --wizard               # Add --wizard-language zh for Chinese prompts
```
The wizard now checks Python/driver prerequisites, lets you pick UDP host/port, mock vs. real BrainFlow mode, joystick backend, and telemetry/dashboard preferences. Profiles are saved under `config/user_profiles/` and reused automatically by the runtime launcher.

4️⃣ Configure Channels
Edit config/channel_map.json:

```json
{
  "serial_port": "COM3",
  "board_id": "CYTON",
  "channels": { "C3": 0, "C4": 1, "Cz": 2, "Oz": 7 }
}
```

> ✅ **配置校验**：启动时会验证 `channel_map.json` 与 `settings.yaml`，确保字段齐全且取值有效。`board_id` 支持 `CYTON`、`CYTON_DAISY`、`GANGLION` 与 `SYNTHETIC`（BrainFlow 仿真板）。

`config/settings.yaml` 参数说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `sample_rate` | float | 期望采样率（用于配置一致性检查） |
| `bandpass` | [float, float] | 带通滤波的低/高截止频率（Hz） |
| `notch` | float | 陷波频率（Hz），典型值 50 或 60 |
| `window_sec` / `hop_sec` | float | 时频分析窗口长度与步长（秒） |
| `ewma_alpha` | float | 指数平滑系数，范围 [0,1] |
| `dead_band` | float | 输出死区阈值 |
| `gains` | dict | `yaw`、`altitude`、`pitch`、`throttle` 四个增益 |
| `calibration_sec` | float | 基线校准时长（秒） |
| `udp_target` | [str, int] | 下游接收端的地址与端口 |

5️⃣ Launch the orchestrated runtime
```bash
# Start with the last-used profile
python -m python.main

# Specify a profile explicitly
python -m python.main --config config/user_profiles/my_profile.json

# Useful overrides
python -m python.main --mock           # 强制使用模拟 EEG 数据
python -m python.main --no-dashboard   # 不启动终端摇杆仪表板
```
`python.main` now starts the BrainFlow controller, the correct virtual joystick bridge (`feed_vjoy` or `feed_uinput`), and the Rich-based telemetry dashboard in one shot. Use `Ctrl+C` to stop all services—shutdown is coordinated automatically.

6️⃣ Manual Startup (advanced / debugging)
```bash
python python/bci_controller.py              # 连接真实硬件
python python/bci_controller.py --mock       # 使用模拟 EEG
python python/feed_vjoy.py --host 0.0.0.0    # Windows vJoy
sudo python python/feed_uinput.py            # Linux uinput
python python/udp_dashboard.py               # 终端摇杆仪表板
```

## 本地自检

仓库提供如下自检命令：

```bash
# Python 语法检查
python -m compileall python

# Python 单元测试
pytest

# Rust UDP 接收端测试
cargo test --manifest-path rust/bci_receiver/Cargo.toml
```

GitHub Actions 在 push / pull request 时会自动运行同样的流程，确保工作流可通过。

## Flight Simulation Integration
**QGroundControl / PX4 SITL**

Bind axes:

X → Yaw

Y → Altitude

Z → Throttle (Speed)

Calibrate sensitivity & dead zones (recommended 5–10%).

**Mission Planner (ArduPilot)**

Enable Joystick Input and assign channels.

**AirSim / VelociDrone**

Select Controller / Joystick mode; vJoy/uinput is detected automatically.

## Project Structure
```text

bci-flystick/
├─ config/      # Channel mapping & signal parameters
├─ python/      # Core controller + virtual joystick scripts
├─ rust/        # Low-latency UDP receiver and SDK bridge
├─ scripts/     # Quick start helpers
└─ docs/        # Documentation and experiment notes
```
## License
MIT License – Open-source, free to modify and distribute.

You may freely use this project for research, education, or development.

## Contact
**Author:** @Skiyoshika

**Email:** hiuramika122@gmail.com

**Keywords:** Brain–Computer Interface, OpenBCI, EEG, Drone Control, vJoy, AirSim, PX4

## Acknowledgements
OpenBCI Cyton Board

BrainFlow SDK

vJoy Virtual Joystick Driver

PX4 SITL & QGroundControl

AirSim (Microsoft)
