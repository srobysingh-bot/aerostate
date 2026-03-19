"""Diagnostics support for AeroState."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
from .providers import BroadlinkProvider
from .validation import build_safe_validation_states

TO_REDACT: set[str] = set()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    registry = get_registry()
    pack_id = entry.options.get(CONF_MODEL_PACK, entry.data.get(CONF_MODEL_PACK))
    try:
        pack = registry.get(pack_id)
    except Exception:
        pack = None

    unique_id = f"{entry.entry_id}_climate"
    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get_entity_id("climate", DOMAIN, unique_id)
    entity_state = hass.states.get(entity_entry) if entity_entry else None

    broadlink_entity = entry.options.get(
        CONF_BROADLINK_ENTITY,
        entry.data.get(CONF_BROADLINK_ENTITY),
    )

    coverage = get_pack_coverage_report(pack) if pack else None
    transport_available = False
    validation_states_ready = False
    if pack and broadlink_entity:
        provider = BroadlinkProvider(hass, broadlink_entity)
        transport_available = await provider.test_connection()
        try:
            states = build_safe_validation_states(pack, "basic")
            validation_states_ready = len(states) > 1
        except Exception:
            validation_states_ready = False

    payload: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "resolved": {
            "broadlink_entity": broadlink_entity,
            "pack_id": pack_id,
            "pack_brand": pack.brand if pack else None,
            "pack_version": pack.pack_version if pack else None,
            "pack_verified": pack.verified if pack else None,
            "pack_experimental": (not pack.verified) if pack else None,
            "pack_notes": pack.notes if pack else None,
            "pack_models": pack.models if pack else None,
            "pack_mvp_test_only": pack.mvp_test_pack if pack else None,
            "pack_temperature_range": [pack.min_temperature, pack.max_temperature] if pack else None,
            "pack_capabilities_summary": {
                "hvac_modes": pack.capabilities.hvac_modes if pack else None,
                "fan_modes": pack.capabilities.fan_modes if pack else None,
                "swing_vertical_modes": pack.capabilities.swing_vertical_modes if pack else None,
                "swing_horizontal_modes": pack.capabilities.swing_horizontal_modes if pack else None,
            },
            "supported_modes": pack.capabilities.hvac_modes if pack else None,
            "supported_fan_modes": pack.capabilities.fan_modes if pack else None,
            "supported_swing_vertical": pack.capabilities.swing_vertical_modes if pack else None,
            "supported_swing_horizontal": pack.capabilities.swing_horizontal_modes if pack else None,
            "linked_temperature_sensor": entry.options.get(CONF_TEMP_SENSOR, entry.data.get(CONF_TEMP_SENSOR)),
            "linked_humidity_sensor": entry.options.get(CONF_HUM_SENSOR, entry.data.get(CONF_HUM_SENSOR)),
            "linked_power_sensor": entry.options.get(CONF_POWER_SENSOR, entry.data.get(CONF_POWER_SENSOR)),
            "validation_readiness": {
                "transport_available": transport_available,
                "validation_states_ready": validation_states_ready,
                "ready": transport_available and validation_states_ready,
            },
            "last_self_test": hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("last_self_test"),
            "coverage": coverage,
        },
        "entity": {
            "entity_id": entity_entry,
            "unique_id": unique_id,
            "state": entity_state.state if entity_state else None,
            "attributes": dict(entity_state.attributes) if entity_state else None,
        },
        "runtime_data_keys": list(hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).keys()),
    }

    return async_redact_data(payload, TO_REDACT)
