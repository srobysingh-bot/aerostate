"""Tests for isolated local Daikin Tuya code-set support."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import custom_components.aerostate as integration
from custom_components.aerostate.const import (
    CONF_BRAND,
    CONF_IR_PROVIDER,
    CONF_SELECTED_TUYA_PACK_ID,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    DOMAIN,
    IR_PROVIDER_TUYA,
)
from custom_components.aerostate.packs.tuya.daikin.loader import (
    get_daikin_tuya_pack,
    list_daikin_tuya_packs,
    load_daikin_tuya_pack,
)
from custom_components.aerostate.providers.tuya_ir_manager import (
    TuyaIRManager,
    create_tuya_ir_manager_from_entry,
)
from scripts.import_tuya_daikin_codes import _normalize_codes
from scripts.import_tuya_daikin_codes import _write_pack as _write_imported_pack


def _write_pack(directory: Path, name: str = "daikin_tuya_set_001.py", *, valid: bool = True) -> Path:
    directory.mkdir(exist_ok=True)
    codes = {
        "power_on": "raw:on",
        "power_off": "raw:off",
        "cool_t24_fauto": "raw:cool24",
        "cool_t25_fauto": "raw:cool25",
        "swing_vertical": "raw:swing",
    }
    if not valid:
        codes.pop("power_off")
    path = directory / name
    path.write_text(
        "METADATA = {\n"
        "  'pack_id': 'daikin_tuya_set_001',\n"
        "  'display_name': 'Daikin Tuya set 001',\n"
        "  'brand': 'Daikin', 'provider': 'tuya_local', 'remote_index': '1',\n"
        "  'source': 'test', 'temp_range': [16, 30], 'fan_modes': ['auto'],\n"
        "  'swing_support': True, 'generated_at': '2026-06-06T00:00:00Z',\n"
        "  'payload_format': 'localtuya_rc_raw'\n"
        "}\n"
        f"CODES = {codes!r}\n",
        encoding="utf-8",
    )
    return path


def test_daikin_loader_discovers_valid_pack_and_returns_metadata(tmp_path) -> None:
    _write_pack(tmp_path)

    packs = list_daikin_tuya_packs(directory=tmp_path)
    pack = get_daikin_tuya_pack("daikin_tuya_set_001", directory=tmp_path)

    assert [item.pack_id for item in packs] == ["daikin_tuya_set_001"]
    assert pack.brand == "Daikin"
    assert pack.provider == "tuya_local"
    assert "power_on" in pack.available_commands
    assert pack.metadata["remote_index"] == "1"


def test_daikin_loader_rejects_invalid_and_broadlink_payloads(tmp_path) -> None:
    invalid = _write_pack(tmp_path, valid=False)

    assert list_daikin_tuya_packs(directory=tmp_path) == []
    with pytest.raises(KeyError, match="not found"):
        load_daikin_tuya_pack("daikin_tuya_set_001", directory=tmp_path)

    invalid = _write_pack(tmp_path, valid=True)
    text = invalid.read_text(encoding="utf-8").replace("'raw:on'", "'b64:BroadlinkPayload'")
    invalid.write_text(text, encoding="utf-8")
    assert list_daikin_tuya_packs(directory=tmp_path) == []


def test_importer_converts_tuya_rule_entries_into_loadable_local_pack(tmp_path) -> None:
    codes = _normalize_codes(
        [
            {"key": "power_on", "code": "raw:on"},
            {"key": "power_off", "code": "raw:off"},
            {"key": "cool_t24_fauto", "code": "raw:cool24"},
        ]
    )

    path = _write_imported_pack(tmp_path, 1, "77", codes)
    pack = load_daikin_tuya_pack("daikin_tuya_set_001", directory=tmp_path)

    assert path.name == "daikin_tuya_set_001.py"
    assert pack.resolve_by_label("cool_t24_fauto") == "raw:cool24"


class _ConfigEntries:
    def __init__(self, entry) -> None:
        self.entry = entry
        self.updates: list[dict] = []
        self.reloads: list[str] = []

    def async_get_entry(self, entry_id: str):
        return self.entry if entry_id == self.entry.entry_id else None

    def async_update_entry(self, entry, **kwargs) -> None:
        self.updates.append(kwargs)
        entry.data = kwargs["data"]
        entry.options = kwargs["options"]

    async def async_reload(self, entry_id: str) -> None:
        self.reloads.append(entry_id)


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry_daikin",
        data={
            CONF_BRAND: "Daikin",
            CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
            CONF_TUYA_IR_ENTITY: "remote.daikin_ir",
        },
        options={},
    )


def _hass(entry) -> SimpleNamespace:
    return SimpleNamespace(
        data={DOMAIN: {entry.entry_id: {}}},
        config_entries=_ConfigEntries(entry),
        services=SimpleNamespace(async_call=AsyncMock()),
        states=SimpleNamespace(get=lambda _entity_id: SimpleNamespace(state="on")),
    )


@pytest.mark.asyncio
async def test_test_tuya_pack_sends_one_command_without_climate_or_cloud(monkeypatch) -> None:
    entry = _entry()
    hass = _hass(entry)
    calls: list[str] = []

    class _Pack:
        @staticmethod
        def resolve_by_label(label: str):
            return "raw:on" if label == "power_on" else None

    class _Manager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def async_test_pack_command(self, command: str) -> None:
            calls.append(command)

    monkeypatch.setattr(
        "custom_components.aerostate.packs.tuya.daikin.loader.load_daikin_tuya_pack",
        lambda _pack_id, **_kwargs: _Pack(),
    )
    monkeypatch.setattr("custom_components.aerostate.providers.tuya_ir_manager.TuyaIRManager", _Manager)
    call = SimpleNamespace(
        data={"entry_id": entry.entry_id, "brand": "daikin", "pack_id": "set1", "command": "power_on"}
    )

    await integration._async_handle_test_tuya_pack(hass, call)

    assert calls == ["power_on"]
    assert hass.config_entries.updates == []
    hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_tuya_pack_rejects_lg_entry() -> None:
    entry = _entry()
    entry.data[CONF_BRAND] = "LG"
    hass = _hass(entry)

    with pytest.raises(Exception, match="LG or non-Daikin"):
        await integration._async_handle_test_tuya_pack(
            hass,
            SimpleNamespace(
                data={
                    "entry_id": entry.entry_id,
                    "brand": "daikin",
                    "pack_id": "set1",
                    "command": "power_on",
                }
            ),
        )


@pytest.mark.asyncio
async def test_confirm_tuya_pack_saves_selected_pack_id(monkeypatch) -> None:
    entry = _entry()
    hass = _hass(entry)
    monkeypatch.setattr(
        "custom_components.aerostate.packs.tuya.daikin.loader.load_daikin_tuya_pack",
        lambda _pack_id, **_kwargs: object(),
    )

    await integration._async_handle_confirm_tuya_pack(
        hass,
        SimpleNamespace(data={"entry_id": entry.entry_id, "brand": "daikin", "pack_id": "set1"}),
    )

    assert entry.data[CONF_BRAND] == "Daikin"
    assert entry.options[CONF_SELECTED_TUYA_PACK_ID] == "set1"
    assert entry.options[CONF_TUYA_MODEL_PACK] == "set1"
    assert hass.config_entries.reloads == [entry.entry_id]


def test_daikin_runtime_factory_uses_only_confirmed_pack() -> None:
    entry = _entry()
    entry.data[CONF_BRAND] = "Daikin"
    entry.data[CONF_TUYA_MODEL_PACK] = "unconfirmed"
    entry.options[CONF_SELECTED_TUYA_PACK_ID] = "confirmed"

    manager = create_tuya_ir_manager_from_entry(_hass(entry), entry)

    assert manager._pack_id == "confirmed"


@pytest.mark.asyncio
async def test_selected_daikin_runtime_off_on_sequence_and_already_on(tmp_path, monkeypatch) -> None:
    _write_pack(tmp_path)
    load_daikin_tuya_pack("daikin_tuya_set_001", directory=tmp_path)
    monkeypatch.setattr("custom_components.aerostate.providers.tuya_ir_manager.POWER_ON_SETTLE_SECONDS", 0)
    hass = _hass(_entry())
    manager = TuyaIRManager(hass, "remote.daikin_ir", "Daikin", "daikin_tuya_set_001")

    await manager.async_send_climate_state(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "auto",
            "previously_off": True,
        }
    )
    await manager.async_send_climate_state(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 25,
            "fan_mode": "auto",
            "previously_off": False,
        }
    )

    assert [call.args[2]["command"] for call in hass.services.async_call.await_args_list] == [
        "raw:on",
        "raw:cool24",
        "raw:cool25",
    ]


@pytest.mark.asyncio
async def test_selected_daikin_runtime_power_off_sends_exactly_once(tmp_path) -> None:
    _write_pack(tmp_path)
    load_daikin_tuya_pack("daikin_tuya_set_001", directory=tmp_path)
    hass = _hass(_entry())
    manager = TuyaIRManager(hass, "remote.daikin_ir", "Daikin", "daikin_tuya_set_001")

    await manager.async_send_climate_state({"power": False, "hvac_mode": "off"})

    hass.services.async_call.assert_awaited_once_with(
        "remote",
        "send_command",
        {
            "entity_id": "remote.daikin_ir",
            "command": "raw:off",
            "num_repeats": 1,
            "delay_secs": 0.05,
        },
        blocking=False,
    )
