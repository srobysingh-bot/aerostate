"""Tests against the active built-in LG pack file used by AeroState."""

from __future__ import annotations

from pathlib import Path

from custom_components.aerostate.packs.coverage import get_pack_coverage_report
from custom_components.aerostate.packs.loader import load_pack_from_path


def _real_lg_pack_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "aerostate"
        / "packs"
        / "builtin"
        / "lg"
        / "pc09sq_nsj_v1.json"
    )


def test_real_lg_pack_loads_and_is_cool_only() -> None:
    pack = load_pack_from_path(str(_real_lg_pack_path()))

    assert pack.pack_id == "lg.pc09sq_nsj.v1"
    assert pack.verified is True
    assert pack.capabilities.hvac_modes == ["cool"]
    assert pack.capabilities.fan_modes == ["auto", "low", "mid", "high"]
    assert pack.capabilities.swing_vertical_modes == []
    assert pack.capabilities.swing_horizontal_modes == []
    assert "off" in pack.commands
    assert "cool" in pack.commands


def test_real_lg_pack_has_full_cool_fan_temp_matrix() -> None:
    pack = load_pack_from_path(str(_real_lg_pack_path()))

    expected_temps = {str(t) for t in range(pack.min_temperature, pack.max_temperature + 1)}
    cool_node = pack.commands["cool"]

    for fan_mode in pack.capabilities.fan_modes:
        assert fan_mode in cool_node
        assert set(cool_node[fan_mode].keys()) == expected_temps


def test_real_lg_pack_coverage_report_matches_active_capabilities() -> None:
    pack = load_pack_from_path(str(_real_lg_pack_path()))
    report = get_pack_coverage_report(pack)

    assert report["supported_hvac_modes"] == ["cool"]
    assert report["supported_fan_modes"] == ["auto", "low", "mid", "high"]
    assert report["swing_vertical_support"] is False
    assert report["swing_horizontal_support"] is False
    assert report["available_temperatures_by_mode"]["cool"] == list(range(18, 31))
    assert report["issues"] == []
