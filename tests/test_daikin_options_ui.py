"""Options UI tests for selecting local Daikin Tuya packs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol

pytest.importorskip("homeassistant")

from custom_components.aerostate.const import (
    CONF_BRAND,
    CONF_IR_PROVIDER,
    CONF_SELECTED_TUYA_PACK_ID,
    CONF_TUYA_DEVICE_NAME,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    IR_PROVIDER_TUYA,
)
from custom_components.aerostate.options_flow import AeroStateOptionsFlowHandler
from custom_components.aerostate.packs.tuya.daikin import loader as daikin_loader
from custom_components.aerostate.packs.tuya.registry import get_tuya_pack_options_for_ui

PACK_ID = "daikin_tuya_set_901"


def _write_daikin_pack(directory: Path) -> None:
    directory.mkdir(exist_ok=True)
    (directory / f"{PACK_ID}.py").write_text(
        "METADATA = {\n"
        f"  'pack_id': '{PACK_ID}', 'display_name': 'Daikin BRC4M150W candidate 901',\n"
        "  'brand': 'Daikin', 'provider': 'tuya_local', 'remote_index': '901',\n"
        "  'source': 'tuya_cloud_one_time_import', 'payload_format': 'localtuya_rc_raw',\n"
        "  'cloud_disabled_at_runtime': True\n"
        "}\n"
        "CODES = {\n"
        "  'power_on': 'raw:on901', 'power_off': 'raw:off901',\n"
        "  'cool_t24_fauto': 'raw:cool901'\n"
        "}\n",
        encoding="utf-8",
    )


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="daikin_entry",
        data={
            CONF_BRAND: "Daikin",
            CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
            CONF_TUYA_IR_ENTITY: "remote.daikin_ir",
            CONF_TUYA_DEVICE_NAME: "Daikin",
            CONF_TUYA_MODEL_PACK: "daikin.brc4c158.localtuya_rc.smartir1109.v1",
        },
        options={},
    )


class _ConfigEntries:
    def __init__(self) -> None:
        self.updates: list[dict] = []
        self.async_reload = AsyncMock()

    def async_entries(self, _domain: str) -> list:
        return []

    def async_update_entry(self, entry, **kwargs) -> None:
        self.updates.append(kwargs)
        if "options" in kwargs:
            entry.options = kwargs["options"]


def _hass(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)),
        config_entries=_ConfigEntries(),
    )


def _schema_field(schema: vol.Schema, key: str):
    for marker, value in schema.schema.items():
        if isinstance(marker, (vol.Required, vol.Optional)) and marker.schema == key:
            return value
    raise AssertionError(f"Missing schema field {key}")


@pytest.mark.asyncio
async def test_daikin_options_ui_shows_package_actions_and_reference_label(tmp_path) -> None:
    handler = AeroStateOptionsFlowHandler(_entry())
    handler.hass = _hass(tmp_path)

    result = await handler.async_step_init()

    action = _schema_field(result["data_schema"], "daikin_setup_action")
    assert {option["value"] for option in action.config["options"]} == {
        "keep_current",
        "test_installed",
        "import_daikin",
    }
    old_pack = next(
        option
        for option in get_tuya_pack_options_for_ui("Daikin")
        if option["value"] == "daikin.brc4c158.localtuya_rc.smartir1109.v1"
    )
    assert "Reference only, not BRC4M150W" in old_pack["label"]


@pytest.mark.asyncio
async def test_daikin_options_tests_one_command_then_confirms_exact_pack(
    tmp_path,
    monkeypatch,
) -> None:
    _write_daikin_pack(tmp_path)
    monkeypatch.setattr(daikin_loader, "_pack_dir", lambda: tmp_path)
    sent: list[tuple[str, str]] = []

    class _Manager:
        def __init__(self, _hass, _remote, _device, pack_id=None) -> None:
            self.pack_id = str(pack_id)

        async def async_test_pack_command(self, command: str) -> None:
            sent.append((self.pack_id, command))

    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_ir_manager.TuyaIRManager",
        _Manager,
    )
    entry = _entry()
    handler = AeroStateOptionsFlowHandler(entry)
    handler.hass = _hass(tmp_path)

    opened = await handler.async_step_init(
        {
            CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
            CONF_TUYA_IR_ENTITY: "remote.daikin_ir",
            CONF_TUYA_DEVICE_NAME: "Daikin",
            CONF_TUYA_MODEL_PACK: PACK_ID,
            "daikin_setup_action": "test_installed",
        }
    )
    tested = await handler.async_step_daikin_pack_test(
        {
            "daikin_pack_id": PACK_ID,
            "daikin_command": "power_on",
            "daikin_pack_action": "test",
        }
    )
    confirmed = await handler.async_step_daikin_pack_test(
        {
            "daikin_pack_id": PACK_ID,
            "daikin_command": "power_on",
            "daikin_pack_action": "confirm",
        }
    )

    assert opened["step_id"] == "daikin_pack_test"
    assert tested["step_id"] == "daikin_pack_test"
    assert sent == [(PACK_ID, "power_on")]
    assert confirmed["type"] == "create_entry"
    assert entry.options[CONF_TUYA_MODEL_PACK] == PACK_ID
    assert entry.options[CONF_SELECTED_TUYA_PACK_ID] == PACK_ID
    handler.hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
