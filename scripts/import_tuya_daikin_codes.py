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
import pprint
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "aerostate"
    / "packs"
    / "tuya"
    / "daikin"
)


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


def _find_id(items: list[dict[str, Any]], wanted_name: str, *id_keys: str) -> str:
    wanted = wanted_name.casefold()
    for item in items:
        name = str(item.get("name") or item.get("brand_name") or item.get("category_name") or "")
        if wanted in name.casefold():
            for key in id_keys:
                if item.get(key) is not None:
                    return str(item[key])
    raise RuntimeError(f"Could not find {wanted_name!r} in Tuya response")


def _normalize_label(entry: dict[str, Any]) -> str | None:
    raw = str(
        entry.get("label")
        or entry.get("command")
        or entry.get("key")
        or entry.get("key_name")
        or ""
    ).strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    aliases = {"on": "power_on", "off": "power_off", "swing": "swing_vertical"}
    return aliases.get(raw, raw or None)


def _normalize_codes(result: Any) -> dict[str, str]:
    codes: dict[str, str] = {}
    for entry in _items(result):
        label = _normalize_label(entry)
        payload = (
            entry.get("key1")
            or entry.get("payload")
            or entry.get("raw")
            or entry.get("code")
            or entry.get("value")
        )
        if label and isinstance(payload, str) and payload.strip():
            codes[label] = payload.strip()
    return codes


def _python_literal(value: Any) -> str:
    return pprint.pformat(value, sort_dicts=True, width=100)


def _write_pack(output: Path, sequence: int, remote_index: str, codes: dict[str, str]) -> Path:
    required = {"power_on", "power_off", "cool_t24_fauto"}
    missing = sorted(required - codes.keys())
    if missing:
        raise RuntimeError(f"remote_index={remote_index} missing required commands: {', '.join(missing)}")
    if any(value.lower().startswith("b64:") for value in codes.values()):
        raise RuntimeError(f"remote_index={remote_index} contains a Broadlink/native-b64 payload")

    pack_id = f"daikin_tuya_set_{sequence:03d}"
    fans = sorted(
        {match.group(1) for label in codes if (match := re.search(r"_f([a-z0-9_]+)$", label))}
    )
    temps = sorted(
        {int(match.group(1)) for label in codes if (match := re.search(r"_t(\d+)_", label))}
    )
    metadata = {
        "pack_id": pack_id,
        "display_name": f"Daikin Tuya code set {sequence:03d}",
        "brand": "Daikin",
        "provider": "tuya_local",
        "remote_index": remote_index,
        "source": "Tuya Cloud IR code library one-time import",
        "temp_range": [min(temps), max(temps)] if temps else [16, 30],
        "fan_modes": fans or ["auto"],
        "swing_support": "swing_vertical" in codes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "payload_format": "localtuya_rc_raw",
    }
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{pack_id}.py"
    path.write_text(
        '"""Generated Daikin Tuya local IR code-set pack. Do not edit manually."""\n\n'
        f"METADATA = {_python_literal(metadata)}\n\n"
        f"CODES = {_python_literal(dict(sorted(codes.items())))}\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.getenv("TUYA_ENDPOINT", "https://openapi.tuyain.com"))
    parser.add_argument("--access-id", default=os.getenv("TUYA_ACCESS_ID"))
    parser.add_argument("--access-secret", default=os.getenv("TUYA_ACCESS_SECRET"))
    parser.add_argument("--infrared-id", default=os.getenv("TUYA_INFRARED_ID"), required=False)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not all([args.access_id, args.access_secret, args.infrared_id]):
        parser.error("--access-id, --access-secret, and --infrared-id (or matching env vars) are required")

    api = TuyaOpenAPI(args.endpoint, args.access_id, args.access_secret)
    api.authenticate()
    categories = _items(api.request("GET", f"/v2.0/infrareds/{args.infrared_id}/categories"))
    category_id = _find_id(categories, "air conditioner", "category_id", "id")
    brands = _items(
        api.request("GET", f"/v2.0/infrareds/{args.infrared_id}/categories/{category_id}/brands")
    )
    brand_id = _find_id(brands, "daikin", "brand_id", "id")
    remote_indexes = _items(
        api.request(
            "GET",
            f"/v2.0/infrareds/{args.infrared_id}/categories/{category_id}/brands/{brand_id}/remote-indexs",
            {"page": "1", "size": "1000"},
        )
    )

    written = 0
    for sequence, item in enumerate(remote_indexes, start=1):
        remote_index = str(item.get("remote_index") or item.get("id") or "").strip()
        if not remote_index:
            continue
        result = api.request(
            "GET",
            f"/v2.0/infrareds/{args.infrared_id}/categories/{category_id}/brands/{brand_id}"
            f"/remotes/{remote_index}/rules",
        )
        try:
            path = _write_pack(args.output, sequence, remote_index, _normalize_codes(result))
        except RuntimeError as err:
            print(f"SKIP {err}")
            continue
        print(f"WROTE {path}")
        written += 1
    print(f"Generated {written} validated Daikin local pack(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
