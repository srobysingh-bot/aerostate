"""Shared helpers for AeroState config and options flows."""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_AREA,
    CONF_BROADLINK_ENTITY,
    CONF_MODEL_PACK,
    CONF_NAME,
    DOMAIN,
)


def build_entry_unique_id(broadlink_entity: str, model_pack_id: str) -> str:
    """Build stable unique ID used to prevent duplicate entries."""
    return f"{broadlink_entity}::{model_pack_id}"


def has_entry_collision(
    hass,
    broadlink_entity: str,
    model_pack_id: str,
    current_entry_id: str | None = None,
) -> bool:
    """Return True if an entry already uses the same remote + pack identity."""
    candidate = build_entry_unique_id(broadlink_entity, model_pack_id)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if current_entry_id and entry.entry_id == current_entry_id:
            continue

        if entry.unique_id == candidate:
            return True

        entry_remote = entry.options.get(
            CONF_BROADLINK_ENTITY,
            entry.data.get(CONF_BROADLINK_ENTITY, ""),
        )
        entry_pack = entry.options.get(
            CONF_MODEL_PACK,
            entry.data.get(CONF_MODEL_PACK, ""),
        )
        if build_entry_unique_id(str(entry_remote), str(entry_pack)) == candidate:
            return True

    return False


def describe_pack_limitations(pack) -> str:
    """Return a concise user-facing limitation summary for selected pack."""
    cool_only = pack.capabilities.hvac_modes == ["cool"]
    no_swing = (
        not pack.capabilities.swing_vertical_modes
        and not pack.capabilities.swing_horizontal_modes
    )

    if pack.verified and cool_only and no_swing:
        return "Verified cool-only pack. No swing payloads included."
    if pack.engine_type == "lg_protocol":
        limitations: list[str] = []
        horizontal_modes = list(getattr(pack.capabilities, "swing_horizontal_modes", []))
        supports_jet = bool(getattr(pack.capabilities, "supports_jet", False))

        if horizontal_modes and all(mode in {"off", "on", "swing", "auto"} for mode in horizontal_modes):
            limitations.append(
                "Horizontal swing is supported in toggle form only (off/on). Advanced horizontal positions are intentionally not exposed until model-specific protocol values or captured frames are verified."
            )
        if not supports_jet:
            limitations.append("Jet/Turbo is disabled until protocol ON/OFF frames are validated.")

        if limitations:
            return " ".join(limitations)

    if pack.engine_type == "lg_protocol" and not pack.verified:
        return "Experimental protocol-generated LG control. Verify behavior on real hardware."
    if not pack.verified:
        return "Experimental pack. Validate behavior before daily use."
    if no_swing:
        return "Verified pack without swing payloads."
    return ""


def build_entry_title(pack, sensor_data: dict[str, Any]) -> str:
    """Build config entry title from name/area/model in stable order."""
    selected_name = (sensor_data.get(CONF_NAME) or "").strip()
    selected_area = (sensor_data.get(CONF_AREA) or "").strip()
    model_label = pack.models[0] if pack.models else f"{pack.brand} AC"
    if selected_name:
        return selected_name
    if selected_area:
        return f"{model_label} ({selected_area})"
    return model_label
