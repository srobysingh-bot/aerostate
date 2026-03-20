"""Unit tests for config/flow helper behavior."""

from __future__ import annotations

from custom_components.aerostate.flow_helpers import describe_pack_limitations
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _verified_protocol_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "low", "mid", "high", "highest"],
            swing_vertical_modes=["off", "on", "highest"],
            swing_horizontal_modes=["off", "on"],
            presets=[],
            preset_modes=[],
            supports_jet=False,
        ),
        engine_type="lg_protocol",
        commands={"off": "protocol_generated"},
        verified=True,
    )


def _verified_cool_only_no_swing_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.cool.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto", "low", "mid", "high"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={"off": "OFF"},
        verified=True,
    )


def test_describe_pack_limitations_for_verified_protocol_pack_is_conservative() -> None:
    limitation = describe_pack_limitations(_verified_protocol_pack())

    assert "Horizontal swing is limited" in limitation
    assert "Jet/Turbo is disabled" in limitation


def test_describe_pack_limitations_for_verified_cool_only_pack() -> None:
    limitation = describe_pack_limitations(_verified_cool_only_no_swing_pack())

    assert limitation == "Verified cool-only pack. No swing payloads included."
