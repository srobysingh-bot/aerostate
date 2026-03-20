"""Tests for the built-in LG protocol-generated pack."""

from __future__ import annotations

from pathlib import Path

from custom_components.aerostate.packs.coverage import get_pack_coverage_report
from custom_components.aerostate.packs.loader import load_pack_from_path


def _protocol_pack_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "aerostate"
        / "packs"
        / "builtin"
        / "lg"
        / "pc09sq_nsj_protocol_v1.json"
    )


def test_protocol_pack_loads_with_lg_protocol_engine_and_vertical_positions() -> None:
    pack = load_pack_from_path(str(_protocol_pack_path()))

    assert pack.pack_id == "lg.pc09sq_nsj.protocol.v1"
    assert pack.engine_type == "lg_protocol"
    assert pack.min_temperature == 16
    assert pack.max_temperature == 30
    assert pack.capabilities.fan_modes == ["auto", "low", "mid", "high", "highest"]
    assert pack.capabilities.swing_vertical_modes == [
        "off",
        "on",
        "swing",
        "highest",
        "high",
        "middle",
        "low",
        "lowest",
    ]
    assert pack.capabilities.swing_horizontal_modes == ["off", "on"]
    assert pack.capabilities.preset_modes == []
    assert pack.capabilities.supports_jet is False
    assert pack.verified is False


def test_protocol_pack_coverage_report_is_complete_for_protocol_engine() -> None:
    pack = load_pack_from_path(str(_protocol_pack_path()))
    report = get_pack_coverage_report(pack)

    assert report["is_complete"] is True
    assert report["issues"] == []
    assert report["swing_vertical_support"] is True
    assert report["swing_horizontal_support"] is True
    assert report["available_temperature_points"] == list(range(16, 31))
