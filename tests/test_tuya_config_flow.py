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
    CONF_TUYA_CLOUD_ACCESS_ID,
    CONF_TUYA_CLOUD_ACCESS_SECRET,
    CONF_TUYA_CLOUD_ENDPOINT,
    CONF_TUYA_CLOUD_MODEL_PACK,
    CONF_TUYA_DEVICE_NAME,
    CONF_TUYA_INFRARED_ID,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    CONF_TUYA_REMOTE_ID,
    DEFAULT_TUYA_DEVICE_NAME,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
    IR_PROVIDER_TUYA_CLOUD,
)
from custom_components.aerostate.providers import tuya_raw_code_library


@pytest.fixture(autouse=True)
def _isolate_bundled_raw_code_library(tmp_path, monkeypatch) -> None:
    bundled_dir = tmp_path / "empty_bundled_raw_codes"
    bundled_dir.mkdir()
    monkeypatch.setattr(tuya_raw_code_library, "_bundled_library_dir", lambda: str(bundled_dir))


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


def _write_storage(tmp_path, device_codes: dict[str, str] | None) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir(exist_ok=True)
    if device_codes is None:
        return
    (storage_dir / "localtuya_rc_codes").write_text(
        json.dumps(
            {
                "version": 1,
                "minor_version": 1,
                "key": "localtuya_rc_codes",
                "data": {DEFAULT_TUYA_DEVICE_NAME: device_codes},
            },
        ),
        encoding="utf-8",
    )


def _write_portable_pack(tmp_path, *, device_name: str, commands: dict[str, str]) -> None:
    library_dir = tmp_path / "aerostate_tuya_raw_codes"
    library_dir.mkdir(exist_ok=True)
    (library_dir / "lg_pc09sq_nsj_v1.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pack_id": "lg_pc09sq_nsj_v1",
                "title": "LG PC09SQ NSJ",
                "device_name": device_name,
                "format": "tuya_remote_send_command_raw",
                "commands": commands,
            },
        ),
        encoding="utf-8",
    )


def _hass(*, states: dict[str, str] | None = None, tmp_path=None, device_codes: dict[str, str] | None = None) -> SimpleNamespace:
    if tmp_path is not None:
        _write_storage(tmp_path, device_codes if device_codes is not None else {"power_off": "raw:off"})
    return SimpleNamespace(
        services=SimpleNamespace(has_service=lambda *_args: False),
        states=_States(states),
        config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)) if tmp_path is not None else SimpleNamespace(path=lambda rel: rel),
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


@pytest.mark.asyncio
async def test_tuya_config_flow_tuya_cloud_path_shows_cloud_device_step() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_user({CONF_IR_PROVIDER: IR_PROVIDER_TUYA_CLOUD})

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_cloud_device"
    assert {
        CONF_TUYA_CLOUD_ENDPOINT,
        CONF_TUYA_CLOUD_ACCESS_ID,
        CONF_TUYA_CLOUD_ACCESS_SECRET,
        CONF_TUYA_INFRARED_ID,
        CONF_TUYA_REMOTE_ID,
        CONF_TUYA_CLOUD_MODEL_PACK,
    }.issubset(_schema_keys(result["data_schema"]))


def test_tuya_device_step_has_human_readable_labels() -> None:
    strings = json.loads(Path("custom_components/aerostate/strings.json").read_text(encoding="utf-8"))
    labels = strings["config"]["step"]["tuya_device"]["data"]
    expected = {
        CONF_TUYA_IR_ENTITY,
        CONF_TUYA_DEVICE_NAME,
        CONF_TUYA_MODEL_PACK,
    }

    assert set(labels) == expected
    for key, label in labels.items():
        assert label
        assert label != key
    assert "Raw-code" in labels[CONF_TUYA_DEVICE_NAME]


def test_tuya_device_step_explains_portable_code_source() -> None:
    strings = json.loads(Path("custom_components/aerostate/strings.json").read_text(encoding="utf-8"))

    assert "aerostate_tuya_raw_codes" in strings["config"]["error"]["tuya_no_learned_codes"]
    assert "code_source_hint" in strings["config"]["step"]["tuya_device"]["description"]


@pytest.mark.asyncio
async def test_tuya_device_step_rejects_missing_remote_entity() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(states={})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.missing",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
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
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_device"
    assert result["errors"] == {"base": "tuya_remote_entity_unavailable"}


@pytest.mark.asyncio
async def test_tuya_device_step_allows_pending_entry_when_no_codes_exist(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    assert result["description_placeholders"]["total_codes"] == "0"
    assert "No raw-code source found yet" in result["description_placeholders"]["code_source_status"]


@pytest.mark.asyncio
async def test_tuya_device_step_accepts_generated_pack_without_learned_codes(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
            CONF_TUYA_MODEL_PACK: "lg.akb75415308.localtuya_rc.protocol.v1",
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    assert result["description_placeholders"]["total_codes"] == "102"
    assert "No learning required" in result["description_placeholders"]["code_source_status"]
    assert result["description_placeholders"]["heat_supported"] == "Yes"
    assert result["description_placeholders"]["dry_supported"] == "Yes"


@pytest.mark.asyncio
async def test_tuya_device_step_allows_pending_entry_when_power_off_missing(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={"temp_24": "raw:24"})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    assert result["description_placeholders"]["total_codes"] == "1"
    assert "missing power_off" in result["description_placeholders"]["code_source_status"]


@pytest.mark.asyncio
async def test_tuya_device_step_accepts_portable_pack_without_localtuya_storage(tmp_path) -> None:
    _write_portable_pack(
        tmp_path,
        device_name="LG PC09SQ NSJ",
        commands={"power_off": "raw:off", "temp_24": "raw:24"},
    )
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    assert result["description_placeholders"]["total_codes"] == "2"


@pytest.mark.asyncio
async def test_tuya_device_step_accepts_only_available_source_when_name_differs(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={"power_off": "raw:off", "temp_24": "raw:24"})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: "Media room",
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    assert result["description_placeholders"]["total_codes"] == "2"


@pytest.mark.asyncio
async def test_tuya_confirm_step_shows_before_entry_creation(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={"power_off": "raw:off", "temp_24": "raw:24"})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    placeholders = result["description_placeholders"]
    assert placeholders["device_name"] == DEFAULT_TUYA_DEVICE_NAME
    assert placeholders["total_codes"] == "2"
    assert placeholders["has_power_off"] == "Yes"


@pytest.mark.asyncio
async def test_tuya_confirm_creates_entry(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    flow._tuya_data = {
        CONF_TUYA_IR_ENTITY: "remote.test_ir",
        CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
    }

    result = await flow.async_step_tuya_confirm({})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_IR_PROVIDER] == IR_PROVIDER_TUYA
    assert result["data"][CONF_TUYA_IR_ENTITY] == "remote.test_ir"
    assert result["data"][CONF_TUYA_DEVICE_NAME] == DEFAULT_TUYA_DEVICE_NAME
    assert result["data"][CONF_TUYA_MODEL_PACK] == "tuya.lg_pc09sq_nsj.v1"
    assert "broadlink_entity" not in result["data"]


@pytest.mark.asyncio
async def test_tuya_cloud_confirm_creates_isolated_cloud_entry(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    flow._tuya_cloud_data = {
        CONF_TUYA_CLOUD_ENDPOINT: "https://openapi.tuyain.com",
        CONF_TUYA_CLOUD_ACCESS_ID: "access-id",
        CONF_TUYA_CLOUD_ACCESS_SECRET: "access-secret",
        CONF_TUYA_INFRARED_ID: "ir-device-id",
        CONF_TUYA_REMOTE_ID: "remote-id",
        CONF_TUYA_CLOUD_MODEL_PACK: "tuya_cloud.daikin_ac.v1",
    }

    result = await flow.async_step_tuya_cloud_confirm({})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_IR_PROVIDER] == IR_PROVIDER_TUYA_CLOUD
    assert result["data"][CONF_TUYA_REMOTE_ID] == "remote-id"
    assert CONF_TUYA_MODEL_PACK not in result["data"]
    assert "broadlink_entity" not in result["data"]
