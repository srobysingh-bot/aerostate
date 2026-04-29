"""Tuya / Local Tuya compatible IR transport (hex payloads via remote.send_command)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ir_base import IRProvider
from .ir_types import IRCommand

_LOGGER = logging.getLogger(__name__)


class TuyaIRProvider(IRProvider):
    """Send hex IR strings through Home Assistant remote.send_command.

    Uses the plain ``command`` form (no ``b64:`` prefix), suitable for Local Tuya
    virtual remotes that accept raw hex learn payloads.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        remote_entity_id: str,
        *,
        blocking: bool = False,
    ) -> None:
        """Initialize.

        Args:
            hass: Home Assistant core.
            remote_entity_id: Remote entity exposed by Local Tuya (or compatible).
            blocking: Passed to ``async_call`` (default ``False`` for HA worker safety).
        """
        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._blocking = blocking
        self._send_lock = asyncio.Lock()

    @staticmethod
    def normalize_hex_payload(payload: str) -> str:
        """Normalize user or pack-supplied hex to a continuous hex digit string."""
        hex_only = "".join(ch for ch in payload if ch in "0123456789abcdefABCDEF")
        if not hex_only or len(hex_only) % 2 != 0:
            raise ValueError(
                f"Tuya IR payload must be an even-length hexadecimal string, got: {payload!r}"
            )
        return hex_only

    async def send_command(self, command: IRCommand) -> None:
        """Send a single hex IR payload."""
        if command.format != "tuya":
            raise ValueError(
                f"TuyaIRProvider only accepts IRCommand(format='tuya'), got {command.format!r}"
            )

        normalized = self.normalize_hex_payload(command.payload)
        payload_hash = hashlib.sha256(normalized.encode("ascii")).hexdigest()[:12]
        enqueue_ts = time.monotonic()

        async with self._send_lock:
            send_start = time.monotonic()
            queued_ms = (send_start - enqueue_ts) * 1000
            _LOGGER.debug(
                "Tuya IR send start entity=%s name=%s payload_sha12=%s queued_ms=%.1f",
                self._remote_entity_id,
                command.name,
                payload_hash,
                queued_ms,
            )

            try:
                await self._hass.services.async_call(
                    "remote",
                    "send_command",
                    {
                        "entity_id": self._remote_entity_id,
                        "command": normalized,
                    },
                    blocking=self._blocking,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Tuya IR send failed entity=%s name=%s: %s",
                    self._remote_entity_id,
                    command.name,
                    err,
                )
                raise HomeAssistantError(
                    f"Failed to send Tuya IR command via {self._remote_entity_id}: {err}"
                ) from err

            send_finish = time.monotonic()
            send_ms = (send_finish - send_start) * 1000
            total_ms = (send_finish - enqueue_ts) * 1000

            _LOGGER.debug(
                "Tuya IR send finish entity=%s name=%s payload_sha12=%s send_ms=%.1f total_ms=%.1f",
                self._remote_entity_id,
                command.name,
                payload_hash,
                send_ms,
                total_ms,
            )

    async def test_connection(self, hex_payload: str | None = None) -> bool:
        """Probe remote availability; optionally sends one hex payload end-to-end."""
        try:
            if not self._hass.services.has_service("remote", "send_command"):
                _LOGGER.warning("Service remote.send_command is not available")
                return False

            entity_state = self._hass.states.get(self._remote_entity_id)
            if entity_state is None:
                _LOGGER.warning("Tuya IR remote entity not found: %s", self._remote_entity_id)
                return False

            is_available = entity_state.state not in ("unavailable", "unknown")
            if not is_available:
                _LOGGER.warning("Tuya IR remote entity %s is unavailable", self._remote_entity_id)
                return False

            if hex_payload:
                try:
                    normalized = self.normalize_hex_payload(hex_payload)
                except ValueError as err:
                    _LOGGER.warning("Invalid Tuya hex test payload: %s", err)
                    return False

                try:
                    await self.send_command(
                        IRCommand(name="transport_test", payload=normalized, format="tuya"),
                    )
                except HomeAssistantError as err:
                    _LOGGER.warning("Tuya IR end-to-end transport test failed: %s", err)
                    return False

            return True

        except Exception:
            _LOGGER.exception("Error testing Tuya IR connection to %s", self._remote_entity_id)
            return False
