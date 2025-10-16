# BCI-Flystick  
### OpenBCI-based Real-Time EEG → Virtual Joystick Bridge for Drone & Flight Simulation Control

---

## Overview

**BCI-Flystick** is an open-source framework that converts real-time EEG signals from the **OpenBCI Cyton** board into a **four-axis virtual joystick**.
If you are looking for the Chinese-language manual, refer to the separate Chinese manual provided in the repository root.
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
| **Live Telemetry Dashboard** | Terminal (Rich) and GUI viewers visualise yaw/altitude/pitch/throttle |
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
0️⃣ One-command bootstrap (optional)
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Skiyoshika/BCI-Flystick/main/scripts/bootstrap.sh)
```
The bootstrap script clones (or updates) the repository, creates the `.venv` virtual environment and installs the Python requirements in a single step. Run it without `curl` if you already have the repository locally:

```bash
git clone https://github.com/Skiyoshika/BCI-Flystick.git
cd BCI-Flystick
bash scripts/bootstrap.sh --skip-git
```

1️⃣ Clone Repository (manual setup)
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
The refreshed wizard first asks whether you want to start in **test mode** (simulated EEG) or **first-time calibration** (real EEG hardware). It still checks Python/driver prerequisites, guides you through joystick backend selection, UDP host/port, throttle scaling and dashboard preferences. Profiles are saved under `config/user_profiles/` and reused automatically by the runtime launcher, while calibration data lives in `config/calibration_profiles/`.

### Usage Modes introduced by the new wizard

| Mode | What happens | When to use |
|------|---------------|-------------|
| **Test mode** | Generates a mock calibration profile, enables the mock EEG controller and launches a new `python.mock_command_gui` window so you can trigger each brainwave action via keyboard buttons while observing the FPV joystick response. | First-time exploration, demoing without hardware, sanity-checking downstream simulators. |
| **First-time calibration** | Guides you through recording eight actions (accelerate/decelerate, yaw left/right, climb/descend, pitch up/down) using your real OpenBCI headset, storing the durations and polarity preferences in a calibration JSON. The runtime uses these axis signs to map live EEG features into joystick commands without extra key presses. | Preparing a user-specific profile for regular gameplay/simulation sessions. |

Once a calibration exists, you can skip the wizard and launch `python -m python.main` directly. The launcher remembers the most recent profile but you can always pick a different one with `--config`.

4️⃣ Configure Channels
Edit `config/channel_map.json`:

```json
{
  "serial_port": "COM3",
  "board_id": "CYTON",
  "channels": { "C3": 0, "C4": 1, "Cz": 2, "Oz": 7 }
}
```

> ✅ **Configuration validation:** Startup verifies that `channel_map.json` and `settings.yaml` contain valid values. `board_id` accepts `CYTON`, `CYTON_DAISY`, `GANGLION`, and `SYNTHETIC` (BrainFlow simulated board).

`config/settings.yaml` parameter reference:

| Field | Type | Description |
|-------|------|-------------|
| `sample_rate` | float | Expected sampling rate (used for configuration consistency checks) |
| `bandpass` | [float, float] | Low/high cut-off frequencies (Hz) for band-pass filtering |
| `notch` | float | Notch frequency (Hz), typically 50 or 60 |
| `window_sec` / `hop_sec` | float | Window length and hop size (seconds) for time-frequency analysis |
| `ewma_alpha` | float | Exponential moving average factor in [0, 1] |
| `dead_band` | float | Output dead-zone threshold |
| `gains` | dict | Gains for `yaw`, `altitude`, `pitch`, and `throttle` |
| `calibration_sec` | float | Baseline calibration duration (seconds) |
| `udp_target` | [str, int] | Address and port of the downstream receiver |

5️⃣ Launch the orchestrated runtime
```bash
# Start with the last-used profile
python -m python.main

# Specify a profile explicitly
python -m python.main --config config/user_profiles/my_profile.json

# Useful overrides
python -m python.main --mock           # Force mock EEG data
python -m python.main --no-dashboard   # Disable the terminal joystick dashboard
python -m python.main --dashboard gui  # Launch the graphical telemetry window directly
```
`python.main` now starts the BrainFlow controller, the correct virtual joystick bridge (`feed_vjoy` or `feed_uinput`), and the selected telemetry dashboard (terminal or GUI) in one shot. If the active profile comes from the wizard's test mode, the launcher also spawns the `python.mock_command_gui` helper so you can emit simulated EEG actions with the keyboard while observing the FPV stick. Use `Ctrl+C` to stop all services—shutdown is coordinated automatically.

6️⃣ Manual Startup (advanced / debugging)
```bash
python python/bci_controller.py              # Connect to real hardware
python python/bci_controller.py --mock       # Use simulated EEG
python python/feed_vjoy.py --host 0.0.0.0    # Windows vJoy
sudo python python/feed_uinput.py            # Linux uinput
python python/udp_dashboard.py               # Terminal joystick dashboard
python python/udp_dashboard.py --once        # Exit after receiving the first frame
python python/gui_dashboard.py               # Graphical joystick telemetry
```

## Local Validation

The repository offers the following self-check commands:

```bash
# Python syntax check
python -m compileall python

# Python unit tests
pytest

# Rust UDP receiver tests
cargo test --manifest-path rust/bci_receiver/Cargo.toml
```

GitHub Actions runs the same workflow automatically on each push or pull request to ensure the pipeline stays green.

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
