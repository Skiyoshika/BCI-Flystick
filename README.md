# BCI-Flystick  
### OpenBCI-based Real-Time EEG → Virtual Joystick Bridge for Drone & Flight Simulation Control

---

## Overview

**BCI-Flystick** is an open-source framework that converts real-time EEG signals from the **OpenBCI Cyton** board into a **three-axis virtual joystick**.  
It decodes **motor-imagery (μ/β)** and **visual-attention (α/SSVEP)** patterns to control yaw, altitude, and throttle, enabling brain-driven flight in drone simulators or robotic testbeds. 

> • **Yaw (left/right rotation)** ← C3/C4 μβ lateralization  
> • **Altitude (up/down)** ← Cz μβ ERD intensity  
> • **Speed (throttle)** ← Oz α power decrease or SSVEP frequency response  

---

## Key Features

| Feature | Description |
|----------|-------------|
| **EEG Acquisition** | Real-time data streaming from OpenBCI Cyton (8 channels) |
| **Signal Processing** | μ/β ERD for motor imagery and α/SSVEP for attention control |
| **Virtual Joystick Output** | vJoy (Windows) or uinput (Linux) creates a USB joystick device |
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
   UDP Stream (Yaw, Alt, Speed)  
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
4️⃣ Start Controller
```bash
python python/bci_controller.py
```
The system performs ~25 s baseline calibration, then streams Yaw / Altitude / Speed.

5️⃣ Connect to Virtual Joystick

**Windows (vJoy):**

```bash
python python/feed_vjoy.py
```
**Linux (uinput):**

```bash
sudo python python/feed_uinput.py
```
A virtual joystick will appear and be recognized by QGroundControl / AirSim / Mission Planner.

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
