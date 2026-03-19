"""Unit tests for protocol-driven LG engine payload generation."""

from __future__ import annotations

import base64

from custom_components.aerostate.engines.lg_engine import LGProtocolEngine
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "low", "mid", "high"],
            swing_vertical_modes=["off", "on"],
            swing_horizontal_modes=["off", "on"],
            presets=[],
        ),
        engine_type="lg_protocol",
        commands={"off": "protocol_generated"},
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
