"""Tests for localtuya_rc learned-code Tuya IR support."""

from __future__ import annotations

import json
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


def test_read_learned_codes_returns_empty_for_missing_device(tmp_path) -> None:
    hass = _hass_with_storage(
        tmp_path,
        {
            "version": 1,
            "minor_version": 1,
            "key": "localtuya_rc_codes",
            "data": {"Other": {"power_off": "raw:1,2,3"}},
        },
    )

    assert read_learned_codes(hass, "Living AC IR") == {}


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
