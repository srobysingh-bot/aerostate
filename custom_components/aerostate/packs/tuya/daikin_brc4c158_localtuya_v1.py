"""Stateful localtuya_rc raw-code pack for Daikin BRC4C158 remotes.

The source commands are SmartIR climate code 1109 for Daikin BRC4C158. They
are bundled as Broadlink base64 packets and converted to Tuya ``raw:`` timing
strings at import time so this pack can use the local Tuya IR sender instead
of Tuya Cloud's AC code-library API.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from .registry import register_tuya_pack
from .schema import TuyaIRCommand, TuyaIRPack

PACK_ID = "daikin.brc4c158.localtuya_rc.smartir1109.v1"
_SOURCE_PATH = Path(__file__).resolve().parent / "source_codes" / "daikin_brc4c158_smartir_1109.json"
_BROADLINK_TICK_US = 269000 / 8192

_FAN_MAP = {
    "low": "low",
    "medium": "mid",
    "high": "high",
}


def _broadlink_b64_to_tuya_raw(payload: str) -> str:
    packet = base64.b64decode(payload.strip())
    if len(packet) < 6 or packet[0] != 0x26:
        raise ValueError("Expected Broadlink learned IR packet")

    length = packet[2] | (packet[3] << 8)
    data = packet[4 : 4 + length]
    timings: list[int] = []
    idx = 0
    while idx < len(data):
        value = data[idx]
        idx += 1
        if value == 0:
            if idx + 1 >= len(data):
                break
            value = (data[idx] << 8) | data[idx + 1]
            idx += 2
        if value > 0:
            timings.append(round(value * _BROADLINK_TICK_US))

    # Broadlink packets include a very long trailing inter-command gap. Tuya
    # raw senders only need the actual burst and are happier without >65ms tail
    # spaces, so trim that final idle period.
    if timings and timings[-1] > 65000:
        timings.pop()

    if len(timings) < 50:
        raise ValueError("Decoded Daikin command has too few timings")
    return "raw:" + ",".join(str(timing) for timing in timings)


def _load_source() -> dict:
    with _SOURCE_PATH.open("r", encoding="utf-8-sig") as file_obj:
        data = json.load(file_obj)
    if data.get("manufacturer") != "Daikin" or "BRC4C158" not in data.get("supportedModels", []):
        raise ValueError("Bundled SmartIR 1109 source is not the Daikin BRC4C158 pack")
    return data


def _build_codes() -> dict[str, str]:
    source = _load_source()
    commands = source["commands"]
    codes = {
        "power_off": _broadlink_b64_to_tuya_raw(commands["off"]),
    }

    for mode in ("cool", "heat", "dry", "fan_only"):
        mode_commands = commands.get(mode, {})
        for source_fan, fan in _FAN_MAP.items():
            temp_commands = mode_commands.get(source_fan, {})
            for temp in range(int(source["minTemperature"]), int(source["maxTemperature"]) + 1):
                payload = temp_commands.get(str(temp))
                if payload:
                    codes[f"{mode}_t{temp}_f{fan}"] = _broadlink_b64_to_tuya_raw(payload)
    return codes


CODES = _build_codes()

_COMMANDS = [
    TuyaIRCommand(label="power_off", hvac_mode="off", key1=CODES["power_off"]),
    *[
        TuyaIRCommand(
            label=label,
            hvac_mode=mode,
            temperature=temp,
            fan_mode=fan,
            key1=CODES[label],
        )
        for mode in ("cool", "heat", "dry", "fan_only")
        for temp in range(16, 33)
        for fan in ("low", "mid", "high")
        if (label := f"{mode}_t{temp}_f{fan}") in CODES
    ],
]

_PACK = TuyaIRPack(
    pack_id=PACK_ID,
    brand="Daikin",
    models=["BRC4C158"],
    verified=False,
    notes=(
        "Daikin BRC4C158 local Tuya IR pack converted from SmartIR climate code 1109. "
        "Use with the normal Tuya IR Device provider, not Tuya Cloud."
    ),
    min_temperature=16,
    max_temperature=32,
    commands=_COMMANDS,
    native_base64=False,
    requires_learned_codes=False,
    swing_vertical_modes=[],
    swing_horizontal_modes=[],
    transport="localtuya_rc",
    protocol="stateful",
)

register_tuya_pack(_PACK)

__all__ = ["CODES", "PACK_ID"]
