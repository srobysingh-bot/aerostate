"""Unit tests for climate capability exposure and validation behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.aerostate.climate import AeroStateClimate
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


class _FakeStates:
    def get(self, entity_id: str):
        return None


class _FakeUnits:
    temperature_unit = "C"


class _FakeConfig:
    units = _FakeUnits()


class _FakeHass:
    def __init__(self) -> None:
        self.config = _FakeConfig()
        self.states = _FakeStates()


class _FakeProvider:
    async def send_base64(self, payload: str) -> None:
        return None


class _FakeEngine:
    def resolve_command(self, state: dict) -> str:
        return "AAA"


class _FakeCapabilityEngine(_FakeEngine):
    def __init__(
        self,
        vertical: list[str] | None = None,
        horizontal: list[str] | None = None,
        presets: list[str] | None = None,
    ) -> None:
        self._vertical = vertical or []
        self._horizontal = horizontal or []
        self._presets = presets or []

    def supported_vertical_swing_modes(self) -> list[str]:
        return list(self._vertical)

    def supported_horizontal_swing_modes(self) -> list[str]:
        return list(self._horizontal)

    def supported_preset_modes(self) -> list[str]:
        return list(self._presets)


def _cool_only_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.pc09sq_nsj.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto", "low", "mid", "high"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "cool": {
                "auto": {"18": "C_AUTO_18"},
                "low": {"18": "C_LOW_18"},
                "mid": {"18": "C_MID_18"},
                "high": {"18": "C_HIGH_18"},
            },
        },
        verified=True,
        notes="Verified cool-only pack. No swing payloads are included yet.",
    )


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry_1",
        data={"model_pack": "lg.pc09sq_nsj.v1", "broadlink_entity": "remote.living"},
        options={},
    )


def test_climate_supported_features_respect_pack_capabilities() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_cool_only_pack(),
        provider=_FakeProvider(),
        engine=_FakeEngine(),
    )

    features = climate.supported_features
    assert features & ClimateEntityFeature.FAN_MODE
    assert not (features & ClimateEntityFeature.SWING_MODE)
    assert not (features & ClimateEntityFeature.SWING_HORIZONTAL_MODE)
    assert climate.swing_modes is None
    assert climate.swing_horizontal_modes is None
    assert climate.hvac_modes == [HVACMode.OFF, HVACMode.COOL]
    assert climate.fan_modes == ["auto", "low", "mid", "high"]


@pytest.mark.asyncio
async def test_climate_rejects_unsupported_fan_mode() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_cool_only_pack(),
        provider=_FakeProvider(),
        engine=_FakeEngine(),
    )

    with pytest.raises(HomeAssistantError, match="not supported"):
        await climate.async_set_fan_mode("turbo")


@pytest.mark.asyncio
async def test_climate_rejects_unsupported_temperature() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_cool_only_pack(),
        provider=_FakeProvider(),
        engine=_FakeEngine(),
    )

    with pytest.raises(HomeAssistantError, match="not available"):
        await climate.async_set_temperature(temperature=26)


@pytest.mark.asyncio
async def test_climate_rejects_unsupported_hvac_mode() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_cool_only_pack(),
        provider=_FakeProvider(),
        engine=_FakeEngine(),
    )

    with pytest.raises(HomeAssistantError, match="not supported"):
        await climate.async_set_hvac_mode(HVACMode.HEAT)


def _full_capability_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.full.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "dry", "fan_only", "cool"],
            fan_modes=["auto", "low", "mid", "high"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "auto": {"auto": {"18": "A"}},
            "heat": {"auto": {"18": "H"}},
            "dry": {"auto": {"18": "D"}},
            "fan_only": {"auto": {"18": "F"}},
            "cool": {"auto": {"18": "C"}},
        },
        verified=True,
        notes="Synthetic full capability pack for unit test",
    )


def test_climate_exposes_all_hvac_modes_from_capabilities() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_full_capability_pack(),
        provider=_FakeProvider(),
        engine=_FakeEngine(),
    )

    assert climate.hvac_modes == [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.COOL,
    ]
    assert climate.fan_modes == ["auto", "low", "mid", "high"]


def _protocol_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.v1",
        brand="LG",
        pack_version=1,
        models=["PC09SQ NSJ"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "cool", "dry", "fan_only"],
            fan_modes=["auto", "f1", "f2", "f3", "f4", "f5"],
            swing_vertical_modes=["off", "swing", "highest", "middle", "lowest"],
            swing_horizontal_modes=["off", "on"],
            presets=["none", "jet"],
            preset_modes=["none", "jet"],
            supports_jet=True,
        ),
        engine_type="lg_protocol",
        commands={"off": "protocol_generated"},
        verified=False,
        notes="Protocol-generated test pack",
    )


def test_protocol_pack_climate_exposes_binary_swing_axes() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_protocol_pack(),
        provider=_FakeProvider(),
        engine=_FakeCapabilityEngine(
            vertical=["off", "swing"],
            horizontal=["off", "on"],
            presets=[],
        ),
    )

    features = climate.supported_features
    assert features & ClimateEntityFeature.SWING_MODE
    assert features & ClimateEntityFeature.SWING_HORIZONTAL_MODE
    assert not (features & ClimateEntityFeature.PRESET_MODE)
    assert climate.swing_modes == ["off", "swing"]
    assert climate.swing_horizontal_modes == ["off", "on"]
    assert climate.min_temp == 16
    assert climate.fan_modes == ["auto", "f1", "f2", "f3", "f4", "f5"]
    assert climate.preset_modes is None


@pytest.mark.asyncio
async def test_protocol_pack_accepts_uppercase_fan_mode_alias_input() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_protocol_pack(),
        provider=_FakeProvider(),
        engine=_FakeCapabilityEngine(
            vertical=["off", "swing"],
            horizontal=["off", "on"],
            presets=[],
        ),
    )

    await climate.async_set_fan_mode("F1")
    assert climate.fan_mode == "f1"


def test_protocol_pack_exposes_advanced_swing_and_jet_only_when_engine_supports() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_protocol_pack(),
        provider=_FakeProvider(),
        engine=_FakeCapabilityEngine(
            vertical=["off", "swing", "highest", "middle", "lowest"],
            horizontal=["off", "on"],
            presets=["none", "jet"],
        ),
    )

    features = climate.supported_features
    assert features & ClimateEntityFeature.SWING_MODE
    assert features & ClimateEntityFeature.SWING_HORIZONTAL_MODE
    assert features & ClimateEntityFeature.PRESET_MODE
    assert climate.swing_modes == ["off", "swing", "highest", "middle", "lowest"]
    assert climate.swing_horizontal_modes == ["off", "on"]
    assert climate.preset_modes == ["none", "jet"]


@pytest.mark.asyncio
async def test_protocol_pack_rejects_temperature_below_supported_range() -> None:
    climate = AeroStateClimate(
        hass=_FakeHass(),
        entry=_entry(),
        pack=_protocol_pack(),
        provider=_FakeProvider(),
        engine=_FakeCapabilityEngine(
            vertical=["off", "swing"],
            horizontal=["off", "on"],
            presets=[],
        ),
    )

    with pytest.raises(HomeAssistantError, match="outside the supported range"):
        await climate.async_set_temperature(temperature=15)
