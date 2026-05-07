"""Standalone Tuya IR state resolver and sender."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..packs.tuya.registry import get_tuya_pack
from ..packs.tuya.schema import TuyaIRPack
from .tuya_ir_transport import TuyaIRTransport

_LOGGER = logging.getLogger(__name__)


class TuyaIRManager:
    """Resolve climate state to Tuya key1 and send it via DP 201."""

    def __init__(
        self,
        hass: Any,
        pack: TuyaIRPack,
        transport: TuyaIRTransport,
    ) -> None:
        self._hass = hass
        self._pack = pack
        self._transport = transport

    def resolve_key1(self, state: dict[str, Any]) -> str:
        """Resolve a climate state dictionary to a Tuya key1 payload."""
        hvac_mode = state.get("hvac_mode", "off")
        temperature = state.get("target_temperature")
        fan_mode = state.get("fan_mode")
        swing_on = bool(state.get("swing_on", state.get("swing_vertical") == "on"))

        key1 = self._pack.resolve(
            hvac_mode=hvac_mode,
            temperature=int(temperature) if temperature is not None and hvac_mode != "off" else None,
            fan_mode=fan_mode if hvac_mode != "off" else None,
            swing_on=swing_on if hvac_mode != "off" else False,
        )

        if key1 is None:
            _LOGGER.error(
                "TuyaIRManager: no command found for state=%s pack=%s",
                state,
                self._pack.pack_id,
            )
            raise KeyError(f"No Tuya IR command for state: {state}")
        return key1

    def payload_hash_for_state(self, state: dict[str, Any]) -> str:
        """Return a stable hash of the resolved key1 payload."""
        return hashlib.sha256(self.resolve_key1(state).encode("utf-8")).hexdigest()[:12]

    async def async_send_climate_state(self, state: dict[str, Any]) -> None:
        """Resolve and send one climate state."""
        key1 = self.resolve_key1(state)
        _LOGGER.debug("TuyaIRManager: resolved state=%s to key1_len=%d", state, len(key1))
        await self._transport.async_send_command(key1)

    async def probe_transport(self) -> bool:
        """Probe the standalone Tuya transport."""
        return await self._transport.probe_transport()

    def describe(self) -> dict[str, Any]:
        """Return debug-safe manager details."""
        return {
            "tuya_ir_manager": True,
            "pack_id": self._pack.pack_id,
            "pack_verified": self._pack.verified,
            "transport": self._transport.describe(),
        }


def create_tuya_ir_manager_from_entry(hass: Any, entry: Any) -> TuyaIRManager:
    """Build a TuyaIRManager from Tuya-specific entry data/options."""
    from ..const import (
        CONF_TUYA_HOST,
        CONF_TUYA_IR_DP,
        CONF_TUYA_IR_NO_ACK_MODE,
        CONF_TUYA_IR_SEND_BLOCKING,
        CONF_TUYA_LOCAL_DEVICE_ID,
        CONF_TUYA_LOCAL_KEY,
        CONF_TUYA_MODEL_PACK,
        DEFAULT_TUYA_IR_DP,
    )

    def _opt(key: str, default: Any = None) -> Any:
        return entry.options.get(key, entry.data.get(key, default))

    pack_id = _opt(CONF_TUYA_MODEL_PACK)
    pack = get_tuya_pack(pack_id)

    transport = TuyaIRTransport(
        hass=hass,
        device_id=_opt(CONF_TUYA_LOCAL_DEVICE_ID, ""),
        local_key=_opt(CONF_TUYA_LOCAL_KEY, ""),
        host=_opt(CONF_TUYA_HOST, ""),
        dp=int(_opt(CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP)),
        no_ack_mode=bool(_opt(CONF_TUYA_IR_NO_ACK_MODE, False)),
        send_blocking=bool(_opt(CONF_TUYA_IR_SEND_BLOCKING, True)),
    )

    return TuyaIRManager(hass=hass, pack=pack, transport=transport)

