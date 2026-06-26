"""One-time Tuya Cloud importer for persistent local Daikin IR code sets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from ..packs.tuya.daikin.loader import (
    TARGET_DISPLAY_NAME,
    TARGET_INDOOR_MODEL,
    TARGET_PACK_ID,
    TARGET_REMOTE_MODEL,
    TARGET_REQUIRED_COMMANDS,
    TARGET_SOURCE,
    DaikinTuyaPackValidationError,
    load_daikin_tuya_pack,
    user_pack_dir,
    write_daikin_target_pack,
    write_daikin_tuya_pack,
)
from .tuya_cloud_ac import TuyaCloudACConfig, TuyaCloudOpenAPI


@dataclass(frozen=True, slots=True)
class DaikinImportResult:
    """Summary of one completed one-time import."""

    remote_index_count: int
    imported_count: int
    skipped_count: int
    pack_ids: tuple[str, ...]
    debug_dump_path: str | None = None


MODEL_HINT = TARGET_INDOOR_MODEL
REMOTE_HINT = TARGET_REMOTE_MODEL
_EXACT_MODEL_PRIORITIES = (
    ("brc4m150w", 120),
    ("brc4m150", 110),
    ("fxaq63pve6", 100),
)
_MODEL_PRIORITIES = (
    *_EXACT_MODEL_PRIORITIES,
    ("fxaq", 80),
    ("commercial", 50),
    ("brc", 45),
    ("vrv", 35),
    ("cassette", 25),
    ("indoor", 20),
    ("wall", 15),
)
_MODE_ALIASES = {
    "0": "cool",
    "cool": "cool",
    "cooling": "cool",
    "1": "heat",
    "heat": "heat",
    "heating": "heat",
    "2": "auto",
    "auto": "auto",
    "automatic": "auto",
    "3": "fan_only",
    "fan": "fan_only",
    "fanonly": "fan_only",
    "fan_only": "fan_only",
    "4": "dry",
    "dry": "dry",
    "dehumidify": "dry",
}
_FAN_ALIASES = {
    "0": "auto",
    "auto": "auto",
    "automatic": "auto",
    "1": "low",
    "low": "low",
    "lo": "low",
    "f1": "low",
    "2": "mid",
    "mid": "mid",
    "medium": "mid",
    "med": "mid",
    "f2": "mid",
    "3": "high",
    "high": "high",
    "hi": "high",
    "f3": "high",
}
_PAYLOAD_KEYS = (
    "key1",
    "payload",
    "raw",
    "raw_code",
    "ir_code",
    "code_value",
    "value",
    "code",
)
_LABEL_KEYS = (
    "label",
    "command",
    "command_name",
    "key",
    "key_name",
    "name",
    "code",
    "function",
)


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("list", "items", "data", "records", "remote_index_list"):
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, dict)]
    return []


def _iter_rule_entries(value: Any) -> list[dict[str, Any]]:
    """Return Tuya rule dictionaries that contain a usable raw payload."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if any(isinstance(node.get(key), str) and node.get(key).strip() for key in _PAYLOAD_KEYS):
            found.append(node)
        for child in node.values():
            if isinstance(child, (dict, list)):
                walk(child)

    walk(value)
    return found


def _find_id(items: list[dict[str, Any]], wanted_name: str, *id_keys: str) -> str:
    wanted = wanted_name.casefold()
    for item in items:
        name = str(item.get("name") or item.get("brand_name") or item.get("category_name") or "")
        if wanted in name.casefold():
            for key in id_keys:
                if item.get(key) is not None:
                    return str(item[key])
    raise HomeAssistantError(f"Tuya did not return the {wanted_name} IR library")


def _stringify_remote(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "name",
        "model",
        "model_name",
        "remote_name",
        "remote_model",
        "remote_index",
        "description",
        "remark",
        "brand_name",
    ):
        if item.get(key) is not None:
            values.append(str(item[key]))
    return " ".join(values).casefold()


def _remote_priority(item: dict[str, Any]) -> int:
    haystack = _stringify_remote(item)
    compact_haystack = re.sub(r"[^a-z0-9]+", "", haystack)
    score = 0
    for needle, weight in _MODEL_PRIORITIES:
        compact_needle = re.sub(r"[^a-z0-9]+", "", needle)
        if needle in haystack or compact_needle in compact_haystack:
            score = max(score, weight)
    return score


def _is_exact_remote_match(item: dict[str, Any]) -> bool:
    compact_haystack = re.sub(r"[^a-z0-9]+", "", _stringify_remote(item))
    return any(needle in compact_haystack for needle, _weight in _EXACT_MODEL_PRIORITIES)


def _prioritized_remote_indexes(remote_indexes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = [(idx, _remote_priority(item), item) for idx, item in enumerate(remote_indexes)]
    exact = [(idx, score, item) for idx, score, item in scored if _is_exact_remote_match(item)]
    if exact:
        return [item for idx, _score, item in sorted(exact, key=lambda row: (-row[1], row[0]))]
    return [item for idx, _score, item in sorted(scored, key=lambda row: (-row[1], row[0]))]


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _truthy_power(value: Any) -> bool | None:
    normalized = _normalize_token(value)
    if normalized in {"1", "true", "on", "power_on", "open", "start"}:
        return True
    if normalized in {"0", "false", "off", "power_off", "close", "stop"}:
        return False
    return None


def _first_present(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if entry.get(key) not in (None, ""):
            return entry[key]
    return None


def _label_from_state_fields(entry: dict[str, Any]) -> str | None:
    power = _first_present(entry, "power", "switch", "switch_state", "on_off", "power_state")
    power_state = _truthy_power(power)
    if power_state is True:
        return "power_on"
    if power_state is False:
        return "power_off"

    mode = _MODE_ALIASES.get(
        _normalize_token(_first_present(entry, "mode", "ac_mode", "work_mode", "mode_value"))
    )
    fan = _FAN_ALIASES.get(
        _normalize_token(_first_present(entry, "fan", "fan_mode", "fan_speed", "wind", "wind_speed"))
    )
    temp_raw = _first_present(
        entry,
        "temp",
        "temperature",
        "target_temperature",
        "temp_value",
        "set_temperature",
    )
    try:
        temp = int(float(temp_raw)) if temp_raw not in (None, "") else None
    except (TypeError, ValueError):
        temp = None

    if mode and fan and temp is not None:
        return f"{mode}_t{temp}_f{fan}"
    return None


def _label_from_text(value: str) -> str | None:
    label = _normalize_token(value)
    match = re.match(
        r"^(cool|heat|dry|auto|fan_only)_t?(\d{2})_f?(auto|low|mid|medium|med|high)$",
        label,
    )
    if not match:
        match = re.match(
            r"^(cool|heat|dry|auto|fan_only)_(\d{2})_(auto|low|mid|medium|med|high)$",
            label,
        )
    if not match:
        return None
    mode, temp, fan = match.groups()
    fan = _FAN_ALIASES.get(fan, fan)
    return f"{mode}_t{temp}_f{fan}"


def _normalize_label(entry: dict[str, Any]) -> str | None:
    state_label = _label_from_state_fields(entry)
    if state_label:
        return state_label

    raw = ""
    for key in _LABEL_KEYS:
        if entry.get(key) not in (None, ""):
            raw = str(entry[key])
            break
    label = _normalize_token(raw)
    text_label = _label_from_text(raw)
    if text_label:
        return text_label
    aliases = {
        "on": "power_on",
        "power": "power_on" if _truthy_power(entry.get("value")) is True else "power",
        "power_on": "power_on",
        "turn_on": "power_on",
        "off": "power_off",
        "power_off": "power_off",
        "turn_off": "power_off",
        "swing": "swing_vertical",
        "swing_on": "swing_vertical",
        "swing_vertical_toggle": "swing_vertical",
    }
    return aliases.get(label, label or None)


def _normalize_codes(result: Any) -> dict[str, str]:
    codes: dict[str, str] = {}
    for entry in _iter_rule_entries(result):
        label = _normalize_label(entry)
        payload = next(
            (
                str(entry[key]).strip()
                for key in _PAYLOAD_KEYS
                if isinstance(entry.get(key), str) and str(entry[key]).strip()
            ),
            None,
        )
        if label and isinstance(payload, str) and payload.strip():
            codes[label] = payload.strip()
    return codes


def _debug_path(output: Any) -> Any:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output / "_debug" / f"tuya_daikin_import_debug_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_debug_dump(
    output: Any,
    *,
    remote_index_count: int,
    selected_remote_index_count: int,
    imported: list[str],
    skipped: int,
    debug: list[dict[str, Any]],
) -> str:
    debug_path = _debug_path(output)
    debug_path.write_text(
        json.dumps(
            {
                "brand": "Daikin",
                "remote_hint": REMOTE_HINT,
                "model_hint": MODEL_HINT,
                "target_pack_id": TARGET_PACK_ID,
                "target_display_name": TARGET_DISPLAY_NAME,
                "cloud_disabled_at_runtime": True,
                "remote_index_count": remote_index_count,
                "selected_remote_index_count": selected_remote_index_count,
                "imported_pack_ids": imported,
                "skipped_count": skipped,
                "responses": debug,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return str(debug_path)


def _redacted_path(path: str, infrared_id: str) -> str:
    return path.replace(infrared_id, "{infrared_id}")


async def _recorded_request(
    api: TuyaCloudOpenAPI,
    debug: list[dict[str, Any]],
    method: str,
    path: str,
    *,
    infrared_id: str,
    query: dict[str, str] | None = None,
) -> Any:
    result = await api._request(method, path, query=query, token_required=True)
    debug.append(
        {
            "request": {
                "method": method,
                "path": _redacted_path(path, infrared_id),
                "query": query or {},
            },
            "result": result,
        }
    )
    return result


async def async_import_daikin_tuya_codes(
    hass,
    *,
    endpoint: str,
    access_id: str,
    access_secret: str,
    infrared_id: str | None = None,
    device_id: str | None = None,
) -> DaikinImportResult:
    """Fetch Daikin sets once, save local packs, and discard credentials."""
    infrared_id = str(infrared_id or device_id or "").strip()
    if not infrared_id:
        raise HomeAssistantError("Tuya infrared_id/device_id is required for Daikin import")
    config = TuyaCloudACConfig(
        endpoint=endpoint,
        access_id=access_id,
        access_secret=access_secret,
        infrared_id=infrared_id,
        remote_id="one-time-import-only",
    )
    api = TuyaCloudOpenAPI(hass, config)
    output = user_pack_dir(hass)
    debug: list[dict[str, Any]] = []
    categories = _items(
        await _recorded_request(
            api,
            debug,
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories",
            infrared_id=infrared_id,
        )
    )
    category_id = _find_id(categories, "air conditioner", "category_id", "id")
    brands = _items(
        await _recorded_request(
            api,
            debug,
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories/{category_id}/brands",
            infrared_id=infrared_id,
        )
    )
    brand_id = _find_id(brands, "daikin", "brand_id", "id")
    remote_indexes = _items(
        await _recorded_request(
            api,
            debug,
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories/{category_id}/brands/{brand_id}/remote-indexs",
            query={"page": "1", "size": "1000"},
            infrared_id=infrared_id,
        )
    )
    selected_remote_indexes = _prioritized_remote_indexes(remote_indexes)

    imported: list[str] = []
    skipped = 0
    target_written = False
    for sequence, item in enumerate(selected_remote_indexes, start=1):
        remote_index = str(item.get("remote_index") or item.get("id") or "").strip()
        if not remote_index:
            skipped += 1
            continue
        rules = await _recorded_request(
            api,
            debug,
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories/{category_id}/brands/{brand_id}"
            f"/remotes/{remote_index}/rules",
            infrared_id=infrared_id,
        )
        codes = _normalize_codes(rules)
        try:
            path = write_daikin_tuya_pack(output, sequence, remote_index, codes)
            load_daikin_tuya_pack(path.stem, directory=output)
        except DaikinTuyaPackValidationError:
            skipped += 1
        else:
            imported.append(path.stem)

        if (
            not target_written
            and _is_exact_remote_match(item)
            and TARGET_REQUIRED_COMMANDS.issubset(codes.keys())
        ):
            try:
                target_path = write_daikin_target_pack(
                    output,
                    codes,
                    remote_index=remote_index,
                    source=TARGET_SOURCE,
                )
                load_daikin_tuya_pack(target_path.stem, directory=output)
            except DaikinTuyaPackValidationError:
                pass
            else:
                target_written = True
                imported.insert(0, target_path.stem)

    debug_dump_path = _write_debug_dump(
        output,
        remote_index_count=len(remote_indexes),
        selected_remote_index_count=len(selected_remote_indexes),
        imported=imported,
        skipped=skipped,
        debug=debug,
    )
    if not imported:
        raise HomeAssistantError(
            "Tuya returned no Daikin code sets containing power_on, power_off, and cool_t24_fauto"
        )
    return DaikinImportResult(
        remote_index_count=len(remote_indexes),
        imported_count=len(imported),
        skipped_count=skipped,
        pack_ids=tuple(imported),
        debug_dump_path=debug_dump_path,
    )


__all__ = ["DaikinImportResult", "async_import_daikin_tuya_codes"]
