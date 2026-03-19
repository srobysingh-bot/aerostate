"""Unit tests for options/title helper behavior."""

from __future__ import annotations

from custom_components.aerostate.flow_helpers import build_entry_title
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.test.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={"off": "OFF", "cool": {"auto": {"18": "X"}}},
    )


def test_build_entry_title_prefers_name() -> None:
    title = build_entry_title(_pack(), {"name": "Bedroom AC", "area": "Bedroom"})
    assert title == "Bedroom AC"


def test_build_entry_title_uses_area_when_name_missing() -> None:
    title = build_entry_title(_pack(), {"area": "Bedroom"})
    assert title == "PC09SQ NSJ (Bedroom)"


def test_build_entry_title_falls_back_to_model() -> None:
    title = build_entry_title(_pack(), {})
    assert title == "PC09SQ NSJ"
