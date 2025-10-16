"""Entry point for the BCI Flystick runtime orchestration."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent.parent / "config" / "user_profiles"
LAST_PROFILE_FILE = DEFAULT_PROFILE_DIR / ".last_profile"
CALIBRATION_ENV_VAR = "BCI_FLYSTICK_CALIBRATION"
MODE_ENV_VAR = "BCI_FLYSTICK_MODE"


def load_profile(profile_path: Path) -> dict[str, Any]:
    """Load a profile JSON file, raising an informative error if it does not exist."""
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with profile_path.open("r", encoding="utf-8") as profile_file:
        return json.load(profile_file)


def remember_profile(profile_path: Path) -> None:
    """Persist the last used profile for convenient subsequent launches."""
    DEFAULT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_PROFILE_FILE.write_text(str(profile_path.resolve()), encoding="utf-8")


def resolve_profile_path(args_profile: str | None) -> Path | None:
    if args_profile:
        return Path(args_profile).expanduser().resolve()

    if LAST_PROFILE_FILE.exists():
        stored = LAST_PROFILE_FILE.read_text(encoding="utf-8").strip()
        if stored:
            return Path(stored)
    return None


def _localise(language: str, english: str, chinese: str) -> str:
    return chinese if language == "zh" else english


@dataclass
class ManagedProcess:
    name: str
    command: list[str]
    process: subprocess.Popen[str]


def _spawn(name: str, command: list[str], *, env: dict[str, str]) -> ManagedProcess:
    print(f"[LAUNCH] {name}: {' '.join(command)}")
    proc = subprocess.Popen(command, env=env)
    return ManagedProcess(name=name, command=command, process=proc)


def _wait_for_processes(language: str, processes: list[ManagedProcess]) -> None:
    while True:
        alive = False
        for managed in processes:
            code = managed.process.poll()
            if code is None:
                alive = True
                continue
            message = _localise(
                language,
                f"Process '{managed.name}' exited with code {code}.",
                f"进程“{managed.name}”已退出，返回码 {code}。",
            )
            print(message)
            return
        if not alive:
            return
        time.sleep(0.5)


def _graceful_shutdown(language: str, processes: Iterable[ManagedProcess]) -> None:
    for managed in processes:
        if managed.process.poll() is not None:
            continue
        message = _localise(
            language,
            f"Stopping '{managed.name}'...",
            f"正在停止“{managed.name}”...",
        )
        print(message)
        try:
            managed.process.send_signal(signal.SIGINT)
        except ValueError:
            managed.process.terminate()

    deadline = time.time() + 5.0
    for managed in processes:
        if managed.process.poll() is not None:
            continue
        remaining = max(0.0, deadline - time.time())
        try:
            managed.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            warning = _localise(
                language,
                f"Force killing '{managed.name}'...",
                f"强制结束“{managed.name}”...",
            )
            print(warning)
            managed.process.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch the BCI Flystick runtime with a previously generated profile.",
    )
    parser.add_argument(
        "--config",
        dest="config",
        help="Path to a profile JSON created by the setup wizard.",
    )
    parser.add_argument(
        "--wizard",
        action="store_true",
        help="Run the interactive setup wizard before launching.",
    )
    parser.add_argument(
        "--wizard-language",
        choices=["en", "zh"],
        help="Optional language override when launching the setup wizard.",
    )
    parser.add_argument(
        "--mock",
        dest="force_mock",
        action="store_true",
        help="Force the controller to use the mock EEG generator, regardless of the profile.",
    )
    parser.add_argument(
        "--hardware",
        dest="force_hardware",
        action="store_true",
        help="Force real OpenBCI hardware mode, even if the profile enables mock mode.",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Do not launch the telemetry dashboard, even if enabled in the profile.",
    )
    parser.add_argument(
        "--dashboard",
        choices=["terminal", "gui", "none"],
        help="Override the telemetry dashboard mode (terminal/gui/none).",
    )
    args = parser.parse_args(argv)

    if args.wizard:
        try:
            from . import setup_wizard
        except ImportError:  # pragma: no cover - fallback when executed as a script
            import python.setup_wizard as setup_wizard  # type: ignore

        wizard_args: list[str] = []
        if args.wizard_language:
            wizard_args.extend(["--language", args.wizard_language])
        setup_wizard.main(wizard_args or None)

    profile_path = resolve_profile_path(args.config)
    if profile_path is None:
        print(
            "No profile specified. Run the setup wizard first (python -m python.setup_wizard).",
            file=sys.stderr,
        )
        return 1

    try:
        profile = load_profile(profile_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid profile JSON in {profile_path}: {exc}", file=sys.stderr)
        return 1

    remember_profile(profile_path)

    language = profile.get("language", "en")
    profile_mode = str(profile.get("mode", "calibration")).strip().lower()
    calibration_path_raw = profile.get("calibration_profile")
    calibration_path: Path | None = None
    if calibration_path_raw:
        try:
            calibration_path = Path(str(calibration_path_raw)).expanduser().resolve()
        except (OSError, TypeError):
            calibration_path = None

    print(_localise(language, "Loaded profile:", "已加载配置："))
    print(json.dumps(profile, indent=2, ensure_ascii=False))

    udp_host = str(profile.get("udp_host", "127.0.0.1"))
    udp_port = int(profile.get("udp_port", 5005))
    control_backend = str(profile.get("control_backend", "vigem"))
    profile_dashboard_mode = str(profile.get("dashboard_mode", "")).strip().lower()
    launch_dashboard_flag = profile.get("launch_dashboard")
    if not profile_dashboard_mode:
        if launch_dashboard_flag is None:
            profile_dashboard_mode = "terminal"
        else:
            profile_dashboard_mode = "terminal" if bool(launch_dashboard_flag) else "none"
    launch_dashboard = profile_dashboard_mode != "none"
    dashboard_mode = profile_dashboard_mode if launch_dashboard else "none"
    mock_mode = bool(profile.get("mock_mode", False))

    if profile_mode == "test":
        mock_mode = True
        print(_localise(language, "Test mode: mock EEG enabled.", "测试模式：已启用模拟 EEG。"))

    if args.force_mock:
        mock_mode = True
    if args.force_hardware:
        mock_mode = False
    if args.no_dashboard:
        launch_dashboard = False
        dashboard_mode = "none"
    if args.dashboard:
        dashboard_mode = args.dashboard
        launch_dashboard = dashboard_mode != "none"

    env = os.environ.copy()
    env["BCI_FLYSTICK_PROFILE"] = str(profile_path.resolve())
    if calibration_path:
        env[CALIBRATION_ENV_VAR] = str(calibration_path)
    else:
        env.pop(CALIBRATION_ENV_VAR, None)
    env[MODE_ENV_VAR] = profile_mode

    processes: list[ManagedProcess] = []
    try:
        controller_cmd = [
            sys.executable,
            "-m",
            "python.bci_controller",
            "--udp-host",
            udp_host,
            "--udp-port",
            str(udp_port),
        ]
        if mock_mode:
            controller_cmd.append("--mock")
            print(_localise(language, "Mock EEG generator enabled.", "已启用模拟 EEG 数据。"))

        processes.append(
            _spawn(
                "bci_controller",
                controller_cmd,
                env=env,
            )
        )

        if control_backend == "vigem":
            backend_module = "python.feed_vjoy"
            backend_name = "feed_vjoy"
        elif control_backend == "uinput":
            backend_module = "python.feed_uinput"
            backend_name = "feed_uinput"
        else:
            print(
                _localise(
                    language,
                    f"Unsupported control backend '{control_backend}'.",
                    f"不支持的控制后端“{control_backend}”。",
                ),
                file=sys.stderr,
            )
            return 1

        processes.append(
            _spawn(
                backend_name,
                [
                    sys.executable,
                    "-m",
                    backend_module,
                    "--host",
                    udp_host,
                    "--port",
                    str(udp_port),
                ],
                env=env,
            )
        )

        if profile_mode == "test":
            gui_cmd = [
                sys.executable,
                "-m",
                "python.mock_command_gui",
                "--host",
                udp_host,
                "--port",
                str(udp_port),
            ]
            if calibration_path:
                gui_cmd.extend(["--calibration", str(calibration_path)])
            processes.append(
                _spawn(
                    "mock_command_gui",
                    gui_cmd,
                    env=env,
                )
            )

        if launch_dashboard and dashboard_mode == "terminal":
            processes.append(
                _spawn(
                    "udp_dashboard",
                    [
                        sys.executable,
                        "-m",
                        "python.udp_dashboard",
                        "--host",
                        udp_host,
                        "--port",
                        str(udp_port),
                    ],
                    env=env,
                )
            )
        elif launch_dashboard and dashboard_mode == "gui":
            processes.append(
                _spawn(
                    "gui_dashboard",
                    [
                        sys.executable,
                        "-m",
                        "python.gui_dashboard",
                        "--host",
                        udp_host,
                        "--port",
                        str(udp_port),
                    ],
                    env=env,
                )
            )

        print(
            _localise(
                language,
                "All services started. Press Ctrl+C to stop.",
                "所有服务已启动，按 Ctrl+C 结束。",
            )
        )

        _wait_for_processes(language, processes)
    except KeyboardInterrupt:
        print(_localise(language, "Stopping services...", "收到中断信号，正在停止服务..."))
    finally:
        _graceful_shutdown(language, processes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
