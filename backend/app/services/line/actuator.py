"""Rejection signal interface.

SimulatedActuator is what the demonstration uses: it only records events and never moves anything.
SerialActuator speaks the protocol in firmware/reject_controller; WebhookActuator posts to a PLC
gateway. Serial and webhook back ends have been tested against fakes only, not physical hardware.
"""
import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


def latency_budget(belt_speed_mm_s: float, camera_to_diverter_mm: float, pitch_mm: float,
                   actuator_ms: float = 30.0) -> Dict[str, Any]:
    """Time available per unit, and the delay to wait before firing the diverter."""
    if belt_speed_mm_s <= 0:
        raise ValueError("belt_speed_mm_s must be positive")
    travel_ms = camera_to_diverter_mm / belt_speed_mm_s * 1000.0
    return {
        "belt_speed_mm_s": belt_speed_mm_s,
        "units_per_minute": round(belt_speed_mm_s / pitch_mm * 60.0, 1) if pitch_mm else None,
        "time_per_unit_ms": round(pitch_mm / belt_speed_mm_s * 1000.0, 1) if pitch_mm else None,
        "travel_to_diverter_ms": round(travel_ms, 1),
        "max_decision_latency_ms": round(travel_ms - actuator_ms, 1),
    }


def fire_delay_ms(belt_speed_mm_s: float, camera_to_diverter_mm: float, elapsed_ms: float, actuator_ms: float = 30.0) -> Optional[float]:
    """Delay still to wait after inference. None means the unit already passed the diverter."""
    remaining = camera_to_diverter_mm / belt_speed_mm_s * 1000.0 - elapsed_ms - actuator_ms
    return None if remaining < 0 else remaining


@dataclass
class RejectCommand:
    unit_code: str
    fire_after_ms: float
    reason: str


class SimulatedActuator:
    """Records when a real diverter would fire. It is labelled SIMULATED in every record."""
    kind = "SIMULATED"

    def __init__(self, sleep: Callable[[float], None] = time.sleep):
        self.events: List[Dict[str, Any]] = []
        self._sleep = sleep

    def fire(self, command: RejectCommand) -> Dict[str, Any]:
        event = {"unit_code": command.unit_code, "fire_after_ms": round(command.fire_after_ms, 1),
                 "actuator": self.kind, "status": "SIMULATED_FIRED", "reason": command.reason, "at": time.time()}
        self.events.append(event)
        return event


class SerialActuator:
    """Line protocol: `R,<unit>,<delay_ms>\\n`; the controller answers `A,<unit>\\n`."""
    kind = "SERIAL"

    def __init__(self, port: str, baud: int = 115200, serial_factory: Optional[Callable[..., Any]] = None, timeout: float = 0.2):
        if serial_factory is None:
            import serial  # optional dependency, only needed with real hardware
            serial_factory = serial.Serial
        self._link = serial_factory(port, baud, timeout=timeout)
        self._lock = threading.Lock()

    def fire(self, command: RejectCommand) -> Dict[str, Any]:
        line = f"R,{command.unit_code},{int(command.fire_after_ms)}\n".encode()
        with self._lock:
            self._link.write(line)
            reply = self._link.readline().decode(errors="ignore").strip()
        acknowledged = reply == f"A,{command.unit_code}"
        return {"unit_code": command.unit_code, "fire_after_ms": round(command.fire_after_ms, 1),
                "actuator": self.kind, "status": "ACKNOWLEDGED" if acknowledged else "NO_ACK",
                "reason": command.reason, "at": time.time()}


class WebhookActuator:
    kind = "WEBHOOK"

    def __init__(self, url: str, opener: Callable[..., Any] = urllib.request.urlopen):
        if not url.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must be http(s)")
        self.url, self._open = url, opener

    def fire(self, command: RejectCommand) -> Dict[str, Any]:
        body = json.dumps({"unit": command.unit_code, "delay_ms": command.fire_after_ms, "reason": command.reason}).encode()
        request = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
        try:
            with self._open(request, timeout=1) as res:
                status = "ACKNOWLEDGED" if 200 <= res.status < 300 else "NO_ACK"
        except OSError:
            status = "NO_ACK"
        return {"unit_code": command.unit_code, "fire_after_ms": round(command.fire_after_ms, 1),
                "actuator": self.kind, "status": status, "reason": command.reason, "at": time.time()}


def build_actuator(kind: str, target: str = "") -> Any:
    kind = (kind or "SIMULATED").upper()
    if kind == "SERIAL":
        return SerialActuator(target)
    if kind == "WEBHOOK":
        return WebhookActuator(target)
    return SimulatedActuator()
