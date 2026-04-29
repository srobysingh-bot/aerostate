"""Unit tests for AeroState self-test service behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import custom_components.aerostate as integration
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
