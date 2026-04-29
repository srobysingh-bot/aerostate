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


class _DiagIR:
    async def probe_active_transport(self) -> bool:
        return True

    def effective_ir_mode(self) -> str:
        return "broadlink"


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


def _protocol_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "f1", "f2", "f3", "f4", "f5"],
            swing_vertical_modes=["off", "on", "highest"],
            swing_horizontal_modes=["off", "on"],
            presets=[],
            preset_modes=[],
            supports_jet=False,
        ),
        engine_type="lg_protocol",
        commands={"off": "protocol_generated"},
        verified=True,
        notes="Production verified protocol pack",
        physically_verified_modes=["auto", "heat", "cool", "dry", "fan_only"],
        mode_status={
            "auto": "verified",
            "heat": "verified",
            "cool": "verified",
            "dry": "verified",
            "fan_only": "verified",
        },
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

    monkeypatch.setattr(diagnostics, "create_ir_manager_from_entry", lambda *_a, **_k: _DiagIR())

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    resolved = result["resolved"]
    assert resolved["pack_id"] == "lg.test.v1"
    assert resolved["selected_pack_id"] == "lg.test.v1"
    assert resolved["engine_type"] == "table"
    assert resolved["protocol_path_active"] is False
    assert resolved["pack_verified"] is True
    assert resolved["pack_mode_truth"]["cool"]["physically_verified"] is True
    assert resolved["physically_verified_modes"] == ["cool"]
    assert resolved["experimental_modes"] == []
    assert resolved["supported_modes"] == ["cool"]
    assert resolved["supported_swing_vertical"] == []
    assert resolved["supported_swing_horizontal"] == []
    assert resolved["broadlink_entity"] == "remote.test"
    assert resolved["broadlink_entity_state"] is None
    assert resolved["linked_temperature_sensor"] == "sensor.temp"
    assert resolved["validation_readiness"]["transport_available"] is True
    assert "available_temperature_points" in resolved["coverage"]
    assert resolved["support_summary"]["selected_pack_id"] == "lg.test.v1"
    assert resolved["support_summary"]["engine_type"] == "table"
    assert resolved["support_summary"]["protocol_path_active"] is False
    assert resolved["support_summary"]["verified"] is True
    assert resolved["support_summary"]["temperature_range"] == [18, 20]
    assert resolved["support_summary"]["fan_modes"] == ["auto"]


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

    monkeypatch.setattr(diagnostics, "create_ir_manager_from_entry", lambda *_a, **_k: _DiagIR())

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    assert result["entity"]["entity_id"] == "climate.living_room_ac"
    assert result["entity"]["state"] == "cool"
    assert result["entity"]["attributes"]["fan_mode"] == "auto"


@pytest.mark.asyncio
async def test_diagnostics_protocol_support_summary(monkeypatch) -> None:
    pack = _protocol_pack()
    hass = _FakeHass()
    entry = SimpleNamespace(
        entry_id="entry1",
        title="Protocol",
        data={"model_pack": "lg.protocol.v1", "broadlink_entity": "remote.test"},
        options={},
    )

    monkeypatch.setattr(diagnostics, "get_registry", lambda: _FakeRegistry(pack))
    monkeypatch.setattr(diagnostics.er, "async_get", lambda _h: _FakeEntityRegistry())

    monkeypatch.setattr(diagnostics, "create_ir_manager_from_entry", lambda *_a, **_k: _DiagIR())

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    summary = result["resolved"]["support_summary"]

    assert summary["selected_pack_id"] == "lg.protocol.v1"
    assert summary["engine_type"] == "lg_protocol"
    assert summary["protocol_path_active"] is True
    assert summary["verified"] is True
    assert summary["physically_verified_hvac_modes"] == ["auto", "heat", "cool", "dry", "fan_only"]
    assert summary["temperature_range"] == [16, 30]
    assert summary["fan_modes"] == ["auto", "f1", "f2", "f3", "f4", "f5"]
    assert summary["swing_support"]["horizontal_modes"] == ["off", "on"]
    assert "toggle form only" in summary["limitations"]
    assert "not exposed" in summary["limitations"]
