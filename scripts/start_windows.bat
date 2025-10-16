@echo off
setlocal

REM Ensure virtual environment exists and is activated
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate

REM Install/update project dependencies
pip install -r python\requirements.txt

REM Launch the core controller, joystick bridge and dashboard together
echo Starting BCI controller...
start "BCI Controller" python python\bci_controller.py %*

echo Starting vJoy bridge...
start "BCI vJoy Bridge" python python\feed_vjoy.py

echo Starting telemetry dashboard...
start "BCI Dashboard" python python\udp_dashboard.py

echo.
echo All BCI-Flystick services have been launched. Close the opened windows to stop them.
pause
endlocal
