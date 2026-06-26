"""One-time Tuya Cloud importer for Daikin IR code-set packs.

This script is intentionally outside the Home Assistant integration runtime.
It uses Tuya Cloud only while generating local data-only packs.

Tuya API references:
- /v2.0/infrareds/{infrared_id}/categories/{category_id}/brands/{brand_id}/remote-indexs
- /v2.0/infrareds/{infrared_id}/categories/{category_id}/brands/{brand_id}/remotes/{remote_index}/rules
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from custom_components.aerostate.packs.tuya.daikin.loader import (
    TARGET_DISPLAY_NAME,
    TARGET_INDOOR_MODEL,
    TARGET_PACK_ID,
    TARGET_REMOTE_MODEL,
    TARGET_REQUIRED_COMMANDS,
    TARGET_SOURCE,
)
from custom_components.aerostate.packs.tuya.daikin.loader import (
    write_daikin_target_pack as _write_daikin_target_pack,
)
from custom_components.aerostate.packs.tuya.daikin.loader import (
    write_daikin_tuya_pack as _write_daikin_tuya_pack,
)

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "aerostate"
    / "packs"
    / "tuya"
    / "daikin"
)
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
_PAYLOAD_KEYS = ("key1", "payload", "raw", "raw_code", "ir_code", "code_value", "value", "code")
_LABEL_KEYS = ("label", "command", "command_name", "key", "key_name", "name", "code", "function")


class TuyaOpenAPI:
    """Small synchronous OpenAPI client used only by this importer."""

    def __init__(self, endpoint: str, access_id: str, access_secret: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.access_id = access_id
        self.access_secret = access_secret
        self.access_token = ""

    def request(self, method: str, path: str, query: dict[str, str] | None = None) -> Any:
        method = method.upper()
        path_query = path
        if query:
            path_query += "?" + urllib.parse.urlencode(sorted(query.items()))
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{method}\n{EMPTY_SHA256}\n\n{path_query}"
        seed = self.access_id + self.access_token + timestamp + string_to_sign
        signature = hmac.new(
            self.access_secret.encode(), seed.encode(), hashlib.sha256
        ).hexdigest().upper()
        headers = {
            "client_id": self.access_id,
            "sign": signature,
            "sign_method": "HMAC-SHA256",
            "t": timestamp,
        }
        if self.access_token:
            headers["access_token"] = self.access_token
        request = urllib.request.Request(self.endpoint + path_query, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("success"):
            raise RuntimeError(f"Tuya Cloud API error {payload.get('code')}: {payload.get('msg')}")
        return payload.get("result")

    def authenticate(self) -> None:
        result = self.request("GET", "/v1.0/token", {"grant_type": "1"})
        self.access_token = str(result["access_token"])


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("list", "items", "data", "records", "remote_index_list"):
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, dict)]
    return []


def _iter_rule_entries(value: Any) -> list[dict[str, Any]]:
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
    raise RuntimeError(f"Could not find {wanted_name!r} in Tuya response")


def _remote_priority(item: dict[str, Any]) -> int:
    haystack = " ".join(
        str(item[key])
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
        )
        if item.get(key) is not None
    ).casefold()
    compact_haystack = re.sub(r"[^a-z0-9]+", "", haystack)
    score = 0
    for needle, weight in _MODEL_PRIORITIES:
        compact_needle = re.sub(r"[^a-z0-9]+", "", needle)
        if needle in haystack or compact_needle in compact_haystack:
            score = max(score, weight)
    return score


def _is_exact_remote_match(item: dict[str, Any]) -> bool:
    compact_haystack = re.sub(
        r"[^a-z0-9]+",
        "",
        " ".join(str(value) for value in item.values()).casefold(),
    )
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

    mode = _MODE_ALIASES.get(_normalize_token(_first_present(entry, "mode", "ac_mode", "work_mode", "mode_value")))
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


def _write_pack(output: Path, sequence: int, remote_index: str, codes: dict[str, str]) -> Path:
    return _write_daikin_tuya_pack(output, sequence, remote_index, codes)


def _codes_from_capture(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("CODES", "codes", "commands"):
            value = payload.get(key)
            if isinstance(value, dict):
                return {
                    str(label).strip(): str(command).strip()
                    for label, command in value.items()
                    if str(label).strip() and isinstance(command, str) and command.strip()
                }
    raise RuntimeError("Capture JSON must contain a CODES, codes, or commands object")


def _redacted_path(path: str, infrared_id: str) -> str:
    return path.replace(infrared_id, "{infrared_id}")


def _debug_path(output: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output / "_debug" / f"tuya_daikin_import_debug_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.getenv("TUYA_ENDPOINT", "https://openapi.tuyain.com"))
    parser.add_argument("--access-id", default=os.getenv("TUYA_ACCESS_ID"))
    parser.add_argument("--access-secret", default=os.getenv("TUYA_ACCESS_SECRET"))
    parser.add_argument("--infrared-id", default=os.getenv("TUYA_INFRARED_ID"), required=False)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--capture-json",
        type=Path,
        help=(
            "Build the BRC4M150W / FXAQ63PVE6 target pack from physical-remote "
            "localtuya_rc captures instead of Tuya Cloud."
        ),
    )
    args = parser.parse_args()
    if args.capture_json:
        path = _write_daikin_target_pack(
            args.output,
            _codes_from_capture(args.capture_json),
            source=TARGET_SOURCE,
        )
        print(f"WROTE {path}")
        return 0

    if not all([args.access_id, args.access_secret, args.infrared_id]):
        parser.error("--access-id, --access-secret, and --infrared-id (or matching env vars) are required")

    api = TuyaOpenAPI(args.endpoint, args.access_id, args.access_secret)
    api.authenticate()
    debug: list[dict[str, Any]] = []

    def recorded_request(method: str, path: str, query: dict[str, str] | None = None) -> Any:
        result = api.request(method, path, query)
        debug.append(
            {
                "request": {
                    "method": method,
                    "path": _redacted_path(path, args.infrared_id),
                    "query": query or {},
                },
                "result": result,
            }
        )
        return result

    categories = _items(recorded_request("GET", f"/v2.0/infrareds/{args.infrared_id}/categories"))
    category_id = _find_id(categories, "air conditioner", "category_id", "id")
    brands = _items(
        recorded_request("GET", f"/v2.0/infrareds/{args.infrared_id}/categories/{category_id}/brands")
    )
    brand_id = _find_id(brands, "daikin", "brand_id", "id")
    remote_indexes = _items(
        recorded_request(
            "GET",
            f"/v2.0/infrareds/{args.infrared_id}/categories/{category_id}/brands/{brand_id}/remote-indexs",
            {"page": "1", "size": "1000"},
        )
    )
    selected_remote_indexes = _prioritized_remote_indexes(remote_indexes)

    written = 0
    pack_ids: list[str] = []
    skipped = 0
    target_written = False
    for sequence, item in enumerate(selected_remote_indexes, start=1):
        remote_index = str(item.get("remote_index") or item.get("id") or "").strip()
        if not remote_index:
            skipped += 1
            continue
        result = recorded_request(
            "GET",
            f"/v2.0/infrareds/{args.infrared_id}/categories/{category_id}/brands/{brand_id}"
            f"/remotes/{remote_index}/rules",
        )
        codes = _normalize_codes(result)
        try:
            path = _write_pack(args.output, sequence, remote_index, codes)
        except Exception as err:
            print(f"SKIP {err}")
            skipped += 1
            continue
        print(f"WROTE {path}")
        pack_ids.append(path.stem)
        written += 1
        if (
            not target_written
            and _is_exact_remote_match(item)
            and TARGET_REQUIRED_COMMANDS.issubset(codes.keys())
        ):
            try:
                target_path = _write_daikin_target_pack(args.output, codes, remote_index=remote_index)
            except Exception as err:
                print(f"SKIP target {err}")
            else:
                print(f"WROTE {target_path}")
                pack_ids.insert(0, target_path.stem)
                target_written = True
    debug_path = _debug_path(args.output)
    debug_path.write_text(
        json.dumps(
            {
                "brand": "Daikin",
                "remote_hint": REMOTE_HINT,
                "model_hint": MODEL_HINT,
                "target_pack_id": TARGET_PACK_ID,
                "target_display_name": TARGET_DISPLAY_NAME,
                "cloud_disabled_at_runtime": True,
                "remote_index_count": len(remote_indexes),
                "selected_remote_index_count": len(selected_remote_indexes),
                "imported_pack_ids": pack_ids,
                "skipped_count": skipped,
                "responses": debug,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"DEBUG {debug_path}")
    print(f"Generated {written} validated Daikin local pack(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
