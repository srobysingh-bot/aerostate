"""Tuya IR helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.ir_types import IRCommand
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider
from custom_components.aerostate.providers.tuya_ir_manager import TuyaIRManager
from custom_components.aerostate.providers.tuya_ir_transport import TuyaIRTransport
from custom_components.aerostate.packs.tuya.schema import TuyaIRCommand, TuyaIRPack


def test_normalize_hex_strips_non_hex_and_requires_even_length() -> None:
    assert TuyaIRProvider.normalize_hex_payload("aa:bb cc dd") == "aabbccdd"
    assert TuyaIRProvider.normalize_hex_payload("aa bb") == "aabb"
    with pytest.raises(ValueError):
        TuyaIRProvider.normalize_hex_payload("aaa")


@pytest.mark.asyncio
async def test_send_prefers_localtuya_set_dp_when_configured_and_service_present() -> None:
    hass = MagicMock()

    def _has(domain: str, service: str) -> bool:
        return domain == "localtuya" and service == "set_dp"

    hass.services.has_service = MagicMock(side_effect=_has)
    spy = AsyncMock()
    hass.services.async_call = spy

    tp = TuyaIRProvider(
        hass,
        "remote.living_room",
        blocking=False,
        entry_id="entry_living",
        localtuya_device_id="bfb5e7c012345678abcd",
        ir_dp=201,
    )
    await tp.send_command(IRCommand(name="cmd", payload="aabb", format="tuya"))

    spy.assert_called_once_with(
        "localtuya",
        "set_dp",
        {"device_id": "bfb5e7c012345678abcd", "dp": 201, "value": "aabb"},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_send_falls_back_to_remote_when_localtuya_unavailable() -> None:
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    spy = AsyncMock()
    hass.services.async_call = spy

    tp = TuyaIRProvider(hass, "remote.x", blocking=False, localtuya_device_id="abc")
    await tp.send_command(IRCommand(name="cmd", payload="ccddee", format="tuya"))

    spy.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.x", "command": "ccddee"},
        blocking=False,
    )


@pytest.mark.asyncio
async def test_standalone_tuya_transport_sends_dp201_json_string() -> None:
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=True)
    spy = AsyncMock()
    hass.services.async_call = spy

    transport = TuyaIRTransport(
        hass,
        device_id="bf123",
        local_key="secret",
        host="192.0.2.10",
        send_blocking=False,
    )

    await transport.async_send_command("AQID")

    spy.assert_called_once()
    domain, service, data = spy.call_args.args
    assert (domain, service) == ("localtuya", "set_dp")
    assert data["device_id"] == "bf123"
    assert data["dp"] == "201"
    assert data["value"] == '{"control": "send_ir", "head": "", "key1": "AQID", "type": 0, "delay": 300}'
    assert spy.call_args.kwargs == {"blocking": False}


@pytest.mark.asyncio
async def test_standalone_tuya_manager_resolves_state_to_key1_without_broadlink() -> None:
    hass = MagicMock()
    transport = MagicMock(spec=TuyaIRTransport)
    transport.async_send_command = AsyncMock()
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

    manager = TuyaIRManager(hass, pack, transport)
    await manager.async_send_climate_state(
        {
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "swing_vertical": "off",
        },
    )

    transport.async_send_command.assert_awaited_once_with("COOLKEY")
