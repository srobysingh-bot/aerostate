"""Repair helpers for AeroState integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_BROADLINK_ENTITY,
    CONF_HUM_SENSOR,
    CONF_MODEL_PACK,
    CONF_POWER_SENSOR,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from .packs.coverage import get_pack_coverage_report
from .packs.registry import get_registry

ISSUE_DOMAIN = DOMAIN


def _issue_id(entry: ConfigEntry, suffix: str) -> str:
    return f"{entry.entry_id}_{suffix}"


def _create_issue(hass: HomeAssistant, entry: ConfigEntry, suffix: str, translation_key: str) -> None:
    ir.async_create_issue(
        hass,
        ISSUE_DOMAIN,
        _issue_id(entry, suffix),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=translation_key,
        data={"entry_id": entry.entry_id},
    )


def _delete_issue(hass: HomeAssistant, entry: ConfigEntry, suffix: str) -> None:
    ir.async_delete_issue(hass, ISSUE_DOMAIN, _issue_id(entry, suffix))


def async_report_command_failure(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a repair issue for command resolution/transport failures."""
    _create_issue(hass, entry, "command_resolution_failure", "command_resolution_failure")


def async_clear_command_failure(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear command failure issue once command path is healthy again."""
    _delete_issue(hass, entry, "command_resolution_failure")


def async_report_validation_failed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a repair issue for self-test or onboarding validation failures."""
    _create_issue(hass, entry, "validation_failed", "validation_failed")


def async_clear_validation_failed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear validation failure issue once validation succeeds."""
    _delete_issue(hass, entry, "validation_failed")


def async_validate_entry_runtime(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create/delete repair issues based on current config/runtime state."""
    broadlink_entity = entry.options.get(CONF_BROADLINK_ENTITY, entry.data.get(CONF_BROADLINK_ENTITY))
    pack_id = entry.options.get(CONF_MODEL_PACK, entry.data.get(CONF_MODEL_PACK))

    if not broadlink_entity or hass.states.get(broadlink_entity) is None:
        _create_issue(hass, entry, "missing_remote", "missing_remote")
    else:
        _delete_issue(hass, entry, "missing_remote")

    try:
        pack = get_registry().get(pack_id)
        if not pack.capabilities.hvac_modes:
            _create_issue(hass, entry, "invalid_pack", "invalid_pack")
        else:
            _delete_issue(hass, entry, "invalid_pack")

        if not pack.verified:
            _create_issue(hass, entry, "experimental_pack", "experimental_pack")
        else:
            _delete_issue(hass, entry, "experimental_pack")

        coverage = get_pack_coverage_report(pack)
        transport_available = bool(
            broadlink_entity
            and hass.states.get(broadlink_entity)
            and hass.states.get(broadlink_entity).state not in ("unknown", "unavailable")
        )
        if transport_available and coverage.get("issues"):
            _create_issue(hass, entry, "incomplete_command_matrix", "incomplete_command_matrix")
        else:
            _delete_issue(hass, entry, "incomplete_command_matrix")
    except Exception:
        _create_issue(hass, entry, "missing_pack", "missing_pack")

    for sensor_key, suffix in (
        (CONF_TEMP_SENSOR, "missing_temp_sensor"),
        (CONF_HUM_SENSOR, "missing_humidity_sensor"),
        (CONF_POWER_SENSOR, "missing_power_sensor"),
    ):
        sensor_entity = entry.options.get(sensor_key, entry.data.get(sensor_key))
        if sensor_entity and hass.states.get(sensor_entity) is None:
            _create_issue(hass, entry, suffix, suffix)
        else:
            _delete_issue(hass, entry, suffix)
