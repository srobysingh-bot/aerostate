"""Tests for SmartIR donor-based Daikin table pack."""

from __future__ import annotations

from pathlib import Path

from custom_components.aerostate.engines.factory import create_engine
from custom_components.aerostate.engines.table_engine import TableEngine
from custom_components.aerostate.packs.loader import load_pack_from_path


def _daikin_table_pack_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "aerostate"
        / "packs"
        / "builtin"
        / "daikin"
        / "daikin_atkc09tv2s_ftkq12tv2s_smartir_1112_v1.json"
    )


def test_daikin_table_pack_loads_as_experimental_donor_pack() -> None:
    pack = load_pack_from_path(str(_daikin_table_pack_path()))

    assert pack.pack_id == "daikin.atkc09tv2s_ftkq12tv2s.smartir1112.v1"
    assert pack.brand == "Daikin"
    assert pack.engine_type == "table"
    assert pack.verified is False
    assert pack.models == ["ATKC09TV2S", "FTKQ12TV2S"]
    assert pack.capabilities.hvac_modes == ["dry", "cool", "fan_only"]
    assert pack.capabilities.fan_modes == [
        "auto",
        "breeze",
        "level1",
        "level2",
        "level3",
        "level4",
        "level5",
        "powerful",
    ]


def test_daikin_table_pack_keeps_unsupported_features_hidden() -> None:
    pack = load_pack_from_path(str(_daikin_table_pack_path()))

    assert "heat" not in pack.capabilities.hvac_modes
    assert "heat_cool" not in pack.capabilities.hvac_modes
    assert pack.capabilities.swing_vertical_modes == []
    assert pack.capabilities.swing_horizontal_modes == []
    assert pack.capabilities.presets == []


def test_daikin_table_pack_resolves_commands_via_existing_table_engine() -> None:
    pack = load_pack_from_path(str(_daikin_table_pack_path()))
    engine = create_engine(pack)

    assert isinstance(engine, TableEngine)

    off = engine.resolve_command({"power": False})
    cool = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "fan_mode": "auto",
            "target_temperature": 24,
        }
    )

    assert isinstance(off, str) and off
    assert isinstance(cool, str) and cool
    assert off != cool
