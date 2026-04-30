"""IRManager deterministic per-device routing (single backend per entry; no hybrid sends)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.const import IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA
from custom_components.aerostate.providers.broadlink import BroadlinkIRProvider, BroadlinkProvider
from custom_components.aerostate.providers.ir_exceptions import IRRoutingMisconfigured
from custom_components.aerostate.providers.ir_manager import IRManager, _normalize_ir_provider_key, create_ir_manager_explicit
from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider


class _LGEngine:
    """Emits base64-like payloads (Broadlink path)."""

    _pack = type("P", (), {"engine_type": "lg_protocol"})()

    def resolve_command(self, state: dict) -> str:
        return "QVBJ" if state.get("power") else "T0ZG"


class _HexTableEngine:
    """Table pack with hex payloads for Tuya."""

    _pack = type("P", (), {"engine_type": "table"})()

    resolve_calls = 0

    def resolve_command(self, state: dict) -> str:
        _HexTableEngine.resolve_calls += 1
        return "aabbccddeeff" if state.get("power") else "ffeeddccbbaa"


class _BroadlinkOutputEngine:
    """Simulates LG/table output as base64 for Broadlink."""

    _pack = type("P", (), {"engine_type": "table"})()

    resolve_calls = 0

    def resolve_command(self, state: dict) -> str:
        _BroadlinkOutputEngine.resolve_calls += 1
        return "BASE64_PAYLOAD" if state.get("power") else "BASE64_OFF"


def _minimal_hass() -> MagicMock:
    hass = MagicMock()
    hass.services.has_service.return_value = True
    hass.services.async_call = MagicMock(return_value=None)
    hass.states.get.return_value = MagicMock(state="on")
    return hass


def test_missing_ir_provider_warns_caplog(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    key = _normalize_ir_provider_key(None, explicit=False, device_id="e1")
    assert key == IR_PROVIDER_BROADLINK
    assert "ir_provider is not set" in caplog.text


def test_effective_ir_mode_misconfigured_when_tuya_incomplete() -> None:
    bp = MagicMock(spec=BroadlinkProvider)
    br = BroadlinkIRProvider(bp)
    mgr = create_ir_manager_explicit(
        lg_engine=_LGEngine(),
        preference_raw="tuya",
        broadlink_impl=bp,
        broadlink_ir=br,
        tuya_engine=None,
        tuya_sender=None,
    )
    assert mgr.effective_ir_mode() == "misconfigured"


@pytest.mark.asyncio
async def test_tuya_incomplete_raises_on_resolve_no_broadlink_fallback() -> None:
    bp = MagicMock(spec=BroadlinkProvider)
    br = BroadlinkIRProvider(bp)
    mgr = create_ir_manager_explicit(
        lg_engine=_LGEngine(),
        preference_raw="tuya",
        broadlink_impl=bp,
        broadlink_ir=br,
        tuya_engine=None,
        tuya_sender=None,
    )
    state = {"power": True}
    with pytest.raises(IRRoutingMisconfigured):
        mgr.resolve_to_ir_commands(state)


@pytest.mark.asyncio
async def test_tuya_sends_normalized_hex_without_broadlink_format() -> None:
    hass = MagicMock()
    hass.services.has_service.return_value = True
    spy = AsyncMock(return_value=None)
    hass.services.async_call = spy
    hass.states.get.return_value = MagicMock(state="on")

    bp_inst = BroadlinkProvider(hass, "remote.rm1")
    br = BroadlinkIRProvider(bp_inst)
    tuya_sender = TuyaIRProvider(hass, "remote.kitchen_tuya_ir", blocking=False)

    _HexTableEngine.resolve_calls = 0
    mgr = IRManager(
        device_id="kitchen_ac",
        lg_engine=_LGEngine(),
        normalized_provider_key=IR_PROVIDER_TUYA,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=_HexTableEngine(),
        tuya_sender=tuya_sender,
    )

    state_on = {"power": True, "hvac_mode": "cool", "target_temperature": 22, "fan_mode": "auto"}
    cmds, _ = mgr.resolve_to_ir_commands(state_on)
    assert _HexTableEngine.resolve_calls >= 1
    assert mgr.active_transport == IR_PROVIDER_TUYA
    assert len(cmds) == 1
    assert cmds[0].format == "tuya"
    await mgr.async_send_commands(cmds)

    spy.assert_awaited_once()
    assert spy.await_args.args[:2] == ("remote", "send_command")
    assert spy.await_args.kwargs.get("blocking") is False
    assert spy.await_args.args[2]["command"] == "aabbccddeeff"
    assert not str(spy.await_args.args[2]["command"]).startswith("b64:")


@pytest.mark.asyncio
async def test_broadlink_resolution_uses_lg_engine_only_never_hex_engine() -> None:
    hass = _minimal_hass()
    bp_inst = BroadlinkProvider(hass, "remote.study_broadlink")
    br = BroadlinkIRProvider(bp_inst)
    tuya_eng = _HexTableEngine()

    mgr = IRManager(
        device_id="study_ac",
        lg_engine=_BroadlinkOutputEngine(),
        normalized_provider_key=IR_PROVIDER_BROADLINK,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=tuya_eng,
        tuya_sender=TuyaIRProvider(hass, "remote.unused_tuya"),
    )

    _HexTableEngine.resolve_calls = 0
    _BroadlinkOutputEngine.resolve_calls = 0

    cmds, _ = mgr.resolve_to_ir_commands(
        {"power": True, "hvac_mode": "cool", "target_temperature": 22, "fan_mode": "auto"},
    )
    assert _BroadlinkOutputEngine.resolve_calls >= 1
    assert _HexTableEngine.resolve_calls == 0
    assert cmds[0].format == "broadlink"
    assert cmds[0].payload == "BASE64_PAYLOAD"

    with patch.object(br, "send_command", new_callable=AsyncMock) as send_b:
        send_b.return_value = None
        await mgr.async_send_commands(cmds)
        send_b.assert_awaited_once()

    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_no_cross_provider_send_both_backends_present() -> None:
    """Broadlink entry must not invoke Tuya service even if Tuya entities exist."""
    hass = _minimal_hass()
    bp_inst = BroadlinkProvider(hass, "remote.rm1")
    br = BroadlinkIRProvider(bp_inst)
    tuya_side = TuyaIRProvider(hass, "remote.tuya")

    mgr = IRManager(
        device_id="dev1",
        lg_engine=_BroadlinkOutputEngine(),
        normalized_provider_key=IR_PROVIDER_BROADLINK,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=_HexTableEngine(),
        tuya_sender=tuya_side,
    )
    cmds, _ = mgr.resolve_to_ir_commands(
        {"power": True, "hvac_mode": "cool", "target_temperature": 22, "fan_mode": "auto"},
    )
    with patch.object(br, "send_command", new_callable=AsyncMock) as send_b:
        send_b.return_value = None
        await mgr.async_send_commands(cmds)
        send_b.assert_awaited_once()
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_same_hvac_target_state_maps_to_backend_specific_payloads_only() -> None:
    """Desired climate fields drive both engines the same IRCommand shape (format differs only)."""
    hass = _minimal_hass()
    bp_inst = BroadlinkProvider(hass, "remote.rm_bl")
    br = BroadlinkIRProvider(bp_inst)
    state = {"power": True, "hvac_mode": "cool", "target_temperature": 22, "fan_mode": "auto"}

    m_bl = IRManager(
        device_id="study_ac",
        lg_engine=_BroadlinkOutputEngine(),
        normalized_provider_key=IR_PROVIDER_BROADLINK,
        invalid_tuya_reason=None,
        broadlink_impl=bp_inst,
        broadlink_ir=br,
        tuya_engine=_HexTableEngine(),
        tuya_sender=TuyaIRProvider(hass, "remote.tuya_x"),
    )
    cmds_bl, _ = m_bl.resolve_to_ir_commands(dict(state))

    bp2 = MagicMock(spec=BroadlinkProvider)
    m_tv = IRManager(
        device_id="kitchen_ac",
        lg_engine=_LGEngine(),
        normalized_provider_key=IR_PROVIDER_TUYA,
        invalid_tuya_reason=None,
        broadlink_impl=bp2,
        broadlink_ir=BroadlinkIRProvider(bp2),
        tuya_engine=_HexTableEngine(),
        tuya_sender=TuyaIRProvider(hass, "remote.tuya_ir"),
    )
    cmds_tv, _ = m_tv.resolve_to_ir_commands(dict(state))

    assert cmds_bl[0].format == "broadlink" and cmds_tv[0].format == "tuya"
    assert cmds_bl[0].payload != cmds_tv[0].payload
