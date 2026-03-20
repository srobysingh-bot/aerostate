"""Unit tests for protocol-driven LG engine payload generation."""

from __future__ import annotations

import base64
import pytest

from custom_components.aerostate.engines.lg_engine import LGProtocolEngine
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "f1", "f2", "f3", "f4", "f5"],
            swing_vertical_modes=["off", "on"],
            swing_horizontal_modes=["off", "on"],
            presets=[],
            preset_modes=[],
            supports_jet=False,
        ),
        engine_type="lg_protocol",
        commands={"off": "protocol_generated"},
        verified=False,
    )


def _advanced_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.advanced.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "f1", "f2", "f3", "f4", "f5"],
            swing_vertical_modes=["off", "swing", "highest", "middle", "lowest"],
            swing_horizontal_modes=["off", "swing", "left", "center", "right"],
            presets=["none", "jet"],
            preset_modes=["none", "jet"],
            supports_jet=True,
        ),
        engine_type="lg_protocol",
        commands={
            "off": "protocol_generated",
            "protocol_features": {
                "swing_vertical_frames": {
                    "off": [136, 19, 21],
                    "swing": [136, 19, 20],
                    "highest": [136, 19, 24],
                    "middle": [136, 19, 25],
                    "lowest": [136, 19, 26],
                },
                "swing_horizontal_frames": {
                    "off": [136, 19, 23],
                    "swing": [136, 19, 22],
                    "left": [136, 19, 32],
                    "center": [136, 19, 33],
                    "right": [136, 19, 34],
                },
                "jet_frames": {
                    "on": [136, 16, 8],
                    "off": [136, 16, 9],
                },
            },
        },
        verified=False,
    )


def _decode_pulses(b64_payload: str) -> list[int]:
    packet = base64.b64decode(b64_payload)
    data = packet[4:-2]
    out: list[int] = []
    idx = 0
    while idx < len(data):
        value = data[idx]
        if value == 0:
            out.append((data[idx + 1] << 8) + data[idx + 2])
            idx += 3
        else:
            out.append(value)
            idx += 1
    return [x for x in out if x > 0]


def test_lg_protocol_engine_generates_off_payload() -> None:
    engine = LGProtocolEngine(_pack())
    payload = engine.resolve_command({"power": False, "hvac_mode": "off", "target_temperature": 24})

    pulses = _decode_pulses(payload)
    assert pulses[:2] == [105, 323]


def test_lg_protocol_engine_adds_extra_frames_for_swing_changes() -> None:
    engine = LGProtocolEngine(_pack())

    base_payload = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    swing_payload = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "on",
            "swing_horizontal": "on",
        }
    )

    assert len(base64.b64decode(swing_payload)) > len(base64.b64decode(base_payload))


def test_lg_protocol_engine_supports_advanced_swing_modes_when_mapped() -> None:
    engine = LGProtocolEngine(_advanced_pack())

    highest = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "highest",
            "swing_horizontal": "left",
            "preset_mode": "none",
        }
    )
    lowest = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "lowest",
            "swing_horizontal": "right",
            "preset_mode": "none",
        }
    )

    assert highest != lowest


def test_lg_protocol_engine_jet_preset_changes_payload_when_mapped() -> None:
    engine = LGProtocolEngine(_advanced_pack())

    jet_on = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
            "preset_mode": "jet",
        }
    )
    jet_off = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
            "preset_mode": "none",
        }
    )

    assert jet_on != jet_off


def test_lg_protocol_engine_rejects_unencodable_advanced_horizontal_swing() -> None:
    engine = LGProtocolEngine(_pack())

    with pytest.raises(ValueError, match="horizontal swing mode"):
        engine.resolve_command(
            {
                "power": True,
                "hvac_mode": "cool",
                "target_temperature": 24,
                "fan_mode": "auto",
                "swing_vertical": "off",
                "swing_horizontal": "left",
            }
        )


def test_lg_protocol_engine_rejects_jet_when_not_configured() -> None:
    engine = LGProtocolEngine(_pack())

    with pytest.raises(ValueError, match="preset mode"):
        engine.resolve_command(
            {
                "power": True,
                "hvac_mode": "cool",
                "target_temperature": 24,
                "fan_mode": "auto",
                "swing_vertical": "off",
                "swing_horizontal": "off",
                "preset_mode": "jet",
            }
        )


def test_lg_protocol_engine_encodes_real_advanced_vertical_positions() -> None:
    engine = LGProtocolEngine(_pack())

    highest = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "highest",
            "swing_horizontal": "off",
        }
    )
    lowest = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "lowest",
            "swing_horizontal": "off",
        }
    )

    assert highest != lowest


def test_lg_protocol_engine_generates_distinct_payloads_for_16_17_and_30() -> None:
    engine = LGProtocolEngine(_pack())

    temp_16 = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 16,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    temp_17 = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 17,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    temp_30 = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 30,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )

    assert temp_16 != temp_17
    assert temp_17 != temp_30


def test_lg_protocol_engine_rejects_temperature_below_pack_minimum() -> None:
    engine = LGProtocolEngine(_pack())

    with pytest.raises(ValueError, match="temperature"):
        engine.resolve_command(
            {
                "power": True,
                "hvac_mode": "cool",
                "target_temperature": 15,
                "fan_mode": "auto",
                "swing_vertical": "off",
                "swing_horizontal": "off",
            }
        )


def test_lg_protocol_engine_encodes_all_real_fan_levels_distinctly() -> None:
    engine = LGProtocolEngine(_pack())

    expected_low_nibbles = {
        "auto": 0x05,
        "f1": 0x00,
        "f2": 0x09,
        "f3": 0x02,
        "f4": 0x0A,
        "f5": 0x04,
    }
    payloads: dict[str, str] = {}

    for fan_mode, expected_nibble in expected_low_nibbles.items():
        frame = engine._build_main_frame(mode="cool", target_temperature=24, fan_mode=fan_mode)
        assert frame[2] & 0x0F == expected_nibble

        payloads[fan_mode] = engine.resolve_command(
            {
                "power": True,
                "hvac_mode": "cool",
                "target_temperature": 24,
                "fan_mode": fan_mode,
                "swing_vertical": "off",
                "swing_horizontal": "off",
            }
        )

    assert len(set(payloads.values())) == len(expected_low_nibbles)


def test_lg_protocol_engine_keeps_legacy_fan_aliases_internal_only() -> None:
    engine = LGProtocolEngine(_pack())

    expected = {
        "lowest": "f1",
        "low": "f2",
        "mid": "f3",
        "high": "f4",
        "highest": "f5",
    }
    for legacy, canonical in expected.items():
        assert engine._normalize_fan_mode(legacy) == canonical
