"""Unit tests for pack coverage helpers."""

from __future__ import annotations

from custom_components.aerostate.packs.coverage import (
    get_pack_coverage_report,
    validate_pack_coverage,
)
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
            "off": "AAA",
            "cool": {
                "auto": {"18": "X", "19": "Y", "20": "Z"},
                "low": {"18": "X", "19": "Y", "20": "Z"},
            },
        },
        verified=True,
        notes="verified",
    )


def test_coverage_report_contains_required_fields() -> None:
    report = get_pack_coverage_report(_pack())
    assert report["supported_hvac_modes"] == ["cool"]
    assert report["supported_fan_modes"] == ["auto", "low"]
    assert report["available_temperature_points"] == [18, 19, 20]
    assert "missing_temperature_gaps" in report
    assert "swing_vertical_support" in report
    assert "swing_horizontal_support" in report


def test_validate_pack_coverage_no_issues_for_complete_matrix() -> None:
    issues = validate_pack_coverage(_pack())
    assert issues == []


def test_coverage_report_detects_missing_temperature_gaps() -> None:
    pack = _pack()
    pack.commands["cool"]["auto"].pop("19")
    pack.commands["cool"]["low"].pop("19")

    report = get_pack_coverage_report(pack)
    assert 19 in report["missing_temperature_gaps"]
    assert any("Missing temperatures" in issue for issue in report["issues"])


def test_coverage_report_includes_per_mode_temperatures_and_swing_support() -> None:
    pack = _pack()
    report = get_pack_coverage_report(pack)

    assert "available_temperatures_by_mode" in report
    assert report["available_temperatures_by_mode"]["cool"] == [18, 19, 20]
    assert "swing_support_by_mode" in report
    assert report["swing_support_by_mode"]["cool"]["vertical"] is False
    assert report["swing_support_by_mode"]["cool"]["horizontal"] is False
    assert "mode_matrix" in report
    assert report["mode_matrix"]["cool"]["fan_branches"] == ["auto", "low"]


def test_validate_pack_coverage_detects_missing_branch_for_additional_mode() -> None:
    pack = _pack()
    pack.capabilities.hvac_modes = ["cool", "heat"]

    issues = validate_pack_coverage(pack)
    assert any("Missing command tree for hvac mode 'heat'" in issue for issue in issues)
