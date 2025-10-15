# BCI-Flystick  
### OpenBCI-based Real-Time EEG → Virtual Joystick Bridge for Drone & Flight Simulation Control  
（基于 OpenBCI Cyton 的三轴脑机接口虚拟飞控系统）

---

## Overview | 项目简介  

**BCI-Flystick** 是一个开源框架，用于将 **OpenBCI Cyton** 采集的实时脑电（EEG）信号转化为三轴飞行控制指令。  
它通过检测 **运动想象 (Motor Imagery)** 与 **视觉注意 (Alpha / SSVEP)** 模式，实现基于脑信号的虚拟摇杆操作，可直接用于 **无人机仿真、飞行模拟器、VR 控制或神经康复训练**。  

> **Yaw（左右旋转）** ← C3/C4 区 μβ 频段侧化变化  
>  
> **Altitude（上升/下降）** ← Cz 区 μβ ERD 强度  
>  
> **Speed（速度/油门）** ← Oz 区 α 波下降或 SSVEP 反应  

---

## Key Features | 核心特性  

| 功能 | 说明 |
|------|------|
| EEG Acquisition | 实时采集 OpenBCI Cyton（8通道）EEG 数据 |
| Signal Processing | μ/β 波（运动想象）与 α/SSVEP（注意/视觉诱发）特征提取 |
| Virtual Joystick | 通过 vJoy (Windows) / uinput (Linux) 输出三轴摇杆信号 |
| Integration | 可与 PX4 SITL、Mission Planner、AirSim、VelociDrone 等模拟器连接 |
| Configurable | JSON + YAML 配置，支持通道映射与滤波参数自定义 |
| Extendable | 支持 Python 端特征提取 + Rust 接口低延迟控制 |

---

## Architecture | 系统架构  

EEG (C3,C4,Cz,Oz)
↓
OpenBCI Cyton
↓
BrainFlow SDK (Python)
↓
Feature Extraction (μ,β,α,SSVEP)
↓
UDP Stream (Yaw,Alt,Speed)
↓
Virtual Joystick (vJoy / uinput)
↓
Drone Sim / Game Engine

yaml
复制代码

---

## Installation | 安装步骤  

 1. Clone Repository
```bash
git clone https://github.com/Skiyoshika/BCI-Flystick.git
cd BCI-Flystick
 2. Setup Python Environment
bash
复制代码
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r python/requirements.txt
 3. Configure Channels
编辑 config/channel_map.json：

json
复制代码
{
  "serial_port": "COM3",
  "board_id": "CYTON",
  "channels": { "C3": 0, "C4": 1, "Cz": 2, "Oz": 7 }
}
 4. Start Controller
bash
复制代码
python python/bci_controller.py
系统会进行约 25 秒的基线标定，然后开始实时输出 Yaw / Altitude / Speed 的三轴数据。

 5. Connect to Virtual Joystick
Windows: 安装 vJoy，运行

bash
复制代码
python python/feed_vjoy.py
Linux: 运行

bash
复制代码
sudo python python/feed_uinput.py
此时系统会自动创建虚拟摇杆设备，可在 QGroundControl、AirSim、Mission Planner 等软件中识别。

 Flight Simulation Integration | 模拟器连接
 QGroundControl / PX4 SITL
打开 Joystick 设置。

绑定：

X → Yaw

Y → Altitude

Z → Throttle (Speed)

校准灵敏度与死区（推荐 Deadband = 5–10%）。

 Mission Planner (ArduPilot)
打开 “Joystick” → “Enable Joystick Input”

绑定通道与动作。

 AirSim / Unreal / VelociDrone
选择 “Controller / Joystick” 模式。

vJoy / uinput 会自动映射为输入源，可直接飞行。

 Control Paradigm | 控制范式
控制轴	脑区	频段	想象/任务	行为
Yaw	C3 / C4	μ, β	想象左/右手运动	向左/右转
Altitude	Cz	μ, β	想象双脚用力蹬地	上升/下降
Speed	Oz	α 或 SSVEP	集中/放松 或 注视闪烁点	加速/减速

 Project Structure | 项目结构
bash
复制代码
bci-flystick/
├─ config/         # 配置文件（通道映射、参数）
├─ python/         # 主控制程序、虚拟摇杆脚本
├─ rust/           # UDP 接收/接口层
├─ scripts/        # 启动脚本
└─ docs/           # 文档与实验笔记
 License
MIT License – Open-source, free to modify and distribute.
你可以在学术研究、实验或教学中自由使用此项目。

 Contact
Author: @Skiyoshika
Email: hiuramika122@gmail.com
Keywords: Brain–Computer Interface, OpenBCI, EEG, Drone Control, vJoy, AirSim, PX4

 Acknowledgements
OpenBCI Cyton Board

BrainFlow SDK

vJoy Virtual Joystick Driver

PX4 SITL & QGroundControl

AirSim (Microsoft)
