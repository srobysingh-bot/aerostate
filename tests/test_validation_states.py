"""Unit tests for validation state generation per supported mode."""

from __future__ import annotations

from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities
from custom_components.aerostate.validation import build_safe_validation_states


def _full_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.full.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=19,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "dry", "fan_only", "cool"],
            fan_modes=["auto", "low"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "auto": {
                "auto": {"18": "A_AUTO_18", "19": "A_AUTO_19"},
                "low": {"18": "A_LOW_18", "19": "A_LOW_19"},
            },
            "heat": {
                "auto": {"18": "H_AUTO_18", "19": "H_AUTO_19"},
                "low": {"18": "H_LOW_18", "19": "H_LOW_19"},
            },
            "dry": {
                "auto": {"18": "D_AUTO_18", "19": "D_AUTO_19"},
                "low": {"18": "D_LOW_18", "19": "D_LOW_19"},
            },
            "fan_only": {
                "auto": {"18": "F_AUTO_18", "19": "F_AUTO_19"},
                "low": {"18": "F_LOW_18", "19": "F_LOW_19"},
            },
            "cool": {
                "auto": {"18": "C_AUTO_18", "19": "C_AUTO_19"},
                "low": {"18": "C_LOW_18", "19": "C_LOW_19"},
            },
        },
        verified=False,
        notes="Synthetic full capability pack for unit test",
    )


def test_build_safe_validation_states_includes_one_state_per_supported_mode() -> None:
    states = build_safe_validation_states(_full_pack(), profile="basic")

    labels = [label for label, _ in states]
    assert labels[0] == "off"
    assert any(label.startswith("auto_") for label in labels)
    assert any(label.startswith("heat_") for label in labels)
    assert any(label.startswith("dry_") for label in labels)
    assert any(label.startswith("fan_only_") for label in labels)
    assert any(label.startswith("cool_") for label in labels)


def test_build_safe_validation_states_full_profile_adds_extra_coverage() -> None:
    states_basic = build_safe_validation_states(_full_pack(), profile="basic")
    states_full = build_safe_validation_states(_full_pack(), profile="full")

    assert len(states_full) > len(states_basic)
    assert states_full[0][0] == "off"
