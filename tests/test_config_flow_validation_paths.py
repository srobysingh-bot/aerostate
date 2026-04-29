"""Tests for config flow validation step success and failure paths."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.config_flow import AeroStateConfigFlow
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


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
        commands={"off": "OFF", "cool": {"auto": {"18": "C18"}}},
        verified=True,
        notes="Verified cool-only pack. No swing payloads included.",
    )


class _FakeRegistry:
    def get(self, _pack_id: str) -> ModelPack:
        return _pack()


class _MissingPackRegistry:
    def get(self, _pack_id: str) -> ModelPack:
        raise ValueError("pack missing")


class _FakeEntries:
    def __init__(self, entries: list) -> None:
        self._entries = entries

    def async_entries(self, _domain: str):
        return self._entries


class _ProviderPass:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls = 0

    async def test_connection(self) -> bool:
        return True

    async def send_base64(self, _payload: str) -> None:
        self.calls += 1


class _ProviderNoTransport:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def test_connection(self) -> bool:
        return False


class _EnginePass:
    def __init__(self, _pack) -> None:
        pass

    def resolve_command(self, _state: dict) -> str:
        return "ABC"


def _minimal_hass() -> SimpleNamespace:
    return SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda _domain: []),
    )


def _collision_hass() -> SimpleNamespace:
    return SimpleNamespace(
        config_entries=_FakeEntries(
            [
                SimpleNamespace(
                    entry_id="entry_existing",
                    unique_id="remote.test::lg.test.v1",
                    data={"broadlink_entity": "remote.test", "model_pack": "lg.test.v1"},
                    options={},
                )
            ]
        )
    )


@pytest.mark.asyncio
async def test_validation_step_success(monkeypatch) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _minimal_hass()
    flow._selected_pack_id = "lg.test.v1"
    flow._broadlink_entity = "remote.test"

    monkeypatch.setattr("custom_components.aerostate.config_flow.get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr("custom_components.aerostate.config_flow.BroadlinkProvider", _ProviderPass)
    monkeypatch.setattr("custom_components.aerostate.config_flow.create_engine", lambda _pack: _EnginePass(_pack))
    monkeypatch.setattr(
        "custom_components.aerostate.config_flow.build_safe_validation_states",
        lambda _pack, _profile: [("off", {"power": False, "hvac_mode": "off", "target_temperature": 18})],
    )

    result = await flow.async_step_validation({"run_validation": True})

    assert result["type"] == "form"
    assert result["step_id"] == "validation_result"
    assert flow._validation_summary["status"] == "passed"
    assert flow._validation_summary["transport_ok"] is True


@pytest.mark.asyncio
async def test_validation_step_transport_failure(monkeypatch) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _minimal_hass()
    flow._selected_pack_id = "lg.test.v1"
    flow._broadlink_entity = "remote.test"

    monkeypatch.setattr("custom_components.aerostate.config_flow.get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr("custom_components.aerostate.config_flow.BroadlinkProvider", _ProviderNoTransport)
    monkeypatch.setattr("custom_components.aerostate.config_flow.create_engine", lambda _pack: _EnginePass(_pack))

    result = await flow.async_step_validation({"run_validation": True})

    assert result["type"] == "form"
    assert result["step_id"] == "validation_result"
    assert flow._validation_summary["status"] == "failed"
    assert flow._validation_summary["error"] == "validation_transport_unavailable"


@pytest.mark.asyncio
async def test_confirm_step_aborts_on_duplicate_identity(monkeypatch) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _collision_hass()
    flow._selected_brand = "LG"
    flow._selected_pack_id = "lg.test.v1"
    flow._broadlink_entity = "remote.test"

    monkeypatch.setattr("custom_components.aerostate.config_flow.get_registry", lambda: _FakeRegistry())

    result = await flow.async_step_confirm({})
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_confirm_step_includes_pack_notes_and_limitations(monkeypatch) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _minimal_hass()
    flow._selected_brand = "LG"
    flow._selected_pack_id = "lg.test.v1"
    flow._broadlink_entity = "remote.test"

    monkeypatch.setattr("custom_components.aerostate.config_flow.get_registry", lambda: _FakeRegistry())

    result = await flow.async_step_confirm()
    assert result["type"] == "form"
    placeholders = result["description_placeholders"]
    assert placeholders["pack_notes"] == "Verified cool-only pack. No swing payloads included."
    assert placeholders["pack_limitations"] == "Verified cool-only pack. No swing payloads included."


@pytest.mark.asyncio
async def test_validation_step_handles_missing_selected_pack(monkeypatch) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _minimal_hass()
    flow._selected_pack_id = "lg.test.v1"
    flow._broadlink_entity = "remote.test"

    monkeypatch.setattr("custom_components.aerostate.config_flow.get_registry", lambda: _MissingPackRegistry())

    result = await flow.async_step_validation({"run_validation": True})

    assert result["type"] == "abort"
    assert result["reason"] == "selected_pack_unavailable"


@pytest.mark.asyncio
async def test_confirm_step_aborts_when_selected_pack_missing(monkeypatch) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _minimal_hass()
    flow._selected_brand = "LG"
    flow._selected_pack_id = "lg.test.v1"
    flow._broadlink_entity = "remote.test"

    monkeypatch.setattr("custom_components.aerostate.config_flow.get_registry", lambda: _MissingPackRegistry())

    result = await flow.async_step_confirm()
    assert result["type"] == "abort"
    assert result["reason"] == "selected_pack_unavailable"
