"""Tests for Tuya Cloud Daikin code-library control."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.aerostate.packs.tuya_cloud.registry import get_tuya_cloud_pack
from custom_components.aerostate.providers.tuya_cloud_ac import (
    TuyaCloudACConfig,
    TuyaCloudACManager,
)


class _FakeTuyaCloudAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, object]] = []

    async def async_send_ac_command(
        self,
        infrared_id: str,
        remote_id: str,
        code: str,
        value: object,
    ) -> None:
        self.calls.append((infrared_id, remote_id, code, value))

    async def async_get_ac_status(self, _infrared_id: str, _remote_id: str) -> dict:
        return {"power": 1}


def _config() -> TuyaCloudACConfig:
    return TuyaCloudACConfig(
        endpoint="https://openapi.tuyain.com",
        access_id="access-id",
        access_secret="access-secret",
        infrared_id="ir-device-id",
        remote_id="daikin-remote-id",
    )


def test_tuya_cloud_daikin_pack_exposes_code_library_capabilities() -> None:
    pack = get_tuya_cloud_pack("tuya_cloud.daikin_ac.v1")

    assert pack.brand == "Daikin"
    assert pack.transport == "tuya_cloud_ac"
    assert pack.capabilities.hvac_modes == ["cool", "heat", "heat_cool", "fan_only", "dry"]
    assert pack.capabilities.fan_modes == ["auto", "low", "medium", "high"]
    assert pack.capabilities.swing_vertical_modes == []


@pytest.mark.asyncio
async def test_tuya_cloud_manager_sends_daikin_single_command_sequence() -> None:
    api = _FakeTuyaCloudAPI()
    manager = TuyaCloudACManager(SimpleNamespace(), _config(), api=api)

    await manager.async_send_climate_state(
        {
            "power": True,
            "hvac_mode": "cool",
            "target_temperature": 24,
            "fan_mode": "high",
        }
    )

    assert api.calls == [
        ("ir-device-id", "daikin-remote-id", "power", 1),
        ("ir-device-id", "daikin-remote-id", "mode", 0),
        ("ir-device-id", "daikin-remote-id", "temp", 24),
        ("ir-device-id", "daikin-remote-id", "wind", 3),
    ]


@pytest.mark.asyncio
async def test_tuya_cloud_manager_sends_only_changed_daikin_setting() -> None:
    api = _FakeTuyaCloudAPI()
    manager = TuyaCloudACManager(SimpleNamespace(), _config(), api=api)

    base = {
        "power": True,
        "hvac_mode": "cool",
        "target_temperature": 24,
        "fan_mode": "auto",
    }
    await manager.async_send_climate_state(base)
    await manager.async_send_climate_state({**base, "target_temperature": 25})

    assert api.calls[-1] == ("ir-device-id", "daikin-remote-id", "temp", 25)


@pytest.mark.asyncio
async def test_tuya_cloud_manager_sends_off_as_power_zero() -> None:
    api = _FakeTuyaCloudAPI()
    manager = TuyaCloudACManager(SimpleNamespace(), _config(), api=api)

    await manager.async_send_climate_state({"power": False, "hvac_mode": "off"})

    assert api.calls == [("ir-device-id", "daikin-remote-id", "power", 0)]

