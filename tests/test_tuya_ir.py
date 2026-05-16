"""Tuya IR helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.packs.tuya import daikin_brc4c158_codes as daikin_brc
from custom_components.aerostate.packs.tuya.daikin_brc4c158_localtuya_v1 import (
    CODES as DAIKIN_BRC4C158_CODES,
)
from custom_components.aerostate.packs.tuya.daikin_brc4c158_localtuya_v1 import (
    PACK_ID as DAIKIN_BRC4C158_PACK_ID,
)
from custom_components.aerostate.packs.tuya.lg_akb75415308_tuya_codes import CODES
from custom_components.aerostate.packs.tuya.registry import get_tuya_pack
from custom_components.aerostate.providers.ir_types import IRCommand
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider


def test_normalize_hex_strips_non_hex_and_requires_even_length() -> None:
    assert TuyaIRProvider.normalize_hex_payload("aa:bb cc dd") == "aabbccdd"
    assert TuyaIRProvider.normalize_hex_payload("aa bb") == "aabb"
    with pytest.raises(ValueError):
        TuyaIRProvider.normalize_hex_payload("aaa")


@pytest.mark.asyncio
async def test_legacy_tuya_provider_sends_remote_command() -> None:
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    spy = AsyncMock()
    hass.services.async_call = spy

    tp = TuyaIRProvider(hass, "remote.x", blocking=False)
    await tp.send_command(IRCommand(name="cmd", payload="ccddee", format="tuya"))

    spy.assert_called_once_with(
        "remote",
        "send_command",
        {"entity_id": "remote.x", "command": "ccddee"},
        blocking=False,
    )


def test_tuya_pack_resolve_cool_24_auto_swing_off() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    assert pack.resolve("cool", 24, "auto", False)


def test_tuya_pack_resolve_off() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    assert pack.resolve("off", None, None, False)


def test_tuya_pack_resolve_unknown_returns_none() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    assert pack.resolve("cool", 99, "auto", False) is None


def test_tuya_pack_has_complete_lg_placeholder_matrix() -> None:
    pack = get_tuya_pack("tuya.lg_pc09sq_nsj.v1")
    labels = {cmd.label for cmd in pack.commands}

    assert len(pack.commands) >= 589
    assert "off" in labels
    assert "cool_16_f1_swing_off" in labels
    assert "cool_30_auto_swing_on" in labels
    assert "heat_16_f1_swing_off" in labels
    assert "heat_30_auto_swing_on" in labels
    assert "dry_16_auto_swing_off" in labels
    assert "dry_30_auto_swing_on" in labels
    assert "fan_f1_swing_off" in labels
    assert "fan_auto_swing_on" in labels
    assert "auto_16_f1_swing_off" in labels
    assert "auto_30_auto_swing_on" in labels
    assert {"turbo_on", "turbo_off", "sleep_on", "sleep_off", "eco_on", "eco_off"} <= labels


def test_akb75415308_tuya_pack_has_stateful_localtuya_rc_codes() -> None:
    pack = get_tuya_pack("lg.akb75415308.localtuya_rc.protocol.v1")
    model_pack = pack.to_model_pack()

    assert pack.native_base64 is False
    assert pack.requires_learned_codes is False
    assert pack.transport == "localtuya_rc"
    assert pack.protocol == "stateful"
    assert len(CODES) == 469
    assert len(pack.commands) == 469
    assert model_pack.transport == "localtuya_rc"
    assert model_pack.capabilities.hvac_modes == ["cool", "heat", "dry", "auto", "fan_only"]
    assert model_pack.capabilities.fan_modes == ["auto", "low", "mid_low", "mid", "mid_high", "high"]
    assert model_pack.capabilities.swing_vertical_modes == [
        "off",
        "on",
        "swing",
        "highest",
        "high",
        "middle",
        "low",
        "lowest",
    ]
    assert model_pack.capabilities.swing_horizontal_modes == [
        "off",
        "on",
        "left_mid",
        "mid",
        "right_mid",
        "right_most",
        "left_swing",
        "right_swing",
        "full_swing",
    ]
    assert pack.resolve_by_label("power_on") == CODES["power_on"]
    assert pack.resolve_by_label("power_off") == CODES["power_off"]
    assert pack.resolve_by_label("swing_vertical_middle") == CODES["swing_vertical_middle"]
    assert pack.resolve_by_label("swing_horizontal_full_swing") == CODES["swing_horizontal_full_swing"]
    assert pack.resolve_by_label("cool_t24_fauto") == CODES["cool_t24_fauto"]
    assert pack.resolve_by_label("cool_t24_flow") == CODES["cool_t24_flow"]
    assert pack.resolve_by_label("heat_t24_fmid_high") == CODES["heat_t24_fmid_high"]
    assert pack.resolve_by_label("dry_t24_fhigh") == CODES["dry_t24_fhigh"]
    assert pack.resolve_by_label("auto_t24_fauto") == CODES["auto_t24_fauto"]
    assert pack.resolve_by_label("fan_only_t25_fmid") == CODES["fan_only_t25_fmid"]


def test_daikin_brc4c158_tuya_pack_has_esphome_brc_localtuya_rc_codes() -> None:
    pack = get_tuya_pack(DAIKIN_BRC4C158_PACK_ID)
    model_pack = pack.to_model_pack()

    assert pack.native_base64 is False
    assert pack.requires_learned_codes is False
    assert pack.transport == "localtuya_rc"
    assert pack.protocol == "stateful"
    assert len(DAIKIN_BRC4C158_CODES) == 46
    assert len(pack.commands) == 46
    assert model_pack.brand == "Daikin"
    assert model_pack.models == ["BRC4C158"]
    assert model_pack.transport == "localtuya_rc"
    assert model_pack.min_temperature == 16
    assert model_pack.max_temperature == 30
    assert model_pack.capabilities.hvac_modes == ["cool"]
    assert model_pack.capabilities.fan_modes == ["auto", "low", "high"]
    assert pack.resolve_by_label("power_off") == DAIKIN_BRC4C158_CODES["power_off"]
    assert pack.resolve_by_label("cool_t16_fauto") == DAIKIN_BRC4C158_CODES["cool_t16_fauto"]
    assert pack.resolve_by_label("cool_t20_flow") == DAIKIN_BRC4C158_CODES["cool_t20_flow"]
    assert pack.resolve_by_label("cool_t30_fhigh") == DAIKIN_BRC4C158_CODES["cool_t30_fhigh"]
    assert pack.resolve_by_label("cool_t24_fmid") is None
    assert pack.resolve_by_label("heat_t24_fhigh") is None
    assert pack.resolve_by_label("fan_only_t25_fmid") is None
    assert pack.resolve_by_label("power_on") is None
    assert DAIKIN_BRC4C158_CODES["cool_t20_flow"].startswith("raw:")
    assert max(int(part) for part in DAIKIN_BRC4C158_CODES["cool_t20_flow"][4:].split(",")) == daikin_brc.MESSAGE_SPACE


def test_daikin_brc4c158_raw_codes_use_brc_timing_and_checksum() -> None:
    timings = [int(part) for part in DAIKIN_BRC4C158_CODES["cool_t16_fauto"][4:].split(",")]

    assert timings[:2] == [daikin_brc.HEADER_MARK, daikin_brc.HEADER_SPACE]
    assert len(timings) == 359
    assert timings[130:134] == [
        daikin_brc.BIT_MARK,
        daikin_brc.MESSAGE_SPACE,
        daikin_brc.HEADER_MARK,
        daikin_brc.HEADER_SPACE,
    ]
    assert timings[-1] == daikin_brc.BIT_MARK

    frame = daikin_brc.build_frame(0x21, 0x23, 16, 0xA0)
    assert frame[:8] == [0x11, 0xDA, 0x17, 0x18, 0x04, 0x00, 0x1E, 0x11]
    assert frame[8:21] == [0xDA, 0x17, 0x18, 0x00, 0x23, 0x00, 0x21, 0x00, 0x00, 32, 0xA0, 0x00, 0x20]
    assert frame[21] == sum(frame[:21]) & 0xFF
