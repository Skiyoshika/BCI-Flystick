"""Simple Tkinter-based telemetry viewer for BCI Flystick."""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Dict, Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005


@dataclass
class TelemetrySample:
    timestamp: float
    payload: Dict[str, float | str]


class TelemetryReceiver(threading.Thread):
    """Background thread that listens for UDP telemetry packets."""

    def __init__(
        self,
        host: str,
        port: int,
        out_queue: "queue.Queue[TelemetrySample]",
        idle_timeout: float,
    ) -> None:
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._queue = out_queue
        self._idle_timeout = idle_timeout
        self._stop_event = threading.Event()
        self._socket: Optional[socket.socket] = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.settimeout(0.3)
        try:
            sock.bind((self._host, self._port))
        except OSError as exc:
            self._queue.put(
                TelemetrySample(
                    timestamp=time.time(),
                    payload={"__text__": f"Failed to bind {(self._host, self._port)}: {exc}"},
                )
            )
            sock.close()
            return

        self._socket = sock
        last_packet = 0.0
        while not self._stop_event.is_set():
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                if self._idle_timeout > 0 and last_packet:
                    if time.time() - last_packet > self._idle_timeout:
                        self._queue.put(
                            TelemetrySample(
                                timestamp=time.time(),
                                payload={"__text__": "Idle timeout reached."},
                            )
                        )
                        break
                continue
            except OSError:
                break

            try:
                payload = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            parsed: Dict[str, float | str] = {}
            for key in ("yaw", "altitude", "pitch", "throttle", "speed"):
                if key in payload:
                    try:
                        parsed[key] = float(payload[key])
                    except (TypeError, ValueError):
                        continue
            if "throttle" not in parsed and "speed" in parsed:
                parsed["throttle"] = parsed["speed"] * 2.0 - 1.0

            last_packet = time.time()
            self._queue.put(TelemetrySample(timestamp=last_packet, payload=parsed))

        try:
            sock.close()
        finally:
            self._socket = None


class TelemetryApp:
    def __init__(self, root: tk.Tk, host: str, port: int, idle_timeout: float) -> None:
        self.root = root
        self.queue: "queue.Queue[TelemetrySample]" = queue.Queue()
        self.receiver = TelemetryReceiver(host, port, self.queue, idle_timeout)
        self.receiver.start()

        self.root.title("BCI Flystick Telemetry")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_widgets()
        self.samples = 0
        self.last_update = 0.0
        self.status_var = tk.StringVar(value=f"Listening on {host}:{port}")
        self.status_label.configure(textvariable=self.status_var)

        self.root.after(100, self._poll_queue)

    def _build_widgets(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        axes = ["Yaw", "Altitude", "Pitch", "Throttle"]
        self.progress_vars: Dict[str, tk.DoubleVar] = {}
        self.value_labels: Dict[str, tk.StringVar] = {}

        for idx, label in enumerate(axes):
            ttk.Label(container, text=label, width=12).grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.DoubleVar(value=50.0)
            self.progress_vars[label.lower()] = var
            progress = ttk.Progressbar(container, orient="horizontal", length=280, maximum=100.0, variable=var)
            progress.grid(row=idx, column=1, sticky="ew", pady=4)
            value_var = tk.StringVar(value="+0.00")
            self.value_labels[label.lower()] = value_var
            ttk.Label(container, textvariable=value_var, width=8, anchor="e").grid(row=idx, column=2, padx=(8, 0))

        self.status_label = ttk.Label(container, text="", anchor="w")
        self.status_label.grid(row=len(axes), column=0, columnspan=3, sticky="ew", pady=(12, 0))

    def _poll_queue(self) -> None:
        try:
            while True:
                sample = self.queue.get_nowait()
                self._handle_sample(sample)
        except queue.Empty:
            pass

        if self.receiver.is_alive():
            if self.last_update:
                age = time.time() - self.last_update
                self.status_var.set(f"Samples: {self.samples} | Last packet: {age:.1f}s ago")
            self.root.after(100, self._poll_queue)
        else:
            if not self.status_var.get():
                self.status_var.set("Receiver stopped.")

    def _handle_sample(self, sample: TelemetrySample) -> None:
        if "__text__" in sample.payload:
            self.status_var.set(sample.payload["__text__"])
            return

        for axis in ("yaw", "altitude", "pitch", "throttle"):
            value = sample.payload.get(axis)
            if value is None:
                continue
            clipped = max(-1.0, min(1.0, float(value)))
            percent = (clipped + 1.0) * 50.0
            self.progress_vars[axis].set(percent)
            self.value_labels[axis].set(f"{clipped:+.2f}")

        self.samples += 1
        self.last_update = sample.timestamp

    def on_close(self) -> None:
        self.receiver.stop()
        self.root.destroy()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GUI telemetry viewer for BCI Flystick")
    parser.add_argument("--host", default=DEFAULT_HOST, help="UDP host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to bind (default: 5005)")
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=0.0,
        help="Automatically stop after this many seconds without packets (0 disables).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = tk.Tk()
    TelemetryApp(root, args.host, args.port, args.idle_timeout)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
