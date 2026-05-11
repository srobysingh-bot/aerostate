"""Tuya IR manager backed by learned localtuya_rc raw codes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .learned_code_resolver import (
    LearnedCodeNotAvailable,
    get_coverage_summary,
    resolve_learned_code,
)
from .localtuya_rc_storage import read_learned_codes

_LOGGER = logging.getLogger(__name__)

POWER_ON_SETTLE_SECONDS = 0.8


class TuyaIRManager:
    """Send IR commands to a Tuya IR blaster using learned raw localtuya_rc codes."""

    def __init__(
        self,
        hass,
        remote_entity_id: str,
        device_name: str,
    ) -> None:
        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._device_name = device_name
        self._learned_codes: dict[str, str] = {}
        self._codes_loaded = False
        self._last_known_power: bool | None = None

    def _ensure_codes_loaded(self) -> None:
        """Load learned codes from storage on first use."""
        if not self._codes_loaded:
            self._learned_codes = read_learned_codes(self._hass, self._device_name)
            self._codes_loaded = True
            _LOGGER.info(
                "TuyaIRManager: loaded %d learned codes for device '%s'",
                len(self._learned_codes),
                self._device_name,
            )

    def reload_codes(self) -> None:
        """Force reload codes from storage."""
        self._codes_loaded = False
        self._ensure_codes_loaded()

    async def async_send_climate_state(self, state: dict[str, Any]) -> None:
        """Resolve climate state to a learned raw IR code and send it."""
        self._ensure_codes_loaded()
        hvac_mode = str(state.get("hvac_mode", "off")).lower()
        wants_power = hvac_mode != "off" and bool(state.get("power", True))
        try:
            raw_command = resolve_learned_code(self._learned_codes, state)
        except LearnedCodeNotAvailable as err:
            _LOGGER.warning("TuyaIRManager: no learned code for state=%s - %s", state, err)
            await self._async_notify_missing_code(state, err)
            raise

        if wants_power and self._last_known_power is not True:
            power_on = self._learned_codes.get("power_on")
            if power_on:
                _LOGGER.info(
                    "TuyaIRManager: waking AC with power_on before state=%s via %s",
                    state,
                    self._remote_entity_id,
                )
                await self._async_send_raw_command(power_on)
                await asyncio.sleep(POWER_ON_SETTLE_SECONDS)
            else:
                _LOGGER.debug(
                    "TuyaIRManager: no power_on raw code available; sending running state directly for state=%s",
                    state,
                )

        _LOGGER.debug("TuyaIRManager: sending state=%s via %s", state, self._remote_entity_id)
        await self._async_send_raw_command(raw_command)
        self._last_known_power = wants_power

    async def _async_send_raw_command(self, raw_command: str) -> None:
        """Send one learned raw command through the configured remote entity.

        Local Tuya IR blasters often do not provide a useful acknowledgement
        after an IR emission. Use a non-blocking service call so AeroState does
        not roll back a valid desired state just because the MCU never echoes
        the IR send.
        """
        await self._hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": self._remote_entity_id,
                "command": raw_command,
            },
            blocking=False,
        )

    async def _async_notify_missing_code(self, state: dict[str, Any], err: LearnedCodeNotAvailable) -> None:
        """Create a visible HA notification for unsupported learned-code gaps."""
        message = (
            f"Cannot send command - {err}\n\n"
            "Learn the missing code using remote.learn_command then reload AeroState."
        )
        try:
            await self._hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "AeroState: IR code not learned",
                    "message": message,
                    "notification_id": "aerostate_tuya_missing_code",
                },
                blocking=False,
            )
        except Exception:
            _LOGGER.exception("Failed to create Tuya IR learned-code notification")

    async def probe_transport(self) -> bool:
        """Check remote entity exists and learned codes are available."""
        state = self._hass.states.get(self._remote_entity_id)
        if state is None:
            _LOGGER.warning("TuyaIRManager: remote entity %s not found", self._remote_entity_id)
            return False
        if state.state in ("unavailable", "unknown"):
            _LOGGER.warning("TuyaIRManager: remote entity %s is %s", self._remote_entity_id, state.state)
            return False

        self._ensure_codes_loaded()
        if not self._learned_codes:
            _LOGGER.warning("TuyaIRManager: no learned codes found for device '%s'", self._device_name)
            return False
        return True

    def describe(self) -> dict[str, Any]:
        """Return debug-safe manager details."""
        self._ensure_codes_loaded()
        return {
            "transport": "tuya_ir_learned_codes",
            "remote_entity": self._remote_entity_id,
            "device_name": self._device_name,
            "coverage": get_coverage_summary(self._learned_codes),
        }


def create_tuya_ir_manager_from_entry(hass, entry) -> TuyaIRManager:
    """Build TuyaIRManager from config entry."""
    from ..const import CONF_TUYA_DEVICE_NAME, CONF_TUYA_IR_ENTITY, DEFAULT_TUYA_DEVICE_NAME

    def _opt(key, default=None):
        return entry.options.get(key, entry.data.get(key, default))

    return TuyaIRManager(
        hass=hass,
        remote_entity_id=_opt(CONF_TUYA_IR_ENTITY),
        device_name=_opt(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
    )


__all__ = ["LearnedCodeNotAvailable", "TuyaIRManager", "create_tuya_ir_manager_from_entry"]
