"""Regression tests for learned Tuya IR manager behavior."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.tuya_ir_manager import TuyaIRManager
from custom_components.aerostate.packs.tuya.schema import TuyaIRCommand, TuyaIRPack


class _LearnedStore:
    def __init__(self, values: dict[tuple[str, str], str] | None = None) -> None:
        self.values = values or {}
        self.loaded = False

    async def async_load(self) -> None:
        self.loaded = True

    async def async_save(self, entry_id: str, label: str, raw_payload: str) -> None:
        self.values[(entry_id, label)] = raw_payload

    def get(self, entry_id: str, label: str) -> str | None:
        return self.values.get((entry_id, label))

    async def async_delete(self, entry_id: str, label: str) -> None:
        self.values.pop((entry_id, label), None)

    def list_labels(self, entry_id: str) -> list[str]:
        return sorted(label for stored_entry, label in self.values if stored_entry == entry_id)


def _pack(key1: str) -> TuyaIRPack:
    return TuyaIRPack(
        pack_id="tuya.test.v1",
        brand="LG",
        models=["TEST"],
        verified=False,
        notes="test",
        min_temperature=16,
        max_temperature=30,
        commands=[
            TuyaIRCommand(
                label="cool_20_auto_swing_off",
                hvac_mode="cool",
                temperature=20,
                fan_mode="auto",
                swing_on=False,
                key1=key1,
            ),
        ],
    )


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get.return_value = SimpleNamespace(state="on", attributes={})
    return hass


def test_placeholder_detection_decodes_real_placeholder_payloads() -> None:
    placeholder = base64.b64encode(b"PLACEHOLDER:cool_20_auto_swing_off").decode("ascii")

    assert TuyaIRManager._is_placeholder("AA==") is True
    assert TuyaIRManager._is_placeholder("AQ==") is True
    assert TuyaIRManager._is_placeholder(placeholder) is True
    assert TuyaIRManager._is_placeholder("UkVBTF9DT0RF") is False


@pytest.mark.asyncio
async def test_raw_send_path_passes_raw_command_directly() -> None:
    hass = _hass()
    manager = TuyaIRManager(hass, "remote.test_ir", _pack("UkVBTA=="))

    await manager._send_command("raw:3060,9586,469,1562")

    hass.services.async_call.assert_awaited_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.test_ir", "command": "raw:3060,9586,469,1562"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_b64_send_path_preserves_prefixed_and_wraps_unprefixed_payloads() -> None:
    hass = _hass()
    manager = TuyaIRManager(hass, "remote.test_ir", _pack("UkVBTA=="))

    await manager._send_command("b64:READY")
    await manager._send_command("UkVBTA==")

    assert hass.services.async_call.await_args_list[0].args == (
        "remote",
        "send_command",
        {"entity_id": "remote.test_ir", "command": "b64:READY"},
    )
    assert hass.services.async_call.await_args_list[1].args == (
        "remote",
        "send_command",
        {"entity_id": "remote.test_ir", "command": "b64:UkVBTA=="},
    )


@pytest.mark.asyncio
async def test_learned_code_lookup_takes_priority_over_pack_payload() -> None:
    hass = _hass()
    store = _LearnedStore({("entry1", "cool_20_auto_swing_off"): "raw:1,2,3"})
    manager = TuyaIRManager(
        hass,
        "remote.test_ir",
        _pack("UkVBTF9QQUNL"),
        entry_id="entry1",
        learned_store=store,
    )

    await manager.async_send_climate_state(
        {
            "hvac_mode": "cool",
            "target_temperature": 20,
            "fan_mode": "auto",
            "swing_vertical": "off",
        },
    )

    assert store.loaded is True
    hass.services.async_call.assert_awaited_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.test_ir", "command": "raw:1,2,3"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_missing_learned_code_with_placeholder_raises_clear_error() -> None:
    hass = _hass()
    placeholder = base64.b64encode(b"PLACEHOLDER:cool_20_auto_swing_off").decode("ascii")
    manager = TuyaIRManager(
        hass,
        "remote.test_ir",
        _pack(placeholder),
        entry_id="entry1",
        learned_store=_LearnedStore(),
    )

    with pytest.raises(KeyError, match="IR command not learned yet for: cool_20_auto_swing_off"):
        await manager.async_send_climate_state(
            {
                "hvac_mode": "cool",
                "target_temperature": 20,
                "fan_mode": "auto",
                "swing_vertical": "off",
            },
        )

    hass.services.async_call.assert_not_awaited()
