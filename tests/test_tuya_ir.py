"""Tuya IR helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.ir_types import IRCommand
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider
from custom_components.aerostate.providers.tuya_ir_manager import TuyaIRManager
from custom_components.aerostate.packs.tuya.registry import get_tuya_pack
from custom_components.aerostate.packs.tuya.schema import TuyaIRCommand, TuyaIRPack


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


@pytest.mark.asyncio
async def test_standalone_tuya_manager_resolves_state_to_key1_without_broadlink() -> None:
    hass = MagicMock()
    spy = AsyncMock()
    hass.services.async_call = spy
    pack = TuyaIRPack(
        pack_id="tuya.test.v1",
        brand="LG",
        models=["TEST"],
        verified=False,
        notes="test",
        min_temperature=16,
        max_temperature=30,
        commands=[
            TuyaIRCommand(label="off", hvac_mode="off", key1="OFFKEY"),
            TuyaIRCommand(
                label="cool_24_auto_swing_off",
                hvac_mode="cool",
                temperature=24,
                fan_mode="auto",
                swing_on=False,
                key1="COOLKEY",
            ),
        ],
    )

    manager = TuyaIRManager(hass, "remote.test_ir", pack)
    await manager.async_send_climate_state(
        {
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
        },
    )

    spy.assert_awaited_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.test_ir", "command": "b64:COOLKEY"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_tuya_manager_probe_checks_remote_entity_state() -> None:
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state="on")
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")

    manager = TuyaIRManager(hass, "remote.test_ir", pack)

    assert await manager.probe_transport() is True
    hass.states.get.assert_called_once_with("remote.test_ir")


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


@pytest.mark.asyncio
async def test_tuya_manager_raises_on_missing_command() -> None:
    pack = TuyaIRPack(
        pack_id="tuya.empty.v1",
        brand="LG",
        models=["TEST"],
        verified=False,
        notes="empty",
        min_temperature=16,
        max_temperature=30,
        commands=[],
    )
    manager = TuyaIRManager(MagicMock(), "remote.test_ir", pack)

    with pytest.raises(KeyError):
        await manager.async_send_climate_state(
            {
                "hvac_mode": "cool",
                "target_temperature": 24,
                "fan_mode": "auto",
                "swing_vertical": "off",
            },
        )
