"""Tuya IR key1 pack for LG PC09SQ NSJ."""

from __future__ import annotations

from .registry import register_tuya_pack
from .schema import TuyaIRCommand, TuyaIRPack

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
    commands=[
        TuyaIRCommand(
            label="off",
            hvac_mode="off",
            key1="AA==",
        ),
        TuyaIRCommand(
            label="cool_24_auto_swing_off",
            hvac_mode="cool",
            temperature=24,
            fan_mode="auto",
            swing_on=False,
            key1="AQ==",
        ),
    ],
)

register_tuya_pack(_PACK)

