"""Standalone Tuya IR manager using remote.send_command with b64 payloads."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class TuyaIRManager:
    """Send Tuya IR commands via remote.send_command using inline b64 payloads."""

    def __init__(self, hass: Any, remote_entity_id: str, pack: Any) -> None:
        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._pack = pack

    async def async_send_climate_state(self, state: dict[str, Any]) -> None:
        """Resolve and send one climate state."""
        hvac_mode = state.get("hvac_mode", "off")
        temperature = state.get("target_temperature")
        fan_mode = state.get("fan_mode")
        swing_on = bool(state.get("swing_on", state.get("swing_vertical") == "on"))
        preset_mode = state.get("preset_mode")

        if preset_mode and preset_mode not in (None, "none", ""):
            key1 = self._pack.resolve_by_label(f"{preset_mode}_on")
            if key1 and key1 not in ("AA==", "AQ=="):
                await self._send_b64(key1)
                return

        key1 = self._pack.resolve(
            hvac_mode=hvac_mode,
            temperature=int(temperature) if temperature is not None else None,
            fan_mode=fan_mode,
            swing_on=swing_on,
        )

        if not key1 or key1 in ("AA==", "AQ=="):
            raise KeyError(
                f"No valid Tuya IR command for state: {state}. "
                "Pack may have placeholder key1 values - run converter first.",
            )

        await self._send_b64(key1)

    async def _send_b64(self, key1: str) -> None:
        """Send one IR command via remote.send_command with b64: prefix."""
        command = f"b64:{key1}"

        _LOGGER.debug(
            "TuyaIRManager: sending via remote.send_command entity=%s command_len=%d",
            self._remote_entity_id,
            len(command),
        )

        await self._hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": self._remote_entity_id,
                "command": command,
            },
            blocking=True,
        )

    async def probe_transport(self) -> bool:
        """Check that the configured remote entity exists and is available."""
        state = self._hass.states.get(self._remote_entity_id)
        if state is None:
            _LOGGER.warning("TuyaIRManager: remote entity %s not found", self._remote_entity_id)
            return False
        if state.state in ("unavailable", "unknown"):
            _LOGGER.warning(
                "TuyaIRManager: remote entity %s is %s",
                self._remote_entity_id,
                state.state,
            )
            return False
        return True

    def describe(self) -> dict[str, Any]:
        """Return debug-safe manager details."""
        return {
            "transport": "tuya_ir_remote_send_command",
            "remote_entity": self._remote_entity_id,
            "pack_id": self._pack.pack_id,
            "pack_verified": self._pack.verified,
        }


def create_tuya_ir_manager_from_entry(hass: Any, entry: Any) -> TuyaIRManager:
    """Build a TuyaIRManager from entry data/options."""
    from ..const import CONF_TUYA_IR_ENTITY, CONF_TUYA_MODEL_PACK
    from ..packs.tuya.registry import get_tuya_pack

    def _opt(key: str, default: Any = None) -> Any:
        return entry.options.get(key, entry.data.get(key, default))

    remote_entity = _opt(CONF_TUYA_IR_ENTITY)
    pack_id = _opt(CONF_TUYA_MODEL_PACK)
    pack = get_tuya_pack(pack_id)

    return TuyaIRManager(
        hass=hass,
        remote_entity_id=remote_entity,
        pack=pack,
    )
