"""Tests for the one-time Home Assistant Daikin Tuya importer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.aerostate.packs.tuya.daikin.loader import list_daikin_tuya_packs
from custom_components.aerostate.providers import tuya_daikin_importer


class _FakeAPI:
    def __init__(self, _hass, _config) -> None:
        self.remote_index_query = None

    async def _request(self, _method: str, path: str, **_kwargs):
        if path.endswith("/categories"):
            return [{"name": "Air Conditioner", "category_id": "ac"}]
        if path.endswith("/brands"):
            return [{"brand_name": "Daikin", "brand_id": "daikin"}]
        if path.endswith("/remote-indexs"):
            self.remote_index_query = _kwargs.get("query")
            assert self.remote_index_query == {"page": "1", "size": "1000"}
            return {
                "remote_index_list": [{"remote_index": "101"}, {"remote_index": "102"}],
                "total_count": 2,
            }
        if path.endswith("/remotes/101/rules"):
            return [
                {"key": "power_on", "code": "raw:on"},
                {"key": "power_off", "code": "raw:off"},
                {"key": "cool_t24_fauto", "code": "raw:cool24"},
            ]
        if path.endswith("/remotes/102/rules"):
            return [{"key": "power_on", "code": "raw:incomplete"}]
        raise AssertionError(path)


@pytest.mark.asyncio
async def test_one_time_import_saves_persistent_user_pack_and_skips_invalid(
    tmp_path,
    monkeypatch,
) -> None:
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda rel: str(tmp_path / rel)))
    monkeypatch.setattr(tuya_daikin_importer, "TuyaCloudOpenAPI", _FakeAPI)

    result = await tuya_daikin_importer.async_import_daikin_tuya_codes(
        hass,
        endpoint="https://openapi.tuyain.com",
        access_id="id",
        access_secret="secret",
        infrared_id="ir-device",
    )

    assert result.imported_count == 1
    assert result.skipped_count == 1
    assert result.pack_ids == ("daikin_tuya_set_001",)
    assert (tmp_path / "aerostate_tuya_daikin_codes" / "daikin_tuya_set_001.py").exists()
    assert [pack.pack_id for pack in list_daikin_tuya_packs(hass=hass)] == [
        "daikin_tuya_set_001"
    ]
