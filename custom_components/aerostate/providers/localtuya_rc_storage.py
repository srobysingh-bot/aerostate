"""Read learned IR codes from localtuya_rc Home Assistant storage."""

from __future__ import annotations

import json
import logging
import os

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "localtuya_rc_codes"


def read_learned_codes(hass, device_name: str) -> dict[str, str]:
    """Read learned IR codes for one localtuya_rc device name."""
    storage_path = hass.config.path(f".storage/{STORAGE_KEY}")
    if not os.path.exists(storage_path):
        _LOGGER.warning("localtuya_rc_codes storage not found at %s", storage_path)
        return {}

    try:
        with open(storage_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
    except (json.JSONDecodeError, OSError) as err:
        _LOGGER.error("Failed to read localtuya_rc_codes storage: %s", err)
        return {}

    devices = data.get("data", {})
    device_codes = devices.get(device_name, {})

    if not device_codes:
        _LOGGER.warning(
            "Device '%s' not found in localtuya_rc_codes storage. Available devices: %s",
            device_name,
            list(devices.keys()) if isinstance(devices, dict) else [],
        )
        return {}

    _LOGGER.debug("Loaded %d learned codes for device '%s'", len(device_codes), device_name)
    return {
        str(command_name): str(raw_string)
        for command_name, raw_string in device_codes.items()
        if isinstance(raw_string, str)
    }
