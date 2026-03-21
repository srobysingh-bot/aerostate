"""Protocol-driven LG state engine that outputs Broadlink base64 payloads."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

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
        "auto": 0x05,
        "f1": 0x00,
        "f2": 0x09,
        "f3": 0x02,
        "f4": 0x0A,
        "f5": 0x04,
    }
    _FAN_ALIASES = {
        "lowest": "f1",
        "low": "f2",
        "mid": "f3",
        "medium": "f3",
        "high": "f4",
        "highest": "f5",
    }

    def __init__(self, pack: object) -> None:
        self._pack = pack
        self._last_mode = "off"
        self._last_swing_vertical = "off"
        self._last_swing_horizontal = "off"
        self._last_jet = False
        self._last_main_signature: tuple[str, int, str] | None = None

    @staticmethod
    def _valid_frame(frame: Any) -> bool:
        return (
            isinstance(frame, list)
            and len(frame) == 3
            and all(isinstance(part, int) and 0 <= part <= 0xFF for part in frame)
        )

    def _protocol_features(self) -> dict[str, Any]:
        commands = getattr(self._pack, "commands", {})
        features = commands.get("protocol_features", {}) if isinstance(commands, dict) else {}
        return features if isinstance(features, dict) else {}

    def _feature_frame_map(self, key: str, defaults: dict[str, list[int]]) -> dict[str, list[int]]:
        features = self._protocol_features()
        raw = features.get(key, {}) if isinstance(features, dict) else {}
        merged: dict[str, list[int]] = dict(defaults)

        if isinstance(raw, dict):
            for mode, frame in raw.items():
                if isinstance(mode, str) and self._valid_frame(frame):
                    merged[mode.lower()] = list(frame)

        return merged

    @staticmethod
    def _broadlink_b64_to_pulses(payload: str) -> list[int]:
        """Decode a Broadlink base64 packet into timing pulses."""
        packet = base64.b64decode(payload)
        if len(packet) < 6:
            raise ValueError("Broadlink payload is too short")

        data = packet[4:-2]
        out: list[int] = []
        idx = 0
        while idx < len(data):
            value = data[idx]
            if value == 0:
                if idx + 2 >= len(data):
                    # Some learned packets contain trailing zero padding.
                    break
                out.append((data[idx + 1] << 8) + data[idx + 2])
                idx += 3
            else:
                out.append(value)
                idx += 1

        out = [x for x in out if x > 0]
        if not out:
            raise ValueError("Broadlink payload has no pulse data")
        return out

    def _horizontal_learned_payload_map(self) -> dict[str, str]:
        features = self._protocol_features()
        raw = (
            features.get("swing_horizontal_learned_payloads", {})
            if isinstance(features, dict)
            else {}
        )
        out: dict[str, str] = {}

        if isinstance(raw, dict):
            for mode, payload in raw.items():
                if not isinstance(mode, str) or not isinstance(payload, str):
                    continue
                try:
                    # Validate configured payload so we only advertise decodable modes.
                    self._broadlink_b64_to_pulses(payload)
                except Exception:
                    _LOGGER.warning(
                        "Ignoring invalid LG learned horizontal payload for mode '%s'",
                        mode,
                    )
                    continue
                out[mode.lower()] = payload

        return out

    def _jet_frame_map(self) -> dict[str, list[int]]:
        features = self._protocol_features()
        raw = features.get("jet_frames", {}) if isinstance(features, dict) else {}
        out: dict[str, list[int]] = {}
        if isinstance(raw, dict):
            for mode, frame in raw.items():
                if isinstance(mode, str) and self._valid_frame(frame):
                    out[mode.lower()] = list(frame)
        return out

    def supported_vertical_swing_modes(self) -> list[str]:
        frame_map = self._feature_frame_map(
            "swing_vertical_frames",
            {
                "lowest": [0x88, 0x13, 0x04],
                "low": [0x88, 0x13, 0x05],
                "middle": [0x88, 0x13, 0x06],
                "high": [0x88, 0x13, 0x08],
                "highest": [0x88, 0x13, 0x09],
                "off": [0x88, 0x13, 0x15],
                "on": [0x88, 0x13, 0x14],
                "swing": [0x88, 0x13, 0x14],
                "auto": [0x88, 0x13, 0x14],
            },
        )
        return sorted(frame_map.keys())

    def supported_horizontal_swing_modes(self) -> list[str]:
        frame_map = self._feature_frame_map(
            "swing_horizontal_frames",
            {
                "off": [0x88, 0x13, 0x17],
                "on": [0x88, 0x13, 0x16],
                "swing": [0x88, 0x13, 0x16],
                "auto": [0x88, 0x13, 0x16],
            },
        )
        learned_map = self._horizontal_learned_payload_map()
        return sorted(set(frame_map.keys()) | set(learned_map.keys()))

    def supported_preset_modes(self) -> list[str]:
        jet_frames = self._jet_frame_map()
        # Preset support is only safe if both Jet ON and OFF are encodable.
        if "on" not in jet_frames or "off" not in jet_frames:
            return []
        return ["none", "jet"]

    def _normalize_hvac_mode(self, raw_mode: str) -> str:
        mode = str(raw_mode or "cool")
        if mode == "fan_only":
            return "fan"
        return mode

    def _normalize_fan_mode(self, raw_fan: str | None) -> str:
        if not raw_fan:
            return "auto"
        fan = str(raw_fan).lower()
        fan = self._FAN_ALIASES.get(fan, fan)
        return fan if fan in self._FAN_MAP else "auto"

    def _normalize_swing_mode(self, raw_swing: str | None, supported_modes: set[str], axis: str) -> str:
        swing = str(raw_swing or "off").lower()
        aliases = {
            "on": ["on", "swing", "auto"],
            "swing": ["swing", "on", "auto"],
            "auto": ["auto", "swing", "on"],
            "off": ["off"],
        }

        for candidate in aliases.get(swing, [swing]):
            if candidate in supported_modes:
                return candidate

        raise ValueError(
            f"Unsupported LG protocol {axis} swing mode '{swing}'. Supported: {sorted(supported_modes)}"
        )

    def _normalize_preset_mode(self, raw_preset: str | None, supported_modes: set[str]) -> str:
        preset = str(raw_preset or "none").lower()
        if preset in {"off", "normal"}:
            preset = "none"
        if preset not in supported_modes:
            raise ValueError(
                f"Unsupported LG protocol preset mode '{preset}'. Supported: {sorted(supported_modes)}"
            )
        return preset

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

        min_temp = int(getattr(self._pack, "min_temperature", 16))
        max_temp = int(getattr(self._pack, "max_temperature", 30))
        if target_temperature < min_temp or target_temperature > max_temp:
            raise ValueError(
                f"Unsupported LG protocol temperature {target_temperature}. Supported range: {min_temp}-{max_temp}"
            )

        bounded = int(target_temperature)
        temp_code = (bounded - 15) << 4

        addit = 0x08 if self._last_mode != "off" else 0x00
        return [0x88, mode_code + addit, temp_code | fan_code]

    def resolve_command(self, state: dict) -> str:
        _LOGGER.debug("LGProtocolEngine input state_dict=%s", state)

        power = state.get("power")
        if power is False or state.get("hvac_mode") == "off":
            self._last_mode = "off"
            self._last_jet = False
            self._last_main_signature = None
            off_frame = [0x88, 0xC0, 0x05]
            _LOGGER.debug("LGProtocolEngine emitted frames=off_only frame_count=1")
            return self._pulses_to_broadlink_b64(self._frame_to_pulses(off_frame))

        mode = self._normalize_hvac_mode(str(state.get("hvac_mode", "cool")))
        fan_mode = self._normalize_fan_mode(state.get("fan_mode"))
        target_temperature = int(round(float(state.get("target_temperature", getattr(self._pack, "min_temperature", 24)))))

        vertical_frames = self._feature_frame_map(
            "swing_vertical_frames",
            {
                "lowest": [0x88, 0x13, 0x04],
                "low": [0x88, 0x13, 0x05],
                "middle": [0x88, 0x13, 0x06],
                "high": [0x88, 0x13, 0x08],
                "highest": [0x88, 0x13, 0x09],
                "off": [0x88, 0x13, 0x15],
                "on": [0x88, 0x13, 0x14],
                "swing": [0x88, 0x13, 0x14],
                "auto": [0x88, 0x13, 0x14],
            },
        )
        horizontal_frames = self._feature_frame_map(
            "swing_horizontal_frames",
            {
                "off": [0x88, 0x13, 0x17],
                "on": [0x88, 0x13, 0x16],
                "swing": [0x88, 0x13, 0x16],
                "auto": [0x88, 0x13, 0x16],
            },
        )
        horizontal_learned_payloads = self._horizontal_learned_payload_map()
        jet_frames = self._jet_frame_map()
        supported_presets = set(self.supported_preset_modes())

        vertical = self._normalize_swing_mode(
            state.get("swing_vertical"),
            set(vertical_frames.keys()),
            "vertical",
        )
        horizontal = self._normalize_swing_mode(
            state.get("swing_horizontal"),
            set(horizontal_frames.keys()) | set(horizontal_learned_payloads.keys()),
            "horizontal",
        )
        preset_mode = self._normalize_preset_mode(state.get("preset_mode"), supported_presets or {"none"})
        jet_enabled = preset_mode == "jet"

        frames: list[list[int]] = [
            self._build_main_frame(mode=mode, target_temperature=target_temperature, fan_mode=fan_mode)
        ]
        emitted = ["main"]

        main_signature = (mode, target_temperature, fan_mode)
        main_changed = self._last_main_signature != main_signature
        self._last_main_signature = main_signature

        if vertical != self._last_swing_vertical:
            frames.append(vertical_frames[vertical])
            self._last_swing_vertical = vertical
            emitted.append("swing_vertical")

        learned_horizontal = {"state_1", "state_2", "state_3", "state_4", "state_5", "auto"}
        learned_horizontal_payload: str | None = None
        if horizontal != self._last_swing_horizontal:
            if horizontal in learned_horizontal and horizontal in horizontal_learned_payloads:
                learned_horizontal_payload = horizontal_learned_payloads[horizontal]
            else:
                horizontal_frame = horizontal_frames.get(horizontal)
                if horizontal_frame is None:
                    raise ValueError(
                        f"Unsupported LG protocol horizontal swing mode '{horizontal}'. Supported: {sorted(set(horizontal_frames.keys()) | set(horizontal_learned_payloads.keys()))}"
                    )
                frames.append(horizontal_frame)
            self._last_swing_horizontal = horizontal
            emitted.append("swing_horizontal")

        if jet_enabled != self._last_jet:
            jet_frame_key = "on" if jet_enabled else "off"
            jet_frame = jet_frames.get(jet_frame_key)
            if jet_frame is None:
                raise ValueError(
                    f"Jet preset transition requires protocol jet '{jet_frame_key}' frame but it is not configured"
                )
            frames.append(jet_frame)
            emitted.append("jet")
            self._last_jet = jet_enabled

        self._last_mode = mode

        pulses: list[int] = []
        for frame in frames:
            pulses.extend(self._frame_to_pulses(frame))

        if learned_horizontal_payload is not None:
            pulses.extend(self._broadlink_b64_to_pulses(learned_horizontal_payload))
            emitted.append("swing_horizontal_learned")

        payload = self._pulses_to_broadlink_b64(pulses)
        payload_hash = hashlib.sha256(payload.encode("ascii")).hexdigest()[:12]

        _LOGGER.debug(
            "LGProtocolEngine normalized mode=%s fan=%s target=%s swing_v=%s swing_h=%s preset=%s jet=%s main_changed=%s emitted=%s frame_count=%s payload_hash=%s",
            mode,
            fan_mode,
            target_temperature,
            vertical,
            horizontal,
            preset_mode,
            jet_enabled,
            main_changed,
            "+".join(emitted),
            len(frames),
            payload_hash,
        )

        return payload
