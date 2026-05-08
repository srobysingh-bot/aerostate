"""Portable AeroState raw-code library for Tuya IR remotes."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

RAW_CODE_LIBRARY_DIR = "aerostate_tuya_raw_codes"
RAW_CODE_LIBRARY_VERSION = 1
BUNDLED_RAW_CODE_LIBRARY_DIR = os.path.join("packs", "tuya", "raw_codes")


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


def _bundled_library_dir() -> str:
    """Return the raw-code library bundled with the installed integration."""
    return str(Path(__file__).resolve().parents[1] / BUNDLED_RAW_CODE_LIBRARY_DIR)


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


def _source_name_from_pack(filename: str, data: dict[str, Any]) -> str:
    """Pick a human-usable source name from portable pack metadata."""
    for key in ("device_name", "title", "pack_id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return filename[:-5]


def _iter_library_files(hass) -> list[tuple[str, str, str]]:
    """Return candidate raw-code JSON files in lookup order."""
    directories = [
        ("portable", _library_dir(hass)),
        ("bundled", _bundled_library_dir()),
    ]
    files: list[tuple[str, str, str]] = []
    seen_paths: set[str] = set()
    for source, directory in directories:
        try:
            filenames = sorted(
                filename
                for filename in os.listdir(directory)
                if filename.endswith(".json")
            )
        except OSError:
            continue
        for filename in filenames:
            path = os.path.join(directory, filename)
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            files.append((source, filename, path))
    return files


def list_portable_raw_code_sources(hass) -> list[dict[str, Any]]:
    """List available AeroState raw-code packs."""
    sources: list[dict[str, Any]] = []
    for source, filename, path in _iter_library_files(hass):
        data, codes = _load_portable_file(path)
        if not codes:
            continue
        sources.append(
            {
                "name": _source_name_from_pack(filename, data),
                "source": source,
                "command_count": len(codes),
                "path": path,
            }
        )
    return sources


def read_portable_raw_codes(hass, device_name: str) -> dict[str, str]:
    """Read raw codes from AeroState's portable or bundled library."""
    usable_packs: list[tuple[str, str, dict[str, str]]] = []
    for source, filename, path in _iter_library_files(hass):
        data, codes = _load_portable_file(path)
        if not codes:
            continue
        usable_packs.append((source, filename, codes))
        if _matches_pack(data, device_name) or _slug(filename[:-5]) == _slug(device_name):
            _LOGGER.info(
                "Loaded %d Tuya raw codes from AeroState %s raw-code pack %s",
                len(codes),
                source,
                filename,
            )
            return codes

    if len(usable_packs) == 1:
        source, filename, codes = usable_packs[0]
        _LOGGER.warning(
            "Loaded %d Tuya raw codes from the only AeroState %s raw-code pack %s; "
            "configured name '%s' did not match pack metadata",
            len(codes),
            source,
            filename,
            device_name,
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
    destination: str = "user",
) -> str:
    """Write raw codes to a user-copyable AeroState JSON pack and return its path."""
    cleaned = _clean_codes(commands)
    if not cleaned:
        raise ValueError("No raw or b64 Tuya IR commands available to export")

    pack_id = pack_id or _slug(device_name)
    library_dir = _bundled_library_dir() if destination == "bundled" else _library_dir(hass)
    os.makedirs(library_dir, exist_ok=True)
    path = os.path.join(library_dir, f"{_slug(pack_id)}.json")
    payload = {
        "version": RAW_CODE_LIBRARY_VERSION,
        "pack_id": pack_id,
        "title": title or device_name,
        "device_name": device_name,
        "format": "tuya_remote_send_command_raw",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": "Portable AeroState Tuya IR raw-code pack. Copy this file to another HA /config/aerostate_tuya_raw_codes/ directory or ship it in custom_components/aerostate/packs/tuya/raw_codes/.",
        "commands": dict(sorted(cleaned.items())),
    }
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=2, sort_keys=True)
        file_obj.write("\n")
    _LOGGER.info("Exported %d Tuya raw codes to %s", len(cleaned), path)
    return path


def ensure_portable_raw_code_pack(
    hass,
    *,
    device_name: str,
    commands: dict[str, str],
    pack_id: str | None = None,
    title: str | None = None,
) -> str | None:
    """Persist localtuya learned codes into AeroState's portable user library if missing."""
    if read_portable_raw_codes(hass, device_name):
        return None
    try:
        return export_portable_raw_codes(
            hass,
            device_name=device_name,
            commands=commands,
            pack_id=pack_id,
            title=title,
        )
    except Exception as err:
        _LOGGER.warning("Could not save AeroState Tuya raw-code pack for '%s': %s", device_name, err)
        return None


def describe_portable_library(hass, device_name: str) -> dict[str, Any]:
    """Return diagnostics-safe details about the portable library."""
    library_dir = _library_dir(hass)
    try:
        filenames = sorted(filename for filename in os.listdir(library_dir) if filename.endswith(".json"))
    except OSError:
        filenames = []
    bundled_dir = _bundled_library_dir()
    try:
        bundled_files = sorted(filename for filename in os.listdir(bundled_dir) if filename.endswith(".json"))
    except OSError:
        bundled_files = []
    codes = read_portable_raw_codes(hass, device_name)
    return {
        "directory": library_dir,
        "json_files": filenames,
        "bundled_directory": bundled_dir,
        "bundled_json_files": bundled_files,
        "matched_command_count": len(codes),
    }
