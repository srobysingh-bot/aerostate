"""Tuya IR helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.packs.tuya.lg_akb75415308_tuya_codes import CODES
from custom_components.aerostate.packs.tuya.registry import get_tuya_pack
from custom_components.aerostate.providers.ir_types import IRCommand
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider


def test_normalize_hex_strips_non_hex_and_requires_even_length() -> None:
    assert TuyaIRProvider.normalize_hex_payload("aa:bb cc dd") == "aabbccdd"
    assert TuyaIRProvider.normalize_hex_payload("aa bb") == "aabb"
    with pytest.raises(ValueError):
        TuyaIRProvider.normalize_hex_payload("aaa")


@pytest.mark.asyncio
async def test_legacy_tuya_provider_sends_remote_command() -> None:
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    spy = AsyncMock()
    hass.services.async_call = spy

    tp = TuyaIRProvider(hass, "remote.x", blocking=False)
    await tp.send_command(IRCommand(name="cmd", payload="ccddee", format="tuya"))

    spy.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.x", "command": "ccddee"},
        blocking=False,
    )


def test_tuya_pack_resolve_cool_24_auto_swing_off() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    assert pack.resolve("cool", 24, "auto", False)


def test_tuya_pack_resolve_off() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    assert pack.resolve("off", None, None, False)


def test_tuya_pack_resolve_unknown_returns_none() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    assert pack.resolve("cool", 99, "auto", False) is None


def test_tuya_pack_has_complete_lg_placeholder_matrix() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    labels = {cmd.label for cmd in pack.commands}

    assert len(pack.commands) >= 589
    assert "off" in labels
    assert "cool_16_f1_swing_off" in labels
    assert "cool_30_auto_swing_on" in labels
    assert "heat_16_f1_swing_off" in labels
    assert "heat_30_auto_swing_on" in labels
    assert "dry_16_auto_swing_off" in labels
    assert "dry_30_auto_swing_on" in labels
    assert "fan_f1_swing_off" in labels
    assert "fan_auto_swing_on" in labels
    assert "auto_16_f1_swing_off" in labels
    assert "auto_30_auto_swing_on" in labels
    assert {"turbo_on", "turbo_off", "sleep_on", "sleep_off", "eco_on", "eco_off"} <= labels


def test_akb75415308_tuya_pack_has_generated_native_b64_matrix() -> None:
    pack = get_tuya_pack("lg.akb75415308.tuya.protocol.v1")
    model_pack = pack.to_model_pack()

    assert pack.native_base64 is True
    assert pack.requires_learned_codes is False
    assert len(CODES) == 472
    assert len(pack.commands) == 472
    assert model_pack.transport == "tuya_remote"
    assert model_pack.capabilities.hvac_modes == ["cool", "heat", "dry", "fan_only", "auto"]
    assert model_pack.capabilities.fan_modes == ["auto", "low", "mid", "high", "highest"]
    assert model_pack.capabilities.swing_vertical_modes == ["off", "on"]
    assert pack.resolve("cool", 24, "auto", False, previously_off=True) == CODES["cool_on_t24_fauto"]
    assert pack.resolve("cool", 24, "auto", False, previously_off=False) == CODES["cool_t24_fauto"]
    assert pack.resolve("fan_only", 24, "high", False, previously_off=True) == CODES["fan_on_fhigh"]
    assert pack.resolve_swing_toggle() == CODES["swing_toggle"]
