"""Protocol-driven LG state engine that outputs Broadlink base64 payloads."""

from __future__ import annotations

import base64
import logging

from .base import StateEngine

_LOGGER: logging.Logger = logging.getLogger(__name__)


class LGProtocolEngine(StateEngine):
    """Generate LG IR commands from state without learned matrix payloads."""

    _START = [3200, 9850]
    _END = [520, 12000]
    _MARK = 520
    _SPACE0 = 520
    _SPACE1 = 1530

    _MODE_MAP = {
        "auto": 0x03,
        "cool": 0x00,
        "dry": 0x01,
        "fan": 0x02,
        "fan_only": 0x02,
        "heat": 0x04,
    }
    _FAN_MAP = {
        "lowest": 0x00,
        "low": 0x09,
        "mid": 0x02,
        "medium": 0x02,
        "high": 0x0A,
        "highest": 0x04,
        "auto": 0x05,
    }

    def __init__(self, pack: object) -> None:
        self._pack = pack
        self._last_mode = "off"
        self._last_swing_vertical = "off"
        self._last_swing_horizontal = "off"

    def _normalize_hvac_mode(self, raw_mode: str) -> str:
        mode = str(raw_mode or "cool")
        if mode == "fan_only":
            return "fan"
        return mode

    def _normalize_fan_mode(self, raw_fan: str | None) -> str:
        if not raw_fan:
            return "auto"
        fan = str(raw_fan).lower()
        return fan if fan in self._FAN_MAP else "auto"

    def _normalize_swing_mode(self, raw_swing: str | None) -> str:
        if not raw_swing:
            return "off"
        swing = str(raw_swing).lower()
        if swing in {"on", "swing", "auto"}:
            return "on"
        return "off"

    def _crc_nibble(self, frame3: list[int]) -> int:
        crc = 0
        for value in frame3:
            crc += (value & 0xF0) >> 4
            crc += value & 0x0F
        return crc & 0x0F

    def _encode_bits_from_frame(self, frame3: list[int]) -> list[int]:
        crc = self._crc_nibble(frame3)
        bits: list[int] = []
        for value in frame3:
            for mask in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
                bits.append(1 if value & mask else 0)
        for mask in (0x08, 0x04, 0x02, 0x01):
            bits.append(1 if crc & mask else 0)
        return bits

    def _frame_to_pulses(self, frame3: list[int]) -> list[int]:
        pulses = list(self._START)
        for bit in self._encode_bits_from_frame(frame3):
            pulses.append(self._MARK)
            pulses.append(self._SPACE1 if bit else self._SPACE0)
        pulses.extend(self._END)
        return pulses

    def _pulses_to_broadlink_b64(self, pulses: list[int]) -> str:
        units: list[int] = []
        for duration_us in pulses:
            units.append(max(1, int(round(duration_us * 269 / 8192))))

        body = bytearray()
        for unit in units:
            if unit < 256:
                body.append(unit)
            else:
                body.extend((0x00, (unit >> 8) & 0xFF, unit & 0xFF))

        packet = bytearray((0x26, 0x00, len(body) & 0xFF, (len(body) >> 8) & 0xFF))
        packet.extend(body)
        packet.extend((0x0D, 0x05))
        return base64.b64encode(packet).decode("ascii")

    def _build_main_frame(self, mode: str, target_temperature: int, fan_mode: str) -> list[int]:
        mode_code = self._MODE_MAP.get(mode)
        if mode_code is None:
            raise ValueError(f"Unsupported LG protocol hvac mode: {mode}")

        if mode == "auto":
            fan_mode = "auto"
        fan_code = self._FAN_MAP.get(fan_mode, self._FAN_MAP["auto"])

        bounded = max(int(getattr(self._pack, "min_temperature", 16)), min(int(target_temperature), int(getattr(self._pack, "max_temperature", 30))))
        temp_code = (bounded - 15) << 4

        addit = 0x08 if self._last_mode != "off" else 0x00
        return [0x88, mode_code + addit, temp_code | fan_code]

    def resolve_command(self, state: dict) -> str:
        _LOGGER.debug("LGProtocolEngine input state_dict=%s", state)

        power = state.get("power")
        if power is False or state.get("hvac_mode") == "off":
            self._last_mode = "off"
            off_frame = [0x88, 0xC0, 0x05]
            _LOGGER.debug("LGProtocolEngine emitted frames=off_only frame_count=1")
            return self._pulses_to_broadlink_b64(self._frame_to_pulses(off_frame))

        mode = self._normalize_hvac_mode(str(state.get("hvac_mode", "cool")))
        fan_mode = self._normalize_fan_mode(state.get("fan_mode"))
        target_temperature = int(round(float(state.get("target_temperature", getattr(self._pack, "min_temperature", 24)))))

        vertical = self._normalize_swing_mode(state.get("swing_vertical"))
        horizontal = self._normalize_swing_mode(state.get("swing_horizontal"))

        frames: list[list[int]] = [
            self._build_main_frame(mode=mode, target_temperature=target_temperature, fan_mode=fan_mode)
        ]
        emitted = ["main"]

        if vertical != self._last_swing_vertical:
            frames.append([0x88, 0x13, 0x14 if vertical == "on" else 0x15])
            self._last_swing_vertical = vertical
            emitted.append("swing_vertical")

        if horizontal != self._last_swing_horizontal:
            frames.append([0x88, 0x13, 0x16 if horizontal == "on" else 0x17])
            self._last_swing_horizontal = horizontal
            emitted.append("swing_horizontal")

        self._last_mode = mode

        pulses: list[int] = []
        for frame in frames:
            pulses.extend(self._frame_to_pulses(frame))

        _LOGGER.debug(
            "LGProtocolEngine emitted frames=%s frame_count=%s mode=%s fan=%s target=%s swing_v=%s swing_h=%s",
            "+".join(emitted),
            len(frames),
            mode,
            fan_mode,
            target_temperature,
            vertical,
            horizontal,
        )

        return self._pulses_to_broadlink_b64(pulses)
