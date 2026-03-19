"""Unit tests for table engine command resolution."""

from __future__ import annotations

import pytest

from custom_components.aerostate.engines.table_engine import TableEngine
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=20,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto", "low"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "cool": {
                "auto": {"18": "C_AUTO_18"},
                "low": {"18": "C_LOW_18"},
            },
        },
    )


def test_table_engine_resolves_off() -> None:
    engine = TableEngine(_pack())
    assert engine.resolve_command({"power": False, "hvac_mode": "off", "target_temperature": 18}) == "OFF"


def test_table_engine_resolves_mode_fan_temp() -> None:
    engine = TableEngine(_pack())
    cmd = engine.resolve_command(
        {"power": True, "hvac_mode": "cool", "fan_mode": "auto", "target_temperature": 18}
    )
    assert cmd == "C_AUTO_18"


def test_table_engine_raises_clear_error_for_missing_temp() -> None:
    engine = TableEngine(_pack())
    with pytest.raises(ValueError, match="Unable to resolve command"):
        engine.resolve_command(
            {"power": True, "hvac_mode": "cool", "fan_mode": "auto", "target_temperature": 20}
        )
