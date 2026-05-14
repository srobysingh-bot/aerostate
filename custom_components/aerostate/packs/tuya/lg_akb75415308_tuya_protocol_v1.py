"""Stateful localtuya_rc raw-code pack for LG AKB75415308 AC remotes."""

from __future__ import annotations

from .lg_akb75415308_tuya_codes import CODES
from .registry import register_tuya_pack
from .schema import TuyaIRCommand, TuyaIRPack

PACK_META = {
    "id": "lg.akb75415308.localtuya_rc.protocol.v1",
    "display_name": "LG AKB75415308 (localtuya_rc)",
    "transport": "localtuya_rc",
    "brand": "LG",
    "remote_model": "AKB75415308",
    "temp_min": 16,
    "temp_max": 30,
    "hvac_modes": ["off", "cool", "heat", "dry", "auto", "fan_only"],
    "fan_modes": ["low", "mid_low", "mid", "mid_high", "high"],
    "swing_modes": ["off", "swing"],
    "protocol": "stateful",
    "verified": False,
    "notes": "Stateful protocol. Send power, mode/temp, then fan as separate commands.",
}

_TEMPS = range(PACK_META["temp_min"], PACK_META["temp_max"] + 1)
_MODE_KEYS = ("cool", "heat", "dry", "auto", "fan_only")
_FAN_KEY_TO_MODE = {
    "fan_low": "low",
    "fan_mid_low": "mid_low",
    "fan_mid": "mid",
    "fan_mid_high": "mid_high",
    "fan_high": "high",
}
_LEGACY_FAN_KEY_TO_MODE = {
    "fan_speed_1": "low",
    "fan_speed_2": "mid_low",
    "fan_speed_3": "mid",
    "fan_speed_4": "mid_high",
    "fan_speed_5": "high",
}

_COMMANDS = [
    TuyaIRCommand(label="power_on", hvac_mode="special", key1=CODES["power_on"]),
    TuyaIRCommand(label="power_off", hvac_mode="off", key1=CODES["power_off"]),
    TuyaIRCommand(label="swing_toggle", hvac_mode="special", key1=CODES["swing_toggle"]),
    *[
        TuyaIRCommand(
            label=f"{mode}_t{temp}",
            hvac_mode=mode,
            temperature=temp,
            key1=CODES[f"{mode}_t{temp}"],
        )
        for mode in _MODE_KEYS
        for temp in _TEMPS
    ],
    *[
        TuyaIRCommand(
            label=label,
            hvac_mode="special",
            fan_mode=fan_mode,
            key1=CODES[label],
        )
        for label, fan_mode in _FAN_KEY_TO_MODE.items()
    ],
    *[
        TuyaIRCommand(
            label=f"temp_{temp}",
            hvac_mode="special",
            temperature=temp,
            key1=CODES[f"temp_{temp}"],
        )
        for temp in _TEMPS
    ],
    *[
        TuyaIRCommand(
            label=label,
            hvac_mode="special",
            fan_mode=fan_mode,
            key1=CODES[label],
        )
        for label, fan_mode in _LEGACY_FAN_KEY_TO_MODE.items()
    ],
]

_PACK = TuyaIRPack(
    pack_id=PACK_META["id"],
    brand=PACK_META["brand"],
    models=[PACK_META["remote_model"]],
    verified=PACK_META["verified"],
    notes=PACK_META["notes"],
    min_temperature=PACK_META["temp_min"],
    max_temperature=PACK_META["temp_max"],
    commands=_COMMANDS,
    native_base64=False,
    requires_learned_codes=False,
    swing_vertical_modes=PACK_META["swing_modes"],
    swing_horizontal_modes=[],
    swing_toggle_label="swing_toggle",
    transport=PACK_META["transport"],
    protocol=PACK_META["protocol"],
)

register_tuya_pack(_PACK)
