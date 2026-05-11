"""Unit tests for AeroState self-test service behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import custom_components.aerostate as integration
from custom_components.aerostate.const import (
    CONF_IR_PROVIDER,
    CONF_TUYA_CLOUD_ACCESS_ID,
    CONF_TUYA_CLOUD_ACCESS_SECRET,
    CONF_TUYA_CLOUD_ENDPOINT,
    CONF_TUYA_CLOUD_MODEL_PACK,
    CONF_TUYA_INFRARED_ID,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    CONF_TUYA_REMOTE_ID,
    IR_PROVIDER_TUYA,
    IR_PROVIDER_TUYA_CLOUD,
)
from custom_components.aerostate.providers.ir_types import IRCommand


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class _FakeConfigEntries:
    def __init__(self, entry) -> None:
        self._entry = entry

    def async_get_entry(self, entry_id: str):
        if self._entry and self._entry.entry_id == entry_id:
            return self._entry
        return None


class _FakeHass:
    def __init__(self, entry) -> None:
        self.bus = _FakeBus()
        self.config_entries = _FakeConfigEntries(entry)
        self.data = {"aerostate": {entry.entry_id: {}}} if entry else {"aerostate": {}}


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry_1",
        data={"broadlink_entity": "remote.test", "model_pack": "lg.test.v1"},
        options={},
    )


class _Engine:
    def __init__(self, _pack) -> None:
        pass

    def resolve_command(self, _state: dict) -> str:
        return "PAYLOAD"


class _IRM:
    async def probe_active_transport(self) -> bool:
        return True

    def effective_ir_mode(self) -> str:
        return "broadlink"

    def resolve_to_ir_commands(self, _state: dict):
        cmds = [IRCommand(name="cmd", payload="PAYLOAD", format="broadlink")]
        return cmds, "abcdefabcdef"

    async def async_send_commands(self, _cmds) -> None:
        return None


@pytest.mark.asyncio
async def test_self_test_uses_full_profile_and_emits_success_event(monkeypatch) -> None:
    entry = _entry()
    hass = _FakeHass(entry)
    call = SimpleNamespace(data={"entry_id": "entry_1", "profile": "full"})

    seen_profiles: list[str] = []

    monkeypatch.setattr(integration, "get_registry", lambda: SimpleNamespace(get=lambda _pid: object()))
    monkeypatch.setattr(integration, "create_ir_manager_from_entry", lambda *_a, **_kw: _IRM())
    monkeypatch.setattr(integration, "create_engine", lambda _pack: _Engine(_pack))
    monkeypatch.setattr(integration, "async_clear_validation_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integration, "async_report_validation_failed", lambda *_args, **_kwargs: None)

    def _states(_pack, profile: str):
        seen_profiles.append(profile)
        return [("off", {"power": False, "hvac_mode": "off", "target_temperature": 18})]

    monkeypatch.setattr(integration, "build_safe_validation_states", _states)

    await integration._async_handle_run_self_test(hass, call)

    assert seen_profiles == ["full"]
    assert hass.bus.events
    event_type, payload = hass.bus.events[-1]
    assert event_type == integration.EVENT_SELF_TEST_RESULT
    assert payload["success"] is True
    assert payload["profile"] == "full"
    assert payload["entry_id"] == "entry_1"
    assert payload["attempted"] == ["off"]
    assert payload["errors"] == []
    assert payload["mode_results"]["off"]["status"] == "passed"


@pytest.mark.asyncio
async def test_self_test_invalid_profile_falls_back_to_basic(monkeypatch) -> None:
    entry = _entry()
    hass = _FakeHass(entry)
    call = SimpleNamespace(data={"entry_id": "entry_1", "profile": "advanced"})

    seen_profiles: list[str] = []

    monkeypatch.setattr(integration, "get_registry", lambda: SimpleNamespace(get=lambda _pid: object()))
    monkeypatch.setattr(integration, "create_ir_manager_from_entry", lambda *_a, **_kw: _IRM())
    monkeypatch.setattr(integration, "create_engine", lambda _pack: _Engine(_pack))
    monkeypatch.setattr(integration, "async_clear_validation_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integration, "async_report_validation_failed", lambda *_args, **_kwargs: None)

    def _states(_pack, profile: str):
        seen_profiles.append(profile)
        return [("off", {"power": False, "hvac_mode": "off", "target_temperature": 18})]

    monkeypatch.setattr(integration, "build_safe_validation_states", _states)

    await integration._async_handle_run_self_test(hass, call)

    assert seen_profiles == ["basic"]
    _, payload = hass.bus.events[-1]
    assert payload["profile"] == "basic"
    assert payload["mode_results"]["off"]["status"] == "passed"


@pytest.mark.asyncio
async def test_self_test_tuya_path_sends_off_and_returns(monkeypatch) -> None:
    entry = SimpleNamespace(
        entry_id="entry_tuya",
        data={
            CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
            CONF_TUYA_MODEL_PACK: "tuya.test.v1",
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
        },
        options={},
    )
    hass = _FakeHass(entry)
    call = SimpleNamespace(data={"entry_id": "entry_tuya", "profile": "full"})

    sent_states: list[dict] = []

    class _TuyaManager:
        async def probe_transport(self) -> bool:
            return True

        async def async_send_climate_state(self, state: dict) -> None:
            sent_states.append(state)

    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_ir_manager.create_tuya_ir_manager_from_entry",
        lambda *_args, **_kwargs: _TuyaManager(),
    )
    monkeypatch.setattr(integration, "async_clear_validation_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integration, "async_report_validation_failed", lambda *_args, **_kwargs: None)

    await integration._async_handle_run_self_test(hass, call)

    assert sent_states == [{"hvac_mode": "off"}]
    event_type, payload = hass.bus.events[-1]
    assert event_type == integration.EVENT_SELF_TEST_RESULT
    assert payload["success"] is True
    assert payload["transport"] == "tuya_ir_learned_codes"
    assert payload["attempted"] == ["off"]


@pytest.mark.asyncio
async def test_self_test_tuya_cloud_path_sends_off_and_returns(monkeypatch) -> None:
    entry = SimpleNamespace(
        entry_id="entry_tuya_cloud",
        data={
            CONF_IR_PROVIDER: IR_PROVIDER_TUYA_CLOUD,
            CONF_TUYA_CLOUD_ENDPOINT: "https://openapi.tuyain.com",
            CONF_TUYA_CLOUD_ACCESS_ID: "access-id",
            CONF_TUYA_CLOUD_ACCESS_SECRET: "access-secret",
            CONF_TUYA_INFRARED_ID: "ir-device-id",
            CONF_TUYA_REMOTE_ID: "remote-id",
            CONF_TUYA_CLOUD_MODEL_PACK: "tuya_cloud.daikin_ac.v1",
        },
        options={},
    )
    hass = _FakeHass(entry)
    call = SimpleNamespace(data={"entry_id": "entry_tuya_cloud", "profile": "full"})

    sent_states: list[dict] = []

    class _TuyaCloudManager:
        async def probe_transport(self) -> bool:
            return True

        async def async_send_climate_state(self, state: dict) -> None:
            sent_states.append(state)

    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_cloud_ac.create_tuya_cloud_ac_manager_from_entry",
        lambda *_args, **_kwargs: _TuyaCloudManager(),
    )
    monkeypatch.setattr(integration, "async_clear_validation_failed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integration, "async_report_validation_failed", lambda *_args, **_kwargs: None)

    await integration._async_handle_run_self_test(hass, call)

    assert sent_states == [{"hvac_mode": "off"}]
    event_type, payload = hass.bus.events[-1]
    assert event_type == integration.EVENT_SELF_TEST_RESULT
    assert payload["success"] is True
    assert payload["transport"] == "tuya_cloud_ac_code_library"
    assert payload["attempted"] == ["off"]
