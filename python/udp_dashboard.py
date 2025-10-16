"""Terminal dashboard for visualising BCI joystick commands."""
from __future__ import annotations

import argparse
import json
import socket
import time
from collections import deque
from typing import Deque, Dict

from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005

console = Console()
if not console.is_terminal:
    console = Console(force_terminal=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualise BCI joystick UDP commands")
    parser.add_argument("--host", default=DEFAULT_HOST, help="UDP host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port to bind (default: 5005)")
    parser.add_argument("--history", type=int, default=120, help="Number of samples to keep in memory")
    return parser.parse_args(argv)


def normalise(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    span = hi - lo
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / span))


def render_bar(value: float, label: str, width: int = 24) -> Table:
    norm = normalise(value)
    filled = int(norm * width)
    empty = width - filled
    bar = "█" * filled + " " * empty
    table = Table.grid(expand=True)
    table.add_column(justify="left")
    table.add_column(justify="right", ratio=0)
    table.add_row(f"{label:<10} {value:+.2f}", f"|{bar}|")
    return table


def build_layout(latest: Dict[str, float], last_update: float, count: int) -> Panel:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_row(render_bar(latest.get("yaw", 0.0), "Yaw"))
    table.add_row(render_bar(latest.get("altitude", 0.0), "Altitude"))
    table.add_row(render_bar(latest.get("pitch", 0.0), "Pitch"))
    table.add_row(render_bar(latest.get("throttle", 0.0), "Throttle"))

    age = time.time() - last_update if last_update else float("inf")
    footer = f"Samples: {count} | Last packet: {age:.1f}s ago"
    return Panel(table, title="BCI-Flystick Telemetry", border_style="cyan", box=box.ROUNDED, subtitle=footer)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    addr = (args.host, args.port)
    console.print(f"[bold cyan]Listening for UDP packets on {addr}[/bold cyan]")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 0)
        except OSError:
            pass
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    try:
        sock.bind(addr)
    except OSError as exc:  # pragma: no cover - dependent on environment
        console.print(f"[bold red]Failed to bind {addr}: {exc}[/bold red]")
        return
    sock.settimeout(0.3)

    latest: Dict[str, float] = {"yaw": 0.0, "altitude": 0.0, "pitch": 0.0, "throttle": 0.0}
    history: Deque[Dict[str, float]] = deque(maxlen=max(1, args.history))
    last_update = 0.0
    received = 0

    with Live(build_layout(latest, last_update, received), console=console, refresh_per_second=12) as live:
        try:
            while True:
                try:
                    data, _ = sock.recvfrom(2048)
                except socket.timeout:
                    live.update(build_layout(latest, last_update, received))
                    continue

                try:
                    payload = json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                for key in ("yaw", "altitude", "pitch", "throttle"):
                    if key in payload:
                        latest[key] = float(payload[key])
                if "throttle" not in payload and "speed" in payload:
                    latest["throttle"] = float(payload["speed"]) * 2.0 - 1.0
                last_update = time.time()
                received += 1
                history.append(dict(latest))
                live.update(build_layout(latest, last_update, received))
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Stopping dashboard...[/bold yellow]")
        finally:
            sock.close()
            console.print("[green]Socket closed.[/green]")


if __name__ == "__main__":
    main()
