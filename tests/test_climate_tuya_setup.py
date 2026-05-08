"""Climate setup routing tests for standalone Tuya entries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate import climate
from custom_components.aerostate.const import (
    CONF_BRAND,
    CONF_BROADLINK_ENTITY,
    CONF_IR_PROVIDER,
    CONF_MODEL_PACK,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    DOMAIN,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
)
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto"],
            swing_vertical_modes=["off", "on"],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={"off": "OFF", "cool": {"auto": {"off": {"24": "COOL24"}}}},
        verified=True,
        notes="test",
    )


def _daikin_pack() -> ModelPack:
    return ModelPack(
        pack_id="daikin.test.v1",
        brand="Daikin",
        pack_version=1,
        models=["DAIKIN"],
        transport="broadlink_base64",
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto"],
            swing_vertical_modes=["off", "on"],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={"off": "OFF", "cool": {"auto": {"off": {"24": "COOL24"}}}},
        verified=True,
        notes="test",
    )


class _Registry:
    def __init__(self) -> None:
        self.pack = _pack()
        self.daikin_pack = _daikin_pack()

    def get(self, pack_id: str) -> ModelPack:
        if pack_id == self.daikin_pack.pack_id:
            return self.daikin_pack
        return self.pack

    def list_brand_packs(self, brand: str) -> list[ModelPack]:
        return [pack for pack in [self.daikin_pack, self.pack] if pack.brand.lower() == brand.lower()]

    def list_all(self) -> list[ModelPack]:
        return [self.daikin_pack, self.pack]


class _IRManager:
    @staticmethod
    async def probe_active_transport() -> bool:
        return True

    @staticmethod
    def effective_ir_mode() -> str:
        return "broadlink"

    @property
    def tuya_assumes_no_ack(self) -> bool:
        return False

    @property
    def preference_configured(self) -> str:
        return "broadlink"


class _TuyaManager:
    @staticmethod
    async def probe_transport() -> bool:
        return True


def _hass(entry) -> SimpleNamespace:
    return SimpleNamespace(
        data={DOMAIN: {entry.entry_id: {"registry": _Registry()}}},
        config=SimpleNamespace(units=SimpleNamespace(temperature_unit="C")),
        states=SimpleNamespace(get=lambda _entity_id: None),
    )


@pytest.mark.asyncio
async def test_climate_setup_entry_tuya_path_no_broadlink_required(monkeypatch) -> None:
    entry = SimpleNamespace(
        entry_id="entry_tuya",
        data={
            CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
            CONF_TUYA_IR_ENTITY: "remote.test_ir",
            CONF_TUYA_MODEL_PACK: "tuya.lg_pc09sq_nsj.v1",
        },
        options={},
    )
    added: list[object] = []

    monkeypatch.setattr(climate, "create_ir_manager_from_entry", lambda *_args, **_kwargs: _IRManager())
    monkeypatch.setattr(
        "custom_components.aerostate.providers.tuya_ir_manager.create_tuya_ir_manager_from_entry",
        lambda *_args, **_kwargs: _TuyaManager(),
    )

    ok = await climate.async_setup_entry(_hass(entry), entry, lambda entities: added.extend(entities))

    assert ok is True
    assert len(added) == 1
    assert added[0]._pack.brand == "LG"


@pytest.mark.asyncio
async def test_climate_setup_entry_broadlink_path_unchanged(monkeypatch) -> None:
    entry = SimpleNamespace(
        entry_id="entry_broadlink",
        data={
            CONF_IR_PROVIDER: IR_PROVIDER_BROADLINK,
            CONF_BROADLINK_ENTITY: "remote.test",
            CONF_BRAND: "LG",
            CONF_MODEL_PACK: "lg.test.v1",
        },
        options={},
    )
    added: list[object] = []

    monkeypatch.setattr(climate, "create_ir_manager_from_entry", lambda *_args, **_kwargs: _IRManager())

    ok = await climate.async_setup_entry(_hass(entry), entry, lambda entities: added.extend(entities))

    assert ok is True
    assert len(added) == 1
