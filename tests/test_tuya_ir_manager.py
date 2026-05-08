"""Tests for localtuya_rc learned-code Tuya IR support."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.learned_code_resolver import (
    LearnedCodeNotAvailable,
    get_coverage_summary,
    resolve_learned_code,
)
from custom_components.aerostate.providers.localtuya_rc_storage import read_learned_codes
from custom_components.aerostate.providers.tuya_ir_manager import TuyaIRManager
from custom_components.aerostate.providers import tuya_raw_code_library
from custom_components.aerostate.providers.tuya_raw_code_library import export_portable_raw_codes


def _hass_with_storage(tmp_path, data: dict) -> SimpleNamespace:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    (storage_dir / "localtuya_rc_codes").write_text(json.dumps(data), encoding="utf-8")
    return SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))


def test_read_learned_codes_returns_dict_for_known_device(tmp_path) -> None:
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Living AC IR": {"power_off": "raw:1,2,3"}},
        },
    )

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:1,2,3"}
    exported = tmp_path / "aerostate_tuya_raw_codes" / "living_ac_ir_learned_raw_codes.json"
    assert exported.exists()


def test_read_learned_codes_uses_only_available_source_for_missing_device_name(tmp_path) -> None:
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Other": {"power_off": "raw:1,2,3"}},
        },
    )

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:1,2,3"}


def test_read_learned_codes_strips_commented_json_primary(tmp_path) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    raw_json = json.dumps(
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Living AC IR": {"power_off": "raw:off"}},
        },
    )
    (storage_dir / "localtuya_rc_codes").write_text(
        "\n".join(f"// {line}" for line in raw_json.splitlines()),
        encoding="utf-8",
    )
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:off"}


def test_read_learned_codes_uses_most_recent_corrupt_backup_when_primary_missing(tmp_path) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    old_data = {
        "version": 1,
        "minor_version": 1,
        "key": "localtuya_rc_codes",
        "data": {"Living AC IR": {"power_off": "raw:old"}},
    }
    new_data = {
        "version": 1,
        "minor_version": 1,
        "key": "localtuya_rc_codes",
        "data": {"Living AC IR": {"power_off": "raw:new"}},
    }
    (storage_dir / "localtuya_rc_codes.corrupt.2026-05-05T121107").write_text(
        json.dumps(old_data),
        encoding="utf-8",
    )
    (storage_dir / "localtuya_rc_codes.corrupt.2026-05-08T130000").write_text(
        json.dumps(new_data),
        encoding="utf-8",
    )
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:new"}


def test_read_learned_codes_tries_older_backup_if_newest_is_unusable(tmp_path) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    good_data = {
        "version": 1,
        "minor_version": 1,
        "key": "localtuya_rc_codes",
        "data": {"Living AC IR": {"power_off": "raw:good"}},
    }
    (storage_dir / "localtuya_rc_codes.corrupt.2026-05-05T121107").write_text(
        json.dumps(good_data),
        encoding="utf-8",
    )
    (storage_dir / "localtuya_rc_codes.corrupt.2026-05-08T130000").write_text(
        "not-json",
        encoding="utf-8",
    )
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:good"}


def test_read_learned_codes_recovers_device_block_from_damaged_backup(tmp_path) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    damaged = '''
"version": 1,
"minor_version": 1,
"key": "localtuya_rc_codes",
"data": {
  "Living AC IR": {
    "power_off": "raw:off",
    "temp_24_f3": "raw:cool"
  }
}
'''
    (storage_dir / "localtuya_rc_codes.corrupt.2026-05-08T130000").write_text(
        damaged,
        encoding="utf-8",
    )
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {
        "power_off": "raw:off",
        "temp_24_f3": "raw:cool",
    }


def test_read_learned_codes_uses_only_device_when_name_has_small_mismatch(tmp_path) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "localtuya_rc_codes",
        "data": {"Living AC IR ": {"power_off": "raw:off"}},
    }
    (storage_dir / "localtuya_rc_codes").write_text(json.dumps(data), encoding="utf-8")
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:off"}


def test_read_learned_codes_uses_only_available_source_when_name_differs(tmp_path) -> None:
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "localtuya_rc_codes",
        "data": {"Living AC IR": {"power_off": "raw:off"}},
    }
    (storage_dir / "localtuya_rc_codes").write_text(json.dumps(data), encoding="utf-8")
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Media room") == {"power_off": "raw:off"}


def test_read_learned_codes_uses_portable_pack_without_localtuya_storage(tmp_path) -> None:
    library_dir = tmp_path / "aerostate_tuya_raw_codes"
    library_dir.mkdir()
    (library_dir / "lg_pc09sq_nsj_v1.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pack_id": "lg_pc09sq_nsj_v1",
                "device_name": "Living AC IR",
                "format": "tuya_remote_send_command_raw",
                "commands": {"power_off": "raw:portable_off", "temp_24": "raw:portable_24"},
            },
        ),
        encoding="utf-8",
    )
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {
        "power_off": "raw:portable_off",
        "temp_24": "raw:portable_24",
    }


def test_read_learned_codes_uses_bundled_pack_without_ha_storage(tmp_path, monkeypatch) -> None:
    bundled_dir = tmp_path / "bundled_raw_codes"
    bundled_dir.mkdir()
    (bundled_dir / "lg_pc09sq_nsj_v1.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pack_id": "lg_pc09sq_nsj_v1",
                "device_name": "LG PC09SQ NSJ",
                "format": "tuya_remote_send_command_raw",
                "commands": {"power_off": "raw:bundled_off", "temp_24": "raw:bundled_24"},
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tuya_raw_code_library, "_bundled_library_dir", lambda: str(bundled_dir))
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "LG PC09SQ NSJ") == {
        "power_off": "raw:bundled_off",
        "temp_24": "raw:bundled_24",
    }


def test_read_learned_codes_uses_single_portable_pack_when_name_differs(tmp_path) -> None:
    library_dir = tmp_path / "aerostate_tuya_raw_codes"
    library_dir.mkdir()
    (library_dir / "lg_pc09sq_nsj_v1.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pack_id": "lg_pc09sq_nsj_v1",
                "device_name": "LG PC09SQ NSJ",
                "format": "tuya_remote_send_command_raw",
                "commands": {"power_off": "raw:portable_off"},
            },
        ),
        encoding="utf-8",
    )
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:portable_off"}


def test_read_learned_codes_prefers_portable_pack_over_localtuya_cache(tmp_path) -> None:
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Living AC IR": {"power_off": "raw:storage_off"}},
        },
    )
    library_dir = tmp_path / "aerostate_tuya_raw_codes"
    library_dir.mkdir()
    (library_dir / "living_ac_ir.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pack_id": "living_ac_ir",
                "device_name": "Living AC IR",
                "commands": {"power_off": "raw:portable_off"},
            },
        ),
        encoding="utf-8",
    )

    assert read_learned_codes(hass, "Living AC IR") == {"power_off": "raw:portable_off"}


def test_export_portable_raw_codes_writes_copyable_pack(tmp_path) -> None:
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    path = export_portable_raw_codes(
        hass,
        device_name="Living AC IR",
        commands={"power_off": "raw:off", "ignored": "not-sendable"},
        pack_id="lg_pc09sq_nsj_v1",
    )

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["pack_id"] == "lg_pc09sq_nsj_v1"
    assert data["device_name"] == "Living AC IR"
    assert data["commands"] == {"power_off": "raw:off"}


def test_export_portable_raw_codes_can_write_integration_bundle(tmp_path, monkeypatch) -> None:
    bundled_dir = tmp_path / "bundled_raw_codes"
    monkeypatch.setattr(tuya_raw_code_library, "_bundled_library_dir", lambda: str(bundled_dir))
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))

    path = export_portable_raw_codes(
        hass,
        device_name="Living AC IR",
        commands={"power_off": "raw:off"},
        pack_id="lg_pc09sq_nsj_v1",
        destination="bundled",
    )

    assert Path(path).parent == bundled_dir
    assert json.loads(Path(path).read_text(encoding="utf-8"))["commands"] == {"power_off": "raw:off"}


def test_resolve_power_off_returns_raw_string() -> None:
    assert resolve_learned_code({"power_off": "raw:off"}, {"hvac_mode": "off"}) == "raw:off"


def test_resolve_cool_24_f3_exact_match() -> None:
    codes = {"temp_24": "raw:auto", "temp_24_f3": "raw:f3"}

    assert (
        resolve_learned_code(
            codes,
            {"hvac_mode": "cool", "target_temperature": 24, "fan_mode": "f3"},
        )
        == "raw:f3"
    )


def test_resolve_cool_27_f3_falls_back_to_temp_27() -> None:
    codes = {"temp_27": "raw:auto27"}

    assert (
        resolve_learned_code(
            codes,
            {"hvac_mode": "cool", "target_temperature": 27, "fan_mode": "f3"},
        )
        == "raw:auto27"
    )


def test_resolve_heat_raises_learned_code_not_available() -> None:
    with pytest.raises(LearnedCodeNotAvailable, match="Heat mode"):
        resolve_learned_code({"temp_24": "raw:cool"}, {"hvac_mode": "heat", "target_temperature": 24})


def test_resolve_dry_raises_learned_code_not_available() -> None:
    with pytest.raises(LearnedCodeNotAvailable, match="Dry mode"):
        resolve_learned_code({"temp_24": "raw:cool"}, {"hvac_mode": "dry", "target_temperature": 24})


def test_coverage_summary_identifies_gaps_correctly() -> None:
    coverage = get_coverage_summary(
        {
            "power_off": "raw:off",
            "power_on": "raw:on",
            "fan_speed_1": "raw:f1",
            "temp_16": "raw:t16",
            "temp_24_f3": "raw:t24f3",
        },
    )

    assert coverage["total_learned"] == 5
    assert coverage["has_power_off"] is True
    assert coverage["cool_temps_auto_fan"] == [16]
    assert coverage["cool_temps_with_specific_fan"] == [24]
    assert "cool temp 17C: no code at all" in coverage["gaps"]


@pytest.mark.asyncio
async def test_tuya_manager_sends_resolved_raw_command(tmp_path) -> None:
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Living AC IR": {"power_off": "raw:off"}},
        },
    )
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(get=lambda _entity_id: MagicMock(state="on"))
    manager = TuyaIRManager(hass, "remote.test_ir", "Living AC IR")

    await manager.async_send_climate_state({"hvac_mode": "off"})

    hass.services.async_call.assert_awaited_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.test_ir", "command": "raw:off"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_tuya_manager_sends_power_on_before_first_running_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("custom_components.aerostate.providers.tuya_ir_manager.POWER_ON_SETTLE_SECONDS", 0)
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {
                "Living AC IR": {
                    "power_on": "raw:on",
                    "power_off": "raw:off",
                    "temp_24": "raw:cool24",
                },
            },
        },
    )
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(get=lambda _entity_id: MagicMock(state="on"))
    manager = TuyaIRManager(hass, "remote.test_ir", "Living AC IR")

    await manager.async_send_climate_state(
        {"power": True, "hvac_mode": "cool", "target_temperature": 24, "fan_mode": "auto"},
    )

    assert [call.args[2]["command"] for call in hass.services.async_call.await_args_list] == [
        "raw:on",
        "raw:cool24",
    ]


@pytest.mark.asyncio
async def test_tuya_manager_sends_power_on_again_after_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("custom_components.aerostate.providers.tuya_ir_manager.POWER_ON_SETTLE_SECONDS", 0)
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {
                "Living AC IR": {
                    "power_on": "raw:on",
                    "power_off": "raw:off",
                    "temp_24": "raw:cool24",
                },
            },
        },
    )
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(get=lambda _entity_id: MagicMock(state="on"))
    manager = TuyaIRManager(hass, "remote.test_ir", "Living AC IR")

    await manager.async_send_climate_state({"power": False, "hvac_mode": "off"})
    await manager.async_send_climate_state(
        {"power": True, "hvac_mode": "cool", "target_temperature": 24, "fan_mode": "auto"},
    )

    assert [call.args[2]["command"] for call in hass.services.async_call.await_args_list] == [
        "raw:off",
        "raw:on",
        "raw:cool24",
    ]


@pytest.mark.asyncio
async def test_tuya_manager_does_not_repeat_power_on_when_already_running(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("custom_components.aerostate.providers.tuya_ir_manager.POWER_ON_SETTLE_SECONDS", 0)
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {
                "Living AC IR": {
                    "power_on": "raw:on",
                    "power_off": "raw:off",
                    "temp_24": "raw:cool24",
                    "temp_25": "raw:cool25",
                },
            },
        },
    )
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(get=lambda _entity_id: MagicMock(state="on"))
    manager = TuyaIRManager(hass, "remote.test_ir", "Living AC IR")

    await manager.async_send_climate_state(
        {"power": True, "hvac_mode": "cool", "target_temperature": 24, "fan_mode": "auto"},
    )
    await manager.async_send_climate_state(
        {"power": True, "hvac_mode": "cool", "target_temperature": 25, "fan_mode": "auto"},
    )

    assert [call.args[2]["command"] for call in hass.services.async_call.await_args_list] == [
        "raw:on",
        "raw:cool24",
        "raw:cool25",
    ]


@pytest.mark.asyncio
async def test_tuya_manager_notifies_when_learned_code_missing(tmp_path) -> None:
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Living AC IR": {"power_off": "raw:off"}},
        },
    )
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(get=lambda _entity_id: MagicMock(state="on"))
    manager = TuyaIRManager(hass, "remote.test_ir", "Living AC IR")

    with pytest.raises(LearnedCodeNotAvailable, match="Heat mode"):
        await manager.async_send_climate_state(
            {"hvac_mode": "heat", "target_temperature": 24, "fan_mode": "f3"},
        )

    hass.services.async_call.assert_awaited_once()
    assert hass.services.async_call.await_args.args[:2] == (
        "persistent_notification",
        "create",
    )
    assert "Heat mode" in hass.services.async_call.await_args.args[2]["message"]
