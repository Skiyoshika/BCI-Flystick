"""Simple Tkinter-based installer for BCI-Flystick.

This utility is intended to be packaged as a Windows executable (for example
with PyInstaller) so that non-technical users can install the project without
typing commands manually. It automates cloning the repository, creating the
virtual environment, installing dependencies, running the guided setup wizard
and generating the basic `config/channel_map.json` file.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


REPO_URL = "https://github.com/Skiyoshika/BCI-Flystick.git"
DEFAULT_CHANNELS = "C3:0,C4:1,Cz:2,Oz:7"


def append_log(widget: tk.Text, message: str) -> None:
    widget.configure(state="normal")
    widget.insert(tk.END, message + "\n")
    widget.see(tk.END)
    widget.configure(state="disabled")


def run_command(cmd: list[str], cwd: Optional[Path], log_widget: tk.Text) -> None:
    append_log(log_widget, f"$ {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    for line in process.stdout:
        append_log(log_widget, line.rstrip())
    exit_code = process.wait()
    append_log(log_widget, f"→ exit code {exit_code}")
    if exit_code != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed with exit code {exit_code}")


def python_executable_from_venv(venv_path: Path) -> Path:
    if platform.system() == "Windows":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def parse_channel_mapping(raw: str) -> Dict[str, int]:
    channels: Dict[str, int] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        try:
            name, index = item.split(":", 1)
        except ValueError as exc:  # pragma: no cover - user error path
            raise ValueError("Channel entries must look like 'C3:0' separated by commas") from exc
        name = name.strip()
        try:
            channels[name] = int(index.strip())
        except ValueError as exc:  # pragma: no cover - user error path
            raise ValueError(f"Channel index for {name} must be an integer") from exc
    if not channels:
        raise ValueError("At least one channel mapping entry is required")
    return channels


@dataclass
class InstallerConfig:
    target_dir: Path
    repo_url: str
    board_id: str
    serial_port: str
    channels: Dict[str, int]
    run_wizard_after_install: bool
    wizard_language: str


class InstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BCI-Flystick GUI Installer")

        container = ttk.Frame(root, padding=10)
        container.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # Installation directory selector
        ttk.Label(container, text="Installation Directory").grid(row=0, column=0, sticky="w")
        self.install_dir_var = tk.StringVar(value=str(Path.home() / "BCI-Flystick"))
        install_entry = ttk.Entry(container, textvariable=self.install_dir_var, width=60)
        install_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(container, text="Browse…", command=self.select_install_dir).grid(row=1, column=2, padx=(8, 0))

        # Repository URL (hidden in advanced toggle)
        ttk.Label(container, text="Repository URL").grid(row=2, column=0, sticky="w")
        self.repo_url_var = tk.StringVar(value=REPO_URL)
        ttk.Entry(container, textvariable=self.repo_url_var).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        # Board and serial port entries
        ttk.Label(container, text="Board ID (CYTON/CYTON_DAISY/GANGLION/SYNTHETIC)").grid(row=4, column=0, sticky="w")
        self.board_id_var = tk.StringVar(value="CYTON")
        ttk.Entry(container, textvariable=self.board_id_var).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(container, text="Serial Port (e.g. COM3 or /dev/ttyUSB0)").grid(row=6, column=0, sticky="w")
        self.serial_port_var = tk.StringVar(value="COM3")
        ttk.Entry(container, textvariable=self.serial_port_var).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(container, text="Channel Mapping (comma-separated label:index pairs)").grid(row=8, column=0, sticky="w")
        self.channels_var = tk.StringVar(value=DEFAULT_CHANNELS)
        ttk.Entry(container, textvariable=self.channels_var).grid(row=9, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        # Wizard checkbox and language
        wizard_frame = ttk.Frame(container)
        wizard_frame.grid(row=10, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.run_wizard_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(wizard_frame, text="Launch setup wizard after installation", variable=self.run_wizard_var).grid(row=0, column=0, sticky="w")
        ttk.Label(wizard_frame, text="Wizard language (en/zh)").grid(row=0, column=1, padx=(12, 4))
        self.wizard_lang_var = tk.StringVar(value="zh")
        ttk.Entry(wizard_frame, textvariable=self.wizard_lang_var, width=6).grid(row=0, column=2)

        # Log output
        ttk.Label(container, text="Progress").grid(row=11, column=0, sticky="w")
        self.log_text = tk.Text(container, height=15, state="disabled")
        self.log_text.grid(row=12, column=0, columnspan=3, sticky="nsew")
        container.rowconfigure(12, weight=1)

        # Action buttons
        button_frame = ttk.Frame(container)
        button_frame.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        button_frame.columnconfigure(0, weight=1)
        self.install_button = ttk.Button(button_frame, text="Start Installation", command=self.start_installation)
        self.install_button.grid(row=0, column=0, sticky="ew")
        self.wizard_button = ttk.Button(button_frame, text="Run Wizard Again", command=self.launch_wizard, state="disabled")
        self.wizard_button.grid(row=0, column=1, padx=(8, 0))

    def select_install_dir(self) -> None:
        directory = filedialog.askdirectory(title="Select installation directory")
        if directory:
            self.install_dir_var.set(directory)

    def collect_config(self) -> InstallerConfig:
        target_dir = Path(self.install_dir_var.get()).expanduser()
        board_id = self.board_id_var.get().strip().upper()
        serial_port = self.serial_port_var.get().strip()
        wizard_language = self.wizard_lang_var.get().strip() or "en"
        channels = parse_channel_mapping(self.channels_var.get())
        if not target_dir:
            raise ValueError("Please choose a valid installation directory")
        if not board_id:
            raise ValueError("Board ID cannot be empty")
        if not serial_port:
            raise ValueError("Serial port cannot be empty")
        return InstallerConfig(
            target_dir=target_dir,
            repo_url=self.repo_url_var.get().strip() or REPO_URL,
            board_id=board_id,
            serial_port=serial_port,
            channels=channels,
            run_wizard_after_install=self.run_wizard_var.get(),
            wizard_language=wizard_language,
        )

    def start_installation(self) -> None:
        try:
            config = self.collect_config()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self.install_button.configure(state="disabled")
        append_log(self.log_text, "Starting installation…")

        def worker() -> None:
            try:
                self.perform_installation(config)
            except Exception as exc:  # pragma: no cover - interactive path
                append_log(self.log_text, f"ERROR: {exc}")
                messagebox.showerror("Installation failed", str(exc))
            else:
                append_log(self.log_text, "Installation complete")
                self.wizard_button.configure(state="normal")
                if config.run_wizard_after_install:
                    self.launch_wizard(config)
            finally:
                self.install_button.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()

    def perform_installation(self, config: InstallerConfig) -> None:
        config.target_dir.mkdir(parents=True, exist_ok=True)
        repo_dir = config.target_dir / "BCI-Flystick"

        if repo_dir.exists():
            append_log(self.log_text, "Repository already exists, pulling latest changes…")
            run_command(["git", "pull"], cwd=repo_dir, log_widget=self.log_text)
        else:
            append_log(self.log_text, "Cloning repository…")
            run_command(["git", "clone", config.repo_url, str(repo_dir)], cwd=config.target_dir, log_widget=self.log_text)

        # Create or reuse the virtual environment
        venv_path = repo_dir / ".venv"
        python_exe = python_executable_from_venv(venv_path)
        if python_exe.exists():
            append_log(self.log_text, "Using existing virtual environment")
        else:
            append_log(self.log_text, "Creating virtual environment…")
            run_command([sys.executable, "-m", "venv", str(venv_path)], cwd=repo_dir, log_widget=self.log_text)

        # Install Python requirements
        append_log(self.log_text, "Installing Python dependencies…")
        run_command([str(python_exe), "-m", "pip", "install", "-r", "python/requirements.txt"], cwd=repo_dir, log_widget=self.log_text)

        # Generate channel_map.json
        channel_map_path = repo_dir / "config" / "channel_map.json"
        append_log(self.log_text, f"Writing {channel_map_path}")
        channel_map = {
            "serial_port": config.serial_port,
            "board_id": config.board_id,
            "channels": config.channels,
        }
        channel_map_path.write_text(json.dumps(channel_map, indent=2), encoding="utf-8")

    def launch_wizard(self, config: Optional[InstallerConfig] = None) -> None:
        if config is None:
            try:
                config = self.collect_config()
            except ValueError as exc:
                messagebox.showerror("Invalid input", str(exc))
                return

        repo_dir = config.target_dir / "BCI-Flystick"
        venv_path = repo_dir / ".venv"
        python_exe = python_executable_from_venv(venv_path)

        if not python_exe.exists():
            messagebox.showerror("Virtual environment missing", "Please run the installation first.")
            return

        append_log(self.log_text, "Launching guided setup wizard…")

        def worker() -> None:
            try:
                run_command(
                    [
                        str(python_exe),
                        "-m",
                        "python.main",
                        "--wizard",
                        "--wizard-language",
                        config.wizard_language,
                    ],
                    cwd=repo_dir,
                    log_widget=self.log_text,
                )
            except Exception as exc:  # pragma: no cover - interactive path
                append_log(self.log_text, f"Wizard exited with error: {exc}")

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    if shutil.which("git") is None:
        messagebox.showerror("Git not found", "Git is required for the installation. Please install Git and try again.")
        return

    root = tk.Tk()
    InstallerApp(root)
    root.geometry("720x600")
    root.mainloop()


if __name__ == "__main__":
    main()
