"""Stateful localtuya_rc raw-code pack for Daikin BRC4C158 remotes.

The commands are generated from the Daikin BRC4CXXX protocol used by
ESPHome's daikin_brc component. BRC4C158 is treated as a cooling-only remote:
off plus cool state commands for 16-30 C and auto/low/high fan.
"""

from __future__ import annotations

from .daikin_brc4c158_codes import CODES
from .registry import register_tuya_pack
from .schema import TuyaIRCommand, TuyaIRPack

PACK_ID = "daikin.brc4c158.localtuya_rc.smartir1109.v1"

_TEMPS = range(16, 31)
_FANS = {
    "auto": "fauto",
    "low": "flow",
    "high": "fhigh",
}

_COMMANDS = [
    TuyaIRCommand(label="power_off", hvac_mode="off", key1=CODES["power_off"]),
    *[
        TuyaIRCommand(
            label=f"cool_t{temp}_{fan_label}",
            hvac_mode="cool",
            temperature=temp,
            fan_mode=fan_mode,
            key1=CODES[f"cool_t{temp}_{fan_label}"],
        )
        for temp in _TEMPS
        for fan_mode, fan_label in _FANS.items()
    ],
]

_PACK = TuyaIRPack(
    pack_id=PACK_ID,
    brand="Daikin",
    models=["BRC4C158"],
    verified=True,
    notes=(
        "Daikin BRC4C158 cooling-only local Tuya IR pack generated from the "
        "Daikin BRC4CXXX protocol used by ESPHome daikin_brc. Use with the "
        "normal Tuya IR Device provider, not Tuya Cloud."
    ),
    min_temperature=16,
    max_temperature=30,
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
