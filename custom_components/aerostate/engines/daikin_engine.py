"""Protocol-driven Daikin state engine that outputs Broadlink base64 payloads."""

from __future__ import annotations

import base64
import hashlib
import logging

from .base import StateEngine

_LOGGER = logging.getLogger(__name__)


class DaikinEngine(StateEngine):
    """Generate complete Daikin IR state frames without learned button payloads."""

    _FRAME_LENGTH = 35
    _HEADER_BITS = 5
    _HDR_MARK = 3650
    _HDR_SPACE = 1623
    _BIT_MARK = 428
    _SPACE0 = 428
    _SPACE1 = 1280
    _GAP = 29000
    _SECTION_LENGTHS = (8, 8, 19)

    _MODE_MAP = {
        "auto": 0b000,
        "dry": 0b010,
        "cool": 0b011,
        "heat": 0b100,
        "fan": 0b110,
        "fan_only": 0b110,
    }
    _MODE_DEFAULT_TEMPS = {
        "auto": 25,
        "dry": 25,
        "fan": 25,
        "fan_only": 25,
        "cool": 24,
        "heat": 23,
    }
    _FAN_MAP = {
        "f1": 0x03,
        "f2": 0x04,
        "f3": 0x05,
        "f4": 0x06,
        "f5": 0x07,
        "auto": 0x0A,
        "quiet": 0x0B,
    }
    _FAN_ALIASES = {
        "lowest": "f1",
        "low": "f2",
        "mid": "f3",
        "medium": "f3",
        "high": "f4",
        "highest": "f5",
        "silent": "quiet",
    }
    _SWING_OFF = 0x00
    _SWING_ON = 0x0F
    _VERTICAL_SWING_MODES = ["off", "auto", "position_low", "position_mid", "position_high"]
    _HORIZONTAL_SWING_MODES = ["off", "auto", "left", "center", "right"]
    _LEGACY_SWING_ALIASES = {
        "on": "auto",
        "swing": "auto",
    }

    def __init__(self, pack: object) -> None:
        self._pack = pack

    def supported_vertical_swing_modes(self) -> list[str]:
        return list(self._VERTICAL_SWING_MODES)

    def supported_horizontal_swing_modes(self) -> list[str]:
        return list(self._HORIZONTAL_SWING_MODES)

    def supported_preset_modes(self) -> list[str]:
        return []

    def resolve_command(self, state: dict) -> str:
        _LOGGER.debug("DaikinEngine input state_dict=%s", state)

        power = not (state.get("power") is False or state.get("hvac_mode") == "off")
        mode = self._normalize_hvac_mode("cool" if not power else state.get("hvac_mode"))
        fan_mode = self._normalize_fan_mode(state.get("fan_mode"))
        target_temperature = self._normalize_temperature(
            state.get("target_temperature"),
            default=self._MODE_DEFAULT_TEMPS.get(mode, 24),
        )
        swing_vertical = self._normalize_swing_mode(state.get("swing_vertical"), "vertical")
        swing_horizontal = self._normalize_swing_mode(state.get("swing_horizontal"), "horizontal")

        frame = self._build_frame(
            power=power,
            mode=mode,
            target_temperature=target_temperature,
            fan_mode=fan_mode,
            swing_vertical=swing_vertical,
            swing_horizontal=swing_horizontal,
        )
        payload = self._pulses_to_broadlink_b64(self._frame_to_pulses(frame))
        payload_hash = hashlib.sha256(payload.encode("ascii")).hexdigest()[:12]
        _LOGGER.debug(
            "DaikinEngine normalized power=%s mode=%s fan=%s target=%s swing_v=%s swing_h=%s payload_hash=%s",
            power,
            mode,
            fan_mode,
            target_temperature,
            swing_vertical,
            swing_horizontal,
            payload_hash,
        )
        return payload

    def _normalize_hvac_mode(self, raw_mode: object) -> str:
        mode = str(raw_mode or "cool").lower()
        if mode == "fan_only":
            return "fan"
        if mode not in self._MODE_MAP:
            raise ValueError(f"Unsupported Daikin protocol hvac mode: {mode}")
        return mode

    def _normalize_fan_mode(self, raw_fan: object) -> str:
        if not raw_fan:
            return "auto"
        fan = str(raw_fan).lower()
        fan = self._FAN_ALIASES.get(fan, fan)
        if fan not in self._FAN_MAP:
            raise ValueError(
                f"Unsupported Daikin protocol fan mode '{fan}'. Supported: {sorted(self._FAN_MAP)}"
            )
        return fan

    def _normalize_temperature(self, raw_temperature: object, *, default: int) -> int:
        try:
            target = int(round(float(raw_temperature)))
        except (TypeError, ValueError):
            target = default

        min_temp = int(getattr(self._pack, "min_temperature", 10))
        max_temp = int(getattr(self._pack, "max_temperature", 32))
        if target < min_temp or target > max_temp:
            raise ValueError(
                f"Unsupported Daikin protocol temperature {target}. Supported range: {min_temp}-{max_temp}"
            )
        return target

    def _build_frame(
        self,
        *,
        power: bool,
        mode: str,
        target_temperature: int,
        fan_mode: str,
        swing_vertical: str,
        swing_horizontal: str,
    ) -> list[int]:
        frame = [
            0x11,
            0xDA,
            0x27,
            0x00,
            0xC5,
            0x00,
            0x00,
            0x00,
            0x11,
            0xDA,
            0x27,
            0x00,
            0x42,
            0x00,
            0x00,
            0x00,
            0x11,
            0xDA,
            0x27,
            0x00,
            0x00,
            0x08,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x06,
            0x60,
            0x00,
            0x00,
            0xC0,
            0x00,
            0x00,
            0x00,
        ]

        mode_code = self._MODE_MAP[mode]
        fan_code = self._FAN_MAP[fan_mode]
        swing_vertical_code = self._swing_protocol_code(
            swing_vertical,
            axis="vertical",
        )
        swing_horizontal_code = self._swing_protocol_code(
            swing_horizontal,
            axis="horizontal",
        )
        frame[21] = (0x01 if power else 0x00) | 0x08 | ((mode_code & 0x07) << 4)
        frame[22] = target_temperature * 2
        frame[24] = (fan_code << 4) | swing_vertical_code
        frame[25] = swing_horizontal_code
        self._checksum(frame, profile=self._checksum_profile())
        return frame

    def _normalize_swing_mode(self, raw_swing: object, axis: str) -> str:
        swing = str(raw_swing or "off").lower()
        swing = self._LEGACY_SWING_ALIASES.get(swing, swing)
        supported = (
            self._VERTICAL_SWING_MODES if axis == "vertical" else self._HORIZONTAL_SWING_MODES
        )
        if swing not in supported:
            raise ValueError(
                f"Unsupported Daikin protocol {axis} swing mode '{swing}'. Supported: {supported}"
            )
        return swing

    def _swing_protocol_code(self, swing: str, *, axis: str) -> int:
        features = self._protocol_features()
        map_key = f"swing_{axis}_protocol_values"
        raw_map = features.get(map_key, {}) if isinstance(features, dict) else {}
        if isinstance(raw_map, dict):
            configured = raw_map.get(swing)
            if isinstance(configured, int) and 0 <= configured <= 0x0F:
                return configured

        # Most Daikin profiles expose richer UI positions than this base frame
        # can safely distinguish. Keep the API expressive, while falling back
        # to the proven protocol-safe off/auto swing bit.
        return self._SWING_OFF if swing == "off" else self._SWING_ON

    def _protocol_features(self) -> dict:
        commands = getattr(self._pack, "commands", {})
        features = commands.get("protocol_features", {}) if isinstance(commands, dict) else {}
        return features if isinstance(features, dict) else {}

    def _checksum_profile(self) -> str:
        features = self._protocol_features()
        profile = features.get("checksum_profile", "v1")
        return str(profile or "v1")

    def _checksum(self, frame: list[int], profile: str = "v1") -> None:
        if len(frame) != self._FRAME_LENGTH:
            raise ValueError(
                f"Daikin checksum requires {self._FRAME_LENGTH} bytes, got {len(frame)}"
            )
        if profile != "v1":
            raise ValueError(f"Unsupported Daikin checksum profile: {profile}")
        self._checksum_v1(frame)

    @staticmethod
    def _checksum_v1(frame: list[int]) -> None:
        frame[7] = sum(frame[:7]) & 0xFF
        frame[15] = sum(frame[8:15]) & 0xFF
        frame[34] = sum(frame[16:34]) & 0xFF

    def _frame_to_pulses(self, frame: list[int]) -> list[int]:
        if len(frame) != self._FRAME_LENGTH:
            raise ValueError(
                f"Daikin frame requires {self._FRAME_LENGTH} bytes, got {len(frame)}"
            )
        pulses: list[int] = []

        # Daikin sends a five-bit zero leader before the three state sections.
        for _ in range(self._HEADER_BITS):
            pulses.extend([self._BIT_MARK, self._SPACE0])
        pulses[-1] += self._GAP

        offset = 0
        for section_length in self._SECTION_LENGTHS:
            section = frame[offset : offset + section_length]
            pulses.extend([self._HDR_MARK, self._HDR_SPACE])
            for byte in section:
                for bit in range(8):
                    pulses.append(self._BIT_MARK)
                    pulses.append(self._SPACE1 if (byte >> bit) & 1 else self._SPACE0)
            pulses.append(self._BIT_MARK)
            pulses.append(self._SPACE0 + self._GAP)
            offset += section_length

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
