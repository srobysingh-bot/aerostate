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
    CONF_BRAND,
    CONF_IR_PROVIDER,
    CONF_SELECTED_TUYA_PACK_ID,
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
from custom_components.aerostate.packs.tuya.daikin import loader as daikin_loader
from custom_components.aerostate.packs.tuya.registry import get_tuya_pack, register_tuya_pack
from custom_components.aerostate.packs.tuya.schema import TuyaIRPack
from custom_components.aerostate.providers import tuya_raw_code_library
from custom_components.aerostate.providers.tuya_daikin_importer import DaikinImportResult


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


def _write_daikin_set(directory: Path, number: int) -> None:
    directory.mkdir(exist_ok=True)
    pack_id = f"daikin_tuya_set_{number:03d}"
    (directory / f"{pack_id}.py").write_text(
        "METADATA = {\n"
        f"  'pack_id': '{pack_id}', 'display_name': 'Daikin set {number:03d}',\n"
        "  'brand': 'Daikin', 'model_hint': 'FXAQ63PVE6', 'provider': 'tuya_local',\n"
        f"  'remote_index': '{number}', 'source': 'tuya_cloud_one_time_import', 'temp_range': [16, 30],\n"
        "  'fan_modes': ['auto'], 'swing_support': True,\n"
        "  'generated_at': '2026-06-06T00:00:00Z', 'payload_format': 'localtuya_rc_raw',\n"
        "  'cloud_disabled_at_runtime': True\n"
        "}\n"
        f"CODES = {{'power_on': 'raw:on{number}', 'power_off': 'raw:off{number}', "
        f"'cool_t24_fauto': 'raw:cool{number}', 'swing_vertical': 'raw:swing{number}'}}\n",
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


def _schema_default(schema: vol.Schema, key: str):
    for marker in schema.schema:
        if isinstance(marker, (vol.Required, vol.Optional)) and marker.schema == key:
            return marker.default()
    raise KeyError(key)


def _selector_options(schema: vol.Schema, key: str) -> list[dict]:
    for marker, field_selector in schema.schema.items():
        if isinstance(marker, (vol.Required, vol.Optional)) and marker.schema == key:
            return list(field_selector.config["options"])
    raise KeyError(key)


@pytest.mark.asyncio
async def test_tuya_config_flow_provider_step_shows_two_options() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass()

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert _schema_keys(result["data_schema"]) == {CONF_IR_PROVIDER}
    provider_selector = next(iter(result["data_schema"].schema.values()))
    options = provider_selector.config["options"]
    assert [option["value"] for option in options] == [IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA]
    assert "Daikin local packs" in options[1]["label"]


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
    assert result["step_id"] == "tuya_brand"
    assert _schema_keys(result["data_schema"]) == {CONF_BRAND}

    result = await flow.async_step_tuya_brand({CONF_BRAND: "Daikin"})

    assert result["step_id"] == "tuya_device"
    assert _schema_default(result["data_schema"], CONF_TUYA_MODEL_PACK) == (
        "daikin.brc4c158.localtuya_rc.smartir1109.v1"
    )


@pytest.mark.asyncio
async def test_tuya_daikin_setup_shows_only_daikin_packs_and_import_action(tmp_path) -> None:
    register_tuya_pack(
        TuyaIRPack(
            pack_id="daikin_tuya_set_999",
            brand="Daikin",
            models=["Stale imported set"],
            verified=False,
            notes="No local pack file exists",
            min_temperature=16,
            max_temperature=30,
        )
    )
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow._selected_brand = "Daikin"

    result = await flow.async_step_tuya_device()

    pack_ids = {
        option["value"]
        for option in _selector_options(result["data_schema"], CONF_TUYA_MODEL_PACK)
    }
    assert pack_ids
    assert all(get_tuya_pack(pack_id).brand == "Daikin" for pack_id in pack_ids)
    assert "lg.akb75415308.localtuya_rc.protocol.v1" not in pack_ids
    assert "tuya.lg_pc09sq_nsj.v1" not in pack_ids
    assert "daikin_tuya_set_999" not in pack_ids
    assert "daikin_setup_action" in _schema_keys(result["data_schema"])


@pytest.mark.asyncio
async def test_tuya_lg_setup_shows_only_lg_packs_without_daikin_import_action(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow._selected_brand = "LG"

    result = await flow.async_step_tuya_device()

    pack_ids = {
        option["value"]
        for option in _selector_options(result["data_schema"], CONF_TUYA_MODEL_PACK)
    }
    assert pack_ids
    assert all(get_tuya_pack(pack_id).brand == "LG" for pack_id in pack_ids)
    assert "daikin.brc4c158.localtuya_rc.smartir1109.v1" not in pack_ids
    assert "daikin_setup_action" not in _schema_keys(result["data_schema"])


@pytest.mark.asyncio
async def test_tuya_setup_rejects_pack_from_another_brand(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow._selected_brand = "Daikin"

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
            CONF_TUYA_MODEL_PACK: "lg.akb75415308.localtuya_rc.protocol.v1",
            "daikin_setup_action": "use_installed",
        }
    )

    assert result["step_id"] == "tuya_device"
    assert result["errors"] == {"base": "tuya_pack_brand_mismatch"}


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
        "daikin_setup_action",
    }

    assert set(labels) == expected
    for key, label in labels.items():
        assert label
        assert label != key
    assert "Raw-code" in labels[CONF_TUYA_DEVICE_NAME]


@pytest.mark.asyncio
async def test_tuya_device_step_routes_to_one_time_daikin_import_without_storing_action(
    tmp_path,
) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
            CONF_TUYA_MODEL_PACK: "daikin.brc4c158.localtuya_rc.smartir1109.v1",
            "daikin_setup_action": "import_daikin",
        }
    )

    assert result["step_id"] == "daikin_import"
    assert "daikin_setup_action" not in flow._tuya_data
    assert CONF_TUYA_MODEL_PACK not in flow._tuya_data


@pytest.mark.asyncio
async def test_daikin_import_step_does_not_store_credentials_and_opens_tester(
    tmp_path,
    monkeypatch,
) -> None:
    daikin_dir = tmp_path / "daikin_generated"
    _write_daikin_set(daikin_dir, 1)
    imported_credentials: list[dict[str, str]] = []
    monkeypatch.setattr(daikin_loader, "_pack_dir", lambda: daikin_dir)

    async def _import(_hass, **kwargs):
        imported_credentials.append(kwargs)
        daikin_loader.load_daikin_tuya_pack("daikin_tuya_set_001")
        return DaikinImportResult(1, 1, 0, ("daikin_tuya_set_001",))

    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_daikin_importer.async_import_daikin_tuya_codes",
        _import,
    )
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow._tuya_data = {
        CONF_TUYA_IR_ENTITY: "remote.test_ir",
        CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
    }

    result = await flow.async_step_daikin_import(
        {
            CONF_TUYA_CLOUD_ENDPOINT: "https://openapi.tuyain.com",
            CONF_TUYA_CLOUD_ACCESS_ID: "temporary-id",
            CONF_TUYA_CLOUD_ACCESS_SECRET: "temporary-secret",
            CONF_TUYA_INFRARED_ID: "temporary-infrared-id",
        }
    )

    assert result["step_id"] == "daikin_pack_test"
    assert imported_credentials[0]["access_secret"] == "temporary-secret"
    assert CONF_TUYA_CLOUD_ACCESS_ID not in flow._tuya_data
    assert CONF_TUYA_CLOUD_ACCESS_SECRET not in flow._tuya_data
    assert CONF_TUYA_INFRARED_ID not in flow._tuya_data


def test_tuya_device_step_explains_portable_code_source() -> None:
    strings = json.loads(Path("custom_components/aerostate/strings.json").read_text(encoding="utf-8"))

    assert "aerostate_tuya_raw_codes" in strings["config"]["error"]["tuya_no_learned_codes"]
    assert "code_source_hint" in strings["config"]["step"]["tuya_device"]["description"]


@pytest.mark.asyncio
async def test_tuya_device_step_rejects_missing_remote_entity() -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(states={})
    flow._selected_brand = "LG"

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
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
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
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
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
    assert result["description_placeholders"]["total_codes"] == str(
        len(get_tuya_pack("lg.akb75415308.localtuya_rc.protocol.v1").commands),
    )
    assert "No learning required" in result["description_placeholders"]["code_source_status"]
    assert result["description_placeholders"]["heat_supported"] == "Yes"
    assert result["description_placeholders"]["dry_supported"] == "Yes"


@pytest.mark.asyncio
async def test_tuya_device_step_accepts_daikin_builtin_pack_without_cloud_or_raw_source(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_MODEL_PACK: "daikin.brc4c158.localtuya_rc.smartir1109.v1",
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "tuya_confirm"
    assert result["description_placeholders"]["device_name"] == "BRC4C158"
    assert result["description_placeholders"]["total_codes"] == "46"
    assert result["description_placeholders"]["cool_temps_auto"] == "16-30"
    assert result["description_placeholders"]["heat_supported"] == "No"
    assert result["description_placeholders"]["dry_supported"] == "No"
    assert result["description_placeholders"]["code_source_status"] == "Pre-generated Tuya code pack selected. No learning required."


@pytest.mark.asyncio
async def test_daikin_pack_test_ui_lists_local_sets_and_sends_one_selected_command(
    tmp_path,
    monkeypatch,
) -> None:
    daikin_dir = tmp_path / "daikin"
    _write_daikin_set(daikin_dir, 1)
    _write_daikin_set(daikin_dir, 2)
    monkeypatch.setattr(daikin_loader, "_pack_dir", lambda: daikin_dir)
    sent: list[tuple[str, str]] = []

    class _Manager:
        def __init__(self, _hass, _remote, _device, pack_id=None) -> None:
            self.pack_id = pack_id

        async def async_test_pack_command(self, command: str) -> None:
            sent.append((str(self.pack_id), command))

    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_ir_manager.TuyaIRManager",
        _Manager,
    )
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow._tuya_data = {
        CONF_TUYA_IR_ENTITY: "remote.test_ir",
        CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        CONF_TUYA_MODEL_PACK: "daikin_tuya_set_001",
    }

    form = await flow.async_step_daikin_pack_test()
    result = await flow.async_step_daikin_pack_test(
        {
            "daikin_pack_id": "daikin_tuya_set_002",
            "daikin_command": "power_on",
            "daikin_pack_action": "test",
        }
    )

    assert form["step_id"] == "daikin_pack_test"
    assert form["description_placeholders"]["pack_count"] == "2"
    assert result["step_id"] == "daikin_pack_test"
    assert sent == [("daikin_tuya_set_002", "power_on")]


@pytest.mark.asyncio
async def test_tuya_device_step_opens_manual_test_ui_for_imported_daikin_set(
    tmp_path,
    monkeypatch,
) -> None:
    daikin_dir = tmp_path / "daikin"
    _write_daikin_set(daikin_dir, 1)
    monkeypatch.setattr(daikin_loader, "_pack_dir", lambda: daikin_dir)
    daikin_loader.load_daikin_tuya_pack("daikin_tuya_set_001")
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
            CONF_TUYA_MODEL_PACK: "daikin_tuya_set_001",
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "daikin_pack_test"
    assert result["description_placeholders"]["pack_count"] == "1"


@pytest.mark.asyncio
async def test_daikin_pack_test_ui_requires_test_before_confirm_and_saves_selection(
    tmp_path,
    monkeypatch,
) -> None:
    daikin_dir = tmp_path / "daikin"
    _write_daikin_set(daikin_dir, 1)
    monkeypatch.setattr(daikin_loader, "_pack_dir", lambda: daikin_dir)
    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_ir_manager.TuyaIRManager.async_test_pack_command",
        AsyncMock(),
    )
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path)
    flow._tuya_data = {
        CONF_TUYA_IR_ENTITY: "remote.test_ir",
        CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
        CONF_TUYA_MODEL_PACK: "daikin_tuya_set_001",
    }

    blocked = await flow.async_step_daikin_pack_test(
        {
            "daikin_pack_id": "daikin_tuya_set_001",
            "daikin_command": "power_on",
            "daikin_pack_action": "confirm",
        }
    )
    await flow.async_step_daikin_pack_test(
        {
            "daikin_pack_id": "daikin_tuya_set_001",
            "daikin_command": "power_on",
            "daikin_pack_action": "test",
        }
    )
    confirmed = await flow.async_step_daikin_pack_test(
        {
            "daikin_pack_id": "daikin_tuya_set_001",
            "daikin_command": "power_on",
            "daikin_pack_action": "confirm",
        }
    )

    assert blocked["errors"] == {"base": "daikin_pack_not_tested"}
    assert confirmed["step_id"] == "tuya_confirm"
    assert flow._tuya_data[CONF_SELECTED_TUYA_PACK_ID] == "daikin_tuya_set_001"
    assert get_tuya_pack("daikin_tuya_set_001").brand == "Daikin"


@pytest.mark.asyncio
async def test_tuya_device_step_allows_pending_entry_when_power_off_missing(tmp_path) -> None:
    flow = AeroStateConfigFlow()
    flow.hass = _hass(tmp_path=tmp_path, device_codes={"temp_24": "raw:24"})

    result = await flow.async_step_tuya_device(
        {
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_DEVICE_NAME: DEFAULT_TUYA_DEVICE_NAME,
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
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
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
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
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
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
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
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
