"""Interactive GUI to emit mock EEG-derived joystick commands."""
from __future__ import annotations

import argparse
import json
import socket
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Dict, Iterable, List

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


@dataclass(slots=True)
class SmoothAxisState:
    value: float = 0.0
    target: float = 0.0

    def reset(self) -> None:
        self.value = 0.0
        self.target = 0.0

    def hold(self) -> None:
        """Freeze the target at the current value to avoid automatic rollback."""
        self.target = self.value

    def step(self, rate_per_sec: float, dt: float) -> bool:
        diff = self.target - self.value
        if abs(diff) <= 1e-6:
            return False
        step = min(abs(diff), rate_per_sec * dt)
        if step <= 0:
            return False
        direction = 1.0 if diff > 0 else -1.0
        new_value = self.value + step * direction
        new_value = max(-1.0, min(1.0, new_value))
        changed = abs(new_value - self.value) > 1e-6
        self.value = new_value
        return changed


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
        self._axes = ("yaw", "altitude", "pitch", "throttle")
        self._build_ui()
        self._binding_map: Dict[str, Action] = {}
        for action in self._ordered_actions:
            if action.binding:
                self._binding_map[action.binding.upper()] = action
        self._bind_keys()
        self.last_label = tk.StringVar(
            value=self._format_status(
                "Neutral",
                {axis: 0.0 for axis in self._axes},
            )
        )
        self.status.configure(textvariable=self.last_label)
        self._axis_states: Dict[str, SmoothAxisState] = {
            axis: SmoothAxisState() for axis in self._axes
        }
        self._axis_action_stack: Dict[str, List[Action]] = {axis: [] for axis in self._axes}
        self._pressed_keys: set[str] = set()
        self._current_label = "Neutral"
        self._sample_history: deque[Dict[str, float]] = deque()
        self._sample_counter = 0
        self._update_interval_ms = 50
        self._schedule_next_tick()

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
            button = ttk.Button(container, text=text)
            button.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
            button.bind("<ButtonPress-1>", lambda _event, a=action: self._on_action_press(a))
            button.bind("<ButtonRelease-1>", lambda _event, a=action: self._on_action_release(a))
            row += 1

        self._sensitivity_var = tk.IntVar(value=5)
        self._sensitivity_label = tk.StringVar()
        self._update_sensitivity_label()
        ttk.Label(container, text="Sensitivity").grid(row=row, column=0, sticky="w", pady=(12, 0))
        scale = tk.Scale(
            container,
            from_=1,
            to=10,
            orient="horizontal",
            variable=self._sensitivity_var,
            resolution=1,
            showvalue=False,
            command=lambda _value: self._update_sensitivity_label(),
        )
        scale.grid(row=row, column=1, sticky="ew", pady=(12, 0))
        row += 1
        ttk.Label(container, textvariable=self._sensitivity_label, anchor="e").grid(
            row=row, column=0, columnspan=2, sticky="ew"
        )
        row += 1

        self.status = ttk.Label(container, text="", anchor="w")
        self.status.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def _bind_keys(self) -> None:
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)

    def _on_key_press(self, event: tk.Event[tk.KeyPressEvent]) -> None:
        key = event.keysym.upper()
        if key in self._pressed_keys:
            return
        self._pressed_keys.add(key)
        action = self._binding_map.get(key)
        if action:
            self._on_action_press(action)
            return
        if key in {"SPACE", "0"}:
            self._send_neutral()

    def _on_key_release(self, event: tk.Event[tk.KeyPressEvent]) -> None:
        key = event.keysym.upper()
        self._pressed_keys.discard(key)
        action = self._binding_map.get(key)
        if action:
            self._on_action_release(action)

    def _on_action_press(self, action: Action) -> None:
        stack = self._axis_action_stack[action.axis]
        if action not in stack:
            stack.append(action)
        active = stack[-1]
        self._axis_states[action.axis].target = 1.0 if active.direction >= 0 else -1.0
        self._current_label = active.label

    def _on_action_release(self, action: Action) -> None:
        stack = self._axis_action_stack[action.axis]
        if action in stack:
            stack.remove(action)
        if stack:
            active = stack[-1]
            self._axis_states[action.axis].target = 1.0 if active.direction >= 0 else -1.0
            self._current_label = active.label
        else:
            state = self._axis_states[action.axis]
            state.hold()

    def _send_neutral(self) -> None:
        self._pressed_keys.clear()
        for axis in self._axes:
            self._axis_action_stack[axis].clear()
            state = self._axis_states[axis]
            state.reset()
        self._current_label = "Neutral"
        payload = self.sender.send({axis: 0.0 for axis in self._axes})
        self._record_sample(payload)
        self.last_label.set(self._format_status("Neutral", payload))

    @staticmethod
    def _format_status(label: str, payload: Dict[str, float]) -> str:
        axes = []
        for axis in ("yaw", "altitude", "pitch", "throttle"):
            value = float(payload.get(axis, 0.0))
            axes.append(f"{axis.title()}: {value:+.2f}")
        return f"Sent: {label} | " + "  ".join(axes)

    def _schedule_next_tick(self) -> None:
        self.root.after(self._update_interval_ms, self._tick)

    def _tick(self) -> None:
        dt = self._update_interval_ms / 1000.0
        sensitivity = max(1, int(self._sensitivity_var.get()))
        rate = 0.05 * sensitivity
        changed = False
        for axis, state in self._axis_states.items():
            changed = state.step(rate, dt) or changed
        if changed:
            payload = self.sender.send({axis: state.value for axis, state in self._axis_states.items()})
            self._record_sample(payload)
            self.last_label.set(self._format_status(self._current_label, payload))
        self._schedule_next_tick()

    def _record_sample(self, payload: Dict[str, float]) -> None:
        self._sample_history.append(payload)
        self._sample_counter += 1
        if self._sample_counter >= 100:
            self._sample_history.clear()
            self._sample_counter = 0

    def _update_sensitivity_label(self) -> None:
        value = max(1, int(self._sensitivity_var.get()))
        self._sensitivity_label.set(f"Current level: {value}")


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
