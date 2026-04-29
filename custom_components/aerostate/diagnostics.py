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
    CONF_IR_CONVERSION_ENABLED,
    CONF_IR_PROVIDER,
    CONF_MODEL_PACK,
    CONF_POWER_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    DEFAULT_IR_PROVIDER,
    DOMAIN,
)
from .engines import create_engine
from .flow_helpers import describe_pack_limitations
from .packs.coverage import get_pack_coverage_report
from .packs.registry import get_registry
from .packs.truth import build_mode_truth
from .providers.ir_manager import create_ir_manager_from_entry
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
    broadlink_state = hass.states.get(broadlink_entity).state if broadlink_entity and hass.states.get(broadlink_entity) else None

    coverage = get_pack_coverage_report(pack) if pack else None
    mode_truth = build_mode_truth(pack) if pack else None
    physically_verified_modes = [mode for mode, meta in (mode_truth or {}).items() if meta.get("physically_verified")]
    experimental_modes = [mode for mode, meta in (mode_truth or {}).items() if meta.get("status") == "experimental"]
    transport_available = False
    validation_states_ready = False
    ir_transport_effective = None

    configured_ir_provider = entry.options.get(CONF_IR_PROVIDER, entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER))

    cfg_ir_conversion = entry.options.get(CONF_IR_CONVERSION_ENABLED, entry.data.get(CONF_IR_CONVERSION_ENABLED, False))
    if isinstance(cfg_ir_conversion, str):
        configured_ir_conversion_enabled = cfg_ir_conversion.strip().lower() in ("1", "true", "yes", "on")
    else:
        configured_ir_conversion_enabled = bool(cfg_ir_conversion)

    if pack and broadlink_entity:
        engine = create_engine(pack)
        ir_mgr = create_ir_manager_from_entry(hass, entry, lg_engine=engine, registry=registry)
        transport_available = await ir_mgr.probe_active_transport()
        ir_transport_effective = ir_mgr.effective_ir_mode()
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
            "broadlink_entity_state": broadlink_state,
            "ir_provider_configured": configured_ir_provider,
            "ir_transport_effective": ir_transport_effective,
            "ir_conversion_enabled": configured_ir_conversion_enabled,
            "tuya_ir_entity": entry.options.get(CONF_TUYA_IR_ENTITY, entry.data.get(CONF_TUYA_IR_ENTITY)),
            "tuya_model_pack": entry.options.get(CONF_TUYA_MODEL_PACK, entry.data.get(CONF_TUYA_MODEL_PACK)),
            "pack_id": pack_id,
            "selected_pack_id": pack_id,
            "pack_brand": pack.brand if pack else None,
            "pack_version": pack.pack_version if pack else None,
            "engine_type": pack.engine_type if pack else None,
            "protocol_path_active": bool(pack and pack.engine_type == "lg_protocol"),
            "pack_verified": pack.verified if pack else None,
            "pack_experimental": (not pack.verified) if pack else None,
            "pack_notes": pack.notes if pack else None,
            "pack_limitations": describe_pack_limitations(pack) if pack else None,
            "pack_models": pack.models if pack else None,
            "pack_mvp_test_only": pack.mvp_test_pack if pack else None,
            "pack_mode_truth": mode_truth,
            "physically_verified_modes": physically_verified_modes,
            "experimental_modes": experimental_modes,
            "pack_temperature_range": [pack.min_temperature, pack.max_temperature] if pack else None,
            "pack_capabilities_summary": {
                "hvac_modes": pack.capabilities.hvac_modes if pack else None,
                "fan_modes": pack.capabilities.fan_modes if pack else None,
                "swing_vertical_modes": pack.capabilities.swing_vertical_modes if pack else None,
                "swing_horizontal_modes": pack.capabilities.swing_horizontal_modes if pack else None,
                "preset_modes": (getattr(pack.capabilities, "preset_modes", []) or pack.capabilities.presets) if pack else None,
                "supports_jet": getattr(pack.capabilities, "supports_jet", False) if pack else None,
            },
            "supported_modes": pack.capabilities.hvac_modes if pack else None,
            "supported_fan_modes": pack.capabilities.fan_modes if pack else None,
            "supported_swing_vertical": pack.capabilities.swing_vertical_modes if pack else None,
            "supported_swing_horizontal": pack.capabilities.swing_horizontal_modes if pack else None,
            "supported_preset_modes": (getattr(pack.capabilities, "preset_modes", []) or pack.capabilities.presets) if pack else None,
            "jet_supported": getattr(pack.capabilities, "supports_jet", False) if pack else None,
            "jet_status": (
                "experimental"
                if pack and getattr(pack.capabilities, "supports_jet", False) and not pack.verified
                else ("verified" if pack and getattr(pack.capabilities, "supports_jet", False) else "unsupported")
            ),
            "linked_temperature_sensor": entry.options.get(CONF_TEMP_SENSOR, entry.data.get(CONF_TEMP_SENSOR)),
            "linked_humidity_sensor": entry.options.get(CONF_HUM_SENSOR, entry.data.get(CONF_HUM_SENSOR)),
            "linked_power_sensor": entry.options.get(CONF_POWER_SENSOR, entry.data.get(CONF_POWER_SENSOR)),
            "validation_readiness": {
                "transport_available": transport_available,
                "validation_states_ready": validation_states_ready,
                "ready": transport_available and validation_states_ready,
            },
            "support_summary": {
                "selected_pack_id": pack_id,
                "engine_type": pack.engine_type if pack else None,
                "protocol_path_active": bool(pack and pack.engine_type == "lg_protocol"),
                "verified": pack.verified if pack else None,
                "physically_verified_hvac_modes": physically_verified_modes,
                "fan_modes": pack.capabilities.fan_modes if pack else None,
                "temperature_range": [pack.min_temperature, pack.max_temperature] if pack else None,
                "swing_support": {
                    "vertical": bool(pack and pack.capabilities.swing_vertical_modes),
                    "horizontal": bool(pack and pack.capabilities.swing_horizontal_modes),
                    "horizontal_modes": pack.capabilities.swing_horizontal_modes if pack else None,
                },
                "linked_sensors": {
                    "temperature": entry.options.get(CONF_TEMP_SENSOR, entry.data.get(CONF_TEMP_SENSOR)),
                    "humidity": entry.options.get(CONF_HUM_SENSOR, entry.data.get(CONF_HUM_SENSOR)),
                    "power": entry.options.get(CONF_POWER_SENSOR, entry.data.get(CONF_POWER_SENSOR)),
                },
                "broadlink_entity": broadlink_entity,
                "broadlink_entity_state": broadlink_state,
                "limitations": describe_pack_limitations(pack) if pack else None,
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
