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
            swing_horizontal_modes=[
                "off",
                "on",
                "left_mid",
                "mid",
                "right_mid",
                "right_most",
                "left_swing",
                "right_swing",
                "full_swing",
            ],
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
                    "on": [136, 19, 22],
                    "swing": [136, 19, 22],
                },
                "swing_horizontal_learned_payloads": {
                    "on": "JgBAAGQAATEQMRARDRIOEw8wDhMPEQ4SDRMOEg8RDjMNEg4TDTMNMg4TDhEOEw0SDjMPEQ0zEDEOMg4yEDEOMg4ADQU=",
                    "left_mid": "JgBAAGQAATIQMQ4TDxEPEg0zDRMOEQ4TDRIQEQ8RDjIQEQ0TDjIOMg0TDhMNEg4TDTMOMg4SDhIPERAQDhMNEw8ADQU=",
                    "mid": "JgBAAGQAATMPMhAQDhMOEQ4yDxIOEg4SDxEQEA4SDjMPEQ4TDjINNA0SDhMPEQ4RDzIOMg8SDTMOEg4SDRMQMA8ADQU=",
                    "right_mid": "JgBAAGUAATEQMg4SDxEOEw0yDhIOEhARDRIOEw0TDzEQEA4SDjMNMw0TDhMNEg4SDjIOMw4yDhINExAQDjMOEhAADQU=",
                    "right_most": "JgBAAGQAATMPMQ4TDxEQEA4yDhMNEg4TDRIQEBARDjIQEA4TDTMNMw4SDhIOEw0SDjMOMg4yEDAOEg4TDzEPMRAADQU=",
                    "left_swing": "JgBAAGUAATIOMRAREBAOEw4yDhIOEw0SDhIPEQ8RDjMOEg0TDjMOMg8QDhMPEQ4yDhMNEg8SDxEOEQ4yEBEPMg0ADQU=",
                    "right_swing": "JgBAAGQAATIQMRAQDhIPEQ4yDhMOEQ8SDxEQEA4SDjMQEA4TDjIOMw0SDhIQEQ0zDRMQEQ8RDjMOEQ4zDzEQEQ0ADQU=",
                    "full_swing": "JgBAAGUAATIPMRARDRMQEBAxDhIQEBARDRMQEQ0SDjMOEg4SDTQNMw8RDhIPEQ4zDRIOMw4yEBEOMg4SDjMNMw0ADQU=",
                    "off": "JgBAAGUAATIPMg4RDhMNEw8xDhIPEQ0TDhINExARDTMNEw4RDjIOMg4TDRMOEg0yDhMQMA00DTMNMg4yDhMNEw8ADQU=",
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


def test_lg_protocol_engine_generates_distinct_payload_for_horizontal_off_on_toggle() -> None:
    engine = LGProtocolEngine(_pack())

    horizontal_off = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    horizontal_on = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "on",
        }
    )

    assert horizontal_off != horizontal_on


def test_lg_protocol_engine_supports_advanced_swing_modes_when_mapped() -> None:
    engine = LGProtocolEngine(_advanced_pack())

    highest = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "highest",
            "swing_horizontal": "left_mid",
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
            "swing_horizontal": "right_most",
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
                "swing_horizontal": "left_mid",
            }
        )


def test_lg_protocol_engine_off_on_horizontal_stays_available_with_learned_mapping() -> None:
    engine = LGProtocolEngine(_advanced_pack())

    horizontal_off = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    horizontal_on = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "on",
        }
    )

    assert horizontal_off != horizontal_on


def test_lg_protocol_engine_advertises_advanced_horizontal_only_when_configured() -> None:
    base_engine = LGProtocolEngine(_pack())
    advanced_engine = LGProtocolEngine(_advanced_pack())

    assert base_engine.supported_horizontal_swing_modes() == ["auto", "off", "on", "swing"]
    assert advanced_engine.supported_horizontal_swing_modes() == [
        "full_swing",
        "left_mid",
        "left_swing",
        "mid",
        "off",
        "on",
        "right_mid",
        "right_most",
        "right_swing",
    ]


def test_lg_protocol_engine_accepts_right_most_when_learned_mapping_exists() -> None:
    engine = LGProtocolEngine(_advanced_pack())

    payload = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "right_most",
        }
    )

    if isinstance(payload, list):
        assert len(payload) == 2
        assert all(isinstance(item, str) and item for item in payload)
    else:
        assert isinstance(payload, str)
        assert payload


def test_lg_protocol_engine_uses_learned_only_payload_for_advanced_horizontal() -> None:
    pack = _advanced_pack()
    engine = LGProtocolEngine(pack)

    learned_map = pack.commands["protocol_features"]["swing_horizontal_learned_payloads"]
    # Establish baseline so advanced horizontal is the only effective change.
    engine.resolve_command(
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

    assert engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "left_mid",
            "preset_mode": "none",
        }
    ) == learned_map["left_mid"]


def test_lg_protocol_engine_uses_learned_off_and_on_payloads() -> None:
    pack = _advanced_pack()
    engine = LGProtocolEngine(pack)

    learned_map = pack.commands["protocol_features"]["swing_horizontal_learned_payloads"]
    # Establish baseline so horizontal-only changes can emit learned-only payloads.
    engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "left_mid",
            "preset_mode": "none",
        }
    )

    assert engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
            "preset_mode": "none",
        }
    ) == learned_map["off"]

    assert engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "on",
            "preset_mode": "none",
        }
    ) == learned_map["on"]


def test_lg_protocol_engine_returns_sequence_for_advanced_horizontal_plus_temperature_change() -> None:
    pack = _advanced_pack()
    engine = LGProtocolEngine(pack)

    learned_map = pack.commands["protocol_features"]["swing_horizontal_learned_payloads"]
    commands = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 25,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "mid",
            "preset_mode": "none",
        }
    )

    assert isinstance(commands, list)
    assert len(commands) == 2
    assert commands[1] == learned_map["mid"]


def test_lg_protocol_engine_returns_sequence_for_advanced_horizontal_plus_vertical_change() -> None:
    pack = _advanced_pack()
    engine = LGProtocolEngine(pack)

    learned_map = pack.commands["protocol_features"]["swing_horizontal_learned_payloads"]
    commands = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "swing",
            "swing_horizontal": "right_mid",
            "preset_mode": "none",
        }
    )

    assert isinstance(commands, list)
    assert len(commands) == 2
    assert commands[1] == learned_map["right_mid"]


def test_lg_protocol_engine_returns_sequence_for_advanced_horizontal_plus_jet_change() -> None:
    pack = _advanced_pack()
    engine = LGProtocolEngine(pack)

    # Establish baseline non-jet state first.
    assert engine.resolve_command(
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

    learned_map = pack.commands["protocol_features"]["swing_horizontal_learned_payloads"]
    commands = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "right_swing",
            "preset_mode": "jet",
        }
    )

    assert isinstance(commands, list)
    assert len(commands) == 2
    assert commands[1] == learned_map["right_swing"]


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
