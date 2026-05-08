"""Tuya config flow regression tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol

pytest.importorskip("homeassistant")

from custom_components.aerostate.config_flow import AeroStateConfigFlow
from custom_components.aerostate.const import (
    CONF_IR_PROVIDER,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
)


class _States:
    def __init__(self, states: dict[str, str] | None = None) -> None:
        self._states = states or {"remote.test_ir": "on"}

    def async_entity_ids(self, _domain: str) -> list[str]:
        return ["remote.test", "remote.test_ir"]

    def get(self, entity_id: str):
        state = self._states.get(entity_id)
        if state is None:
            return None
        return SimpleNamespace(state=state)


def _hass(*, states: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        services=SimpleNamespace(has_service=lambda *_args: False),
        states=_States(states),
        config_entries=SimpleNamespace(async_entries=lambda _domain: []),
    )


def _schema_keys(schema: vol.Schema) -> set[str]:
    return {
        marker.schema
        for marker in schema.schema
        if isinstance(marker, (vol.Required, vol.Optional))
    }


@pytest.mark.asyncio
async def test_tuya_config_flow_provider_step_shows_two_options() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert _schema_keys(result["data_schema"]) == {CONF_IR_PROVIDER}


@pytest.mark.asyncio
async def test_tuya_config_flow_broadlink_path_unchanged() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_user({CONF_IR_PROVIDER: IR_PROVIDER_BROADLINK})

    assert result["type"] == "form"
    assert result["step_id"] == "broadlink_remote"
    assert CONF_TUYA_IR_ENTITY not in _schema_keys(result["data_schema"])


@pytest.mark.asyncio
async def test_tuya_config_flow_tuya_path_shows_tuya_device_step() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_user({CONF_IR_PROVIDER: IR_PROVIDER_TUYA})

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_device"
    assert CONF_TUYA_IR_ENTITY in _schema_keys(result["data_schema"])


def test_tuya_device_step_has_human_readable_labels() -> None:
    strings = json.loads(Path("custom_components/aerostate/strings.json").read_text(encoding="utf-8"))
    labels = strings["config"]["step"]["tuya_device"]["data"]
    expected = {
        CONF_TUYA_IR_ENTITY,
        CONF_TUYA_MODEL_PACK,
    }

    assert set(labels) == expected
    for key, label in labels.items():
        assert label
        assert label != key


@pytest.mark.asyncio
async def test_tuya_device_step_rejects_missing_remote_entity() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(states={})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.missing",
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_device"
    assert result["errors"] == {"base": "tuya_remote_entity_not_found"}


@pytest.mark.asyncio
async def test_tuya_device_step_rejects_unavailable_remote_entity() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(states={"remote.test_ir": "unavailable"})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_device"
    assert result["errors"] == {"base": "tuya_remote_entity_unavailable"}


@pytest.mark.asyncio
async def test_tuya_confirm_step_shows_before_entry_creation() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    placeholders = result["description_placeholders"]
    assert placeholders["remote_entity"] == "remote.test_ir"
    assert placeholders["pack_label"] == "PC09SQ NSJ"


@pytest.mark.asyncio
async def test_tuya_confirm_creates_entry() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    flow._tuya_data = {
        CONF_TUYA_IR_ENTITY: "remote.test_ir",
        CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
    }

    result = await flow.async_step_tuya_confirm({})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_IR_PROVIDER] == IR_PROVIDER_TUYA
    assert result["data"][CONF_TUYA_IR_ENTITY] == "remote.test_ir"
    assert result["data"][CONF_TUYA_MODEL_PACK] == "tuya.lg_pc09sq_nsj.v1"
    assert "broadlink_entity" not in result["data"]
