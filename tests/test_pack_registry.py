"""Unit tests for pack registry behavior."""

from __future__ import annotations

import pytest

from custom_components.aerostate.packs.loader import validate_pack_dict
from custom_components.aerostate.packs.registry import PackRegistry
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.verified.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto", "low"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={"off": "OFF", "cool": {"auto": {"18": "X"}, "low": {"18": "Y"}}},
        verified=True,
        notes="Verified cool-only pack. No swing payloads included.",
    )


def test_registry_preserves_verified_and_notes_metadata() -> None:
    registry = PackRegistry()
    pack = _pack()
    registry.add_pack(pack)

    resolved = registry.get("lg.verified.v1")
    assert resolved.verified is True
    assert resolved.notes == "Verified cool-only pack. No swing payloads included."


def test_loader_validation_rejects_invalid_pack_dict() -> None:
    invalid = {
        "id": "lg.invalid.v1",
        "brand": "LG",
        "pack_version": 1,
        "models": ["TEST"],
        "transport": "broadlink_base64",
        "min_temperature": 18,
        "max_temperature": 30,
        "capabilities": {
            "hvac_modes": ["cool"],
            "fan_modes": ["auto"],
            "swing_vertical_modes": [],
            "swing_horizontal_modes": [],
            "presets": [],
        },
        # missing commands key
    }

    with pytest.raises(ValueError, match="required keys"):
        validate_pack_dict(invalid)
