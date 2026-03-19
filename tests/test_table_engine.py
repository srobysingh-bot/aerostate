"""Unit tests for table engine command resolution."""

from __future__ import annotations

import pytest

from custom_components.aerostate.engines.table_engine import TableEngine
from custom_components.aerostate.packs.schema import ModelPack, PackCapabilities


def _pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=20,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto", "low"],
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
            },
        },
    )


def test_table_engine_resolves_off() -> None:
    engine = TableEngine(_pack())
    assert engine.resolve_command({"power": False, "hvac_mode": "off", "target_temperature": 18}) == "OFF"


def test_table_engine_resolves_mode_fan_temp() -> None:
    engine = TableEngine(_pack())
    cmd = engine.resolve_command(
        {"power": True, "hvac_mode": "cool", "fan_mode": "auto", "target_temperature": 18}
    )
    assert cmd == "C_AUTO_18"


def test_table_engine_raises_clear_error_for_missing_temp() -> None:
    engine = TableEngine(_pack())
    with pytest.raises(ValueError, match="Unable to resolve command"):
        engine.resolve_command(
            {"power": True, "hvac_mode": "cool", "fan_mode": "auto", "target_temperature": 20}
        )


def _full_pack() -> ModelPack:
    return ModelPack(
        pack_id="lg.full.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=19,
        capabilities=PackCapabilities(
            hvac_modes=["auto", "heat", "dry", "fan_only", "cool"],
            fan_modes=["auto", "low"],
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "auto": {
                "auto": {"18": "A_AUTO_18", "19": "A_AUTO_19"},
                "low": {"18": "A_LOW_18", "19": "A_LOW_19"},
            },
            "heat": {
                "auto": {"18": "H_AUTO_18", "19": "H_AUTO_19"},
                "low": {"18": "H_LOW_18", "19": "H_LOW_19"},
            },
            "dry": {
                "auto": {"18": "D_AUTO_18", "19": "D_AUTO_19"},
                "low": {"18": "D_LOW_18", "19": "D_LOW_19"},
            },
            "fan_only": {
                "auto": {"18": "F_AUTO_18", "19": "F_AUTO_19"},
                "low": {"18": "F_LOW_18", "19": "F_LOW_19"},
            },
            "cool": {
                "auto": {"18": "C_AUTO_18", "19": "C_AUTO_19"},
                "low": {"18": "C_LOW_18", "19": "C_LOW_19"},
            },
        },
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("auto", "A_AUTO_18"),
        ("heat", "H_AUTO_18"),
        ("dry", "D_AUTO_18"),
        ("fan_only", "F_AUTO_18"),
        ("cool", "C_AUTO_18"),
    ],
)
def test_table_engine_resolves_each_supported_mode(mode: str, expected: str) -> None:
    engine = TableEngine(_full_pack())
    cmd = engine.resolve_command(
        {"power": True, "hvac_mode": mode, "fan_mode": "auto", "target_temperature": 18}
    )
    assert cmd == expected


def test_table_engine_supports_mode_fan_swing_vertical_temp_shape() -> None:
    pack = ModelPack(
        pack_id="lg.swing.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=18,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto"],
            swing_vertical_modes=["on"],
            swing_horizontal_modes=[],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "cool": {
                "auto": {
                    "on": {"18": "C_AUTO_SV_ON_18"},
                }
            },
        },
    )
    engine = TableEngine(pack)
    cmd = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "fan_mode": "auto",
            "swing_vertical": "on",
            "target_temperature": 18,
        }
    )
    assert cmd == "C_AUTO_SV_ON_18"


def test_table_engine_supports_mode_fan_sv_sh_temp_shape() -> None:
    pack = ModelPack(
        pack_id="lg.swing2.test.v1",
        brand="LG",
        pack_version=1,
        models=["TEST"],
        transport="broadlink_base64",
        min_temperature=18,
        max_temperature=18,
        capabilities=PackCapabilities(
            hvac_modes=["cool"],
            fan_modes=["auto"],
            swing_vertical_modes=["on"],
            swing_horizontal_modes=["left"],
            presets=[],
        ),
        engine_type="table",
        commands={
            "off": "OFF",
            "cool": {
                "auto": {
                    "on": {
                        "left": {"18": "C_AUTO_SV_ON_SH_LEFT_18"},
                    },
                }
            },
        },
    )
    engine = TableEngine(pack)
    cmd = engine.resolve_command(
        {
            "power": True,
            "hvac_mode": "cool",
            "fan_mode": "auto",
            "swing_vertical": "on",
            "swing_horizontal": "left",
            "target_temperature": 18,
        }
    )
    assert cmd == "C_AUTO_SV_ON_SH_LEFT_18"


def test_table_engine_raises_clear_error_for_unsupported_mode() -> None:
    engine = TableEngine(_full_pack())
    with pytest.raises(ValueError, match="hvac_mode 'turbo' not found"):
        engine.resolve_command(
            {"power": True, "hvac_mode": "turbo", "fan_mode": "auto", "target_temperature": 18}
        )
