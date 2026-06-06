"""One-time Tuya Cloud importer for persistent local Daikin IR code sets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from ..packs.tuya.daikin.loader import (
    DaikinTuyaPackValidationError,
    load_daikin_tuya_pack,
    user_pack_dir,
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
    raise HomeAssistantError(f"Tuya did not return the {wanted_name} IR library")


def _normalize_codes(result: Any) -> dict[str, str]:
    codes: dict[str, str] = {}
    aliases = {"on": "power_on", "off": "power_off", "swing": "swing_vertical"}
    for entry in _items(result):
        raw_label = str(
            entry.get("label")
            or entry.get("command")
            or entry.get("key")
            or entry.get("key_name")
            or ""
        ).strip().lower()
        label = re.sub(r"[^a-z0-9]+", "_", raw_label).strip("_")
        label = aliases.get(label, label)
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


async def async_import_daikin_tuya_codes(
    hass,
    *,
    endpoint: str,
    access_id: str,
    access_secret: str,
    infrared_id: str,
) -> DaikinImportResult:
    """Fetch Daikin sets once, save local packs, and discard credentials."""
    config = TuyaCloudACConfig(
        endpoint=endpoint,
        access_id=access_id,
        access_secret=access_secret,
        infrared_id=infrared_id,
        remote_id="one-time-import-only",
    )
    api = TuyaCloudOpenAPI(hass, config)
    categories = _items(
        await api._request("GET", f"/v2.0/infrareds/{infrared_id}/categories", token_required=True)
    )
    category_id = _find_id(categories, "air conditioner", "category_id", "id")
    brands = _items(
        await api._request(
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories/{category_id}/brands",
            token_required=True,
        )
    )
    brand_id = _find_id(brands, "daikin", "brand_id", "id")
    remote_indexes = _items(
        await api._request(
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories/{category_id}/brands/{brand_id}/remote-indexs",
            query={"page": "1", "size": "1000"},
            token_required=True,
        )
    )

    imported: list[str] = []
    skipped = 0
    output = user_pack_dir(hass)
    for sequence, item in enumerate(remote_indexes, start=1):
        remote_index = str(item.get("remote_index") or item.get("id") or "").strip()
        if not remote_index:
            skipped += 1
            continue
        rules = await api._request(
            "GET",
            f"/v2.0/infrareds/{infrared_id}/categories/{category_id}/brands/{brand_id}"
            f"/remotes/{remote_index}/rules",
            token_required=True,
        )
        try:
            path = write_daikin_tuya_pack(output, sequence, remote_index, _normalize_codes(rules))
            load_daikin_tuya_pack(path.stem, hass=hass)
        except DaikinTuyaPackValidationError:
            skipped += 1
            continue
        imported.append(path.stem)

    if not imported:
        raise HomeAssistantError(
            "Tuya returned no Daikin code sets containing power_on, power_off, and cool_t24_fauto"
        )
    return DaikinImportResult(
        remote_index_count=len(remote_indexes),
        imported_count=len(imported),
        skipped_count=skipped,
        pack_ids=tuple(imported),
    )


__all__ = ["DaikinImportResult", "async_import_daikin_tuya_codes"]
