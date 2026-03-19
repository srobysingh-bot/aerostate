"""Unit tests for diagnostics coverage output content."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate import diagnostics
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


class _FakeStates:
    def __init__(self) -> None:
        self._entities = {}

    def add(self, entity_id: str, state: str, attributes: dict | None = None) -> None:
        self._entities[entity_id] = SimpleNamespace(state=state, attributes=attributes or {})

    def get(self, entity_id: str):
        return self._entities.get(entity_id)


class _FakeEntityRegistry:
    def __init__(self, entity_id: str | None = None) -> None:
        self._entity_id = entity_id

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str):
        return self._entity_id


class _FakeHass:
    def __init__(self) -> None:
        self.states = _FakeStates()
        self.data = {"aerostate": {"entry1": {"last_self_test": {"success": True}}}}
        self.services = SimpleNamespace(has_service=lambda *_: True)


class _FakeRegistry:
    def __init__(self, pack: ModelPack) -> None:
        self._pack = pack

    def get(self, pack_id: str) -> ModelPack:
        return self._pack


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=20,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={"off": "OFF", "cool": {"auto": {"18": "X"}}},
        verified=True,
        notes="verified",
        physically_verified_modes=["cool"],
        mode_status={"cool": "verified"},
    )


@pytest.mark.asyncio
async def test_diagnostics_includes_coverage_and_validation(monkeypatch) -> None:
    pack = _pack()
    hass = _FakeHass()
    entry = SimpleNamespace(
        entry_id="entry1",
        title="Test",
        data={"model_pack": "lg.test.v1", "broadlink_entity": "remote.test"},
        options={"temperature_sensor": "sensor.temp", "humidity_sensor": "sensor.hum", "power_sensor": "sensor.power"},
    )

    monkeypatch.setattr(diagnostics, "get_registry", lambda: _FakeRegistry(pack))
    monkeypatch.setattr(diagnostics.er, "async_get", lambda _h: _FakeEntityRegistry())

    class _Provider:
        send_calls = 0

        def __init__(self, *_):
            pass

        async def test_connection(self, payload=None):
            return True

        async def send_base64(self, _payload):
            _Provider.send_calls += 1

    monkeypatch.setattr(diagnostics, "BroadlinkProvider", _Provider)

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    resolved = result["resolved"]
    assert resolved["pack_id"] == "lg.test.v1"
    assert resolved["pack_verified"] is True
    assert resolved["pack_mode_truth"]["cool"]["physically_verified"] is True
    assert resolved["physically_verified_modes"] == ["cool"]
    assert resolved["experimental_modes"] == []
    assert resolved["supported_modes"] == ["cool"]
    assert resolved["supported_swing_vertical"] == []
    assert resolved["supported_swing_horizontal"] == []
    assert resolved["broadlink_entity"] == "remote.test"
    assert resolved["linked_temperature_sensor"] == "sensor.temp"
    assert resolved["validation_readiness"]["transport_available"] is True
    assert "available_temperature_points" in resolved["coverage"]
    assert _Provider.send_calls == 0


@pytest.mark.asyncio
async def test_diagnostics_entity_lookup_via_registry(monkeypatch) -> None:
    pack = _pack()
    hass = _FakeHass()
    hass.states.add("climate.living_room_ac", "cool", {"fan_mode": "auto"})
    entry = SimpleNamespace(
        entry_id="entry1",
        title="Living",
        data={"model_pack": "lg.test.v1", "broadlink_entity": "remote.test"},
        options={"temperature_sensor": "sensor.temp"},
    )

    monkeypatch.setattr(diagnostics, "get_registry", lambda: _FakeRegistry(pack))
    monkeypatch.setattr(
        diagnostics.er,
        "async_get",
        lambda _h: _FakeEntityRegistry("climate.living_room_ac"),
    )

    class _Provider:
        def __init__(self, *_):
            pass

        async def test_connection(self, payload=None):
            return True

    monkeypatch.setattr(diagnostics, "BroadlinkProvider", _Provider)

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    assert result["entity"]["entity_id"] == "climate.living_room_ac"
    assert result["entity"]["state"] == "cool"
    assert result["entity"]["attributes"]["fan_mode"] == "auto"
