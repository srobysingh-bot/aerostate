"""Stateful localtuya_rc raw-code pack for LG AKB75415308 AC remotes."""

from __future__ import annotations

from .lg_akb75415308_localtuya_codes_v2 import CODES
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
    "fan_modes": ["auto", "low", "mid_low", "mid", "mid_high", "high"],
    "swing_modes": ["off", "swing"],
    "protocol": "stateful",
    "verified": False,
    "notes": "Stateful protocol. Send power, then one combined mode/temp/fan command.",
}

_MODES = ("cool", "heat", "dry", "auto", "fan_only")
_FAN_KEYS = ("auto", "low", "mid_low", "mid", "mid_high", "high")
_TEMPS = range(16, 31)

_COMMANDS = [
    TuyaIRCommand(label="power_on", hvac_mode="special", key1=CODES["power_on"]),
    TuyaIRCommand(label="power_off", hvac_mode="off", key1=CODES["power_off"]),
    # Combined mode+temp+fan commands
    *[
        TuyaIRCommand(
            label=f"{mode}_t{temp}_f{fan}",
            hvac_mode=mode,
            temperature=temp,
            fan_mode=fan,
            key1=CODES[f"{mode}_t{temp}_f{fan}"],
        )
        for mode in _MODES
        for temp in _TEMPS
        for fan in _FAN_KEYS
    ],
    TuyaIRCommand(
        label="swing_vertical_toggle",
        hvac_mode="special",
        key1=CODES["swing_vertical_toggle"],
    ),
    TuyaIRCommand(
        label="swing_horizontal_toggle",
        hvac_mode="special",
        key1=CODES["swing_horizontal_toggle"],
    ),
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
    swing_vertical_modes=["off", "swing"],
    swing_horizontal_modes=["off", "swing"],
    transport=PACK_META["transport"],
    protocol=PACK_META["protocol"],
)

register_tuya_pack(_PACK)
