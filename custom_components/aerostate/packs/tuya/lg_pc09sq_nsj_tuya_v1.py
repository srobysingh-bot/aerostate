"""Tuya IR key1 pack for LG PC09SQ NSJ.

The command matrix is intentionally complete, but the key1 payloads are
deterministic placeholders until replaced with real IRTuya-converted captures.
"""

from __future__ import annotations

import base64

from .registry import register_tuya_pack
from .schema import TuyaIRCommand, TuyaIRPack

_TEMPS = range(16, 31)
_FANS = ("f1", "f2", "f3", "f4", "f5", "auto")
_SWING = (False, True)


def _placeholder_key1(label: str) -> str:
    """Return a non-empty base64 placeholder for an unfilled Tuya key1 value."""
    return base64.b64encode(f"PLACEHOLDER:{label}".encode("ascii")).decode("ascii")


def _state_commands(mode: str) -> list[TuyaIRCommand]:
    return [
        TuyaIRCommand(
            label=f"{mode}_{temp}_{fan}_swing_{'on' if swing else 'off'}",
            hvac_mode=mode,
            temperature=temp,
            fan_mode=fan,
            swing_on=swing,
            key1=_placeholder_key1(f"{mode}_{temp}_{fan}_swing_{'on' if swing else 'off'}"),
        )
        for temp in _TEMPS
        for fan in _FANS
        for swing in _SWING
    ]


def _dry_commands() -> list[TuyaIRCommand]:
    return [
        TuyaIRCommand(
            label=f"dry_{temp}_auto_swing_{'on' if swing else 'off'}",
            hvac_mode="dry",
            temperature=temp,
            fan_mode="auto",
            swing_on=swing,
            key1=_placeholder_key1(f"dry_{temp}_auto_swing_{'on' if swing else 'off'}"),
        )
        for temp in _TEMPS
        for swing in _SWING
    ]


def _fan_commands() -> list[TuyaIRCommand]:
    return [
        TuyaIRCommand(
            label=f"fan_{fan}_swing_{'on' if swing else 'off'}",
            hvac_mode="fan_only",
            fan_mode=fan,
            swing_on=swing,
            key1=_placeholder_key1(f"fan_{fan}_swing_{'on' if swing else 'off'}"),
        )
        for fan in _FANS
        for swing in _SWING
    ]


def _special_commands() -> list[TuyaIRCommand]:
    labels = ("turbo_on", "turbo_off", "sleep_on", "sleep_off", "eco_on", "eco_off")
    return [
        TuyaIRCommand(
            label=label,
            hvac_mode="special",
            key1=_placeholder_key1(label),
        )
        for label in labels
    ]


_COMMANDS = [
    TuyaIRCommand(label="off", hvac_mode="off", key1=_placeholder_key1("off")),
    *_state_commands("cool"),
    *_state_commands("heat"),
    *_dry_commands(),
    *_fan_commands(),
    *_state_commands("auto"),
    *_special_commands(),
]

_PACK = TuyaIRPack(
    pack_id="tuya.lg_pc09sq_nsj.v1",
    brand="LG",
    models=["PC09SQ NSJ"],
    verified=False,
    notes=(
        "Tuya IR pack. key1 payloads must be replaced with real Tuya base64 values "
        "converted offline from captured IR timings."
    ),
    min_temperature=16,
    max_temperature=30,
    commands=_COMMANDS,
)

register_tuya_pack(_PACK)
