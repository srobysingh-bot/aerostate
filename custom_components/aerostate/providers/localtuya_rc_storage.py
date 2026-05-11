"""Read learned IR codes from localtuya_rc Home Assistant storage."""

from __future__ import annotations

import json
import logging
import os
import re

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "localtuya_rc_codes"


def _strip_json_comments(raw: str) -> str:
    """Strip localtuya_rc // prefixes while preserving normal JSON lines."""
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("// "):
            lines.append(stripped[3:])
        elif stripped.startswith("//"):
            lines.append(stripped[2:].lstrip())
        else:
            lines.append(line)
    return "\n".join(lines)


def _clean_device_codes(device_codes: object) -> dict[str, str]:
    """Normalize a parsed command map to string raw payloads."""
    if not isinstance(device_codes, dict):
        return {}
    return {
        str(command_name): raw_string
        for command_name, raw_string in device_codes.items()
        if isinstance(raw_string, str)
    }


def _normalize_name(name: str) -> str:
    """Normalize localtuya_rc device names for tolerant matching."""
    return " ".join(str(name).strip().casefold().split())


def _device_codes_from_parsed(data: object, device_name: str, path: str) -> dict[str, str]:
    """Extract device command map from parsed localtuya_rc storage JSON."""
    if not isinstance(data, dict):
        return {}

    devices = data.get("data", data)
    if not isinstance(devices, dict):
        _LOGGER.error("Storage file %s has invalid data section", path)
        return {}

    requested = _normalize_name(device_name)
    matched_device_name = None
    device_codes = None
    if device_name.strip():
        device_codes = devices.get(device_name)
        if isinstance(device_codes, dict):
            matched_device_name = device_name
        else:
            for candidate_name, candidate_codes in devices.items():
                if _normalize_name(str(candidate_name)) == requested:
                    matched_device_name = str(candidate_name)
                    device_codes = candidate_codes
                    break
    elif len(devices) == 1:
        matched_device_name, device_codes = next(iter(devices.items()))
    else:
        for candidate_name, candidate_codes in devices.items():
            if _normalize_name(str(candidate_name)) == requested:
                matched_device_name = str(candidate_name)
                device_codes = candidate_codes
                break

    cleaned = _clean_device_codes(device_codes)
    if not cleaned:
        _LOGGER.error(
            "Device '%s' not found in storage. Available devices: %s - check your device name in AeroState options.",
            device_name,
            list(devices.keys()),
        )
        return {}

    _LOGGER.debug(
        "Loaded %d codes for '%s' from %s",
        len(cleaned),
        matched_device_name or device_name,
        os.path.basename(path),
    )
    return cleaned


def _all_device_codes_from_parsed(data: object) -> dict[str, dict[str, str]]:
    """Extract all usable device command maps from parsed localtuya_rc data."""
    if not isinstance(data, dict):
        return {}
    devices = data.get("data", data)
    if not isinstance(devices, dict):
        return {}
    return {
        str(device_name): cleaned
        for device_name, device_codes in devices.items()
        if (cleaned := _clean_device_codes(device_codes))
    }


def _extract_device_codes_from_fragment(clean_json: str, device_name: str, path: str) -> dict[str, str]:
    """
    Recover a device command map from a damaged storage backup.

    Some .corrupt files can be JSON-like fragments but still contain a valid
    "Living AC IR": {...} object. Extract that object directly.
    """
    decoder = json.JSONDecoder()
    requested = _normalize_name(device_name)
    for match in re.finditer(r'"(?P<name>[^"]+)"\s*:\s*\{', clean_json):
        candidate_name = match.group("name")
        brace_pos = clean_json.find("{", match.start())
        if brace_pos < 0:
            continue
        try:
            parsed, _end = decoder.raw_decode(clean_json[brace_pos:])
        except json.JSONDecodeError:
            continue
        cleaned = _clean_device_codes(parsed)
        if cleaned:
            if _normalize_name(candidate_name) == requested:
                _LOGGER.warning(
                    "Recovered %d codes for '%s' from damaged storage file %s",
                    len(cleaned),
                    candidate_name,
                    os.path.basename(path),
                )
                return cleaned
    return {}


def _extract_all_device_codes_from_fragment(clean_json: str) -> dict[str, dict[str, str]]:
    """Recover all valid device command maps from a damaged storage backup."""
    decoder = json.JSONDecoder()
    recovered: dict[str, dict[str, str]] = {}
    for match in re.finditer(r'"(?P<name>[^"]+)"\s*:\s*\{', clean_json):
        candidate_name = match.group("name")
        brace_pos = clean_json.find("{", match.start())
        if brace_pos < 0:
            continue
        try:
            parsed, _end = decoder.raw_decode(clean_json[brace_pos:])
        except json.JSONDecodeError:
            continue
        cleaned = _clean_device_codes(parsed)
        if cleaned:
            recovered[candidate_name] = cleaned
    return recovered


def _load_device_codes(path: str, device_name: str) -> dict[str, str]:
    """Load device codes from a localtuya_rc storage file path."""
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            raw = file_obj.read()
    except OSError as err:
        _LOGGER.error("Cannot read storage file %s: %s", path, err)
        return {}
    if not raw.strip():
        _LOGGER.error("Storage file %s is empty", path)
        return {}

    clean_json = _strip_json_comments(raw)
    try:
        data = json.loads(clean_json)
    except json.JSONDecodeError as err:
        recovered = _extract_device_codes_from_fragment(clean_json, device_name, path)
        if recovered:
            return recovered
        _LOGGER.error("Failed to parse %s after stripping comments: %s", os.path.basename(path), err)
        return {}
    return _device_codes_from_parsed(data, device_name, path)


def _load_all_device_codes(path: str) -> dict[str, dict[str, str]]:
    """Load all device code maps from one localtuya_rc storage file path."""
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            raw = file_obj.read()
    except OSError as err:
        _LOGGER.error("Cannot read storage file %s: %s", path, err)
        return {}
    if not raw.strip():
        return {}

    clean_json = _strip_json_comments(raw)
    try:
        data = json.loads(clean_json)
    except json.JSONDecodeError:
        return _extract_all_device_codes_from_fragment(clean_json)
    return _all_device_codes_from_parsed(data)


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
    """Read raw Tuya IR codes from portable AeroState pack, then localtuya_rc cache."""
    from .tuya_raw_code_library import read_portable_raw_codes

    portable_codes = read_portable_raw_codes(hass, device_name)
    localtuya_codes = read_localtuya_storage_codes(hass, device_name, log_missing=not bool(portable_codes))

    if portable_codes and localtuya_codes:
        merged_codes = dict(portable_codes)
        merged_codes.update(localtuya_codes)
        if len(merged_codes) > len(portable_codes):
            _LOGGER.warning(
                "AeroState portable raw-code pack for '%s' had %d commands; "
                "localtuya_rc storage filled it to %d commands",
                device_name,
                len(portable_codes),
                len(merged_codes),
            )
            _save_portable_copy(hass, device_name=device_name, commands=merged_codes)
        return merged_codes

    if portable_codes:
        return portable_codes

    if localtuya_codes:
        _save_portable_copy(hass, device_name=device_name, commands=localtuya_codes)
        return localtuya_codes

    sources = list_available_code_sources(hass)
    if len(sources) == 1:
        source_name = str(sources[0].get("name", "")).strip()
        if source_name and _normalize_name(source_name) != _normalize_name(device_name):
            _LOGGER.warning(
                "Configured Tuya code source '%s' did not match; using the only available source '%s'",
                device_name,
                source_name,
            )
            fallback_codes = read_portable_raw_codes(hass, source_name) or read_localtuya_storage_codes(hass, source_name)
            if fallback_codes:
                _save_portable_copy(hass, device_name=source_name, commands=fallback_codes)
            return fallback_codes
    return {}


def _save_portable_copy(hass, *, device_name: str, commands: dict[str, str]) -> None:
    """Best-effort save of learned codes into AeroState's portable user library."""
    from .tuya_raw_code_library import export_portable_raw_codes

    clean_name = device_name.strip()
    try:
        export_portable_raw_codes(
            hass,
            device_name=clean_name,
            commands=commands,
            pack_id=f"{clean_name}_learned_raw_codes" if clean_name else None,
            title=clean_name or None,
        )
    except Exception as err:
        _LOGGER.warning("Could not save AeroState Tuya raw-code pack for '%s': %s", device_name, err)


def list_available_code_sources(hass) -> list[dict[str, object]]:
    """List portable and localtuya_rc code sources available on this HA."""
    from .tuya_raw_code_library import list_portable_raw_code_sources

    sources = list_portable_raw_code_sources(hass)
    seen = {("portable", str(source.get("name", ""))) for source in sources}
    for name, codes, path in _iter_localtuya_source_codes(hass):
        key = ("localtuya_rc", name)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "name": name,
                "source": "localtuya_rc",
                "command_count": len(codes),
                "path": path,
            }
        )
    return sources


def _iter_localtuya_source_codes(hass):
    """Yield available localtuya_rc device code maps from primary/backups."""
    config_dir = _config_dir(hass)
    storage_dir = os.path.join(config_dir, ".storage")
    paths: list[str] = []
    primary_path = os.path.join(storage_dir, STORAGE_KEY)
    if os.path.exists(primary_path):
        paths.append(primary_path)
    try:
        candidates = [
            os.path.join(storage_dir, filename)
            for filename in sorted(os.listdir(storage_dir), reverse=True)
            if filename.startswith(f"{STORAGE_KEY}.corrupt.")
        ]
    except OSError:
        candidates = []
    paths.extend(candidates)

    seen_names: set[str] = set()
    for path in paths:
        for name, codes in _load_all_device_codes(path).items():
            normalized = _normalize_name(name)
            if normalized in seen_names:
                continue
            seen_names.add(normalized)
            yield name, codes, path


def read_localtuya_storage_codes(hass, device_name: str, *, log_missing: bool = True) -> dict[str, str]:
    """
    Read learned IR codes for a device from localtuya_rc storage only.

    Tries the normal file first, then the most recent corrupt backup if the
    normal file is missing. Handles // commented JSON automatically.
    """
    config_dir = _config_dir(hass)
    storage_dir = os.path.join(config_dir, ".storage")
    primary_path = os.path.join(storage_dir, STORAGE_KEY)

    if os.path.exists(primary_path):
        result = _load_device_codes(primary_path, device_name)
        if result:
            return result
        if log_missing:
            _LOGGER.warning("localtuya_rc_codes at %s was not usable - searching backups", primary_path)
    else:
        if log_missing:
            _LOGGER.warning("localtuya_rc_codes not found at %s - searching for backup", primary_path)

    try:
        candidates = [
            filename
            for filename in os.listdir(storage_dir)
            if filename.startswith(f"{STORAGE_KEY}.corrupt.")
        ]
    except OSError:
        candidates = []

    if not candidates:
        if log_missing:
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
    for candidate in candidates:
        backup_path = os.path.join(storage_dir, candidate)
        _LOGGER.warning(
            "Trying corrupt backup: %s - Fix this permanently by copying a working backup to localtuya_rc_codes:\n"
            "  cp '%s' '%s'",
            candidate,
            backup_path,
            primary_path,
        )
        result = _load_device_codes(backup_path, device_name)
        if result:
            return result

    if log_missing:
        _LOGGER.error("No usable localtuya_rc_codes backup found in %s", storage_dir)
    return {}
