"""Portable AeroState raw-code library for Tuya IR remotes."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

RAW_CODE_LIBRARY_DIR = "aerostate_tuya_raw_codes"
RAW_CODE_LIBRARY_VERSION = 1


def _config_dir(hass) -> str:
    """Return Home Assistant config dir, tolerating lightweight test hass objects."""
    hass_config = getattr(hass, "config", None)
    config_dir = getattr(hass_config, "config_dir", None)
    if config_dir:
        return str(config_dir)
    config_path = getattr(hass_config, "path", None)
    if callable(config_path):
        return os.path.dirname(config_path(RAW_CODE_LIBRARY_DIR))
    return os.getcwd()


def _library_dir(hass) -> str:
    """Return the user-copyable AeroState raw-code library directory."""
    return os.path.join(_config_dir(hass), RAW_CODE_LIBRARY_DIR)


def _slug(value: str) -> str:
    """Return a stable file-safe id."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold()).strip("_")
    return slug or "tuya_raw_codes"


def _clean_codes(raw_codes: object) -> dict[str, str]:
    """Keep only string command payloads that look sendable."""
    if not isinstance(raw_codes, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in raw_codes.items():
        if not isinstance(value, str):
            continue
        payload = value.strip()
        if payload.startswith(("raw:", "b64:")):
            cleaned[str(key)] = payload
    return cleaned


def _matches_pack(data: dict[str, Any], requested_name: str) -> bool:
    """Return True if a portable pack matches the configured device/pack name."""
    requested = _slug(requested_name)
    candidates = [
        data.get("pack_id"),
        data.get("device_name"),
        data.get("title"),
    ]
    candidates.extend(data.get("models", []) if isinstance(data.get("models"), list) else [])
    return requested in {_slug(str(candidate)) for candidate in candidates if candidate}


def _load_portable_file(path: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Load one portable AeroState raw-code JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
    except (OSError, json.JSONDecodeError) as err:
        _LOGGER.warning("Skipping invalid AeroState raw-code file %s: %s", path, err)
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}
    codes = _clean_codes(data.get("commands") or data.get("codes"))
    return data, codes


def read_portable_raw_codes(hass, device_name: str) -> dict[str, str]:
    """Read raw codes from AeroState's portable library."""
    library_dir = _library_dir(hass)
    try:
        filenames = sorted(
            filename
            for filename in os.listdir(library_dir)
            if filename.endswith(".json")
        )
    except OSError:
        return {}

    first_pack: tuple[str, dict[str, str]] | None = None
    for filename in filenames:
        path = os.path.join(library_dir, filename)
        data, codes = _load_portable_file(path)
        if not codes:
            continue
        if first_pack is None:
            first_pack = (filename, codes)
        if _matches_pack(data, device_name) or _slug(filename[:-5]) == _slug(device_name):
            _LOGGER.info(
                "Loaded %d Tuya raw codes from AeroState portable pack %s",
                len(codes),
                filename,
            )
            return codes

    if first_pack and device_name.strip() == "":
        filename, codes = first_pack
        _LOGGER.info(
            "Loaded %d Tuya raw codes from first AeroState portable pack %s",
            len(codes),
            filename,
        )
        return codes
    return {}


def export_portable_raw_codes(
    hass,
    *,
    device_name: str,
    commands: dict[str, str],
    pack_id: str | None = None,
    title: str | None = None,
) -> str:
    """Write raw codes to a user-copyable AeroState JSON pack and return its path."""
    cleaned = _clean_codes(commands)
    if not cleaned:
        raise ValueError("No raw or b64 Tuya IR commands available to export")

    pack_id = pack_id or _slug(device_name)
    library_dir = _library_dir(hass)
    os.makedirs(library_dir, exist_ok=True)
    path = os.path.join(library_dir, f"{_slug(pack_id)}.json")
    payload = {
        "version": RAW_CODE_LIBRARY_VERSION,
        "pack_id": pack_id,
        "title": title or device_name,
        "device_name": device_name,
        "format": "tuya_remote_send_command_raw",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": "Portable AeroState Tuya IR raw-code pack. Copy this file to another HA /config/aerostate_tuya_raw_codes/ directory.",
        "commands": dict(sorted(cleaned.items())),
    }
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=2, sort_keys=True)
        file_obj.write("\n")
    _LOGGER.info("Exported %d Tuya raw codes to %s", len(cleaned), path)
    return path


def describe_portable_library(hass, device_name: str) -> dict[str, Any]:
    """Return diagnostics-safe details about the portable library."""
    library_dir = _library_dir(hass)
    try:
        filenames = sorted(filename for filename in os.listdir(library_dir) if filename.endswith(".json"))
    except OSError:
        filenames = []
    codes = read_portable_raw_codes(hass, device_name)
    return {
        "directory": library_dir,
        "json_files": filenames,
        "matched_command_count": len(codes),
    }
