"""Broadlink remote provider for sending IR commands."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ir_base import IRProvider
from .ir_types import IRCommand

_LOGGER: logging.Logger = logging.getLogger(__name__)


class BroadlinkProvider:

    def __init__(self, hass: HomeAssistant, remote_entity_id: str) -> None:
        """Initialize with Home Assistant instance and remote entity ID.

        Args:
            hass: Home Assistant instance
            remote_entity_id: Entity ID of the Broadlink remote (e.g., remote.living_room)
        """
        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._send_lock = asyncio.Lock()

    async def send_base64(self, payload: str) -> None:
        """Send a base64 IR payload to the Broadlink remote.

        Args:
            payload: Base64-encoded IR command

        Raises:
            HomeAssistantError: If the service call fails
        """
        payload_hash = hashlib.md5(payload.encode()).hexdigest()[:8]
        enqueue_ts = time.monotonic()

        try:
            async with self._send_lock:
                send_start = time.monotonic()
                queued_ms = (send_start - enqueue_ts) * 1000

                _LOGGER.debug(
                    "Broadlink send start entity=%s payload_hash=%s queued_ms=%.1f",
                    self._remote_entity_id,
                    payload_hash,
                    queued_ms,
                )

                # Broadlink remote.send_command accepts a b64-prefixed command payload.
                await self._hass.services.async_call(
                    "remote",
                    "send_command",
                    {
                        "entity_id": self._remote_entity_id,
                        "command": f"b64:{payload}",
                    },
                    blocking=True,
                )

                send_finish = time.monotonic()
                send_ms = (send_finish - send_start) * 1000
                total_ms = (send_finish - enqueue_ts) * 1000

                _LOGGER.debug(
                    "Broadlink send finish entity=%s payload_hash=%s send_ms=%.1f total_ms=%.1f",
                    self._remote_entity_id,
                    payload_hash,
                    send_ms,
                    total_ms,
                )

        except Exception as err:
            _LOGGER.exception(
                "Failed to send IR command entity=%s payload_hash=%s",
                self._remote_entity_id,
                payload_hash,
            )
            raise HomeAssistantError(
                f"Failed to send IR command via {self._remote_entity_id}: {err}"
            ) from err

    async def test_connection(self, payload: str | None = None) -> bool:
        """Test if the Broadlink remote is available.

        If a payload is provided, performs an end-to-end command send test.

        Returns:
            True if remote entity exists and is available, False otherwise
        """
        try:
            if not self._hass.services.has_service("remote", "send_command"):
                _LOGGER.warning("Service remote.send_command is not available")
                return False

            entity_state = self._hass.states.get(self._remote_entity_id)

            if entity_state is None:
                _LOGGER.warning(
                    "Remote entity not found: %s",
                    self._remote_entity_id,
                )
                return False

            # Check if entity is available
            is_available = entity_state.state not in ("unavailable", "unknown")

            if is_available:
                _LOGGER.debug(
                    "Remote entity %s is available",
                    self._remote_entity_id,
                )
            else:
                _LOGGER.warning(
                    "Remote entity %s is unavailable",
                    self._remote_entity_id,
                )

            if not is_available:
                return False

            if payload:
                try:
                    await self.send_base64(payload)
                except HomeAssistantError as err:
                    _LOGGER.warning("End-to-end transport test failed: %s", err)
                    return False

            return True

        except Exception:
            _LOGGER.exception(
                "Error testing connection to %s",
                self._remote_entity_id,
            )
            return False

    async def send_sequence(self, payloads: list[tuple[str, str]]) -> dict[str, object]:
        """Send a labeled sequence of payloads and return summary.

        Args:
            payloads: List of (label, base64 payload) pairs.

        Returns:
            Dictionary with attempted labels and errors.
        """
        attempted: list[str] = []
        errors: list[str] = []
        for label, payload in payloads:
            attempted.append(label)
            try:
                await self.send_base64(payload)
            except HomeAssistantError as err:
                errors.append(f"{label}: {err}")
                break
        return {"attempted": attempted, "errors": errors, "success": len(errors) == 0}


class BroadlinkIRProvider(IRProvider):
    """Wraps :class:`BroadlinkProvider` with normalized :class:`IRCommand` input."""

    def __init__(self, delegate: BroadlinkProvider) -> None:
        self._delegate = delegate

    async def send_command(self, command: IRCommand) -> None:
        """Send a single Broadlink base64 payload."""
        if command.format != "broadlink":
            raise ValueError(
                f"BroadlinkIRProvider only accepts IRCommand(format='broadlink'), got {command.format!r}"
            )
        await self._delegate.send_base64(command.payload)

    async def send_sequence(self, commands: list[IRCommand]) -> dict[str, object]:
        """Send a sequence of Broadlink commands with existing lock/ordering semantics."""
        for command in commands:
            if command.format != "broadlink":
                raise ValueError(
                    f"BroadlinkIRProvider only accepts IRCommand(format='broadlink'), got {command.format!r}"
                )
        return await self._delegate.send_sequence([(c.name, c.payload) for c in commands])
