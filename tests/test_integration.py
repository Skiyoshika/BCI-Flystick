from __future__ import annotations

import json
import queue
import socket
import sys
import threading
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from mock_command_gui import CommandSender  # type: ignore


def _reserve_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()
    return int(port)


def _start_udp_receiver(port: int, output: queue.Queue[Dict[str, float]]) -> threading.Thread:
    ready = threading.Event()

    def _receiver() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", port))
        ready.set()
        try:
            data, _ = sock.recvfrom(4096)
        finally:
            sock.close()
        payload = json.loads(data.decode("utf-8"))
        output.put(payload)

    thread = threading.Thread(target=_receiver, daemon=True)
    thread.start()
    if not ready.wait(timeout=1):
        raise RuntimeError("UDP receiver did not become ready in time")
    return thread


def test_mock_gui_udp_flow() -> None:
    port = _reserve_udp_port()
    received: queue.Queue[Dict[str, float]] = queue.Queue()
    receiver_thread = _start_udp_receiver(port, received)

    axis_signs = {"yaw": -1.0, "altitude": 1.0, "pitch": 1.0, "throttle": 1.0}
    sender = CommandSender("127.0.0.1", port, axis_signs=axis_signs)
    sample_axes = {"yaw": 0.8, "altitude": 0.25, "pitch": -0.4, "throttle": 1.5}
    payload = sender.send(sample_axes)
    sender.socket.close()

    forwarded = received.get(timeout=2)
    receiver_thread.join(timeout=1)

    assert forwarded["yaw"] == payload["yaw"] == -0.8
    assert forwarded["altitude"] == payload["altitude"] == 0.25
    assert forwarded["pitch"] == payload["pitch"] == -0.4
    assert forwarded["throttle"] == payload["throttle"] == 1.0
    assert forwarded["speed"] == payload["speed"] == 1.0
    assert "ts" in forwarded and isinstance(forwarded["ts"], float)
