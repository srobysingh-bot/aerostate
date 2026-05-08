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
    CONF_TUYA_HOST,
    CONF_TUYA_IR_DP,
    CONF_TUYA_IR_SEND_BLOCKING,
    CONF_TUYA_LOCAL_DEVICE_ID,
    CONF_TUYA_LOCAL_KEY,
    CONF_TUYA_MODEL_PACK,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
)


class _Services:
    def __init__(self, available: bool) -> None:
        self._available = available

    def has_service(self, domain: str, service: str) -> bool:
        return self._available and domain == "localtuya" and service == "set_dp"


class _States:
    @staticmethod
    def async_entity_ids(_domain: str) -> list[str]:
        return ["remote.test"]


def _hass(*, localtuya_available: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        services=_Services(localtuya_available),
        states=_States(),
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
    assert CONF_TUYA_LOCAL_DEVICE_ID not in _schema_keys(result["data_schema"])


@pytest.mark.asyncio
async def test_tuya_config_flow_tuya_path_shows_tuya_device_step() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_user({CONF_IR_PROVIDER: IR_PROVIDER_TUYA})

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_device"
    assert CONF_TUYA_LOCAL_DEVICE_ID in _schema_keys(result["data_schema"])


def test_tuya_device_step_has_human_readable_labels() -> None:
    strings = json.loads(Path("custom_components/aerostate/strings.json").read_text(encoding="utf-8"))
    labels = strings["config"]["step"]["tuya_device"]["data"]
    expected = {
        CONF_TUYA_LOCAL_DEVICE_ID,
        CONF_TUYA_LOCAL_KEY,
        CONF_TUYA_HOST,
        CONF_TUYA_IR_DP,
        CONF_TUYA_MODEL_PACK,
        CONF_TUYA_IR_SEND_BLOCKING,
    }

    assert set(labels) == expected
    for key, label in labels.items():
        assert label
        assert label != key


@pytest.mark.asyncio
async def test_tuya_device_step_rejects_missing_localtuya_service() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(localtuya_available=False)

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_LOCAL_DEVICE_ID: "bf1234567890",
            CONF_TUYA_LOCAL_KEY: "secret",
            CONF_TUYA_HOST: "192.0.2.10",
            CONF_TUYA_IR_DP: 201,
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
            CONF_TUYA_IR_SEND_BLOCKING: True,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_device"
    assert result["errors"] == {"base": "tuya_set_dp_not_available"}


@pytest.mark.asyncio
async def test_tuya_confirm_step_shows_before_entry_creation() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_LOCAL_DEVICE_ID: "bf1234567890",
            CONF_TUYA_LOCAL_KEY: "secret",
            CONF_TUYA_HOST: "192.0.2.10",
            CONF_TUYA_IR_DP: 201,
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
            CONF_TUYA_IR_SEND_BLOCKING: True,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    placeholders = result["description_placeholders"]
    assert placeholders["device_id_short"] == "bf123456..."
    assert placeholders["host"] == "192.0.2.10"
    assert placeholders["pack_label"] == "PC09SQ NSJ"


@pytest.mark.asyncio
async def test_tuya_confirm_creates_entry() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    flow._tuya_data = {
        CONF_TUYA_LOCAL_DEVICE_ID: "bf1234567890",
        CONF_TUYA_LOCAL_KEY: "secret",
        CONF_TUYA_HOST: "192.0.2.10",
        CONF_TUYA_IR_DP: 201,
        CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
        CONF_TUYA_IR_SEND_BLOCKING: True,
    }

    result = await flow.async_step_tuya_confirm({})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_IR_PROVIDER] == IR_PROVIDER_TUYA
    assert result["data"][CONF_TUYA_LOCAL_DEVICE_ID] == "bf1234567890"
    assert result["data"][CONF_TUYA_HOST] == "192.0.2.10"
    assert result["data"][CONF_TUYA_MODEL_PACK] == "tuya.lg_pc09sq_nsj.v1"
    assert "broadlink_entity" not in result["data"]
