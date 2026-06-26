"""Tests for the one-time Home Assistant Daikin Tuya importer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.aerostate.packs.tuya.daikin.loader import (
    TARGET_PACK_ID,
    list_daikin_tuya_packs,
)
from custom_components.aerostate.providers import tuya_daikin_importer


class _FakeAPI:
    def __init__(self, _hass, _config) -> None:
        self.remote_index_query = None
        self.paths: list[str] = []

    async def _request(self, _method: str, path: str, **_kwargs):
        self.paths.append(path)
        if path.endswith("/categories"):
            return [{"name": "Air Conditioner", "category_id": "ac"}]
        if path.endswith("/brands"):
            return [{"brand_name": "Daikin", "brand_id": "daikin"}]
        if path.endswith("/remote-indexs"):
            self.remote_index_query = _kwargs.get("query")
            assert self.remote_index_query == {"page": "1", "size": "1000"}
            return {
                "remote_index_list": [
                    {"remote_index": "101", "remote_name": "Generic Daikin"},
                    {"remote_index": "102", "remote_name": "Daikin BRC4M150W FXAQ63PVE6 VRV indoor"},
                    {"remote_index": "103", "remote_name": "Daikin cassette BRC family"},
                ],
                "total_count": 3,
            }
        if path.endswith("/remotes/102/rules"):
            return [
                {"key": "power_on", "key1": "raw:on"},
                {"key": "power_off", "key1": "raw:off"},
                {"mode": 0, "temp": 24, "wind": 0, "key1": "raw:cool24"},
                {"key": "cool 24 low", "key1": "raw:cool24low"},
                {"key": "cool_t24_medium", "key1": "raw:cool24mid"},
                {"key": "cool_t24_fhigh", "key1": "raw:cool24high"},
            ]
        if path.endswith("/remotes/103/rules"):
            return [{"key": "power_on", "code": "raw:incomplete"}]
        raise AssertionError(path)


@pytest.mark.asyncio
async def test_one_time_import_saves_persistent_user_pack_and_skips_invalid(
    tmp_path,
    monkeypatch,
) -> None:
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))
    monkeypatch.setattr(tuya_daikin_importer, "TuyaCloudOpenAPI", _FakeAPI)
    monkeypatch.setattr(tuya_daikin_importer, "user_pack_dir", lambda _hass: tmp_path)

    result = await tuya_daikin_importer.async_import_daikin_tuya_codes(
        hass,
        endpoint="https://openapi.tuyain.com",
        access_id="id",
        access_secret="secret",
        infrared_id="ir-device",
    )

    assert result.imported_count == 2
    assert result.skipped_count == 0
    assert result.pack_ids == (TARGET_PACK_ID, "daikin_tuya_set_001")
    assert (tmp_path / "daikin_tuya_set_001.py").exists()
    assert (tmp_path / f"{TARGET_PACK_ID}.py").exists()
    assert result.debug_dump_path is not None
    assert (tmp_path / "_debug").exists()
    assert [pack.pack_id for pack in list_daikin_tuya_packs(directory=tmp_path)] == [
        TARGET_PACK_ID,
        "daikin_tuya_set_001"
    ]
