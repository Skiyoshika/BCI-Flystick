"""Interactive GUI to emit mock EEG-derived joystick commands."""
from __future__ import annotations

import argparse
import json
import socket
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Dict, Iterable

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005
@dataclass
class Action:
    name: str
    label: str
    axis: str
    direction: float
    binding: str | None = None

    def payload(self) -> Dict[str, float]:
        value = 1.0 if self.direction >= 0 else -1.0
        axes = {"yaw": 0.0, "altitude": 0.0, "pitch": 0.0, "throttle": 0.0}
        axes[self.axis] = value
        if self.axis == "throttle":
            axes.setdefault("speed", (value + 1.0) * 0.5)
        return axes


def load_calibration(path: Path | None) -> tuple[Dict[str, float], Dict[str, Action]]:
    axis_signs = {"yaw": 1.0, "altitude": 1.0, "pitch": 1.0, "throttle": 1.0}
    actions: Dict[str, Action] = {}
    if not path:
        return axis_signs, actions
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return axis_signs, actions
    except json.JSONDecodeError:
        return axis_signs, actions

    if isinstance(data, dict):
        axis_data = data.get("axis_signs")
        if isinstance(axis_data, dict):
            for key, value in axis_data.items():
                if key in axis_signs and isinstance(value, (int, float)):
                    axis_signs[key] = 1.0 if value >= 0 else -1.0
        action_items = data.get("actions")
        if isinstance(action_items, list):
            for item in action_items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                label = item.get("label") or name
                axis = item.get("axis")
                direction = item.get("direction", 1.0)
                binding = item.get("binding")
                if (
                    isinstance(name, str)
                    and isinstance(axis, str)
                    and axis in axis_signs
                    and isinstance(direction, (int, float))
                ):
                    actions[name] = Action(
                        name=name,
                        label=str(label),
                        axis=axis,
                        direction=float(direction),
                        binding=str(binding) if isinstance(binding, str) else None,
                    )
    return axis_signs, actions


class CommandSender:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        axis_signs: Dict[str, float],
        echo: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.axis_signs = axis_signs
        self.echo = echo
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, axes: Dict[str, float]) -> Dict[str, float]:
        payload = {"ts": time.time()}
        for axis in ("yaw", "altitude", "pitch", "throttle"):
            value = float(axes.get(axis, 0.0))
            payload[axis] = max(-1.0, min(1.0, value * self.axis_signs.get(axis, 1.0)))
        payload["speed"] = (payload["throttle"] + 1.0) * 0.5
        message = json.dumps(payload)
        self.socket.sendto(message.encode("utf-8"), (self.host, self.port))
        if self.echo:
            print(f"Sent UDP payload: {message}")
        return payload


class MockEEGGui:
    def __init__(
        self,
        root: tk.Tk,
        sender: CommandSender,
        actions: Iterable[Action],
    ) -> None:
        self.root = root
        self.sender = sender
        action_sequence = list(actions)
        self.actions: Dict[str, Action] = {action.name: action for action in action_sequence}
        self._ordered_actions = action_sequence
        self._build_ui()
        self._bind_keys()
        self.last_label = tk.StringVar(
            value=self._format_status(
                "Neutral",
                {axis: 0.0 for axis in ("yaw", "altitude", "pitch", "throttle")},
            )
        )
        self.status.configure(textvariable=self.last_label)

    def _build_ui(self) -> None:
        self.root.title("BCI Flystick Mock EEG Console")
        container = ttk.Frame(self.root, padding=16)
        container.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        ttk.Label(container, text="Select an action to emit a command").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Button(container, text="Neutral", command=self._send_neutral).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=4
        )

        row = 2
        for action in self._ordered_actions:
            text = action.label
            if action.binding:
                text = f"{text} ({action.binding})"
            button = ttk.Button(container, text=text, command=lambda a=action: self._trigger(a))
            button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
            row += 1

        self.status = ttk.Label(container, text="", anchor="w")
        self.status.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def _bind_keys(self) -> None:
        self.root.bind("<KeyPress>", self._on_key)

    def _on_key(self, event: tk.Event[tk.KeyPressEvent]) -> None:
        key = event.keysym.upper()
        for action in self._ordered_actions:
            if action.binding and action.binding.upper() == key:
                self._trigger(action)
                return
        if key in {"SPACE", "0"}:
            self._send_neutral()

    def _trigger(self, action: Action) -> None:
        payload = self.sender.send(action.payload())
        self.last_label.set(self._format_status(action.label, payload))

    def _send_neutral(self) -> None:
        payload = self.sender.send({})
        self.last_label.set(self._format_status("Neutral", payload))

    @staticmethod
    def _format_status(label: str, payload: Dict[str, float]) -> str:
        axes = []
        for axis in ("yaw", "altitude", "pitch", "throttle"):
            value = float(payload.get(axis, 0.0))
            axes.append(f"{axis.title()}: {value:+.2f}")
        return f"Sent: {label} | " + "  ".join(axes)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock EEG joystick GUI")
    parser.add_argument("--host", default=DEFAULT_HOST, help="UDP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port (default: 5005)")
    parser.add_argument("--calibration", help="Optional calibration profile JSON path")
    parser.add_argument(
        "--echo",
        action="store_true",
        help="Print every UDP payload to the console for debugging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    calibration_path = Path(args.calibration).expanduser() if args.calibration else None
    axis_signs, actions = load_calibration(calibration_path)
    if not actions:
        defaults = {
            "accelerate": ("Accelerate", "throttle", 1.0, "W"),
            "decelerate": ("Decelerate", "throttle", -1.0, "S"),
            "turn_left": ("Turn Left", "yaw", -1.0, "A"),
            "turn_right": ("Turn Right", "yaw", 1.0, "D"),
            "climb": ("Climb", "altitude", 1.0, "Q"),
            "descend": ("Descend", "altitude", -1.0, "E"),
            "pitch_up": ("Pitch Up", "pitch", 1.0, "I"),
            "pitch_down": ("Pitch Down", "pitch", -1.0, "K"),
        }
        for name, (label, axis, direction, binding) in defaults.items():
            actions[name] = Action(
                name=name, label=label, axis=axis, direction=direction, binding=binding
            )

    sender = CommandSender(args.host, args.port, axis_signs=axis_signs, echo=args.echo)
    root = tk.Tk()
    app = MockEEGGui(root, sender, actions.values())
    try:
        root.mainloop()
    finally:
        sender.socket.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
