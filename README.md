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
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r python/requirements.txt
```
3️⃣ Configure Channels
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

4️⃣ One-Click Launch (Windows)
```powershell
scripts\start_windows.bat                   # 可附加 --mock、--duration 等参数
```
The batch script sets up the virtual environment (if needed), installs dependencies, then launches
the controller, vJoy bridge and telemetry dashboard in dedicated consoles. Close the opened windows
to stop all services.

5️⃣ Manual Startup (Cross-Platform)
```bash
python python/bci_controller.py              # 连接真实硬件
# 离线调试：使用内置模拟器并在 N 秒后退出
python python/bci_controller.py --mock --duration 30
```
The system performs ~25 s baseline calibration, then streams Yaw / Altitude / Pitch / Throttle.

**Windows (vJoy):** `python python/feed_vjoy.py`

**Linux (uinput):** `sudo python python/feed_uinput.py`

6️⃣ Visualise Command Telemetry (manual mode)

```bash
python python/udp_dashboard.py
```
The terminal dashboard displays the four joystick axes in real time for quick verification.

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
