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


def test_real_lg_pack_loads_with_expanded_modes() -> None:
    pack = load_pack_from_path(str(_real_lg_pack_path()))

    assert pack.pack_id == "lg.pc09sq_nsj.v1"
    assert pack.verified is False
    assert pack.capabilities.hvac_modes == ["auto", "heat", "cool", "dry", "fan_only"]
    assert pack.capabilities.fan_modes == ["auto", "low", "mid", "high"]
    assert pack.capabilities.swing_vertical_modes == []
    assert pack.capabilities.swing_horizontal_modes == []
    assert "off" in pack.commands
    for mode in pack.capabilities.hvac_modes:
        assert mode in pack.commands


def test_real_lg_pack_has_full_fan_temp_matrix_for_each_mode() -> None:
    pack = load_pack_from_path(str(_real_lg_pack_path()))

    expected_temps = {str(t) for t in range(pack.min_temperature, pack.max_temperature + 1)}
    for mode in pack.capabilities.hvac_modes:
        mode_node = pack.commands[mode]

        for fan_mode in pack.capabilities.fan_modes:
            assert fan_mode in mode_node
            assert set(mode_node[fan_mode].keys()) == expected_temps


def test_real_lg_pack_coverage_report_matches_active_capabilities() -> None:
    pack = load_pack_from_path(str(_real_lg_pack_path()))
    report = get_pack_coverage_report(pack)

    assert report["supported_hvac_modes"] == ["auto", "heat", "cool", "dry", "fan_only"]
    assert report["supported_fan_modes"] == ["auto", "low", "mid", "high"]
    assert report["swing_vertical_support"] is False
    assert report["swing_horizontal_support"] is False
    for mode in report["supported_hvac_modes"]:
        assert report["available_temperatures_by_mode"][mode] == list(range(18, 31))
    assert report["issues"] == []
