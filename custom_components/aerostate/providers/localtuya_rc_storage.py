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

    Handles missing primary files by finding the largest corrupt backup and
    handles // commented JSON automatically.
    """
    config_dir = _config_dir(hass)
    storage_dir = os.path.join(config_dir, ".storage")
    primary_path = os.path.join(storage_dir, STORAGE_KEY)

    if os.path.exists(primary_path) and os.path.getsize(primary_path) > 100:
        result = _load_device_codes(primary_path, device_name)
        if result:
            return result

    _LOGGER.warning(
        "Primary localtuya_rc_codes not usable, searching backups in %s",
        storage_dir,
    )

    try:
        candidates = [
            filename
            for filename in os.listdir(storage_dir)
            if filename.startswith(f"{STORAGE_KEY}.corrupt.")
        ]
    except OSError:
        _LOGGER.error("Cannot list storage directory %s", storage_dir)
        return {}

    if not candidates:
        _LOGGER.error(
            "No localtuya_rc_codes backups found in %s. Learn IR codes first using remote.learn_command.",
            storage_dir,
        )
        return {}

    best_path = None
    best_size = 0
    for candidate in candidates:
        full_path = os.path.join(storage_dir, candidate)
        try:
            size = os.path.getsize(full_path)
        except OSError:
            continue
        if size > best_size:
            best_size = size
            best_path = full_path

    if not best_path:
        return {}

    _LOGGER.warning(
        "Using backup %s (%d bytes). Fix permanently: cp '%s' '/config/.storage/localtuya_rc_codes'",
        os.path.basename(best_path),
        best_size,
        best_path,
    )
    return _load_device_codes(best_path, device_name)
