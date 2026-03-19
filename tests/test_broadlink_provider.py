"""Unit tests for Broadlink provider transport behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.broadlink import BroadlinkProvider


class _FakeServices:
    def __init__(self, available: bool = True) -> None:
        self.calls: list[tuple[str, str, dict, bool]] = []
        self._available = available

    def has_service(self, domain: str, service: str) -> bool:
        return self._available and domain == "remote" and service == "send_command"

    async def async_call(self, domain: str, service: str, data: dict, blocking: bool = False) -> None:
        self.calls.append((domain, service, data, blocking))


class _FakeStates:
    def __init__(self, state: str = "on", include_entity: bool = True) -> None:
        self._state = state
        self._include_entity = include_entity

    def get(self, entity_id: str):
        class _State:
            def __init__(self, value: str) -> None:
                self.state = value

        if entity_id == "remote.test" and self._include_entity:
            return _State(self._state)
        return None


class _FakeHass:
    def __init__(self, state: str = "on", service_available: bool = True, include_entity: bool = True) -> None:
        self.services = _FakeServices(service_available)
        self.states = _FakeStates(state, include_entity)


@pytest.mark.asyncio
async def test_send_base64_uses_b64_prefix() -> None:
    hass = _FakeHass()
    provider = BroadlinkProvider(hass, "remote.test")

    await provider.send_base64("ABCDEF")

    _, _, data, _ = hass.services.calls[0]
    assert data["command"] == "b64:ABCDEF"
    assert "command_type" not in data


@pytest.mark.asyncio
async def test_test_connection_with_payload_uses_send_path() -> None:
    hass = _FakeHass()
    provider = BroadlinkProvider(hass, "remote.test")

    ok = await provider.test_connection(payload="ABCDEF")
    assert ok is True
    _, _, data, _ = hass.services.calls[0]
    assert data["command"] == "b64:ABCDEF"


@pytest.mark.asyncio
async def test_test_connection_fails_when_service_missing() -> None:
    hass = _FakeHass(service_available=False)
    provider = BroadlinkProvider(hass, "remote.test")

    ok = await provider.test_connection()
    assert ok is False


@pytest.mark.asyncio
async def test_test_connection_fails_when_entity_missing() -> None:
    hass = _FakeHass(include_entity=False)
    provider = BroadlinkProvider(hass, "remote.test")

    ok = await provider.test_connection()
    assert ok is False


@pytest.mark.asyncio
async def test_test_connection_fails_when_entity_unavailable() -> None:
    hass = _FakeHass(state="unavailable")
    provider = BroadlinkProvider(hass, "remote.test")

    ok = await provider.test_connection()
    assert ok is False
