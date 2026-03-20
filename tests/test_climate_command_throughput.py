"""Tests for climate command coalescing and latest-wins send behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.climate import HVACMode

from custom_components.aerostate.climate import AeroStateClimate
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


class _FakeStates:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, _entity_id: str):
        value = self.values.get(_entity_id)
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


class _TrackingProvider:
    def __init__(self, send_delay: float = 0.0) -> None:
        self.sent_payloads: list[str] = []
        self.send_delay = send_delay

    async def send_base64(self, payload: str) -> None:
        if self.send_delay:
            await asyncio.sleep(self.send_delay)
        self.sent_payloads.append(payload)


class _StateEchoEngine:
    def resolve_command(self, state: dict) -> str:
        return (
            f"m={state.get('hvac_mode')}"
            f"|t={state.get('target_temperature')}"
            f"|f={state.get('fan_mode')}"
            f"|sv={state.get('swing_vertical')}"
            f"|sh={state.get('swing_horizontal')}"
        )


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.protocol.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool", "heat", "dry"],
            fan_modes=["auto", "low", "mid", "high"],
            swing_vertical_modes=["off", "on"],
            swing_horizontal_modes=["off", "on"],
            presets=[],
        ),
        engine_type="lg_protocol",
        commands={"off": "protocol_generated"},
        verified=False,
    )


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry_1",
        data={"model_pack": "lg.protocol.test.v1", "broadlink_entity": "remote.living"},
        options={},
    )


def _entry_with_power_sensor() -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry_1",
        data={
            "model_pack": "lg.protocol.test.v1",
            "broadlink_entity": "remote.living",
            "power_sensor": "sensor.ac_power",
        },
        options={},
    )


def _build_climate(
    send_delay: float = 0.0,
    hass: _FakeHass | None = None,
    entry: SimpleNamespace | None = None,
) -> tuple[AeroStateClimate, _TrackingProvider]:
    provider = _TrackingProvider(send_delay=send_delay)
    if hass is None:
        hass = _FakeHass()
    if entry is None:
        entry = _entry()
    climate = AeroStateClimate(
        hass=hass,
        entry=entry,
        pack=_pack(),
        provider=provider,
        engine=_StateEchoEngine(),
    )
    climate._command_debounce_seconds = 0.01
    return climate, provider


@pytest.mark.asyncio
async def test_rapid_mode_temp_fan_changes_collapse_to_final_state() -> None:
    climate, provider = _build_climate()

    await climate.async_set_hvac_mode(HVACMode.COOL)
    await climate.async_set_temperature(temperature=24)
    await climate.async_set_fan_mode("high")

    await asyncio.sleep(0.06)

    assert len(provider.sent_payloads) == 1
    assert provider.sent_payloads[0] == "m=cool|t=24|f=high|sv=off|sh=off"


@pytest.mark.asyncio
async def test_repeated_temp_slider_changes_only_send_last_temp() -> None:
    climate, provider = _build_climate()

    for temp in [20, 21, 22, 23, 24, 25]:
        await climate.async_set_temperature(temperature=temp)

    await asyncio.sleep(0.06)

    assert len(provider.sent_payloads) == 1
    assert "|t=25|" in provider.sent_payloads[0]


@pytest.mark.asyncio
async def test_swing_spam_final_state_wins() -> None:
    climate, provider = _build_climate()

    await climate.async_set_swing_mode("on")
    await climate.async_set_swing_mode("off")
    await climate.async_set_swing_mode("on")

    await asyncio.sleep(0.06)

    assert len(provider.sent_payloads) == 1
    assert "|sv=on|" in provider.sent_payloads[0]


@pytest.mark.asyncio
async def test_unchanged_state_does_not_duplicate_send() -> None:
    climate, provider = _build_climate()

    await climate.async_set_temperature(temperature=23)
    await asyncio.sleep(0.06)
    await climate.async_set_temperature(temperature=23)
    await asyncio.sleep(0.06)

    assert len(provider.sent_payloads) == 1


@pytest.mark.asyncio
async def test_latest_state_wins_while_send_in_flight() -> None:
    climate, provider = _build_climate(send_delay=0.05)
    climate._command_debounce_seconds = 0.0

    await climate.async_set_temperature(temperature=20)
    await asyncio.sleep(0.01)

    await climate.async_set_temperature(temperature=21)
    await climate.async_set_temperature(temperature=22)
    await climate.async_set_temperature(temperature=23)

    await asyncio.sleep(0.2)

    assert len(provider.sent_payloads) == 2
    assert "|t=20|" in provider.sent_payloads[0]
    assert "|t=23|" in provider.sent_payloads[1]


@pytest.mark.asyncio
async def test_rapid_mixed_updates_with_power_sensor_lag_keep_latest_state_wins() -> None:
    hass = _FakeHass()
    hass.states.set("sensor.ac_power", "off")
    climate, provider = _build_climate(
        hass=hass,
        entry=_entry_with_power_sensor(),
    )

    await climate.async_set_hvac_mode(HVACMode.COOL)
    await climate.async_set_temperature(temperature=24)
    hass.states.set("sensor.ac_power", "unknown")
    await climate.async_set_fan_mode("high")
    await climate.async_set_swing_mode("on")

    await asyncio.sleep(0.06)

    assert len(provider.sent_payloads) == 1
    assert provider.sent_payloads[0] == "m=cool|t=24|f=high|sv=on|sh=off"