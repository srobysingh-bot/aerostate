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


def test_akb75415308_tuya_pack_has_stateful_localtuya_rc_codes() -> None:
    pack = get_tuya_pack("lg.akb75415308.localtuya_rc.protocol.v1")
    model_pack = pack.to_model_pack()

    assert pack.native_base64 is False
    assert pack.requires_learned_codes is False
    assert pack.transport == "localtuya_rc"
    assert pack.protocol == "stateful"
    assert len(CODES) == 454
    assert len(pack.commands) == 454
    assert model_pack.transport == "localtuya_rc"
    assert model_pack.capabilities.hvac_modes == ["cool", "heat", "dry", "auto", "fan_only"]
    assert model_pack.capabilities.fan_modes == ["auto", "low", "mid_low", "mid", "mid_high", "high"]
    assert model_pack.capabilities.swing_vertical_modes == ["off", "swing"]
    assert model_pack.capabilities.swing_horizontal_modes == ["off", "swing"]
    assert pack.resolve_by_label("power_on") == CODES["power_on"]
    assert pack.resolve_by_label("power_off") == CODES["power_off"]
    assert pack.resolve_by_label("swing_vertical_toggle") == CODES["swing_vertical_toggle"]
    assert pack.resolve_by_label("swing_horizontal_toggle") == CODES["swing_horizontal_toggle"]
    assert pack.resolve_by_label("cool_t24_fauto") == CODES["cool_t24_fauto"]
    assert pack.resolve_by_label("cool_t24_flow") == CODES["cool_t24_flow"]
    assert pack.resolve_by_label("heat_t24_fmid_high") == CODES["heat_t24_fmid_high"]
    assert pack.resolve_by_label("dry_t24_fhigh") == CODES["dry_t24_fhigh"]
    assert pack.resolve_by_label("auto_t24_fauto") == CODES["auto_t24_fauto"]
    assert pack.resolve_by_label("fan_only_t25_fmid") == CODES["fan_only_t25_fmid"]
