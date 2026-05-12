"""Pre-generated Tuya IR pack for LG AKB75415308 AC remotes."""

from __future__ import annotations

from .lg_akb75415308_tuya_codes import CODES
from .registry import register_tuya_pack
from .schema import TuyaIRCommand, TuyaIRPack

_TEMPS = range(16, 31)
_FANS = ("auto", "low", "mid", "high", "highest")


def _temp_mode_commands(mode: str) -> list[TuyaIRCommand]:
    """Build command metadata for temperature-bearing LG modes."""

    commands: list[TuyaIRCommand] = []
    for temp in _TEMPS:
        for fan in _FANS:
            commands.append(
                TuyaIRCommand(
                    label=f"{mode}_on_t{temp}_f{fan}",
                    hvac_mode=mode,
                    temperature=temp,
                    fan_mode=fan,
                    key1=CODES[f"{mode}_on_t{temp}_f{fan}"],
                    turn_on_variant=True,
                )
            )
            commands.append(
                TuyaIRCommand(
                    label=f"{mode}_t{temp}_f{fan}",
                    hvac_mode=mode,
                    temperature=temp,
                    fan_mode=fan,
                    key1=CODES[f"{mode}_t{temp}_f{fan}"],
                )
            )
    return commands


def _fan_mode_commands(mode: str, prefix: str) -> list[TuyaIRCommand]:
    """Build command metadata for LG modes that encode a fixed 25 C temperature."""

    commands: list[TuyaIRCommand] = []
    for fan in _FANS:
        commands.append(
            TuyaIRCommand(
                label=f"{prefix}_on_f{fan}",
                hvac_mode=mode,
                fan_mode=fan,
                key1=CODES[f"{prefix}_on_f{fan}"],
                turn_on_variant=True,
            )
        )
        commands.append(
            TuyaIRCommand(
                label=f"{prefix}_f{fan}",
                hvac_mode=mode,
                fan_mode=fan,
                key1=CODES[f"{prefix}_f{fan}"],
            )
        )
    return commands


_COMMANDS = [
    TuyaIRCommand(label="off", hvac_mode="off", key1=CODES["off"]),
    *_temp_mode_commands("cool"),
    *_temp_mode_commands("heat"),
    *_temp_mode_commands("dry"),
    *_fan_mode_commands("fan_only", "fan"),
    *_fan_mode_commands("auto", "auto"),
    TuyaIRCommand(
        label="swing_toggle",
        hvac_mode="special",
        key1=CODES["swing_toggle"],
    ),
]

_PACK = TuyaIRPack(
    pack_id="lg.akb75415308.tuya.protocol.v1",
    brand="LG",
    models=["AKB75415308"],
    verified=False,
    notes=(
        "Pre-generated LG 28-bit AC IR codes for Tuya IR blasters. "
        "No manual learning required. Swing is an independent toggle command."
    ),
    min_temperature=16,
    max_temperature=30,
    commands=_COMMANDS,
    native_base64=True,
    requires_learned_codes=False,
    swing_toggle_label="swing_toggle",
)

register_tuya_pack(_PACK)
