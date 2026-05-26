"""Unit tests for protocol-driven Daikin engine payload generation."""

from __future__ import annotations

import base64

import pytest

from custom_components.aerostate.engines.daikin_engine import DaikinEngine
from custom_components.aerostate.packs.loader import load_pack_from_path
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="daikin.protocol.test.v1",
        brand="Daikin",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=10,
        max_temperature=32,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "f1", "f2", "f3", "f4", "f5", "quiet"],
            swing_vertical_modes=[
                "off",
                "auto",
                "position_low",
                "position_mid",
                "position_high",
            ],
            swing_horizontal_modes=["off", "auto", "left", "center", "right"],
            presets=[],
            preset_modes=[],
            supports_jet=False,
        ),
        engine_type="daikin_protocol",
        commands={"off": "protocol_generated"},
        verified=False,
    )


def _decode_broadlink_units(b64_payload: str) -> list[int]:
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


def test_daikin_protocol_engine_builds_complete_state_frame() -> None:
    engine = DaikinEngine(_pack())

    frame = engine._build_frame(
        power=True,
        mode="cool",
        target_temperature=24,
        fan_mode="f3",
        swing_vertical="position_mid",
        swing_horizontal="right",
    )

    assert len(frame) == 35
    assert frame[:7] == [0x11, 0xDA, 0x27, 0x00, 0xC5, 0x00, 0x00]
    assert frame[7] == sum(frame[:7]) & 0xFF
    assert frame[15] == sum(frame[8:15]) & 0xFF
    assert frame[21] == 0x39
    assert frame[22] == 48
    assert frame[24] == 0x5F
    assert frame[25] == 0x0F
    assert frame[34] == sum(frame[16:34]) & 0xFF


def test_daikin_protocol_engine_generates_broadlink_payload_from_state() -> None:
    engine = DaikinEngine(_pack())

    payload = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )

    assert isinstance(payload, str) and payload
    packet = base64.b64decode(payload)
    assert packet[:2] == b"\x26\x00"
    units = _decode_broadlink_units(payload)
    assert units[:10] == [14, 14, 14, 14, 14, 14, 14, 14, 14, 966]


def test_daikin_protocol_engine_generates_distinct_full_frames_for_temp_mode_fan_swing() -> None:
    engine = DaikinEngine(_pack())

    base = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    temp = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 25,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    heat = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "heat",
            "target_temperature": 25,
            "fan_mode": "auto",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    fan = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "heat",
            "target_temperature": 25,
            "fan_mode": "f5",
            "swing_vertical": "off",
            "swing_horizontal": "off",
        }
    )
    swing = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "heat",
            "target_temperature": 25,
            "fan_mode": "f5",
            "swing_vertical": "position_high",
            "swing_horizontal": "left",
        }
    )

    assert len({base, temp, heat, fan, swing}) == 5


def test_daikin_protocol_engine_generates_off_as_full_state_frame() -> None:
    engine = DaikinEngine(_pack())

    off_frame = engine._build_frame(
        power=False,
        mode="cool",
        target_temperature=24,
        fan_mode="auto",
        swing_vertical="off",
        swing_horizontal="off",
    )
    on_frame = engine._build_frame(
        power=True,
        mode="cool",
        target_temperature=24,
        fan_mode="auto",
        swing_vertical="off",
        swing_horizontal="off",
    )

    assert off_frame[21] == 0x38
    assert on_frame[21] == 0x39
    assert engine.resolve_command({"power": False, "hvac_mode": "off", "target_temperature": 24})


def test_daikin_protocol_engine_exposes_extended_swing_model_with_safe_fallback() -> None:
    engine = DaikinEngine(_pack())

    assert engine.supported_vertical_swing_modes() == [
        "off",
        "auto",
        "position_low",
        "position_mid",
        "position_high",
    ]
    assert engine.supported_horizontal_swing_modes() == ["off", "auto", "left", "center", "right"]
    assert engine._swing_protocol_code("off", axis="vertical") == 0x00
    assert engine._swing_protocol_code("position_low", axis="vertical") == 0x0F
    assert engine._swing_protocol_code("center", axis="horizontal") == 0x0F


def test_daikin_protocol_engine_accepts_configured_swing_protocol_overrides() -> None:
    pack = _pack()
    pack.commands = {
        "off": "protocol_generated",
        "protocol_features": {
            "swing_vertical_protocol_values": {"position_low": 0x03},
            "swing_horizontal_protocol_values": {"left": 0x04},
        },
    }
    engine = DaikinEngine(pack)

    frame = engine._build_frame(
        power=True,
        mode="cool",
        target_temperature=24,
        fan_mode="f3",
        swing_vertical="position_low",
        swing_horizontal="left",
    )

    assert frame[24] == 0x53
    assert frame[25] == 0x04


def test_daikin_protocol_engine_checksum_validates_frame_length_and_profile() -> None:
    engine = DaikinEngine(_pack())

    with pytest.raises(ValueError, match="35 bytes"):
        engine._checksum([0] * 34)

    with pytest.raises(ValueError, match="checksum profile"):
        engine._checksum([0] * 35, profile="future")


def test_daikin_protocol_engine_rejects_invalid_state() -> None:
    engine = DaikinEngine(_pack())

    with pytest.raises(ValueError, match="hvac mode"):
        engine.resolve_command({"power": True, "hvac_mode": "eco"})

    with pytest.raises(ValueError, match="fan mode"):
        engine.resolve_command({"power": True, "hvac_mode": "cool", "fan_mode": "turbo"})

    with pytest.raises(ValueError, match="swing mode"):
        engine.resolve_command(
            {
                "power": True,
                "hvac_mode": "cool",
                "target_temperature": 24,
                "swing_vertical": "middle",
            }
        )


def test_builtin_daikin_protocol_pack_loads() -> None:
    pack = load_pack_from_path(
        "custom_components/aerostate/packs/builtin/daikin/daikin_protocol_v1.json"
    )

    assert pack.pack_id == "daikin.protocol.v1"
    assert pack.engine_type == "daikin_protocol"
    assert pack.brand == "Daikin"
    assert pack.commands == {"off": "protocol_generated"}
    assert pack.capabilities.swing_vertical_modes == [
        "off",
        "auto",
        "position_low",
        "position_mid",
        "position_high",
    ]
    assert pack.capabilities.swing_horizontal_modes == ["off", "auto", "left", "center", "right"]
