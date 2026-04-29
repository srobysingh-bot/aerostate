"""IRConverter / IRConversionLayer best-effort Broadlink→Tuya tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.const import IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA
from custom_components.aerostate.engines.lg_engine import LGProtocolEngine
from custom_components.aerostate.providers.broadlink import BroadlinkIRProvider, BroadlinkProvider
from custom_components.aerostate.providers.ir_conversion import ConversionResult, IRConversionLayer, IRConverter
from custom_components.aerostate.providers.ir_manager import IRManager
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider
from tests.test_lg_protocol_engine import _pack


def test_lg_broadlink_converts_to_non_empty_hex() -> None:
    eng = LGProtocolEngine(_pack())
    payload = eng.resolve_command({"power": False, "hvac_mode": "off", "target_temperature": 24})
    res = IRConverter().convert(payload)
    assert res.hex_payload is not None
    assert len(res.hex_payload) >= 8 and len(res.hex_payload) % 2 == 0
    assert res.confidence >= 0.8
    assert res.failure_reason is None


def test_invalid_packet_handling_returns_failure_reason() -> None:
    res = IRConverter().convert("%%%%")
    assert res.hex_payload is None
    assert res.failure_reason is not None


@pytest.mark.asyncio
async def test_tuya_conversion_then_send_uses_remote_service() -> None:
    hass = MagicMock()
    hass.services.has_service.return_value = True
    hass.services.async_call = AsyncMock(return_value=None)
    hass.states.get.return_value = MagicMock(state="on")

    bp_inst = BroadlinkProvider(hass, "remote.rm_bl")
    br = BroadlinkIRProvider(bp_inst)
    tuya = TuyaIRProvider(hass, "remote.tuya_ir")
    lg = LGProtocolEngine(_pack())
    mgr = IRManager(
        device_id="kitchen",
        lg_engine=lg,
        normalized_provider_key=IR_PROVIDER_TUYA,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=None,
        tuya_sender=tuya,
        ir_conversion_enabled=True,
        ir_conversion_layer=IRConversionLayer(IRConverter()),
    )
    cmds, _ = mgr.resolve_to_ir_commands({"power": False, "hvac_mode": "off", "target_temperature": 24})
    assert cmds[0].format == "tuya"
    await mgr.async_send_commands(cmds)
    hass.services.async_call.assert_called()


@pytest.mark.asyncio
async def test_conversion_failure_falls_back_to_manual_tuya_engine() -> None:
    hass = MagicMock()
    hass.services.has_service.return_value = True
    hass.services.async_call = AsyncMock(return_value=None)

    bp_inst = BroadlinkProvider(hass, "remote.rm")
    br = BroadlinkIRProvider(bp_inst)

    class _BadConv(IRConverter):
        def convert(self, broadlink_packet, *, target="tuya"):
            return ConversionResult(hex_payload=None, confidence=0.0, failure_reason="test_forced_failure")

    class _ManualTable:
        _pack = type("P", (), {"engine_type": "table"})()

        def resolve_command(self, _state):
            return "aabbccddeeff"

    lg = LGProtocolEngine(_pack())
    mgr = IRManager(
        device_id="k2",
        lg_engine=lg,
        normalized_provider_key=IR_PROVIDER_TUYA,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=_ManualTable(),
        tuya_sender=TuyaIRProvider(hass, "remote.tuya_ent"),
        ir_conversion_enabled=True,
        ir_conversion_layer=IRConversionLayer(_BadConv()),
    )
    cmds, _ = mgr.resolve_to_ir_commands({"power": True})
    assert cmds[0].format == "tuya"
    assert cmds[0].payload == "aabbccddeeff"


def test_broadlink_path_unaffected_when_flag_on_provider_broadlink() -> None:
    hass = MagicMock()
    hass.services.has_service.return_value = True
    bp_inst = BroadlinkProvider(hass, "remote.study")
    br = BroadlinkIRProvider(bp_inst)
    lg = LGProtocolEngine(_pack())

    mgr = IRManager(
        device_id="study",
        lg_engine=lg,
        normalized_provider_key=IR_PROVIDER_BROADLINK,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=None,
        tuya_sender=None,
        ir_conversion_enabled=True,
        ir_conversion_layer=IRConversionLayer(IRConverter()),
    )
    cmds, _ = mgr.resolve_to_ir_commands({"power": False})
    assert cmds[0].format == "broadlink"


def test_feature_flag_disabled_uses_manual_tuya_pack_only() -> None:
    hass = MagicMock()
    bp_inst = BroadlinkProvider(hass, "remote.r")
    br = BroadlinkIRProvider(bp_inst)
    lg = LGProtocolEngine(_pack())

    class _ManualPack:
        _pack = type("P", (), {"engine_type": "table"})()

        def resolve_command(self, _state):
            return "cafebeef"

    mgr = IRManager(
        device_id="t3",
        lg_engine=lg,
        normalized_provider_key=IR_PROVIDER_TUYA,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=_ManualPack(),
        tuya_sender=TuyaIRProvider(hass, "remote.t"),
        ir_conversion_enabled=False,
        ir_conversion_layer=None,
    )
    cmds, _ = mgr.resolve_to_ir_commands({"power": True})
    assert cmds[0].payload == "cafebeef"


def test_conversion_disabled_does_not_store_layer_stub() -> None:
    mgr = IRManager(
        device_id="t4",
        lg_engine=LGProtocolEngine(_pack()),
        normalized_provider_key=IR_PROVIDER_TUYA,
        invalid_tuya_reason=None,
        broadlink_impl=BroadlinkProvider(MagicMock(), "remote.r"),
        broadlink_ir=BroadlinkIRProvider(BroadlinkProvider(MagicMock(), "remote.r")),
        tuya_engine=type("_M", (), {"_pack": type("P", (), {"engine_type": "table"})(), "resolve_command": lambda _s, _x: "feedface"})(),
        tuya_sender=TuyaIRProvider(MagicMock(), "remote.t"),
        ir_conversion_enabled=False,
        ir_conversion_layer=IRConversionLayer(IRConverter()),
    )
    cmds, _ = mgr.resolve_to_ir_commands({"power": True})
    assert cmds[0].payload == "feedface"
    assert mgr._conversion_layer is None