"""Read learned IR codes from localtuya_rc Home Assistant storage."""

from __future__ import annotations

import json
import logging
import os

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "localtuya_rc_codes"


def _load_device_codes(path: str, device_name: str) -> dict[str, str]:
    """
    Load device codes from localtuya_rc storage file.

    localtuya_rc may store exported/recovered data as commented JSON where each
    line is prefixed with // or // . Strip those prefixes before parsing.
    """
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            raw = file_obj.read()
    except OSError as err:
        _LOGGER.error("Cannot read storage file %s: %s", path, err)
        return {}

    if not raw.strip():
        _LOGGER.error("Storage file %s is empty", path)
        return {}

    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("// "):
            lines.append(stripped[3:])
        elif stripped.startswith("//"):
            lines.append(stripped[2:].lstrip())
        else:
            lines.append(line)

    try:
        data = json.loads("\n".join(lines))
    except json.JSONDecodeError as err:
        _LOGGER.error(
            "Failed to parse %s after stripping comments: %s",
            os.path.basename(path),
            err,
        )
        return {}

    devices = data.get("data", {})
    if not isinstance(devices, dict):
        _LOGGER.error("Storage file %s has invalid data section", path)
        return {}

    device_codes = devices.get(device_name, {})
    if not device_codes:
        _LOGGER.error(
            "Device '%s' not found in storage. Available: %s",
            device_name,
            list(devices.keys()),
        )
        return {}
    if not isinstance(device_codes, dict):
        _LOGGER.error("Device '%s' storage entry is not a command map", device_name)
        return {}

    _LOGGER.debug(
        "Loaded %d codes for '%s' from %s",
        len(device_codes),
        device_name,
        os.path.basename(path),
    )
    return {
        str(command_name): str(raw_string)
        for command_name, raw_string in device_codes.items()
        if isinstance(raw_string, str)
    }


def _config_dir(hass) -> str:
    """Return HA config dir, tolerating lightweight test hass objects."""
    config_dir = getattr(hass.config, "config_dir", None)
    if config_dir:
        return str(config_dir)
    config_path = getattr(hass.config, "path", None)
    if callable(config_path):
        return os.path.dirname(config_path(".storage"))
    return os.getcwd()


def read_learned_codes(hass, device_name: str) -> dict[str, str]:
    """
    Read learned IR codes for a device from localtuya_rc storage.

    Tries the normal file first, then the most recent corrupt backup if the
    normal file is missing. Handles // commented JSON automatically.
    """
    config_dir = _config_dir(hass)
    storage_dir = os.path.join(config_dir, ".storage")
    primary_path = os.path.join(storage_dir, STORAGE_KEY)

    if os.path.exists(primary_path):
        return _load_device_codes(primary_path, device_name)

    _LOGGER.warning(
        "localtuya_rc_codes not found at %s - searching for backup",
        primary_path,
    )

    try:
        candidates = [
            filename
            for filename in os.listdir(storage_dir)
            if filename.startswith(f"{STORAGE_KEY}.corrupt.")
        ]
    except OSError:
        candidates = []

    if not candidates:
        _LOGGER.error(
            "No localtuya_rc_codes file found in %s. Fix: run this in Terminal:\n"
            "  ls /config/.storage/localtuya_rc_codes*\n"
            "If you see a .corrupt file, copy it:\n"
            "  cp '/config/.storage/localtuya_rc_codes.corrupt.TIMESTAMP' "
            "'/config/.storage/localtuya_rc_codes'",
            storage_dir,
        )
        return {}

    candidates.sort(reverse=True)
    backup_path = os.path.join(storage_dir, candidates[0])

    _LOGGER.warning(
        "Using corrupt backup: %s - Fix this permanently by copying it to localtuya_rc_codes:\n"
        "  cp '%s' '%s'",
        candidates[0],
        backup_path,
        primary_path,
    )
    return _load_device_codes(backup_path, device_name)
