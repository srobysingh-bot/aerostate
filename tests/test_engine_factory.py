"""Unit tests for engine factory routing."""

from __future__ import annotations

import pytest

from custom_components.aerostate.engines.factory import create_engine
from custom_components.aerostate.engines.lg_engine import LGProtocolEngine
from custom_components.aerostate.engines.table_engine import TableEngine
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack(engine_type: str) -> ModelPack:
    return ModelPack(
        pack_id=f"test.{engine_type}.v1",
        brand="TEST",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=24,
        max_temperature=24,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=[],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type=engine_type,
        commands={"off": "AAA"},
    )


def test_factory_routes_table_engine_unchanged() -> None:
    engine = create_engine(_pack("table"))
    assert isinstance(engine, TableEngine)


def test_factory_routes_lg_engine_unchanged() -> None:
    engine = create_engine(_pack("lg_protocol"))
    assert isinstance(engine, LGProtocolEngine)


def test_factory_rejects_unsupported_engine_type() -> None:
    with pytest.raises(ValueError, match="Unsupported engine type"):
        create_engine(_pack("unsupported_engine"))
