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
Hardware mode (default)
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

```text
Test mode (hardware-free)
Mock Command GUI (keyboard)
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

# Refresh dependencies in an existing checkout without recreating the venv
bash scripts/bootstrap.sh --skip-git --upgrade-deps
```

> ⚠️ **Windows note:** `bash` is not available in plain PowerShell/CMD sessions. Run the
> bootstrap commands from **Git Bash** (bundled with Git for Windows) or **Windows Subsystem
> for Linux**. If you prefer to stay in PowerShell, use `wsl bash scripts/bootstrap.sh ...`
> or upgrade the virtualenv directly with `& .\.venv\Scripts\python.exe -m pip install --upgrade -r
> python/requirements.txt`.

1️⃣ Windows GUI installer

For non-technical Windows users, a minimal GUI installer is provided in
`scripts/gui_installer.py`. Package it into a standalone `.exe` with
[PyInstaller](https://pyinstaller.org/en/stable/) and run it to perform the
first four setup steps (clone the repository, create the virtual environment,
install dependencies and populate `config/channel_map.json`). The installer also
offers to launch the guided setup wizard automatically. The repository does not
ship with a pre-built executable—run the following command locally to generate
`dist/gui_installer.exe` whenever you need a fresh build.

```powershell
# From a separate helper folder (outside the repository clone)
pyinstaller --noconsole --onefile scripts/gui_installer.py
dist\gui_installer.exe
```

The executable lets you pick the installation directory, serial port, board ID
and EEG channel mapping. It will clone the repository into the selected
directory, create or reuse `.venv`, install the Python requirements and then
launch the wizard if requested.

> ⚠️ The GUI installer still requires Git to be available in `PATH`. Install
> [Git for Windows](https://gitforwindows.org/) before running the executable.

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

# Later updates inside the virtualenv
pip install --upgrade -r python/requirements.txt
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
| **Test mode** | Generates a mock calibration profile and launches `python.mock_command_gui` as the only UDP publisher so you can trigger each brainwave action via keyboard buttons while observing the FPV joystick response. | First-time exploration, demoing without hardware, sanity-checking downstream simulators. |
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
`python.main` now starts the BrainFlow controller (for hardware-driven profiles), the correct virtual joystick bridge (`feed_vjoy` or `feed_uinput`), and the selected telemetry dashboard (terminal or GUI) in one shot. If the active profile comes from the wizard's test mode, the launcher skips the controller and instead spawns `python.mock_command_gui` as the sole UDP sender so you can emit simulated EEG actions with the keyboard while observing the FPV stick. Use `Ctrl+C` to stop all services—shutdown is coordinated automatically.

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

### Hardware-free console test pack

If the telemetry dashboard stays idle because no EEG packets arrive, load the
pre-generated mock motor imagery profile and trigger commands from the Console
window:

```bash
python -m python.main --config config/user_profiles/mock_motor_imagery.json
```

The launcher will open the GUI dashboard together with `python.mock_command_gui`.
Each button press now updates the dashboard and prints the effective joystick
axes in the Console footer. Because the controller stays offline in this mode,
the GUI is the only UDP source, preventing conflicts on port 5005. When you
need additional confirmation, launch the Console with `--echo` to mirror every
UDP packet:

```bash
python -m python.mock_command_gui --calibration config/calibration_profiles/mock_motor_imagery.json --echo
```

This lets you verify axis movement even on systems where vJoy/uinput is not yet
active.

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
