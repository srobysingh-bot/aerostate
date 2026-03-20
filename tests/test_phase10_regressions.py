"""Regression tests for options flow and runtime validation setup paths."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

import custom_components.aerostate as integration


class _FakeConfigEntries:
    def __init__(self) -> None:
        self.forward_calls: list[tuple[object, list[object]]] = []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forward_calls.append((entry, platforms))


class _FakeHassForSetup:
    def __init__(self) -> None:
        self.data: dict = {}
        self.config_entries = _FakeConfigEntries()


@pytest.mark.asyncio
async def test_async_setup_entry_calls_sync_runtime_validator_without_await(monkeypatch) -> None:
    """Ensure setup works when runtime validator is a synchronous function."""
    hass = _FakeHassForSetup()
    entry = SimpleNamespace(entry_id="entry_1", data={}, options={})

    class _Registry:
        @staticmethod
        def list_all():
            return ["pack"]

    calls: list[tuple[object, object]] = []

    monkeypatch.setattr(integration, "get_registry", lambda: _Registry())

    def _sync_runtime_validator(hass_arg, entry_arg):
        calls.append((hass_arg, entry_arg))

    monkeypatch.setattr(integration, "async_validate_entry_runtime", _sync_runtime_validator)

    ok = await integration.async_setup_entry(hass, entry)

    assert ok is True
    assert entry.entry_id in hass.data[integration.DOMAIN]
    assert calls == [(hass, entry)]


@pytest.mark.skipif(importlib.util.find_spec("homeassistant") is None, reason="homeassistant not installed")
def test_options_flow_constructor_uses_private_config_entry_reference() -> None:
    """Ensure options flow no longer assigns to read-only config_entry property."""
    from custom_components.aerostate.options_flow import AeroStateOptionsFlowHandler

    config_entry = SimpleNamespace(
        entry_id="entry_1",
        data={"brand": "LG", "model_pack": "lg.pc09sq_nsj.v1", "broadlink_entity": "remote.test"},
        options={},
    )

    handler = AeroStateOptionsFlowHandler(config_entry)

    assert handler._config_entry is config_entry


@pytest.mark.skipif(importlib.util.find_spec("homeassistant") is None, reason="homeassistant not installed")
@pytest.mark.asyncio
async def test_options_flow_rejects_invalid_model_pack(monkeypatch) -> None:
    from custom_components.aerostate.options_flow import AeroStateOptionsFlowHandler

    config_entry = SimpleNamespace(
        entry_id="entry_1",
        data={"brand": "LG", "model_pack": "lg.pc09sq_nsj.protocol.v1", "broadlink_entity": "remote.test"},
        options={},
    )

    class _Registry:
        @staticmethod
        def list_brand_packs(_brand: str):
            return [
                SimpleNamespace(
                    pack_id="lg.pc09sq_nsj.protocol.v1",
                    models=["PC09SQ NSJ"],
                    verified=True,
                    notes="verified",
                    capabilities=SimpleNamespace(swing_vertical_modes=["on"], swing_horizontal_modes=["off", "on"]),
                    engine_type="lg_protocol",
                )
            ]

        @staticmethod
        def get(_pack_id: str):
            raise ValueError("missing pack")

    class _Entries:
        @staticmethod
        def async_entries(_domain: str):
            return []

        @staticmethod
        def async_update_entry(*_args, **_kwargs):
            raise AssertionError("should not update entry for invalid pack")

        @staticmethod
        async def async_reload(*_args, **_kwargs):
            raise AssertionError("should not reload entry for invalid pack")

    handler = AeroStateOptionsFlowHandler(config_entry)
    handler.hass = SimpleNamespace(config_entries=_Entries())

    monkeypatch.setattr("custom_components.aerostate.options_flow.get_registry", lambda: _Registry())

    result = await handler.async_step_init({"broadlink_entity": "remote.test", "model_pack": "lg.missing.v9"})
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "invalid_model_pack"}
