# Hardware Interface

**Status: no physical conveyor, diverter, Arduino or ESP32 has been connected.** The demonstration uses `SimulatedActuator`, which records when a diverter would fire and moves nothing. Serial and webhook back ends are tested against fakes only. `firmware/reject_controller/reject_controller.ino` has not been compiled or flashed.

## Signal path

```
Camera ─▶ tracker ─▶ trigger line ─▶ inference + decision ─▶ RejectCommand(unit, delay_ms) ─▶ actuator ─▶ diverter
```

Delay: `camera_to_diverter_mm / belt_speed_mm_s − elapsed − actuator_ms`.
If the delay is negative the part has already passed. The event is logged as `MISSED_WINDOW`, so an escaped part is visible rather than silent.

Per-line settings live in `production_lines`: belt speed, camera-to-diverter distance, pitch, actuator kind, actuator target.

## Serial protocol (115200 baud)

| Direction | Line | Meaning |
|---|---|---|
| Host → controller | `R,<unit_code>,<delay_ms>\n` | Fire the diverter after the delay |
| Controller → host | `A,<unit_code>\n` | Accepted |
| none | | Recorded as `NO_ACK` |

## Webhook

`POST <target>` with `{"unit": "...", "delay_ms": 123.0, "reason": "..."}`. A 2xx reply counts as acknowledged. Use this for a PLC gateway.

## To connect real hardware

1. `pip install pyserial` on the edge node.
2. Flash the sketch and wire pin 9 through a relay or driver board. Do not drive a solenoid or servo directly from the pin.
3. Set the line's `actuator_kind` to `SERIAL` and `actuator_target` to the port, e.g. `/dev/ttyUSB0`.
4. Measure belt speed and camera-to-diverter distance, then verify timing with a marked part before running product.

Unverified assumptions: USB serial latency, actuator response of 30 ms, constant belt speed. A real diverter also needs a safety interlock outside this software.
