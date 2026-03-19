"""Unit tests for pack loader validation."""

from __future__ import annotations

import json

import pytest

from custom_components.aerostate.packs.loader import load_pack_from_path


def _base_pack_dict() -> dict:
    return {
        "id": "lg.test.v1",
        "brand": "LG",
        "pack_version": 1,
        "models": ["TEST"],
        "transport": "broadlink_base64",
        "verified": False,
        "notes": "test",
        "min_temperature": 18,
        "max_temperature": 30,
        "engine": {"type": "table"},
        "capabilities": {
            "hvac_modes": ["cool"],
            "fan_modes": ["auto"],
            "swing_vertical_modes": [],
            "swing_horizontal_modes": [],
            "presets": [],
        },
        "commands": {
            "off": "AAA",
            "cool": {"auto": {"18": "BBB", "30": "CCC"}},
        },
    }


def test_loader_accepts_valid_pack(tmp_path) -> None:
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(_base_pack_dict()), encoding="utf-8")

    pack = load_pack_from_path(str(pack_file))
    assert pack.pack_id == "lg.test.v1"
    assert pack.pack_version == 1
    assert pack.verified is False
    assert pack.physically_verified_modes == []
    assert pack.mode_status == {}


def test_loader_accepts_mode_truth_metadata(tmp_path) -> None:
    data = _base_pack_dict()
    data["physically_verified_modes"] = ["cool"]
    data["mode_status"] = {"cool": "verified"}
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")

    pack = load_pack_from_path(str(pack_file))
    assert pack.physically_verified_modes == ["cool"]
    assert pack.mode_status == {"cool": "verified"}


def test_loader_accepts_lg_protocol_engine_type(tmp_path) -> None:
    data = _base_pack_dict()
    data["engine"] = {"type": "lg_protocol"}
    data["commands"] = {"off": "protocol_generated"}
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")

    pack = load_pack_from_path(str(pack_file))
    assert pack.engine_type == "lg_protocol"


def test_loader_rejects_mode_truth_for_unsupported_mode(tmp_path) -> None:
    data = _base_pack_dict()
    data["mode_status"] = {"heat": "experimental"}
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="mode_status"):
        load_pack_from_path(str(pack_file))


def test_loader_rejects_off_in_capabilities(tmp_path) -> None:
    data = _base_pack_dict()
    data["capabilities"]["hvac_modes"] = ["off", "cool"]
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="must not contain 'off'"):
        load_pack_from_path(str(pack_file))


def test_loader_rejects_missing_required_key(tmp_path) -> None:
    data = _base_pack_dict()
    data.pop("pack_version")
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required keys"):
        load_pack_from_path(str(pack_file))


def test_loader_rejects_invalid_transport(tmp_path) -> None:
    data = _base_pack_dict()
    data["transport"] = "mqtt"
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Only 'broadlink_base64' transport"):
        load_pack_from_path(str(pack_file))
