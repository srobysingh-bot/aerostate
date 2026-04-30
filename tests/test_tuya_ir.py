"""Tuya IR helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.ir_types import IRCommand
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider


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
