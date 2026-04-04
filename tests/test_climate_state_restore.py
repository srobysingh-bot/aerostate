"""Tests for climate state restoration and power-sensor reconciliation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.aerostate.climate import AeroStateClimate
from custom_components.aerostate.const import CONF_POWER_SENSOR
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


class _FakeStates:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, entity_id: str):
        value = self.values.get(entity_id)
        if value is None:
            return None

        class _State:
            def __init__(self, state: str) -> None:
                self.state = state

        return _State(value)

    def set(self, entity_id: str, value: str) -> None:
        self.values[entity_id] = value


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
    def supported_vertical_swing_modes(self) -> list[str]:
        return ["off", "on"]

    def supported_horizontal_swing_modes(self) -> list[str]:
        return ["off", "on"]

    def supported_preset_modes(self) -> list[str]:
        return ["none", "jet"]

    def resolve_command(self, state: dict) -> str:
        return "AAA"


class _StoredState:
    def __init__(self, state: str, attributes: dict[str, object]) -> None:
        self.state = state
        self.attributes = attributes


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.restore.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool", "heat", "dry"],
            fan_modes=["auto", "low", "high"],
            swing_vertical_modes=["off", "on"],
            swing_horizontal_modes=["off", "on"],
            presets=["none", "jet"],
            preset_modes=["none", "jet"],
            supports_jet=True,
        ),
        engine_type="lg_protocol",
        commands={
            "off": "OFF",
            "cool": {"auto": {"18": "C_AUTO_18", "24": "C_AUTO_24"}},
            "heat": {"auto": {"18": "H_AUTO_18", "24": "H_AUTO_24"}},
            "dry": {"auto": {"18": "D_AUTO_18", "24": "D_AUTO_24"}},
        },
        verified=False,
    )


def _entry(with_power_sensor: bool = False) -> SimpleNamespace:
    data = {
        "model_pack": "lg.protocol.restore.v1",
        "broadlink_entity": "remote.living",
    }
    if with_power_sensor:
        data[CONF_POWER_SENSOR] = "sensor.ac_power"

    return SimpleNamespace(entry_id="entry_1", data=data, options={})


def _build_climate(with_power_sensor: bool = False, hass: _FakeHass | None = None) -> AeroStateClimate:
    climate = AeroStateClimate(
        hass=hass or _FakeHass(),
        entry=_entry(with_power_sensor=with_power_sensor),
        pack=_pack(),
        provider=_FakeProvider(),
        engine=_FakeEngine(),
    )
    return climate


async def _run_restore(climate: AeroStateClimate, stored: _StoredState | None) -> None:
    async def _fake_last_state() -> _StoredState | None:
        return stored

    climate.async_get_last_state = _fake_last_state  # type: ignore[method-assign]
    climate.async_write_ha_state = lambda: None  # type: ignore[assignment]
    await climate.async_added_to_hass()


@pytest.mark.asyncio
async def test_restore_last_hvac_mode_after_restart() -> None:
    climate = _build_climate()

    await _run_restore(
        climate,
        _StoredState(
            state="heat",
            attributes={"last_requested_hvac_mode": "heat"},
        ),
    )

    assert climate.hvac_mode == HVACMode.HEAT


@pytest.mark.asyncio
async def test_restore_supported_target_fan_swing_horizontal_and_preset() -> None:
    climate = _build_climate()

    await _run_restore(
        climate,
        _StoredState(
            state="cool",
            attributes={
                ATTR_TEMPERATURE: 24,
                "fan_mode": "high",
                "swing_mode": "on",
                "swing_horizontal_mode": "on",
                "preset_mode": "jet",
                "last_requested_hvac_mode": "cool",
            },
        ),
    )

    assert climate.hvac_mode == HVACMode.COOL
    assert climate.target_temperature == 24
    assert climate.fan_mode == "high"
    assert climate.swing_mode == "on"
    assert climate.swing_horizontal_mode == "on"
    assert climate.preset_mode == "jet"


@pytest.mark.asyncio
async def test_restore_ignores_unsupported_values_safely() -> None:
    climate = _build_climate()
    default_fan = climate.fan_mode
    default_swing = climate.swing_mode
    default_swing_horizontal = climate.swing_horizontal_mode
    default_preset = climate.preset_mode

    await _run_restore(
        climate,
        _StoredState(
            state="cool",
            attributes={
                ATTR_TEMPERATURE: 29,
                "fan_mode": "turbo",
                "swing_mode": "wide",
                "swing_horizontal_mode": "wide",
                "preset_mode": "sleep",
                "last_requested_hvac_mode": "fan_only",
            },
        ),
    )

    assert climate.hvac_mode == HVACMode.COOL
    assert climate.target_temperature == 18
    assert climate.fan_mode == default_fan
    assert climate.swing_mode == default_swing
    assert climate.swing_horizontal_mode == default_swing_horizontal
    assert climate.preset_mode == default_preset


@pytest.mark.asyncio
async def test_linked_power_sensor_forces_off_after_restore() -> None:
    hass = _FakeHass()
    hass.states.set("sensor.ac_power", "off")
    climate = _build_climate(with_power_sensor=True, hass=hass)

    await _run_restore(
        climate,
        _StoredState(
            state="heat",
            attributes={"last_requested_hvac_mode": "heat"},
        ),
    )

    assert climate.hvac_mode == HVACMode.OFF


@pytest.mark.asyncio
async def test_linked_power_sensor_on_restores_last_requested_running_mode() -> None:
    hass = _FakeHass()
    hass.states.set("sensor.ac_power", "on")
    climate = _build_climate(with_power_sensor=True, hass=hass)

    await _run_restore(
        climate,
        _StoredState(
            state="off",
            attributes={"last_requested_hvac_mode": "heat"},
        ),
    )

    assert climate.hvac_mode == HVACMode.HEAT
