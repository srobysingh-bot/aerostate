"""Broadlink remote provider for sending IR commands."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    pass

_LOGGER: logging.Logger = logging.getLogger(__name__)


class BroadlinkProvider:
    """Manages communication with a Broadlink remote device."""

    def __init__(self, hass: HomeAssistant, remote_entity_id: str) -> None:
        """Initialize with Home Assistant instance and remote entity ID.

        Args:
            hass: Home Assistant instance
            remote_entity_id: Entity ID of the Broadlink remote (e.g., remote.living_room)
        """
        self._hass = hass
        self._remote_entity_id = remote_entity_id

    async def send_base64(self, payload: str) -> None:
        """Send a base64 IR payload to the Broadlink remote.

        Args:
            payload: Base64-encoded IR command

        Raises:
            HomeAssistantError: If the service call fails
        """
        try:
            payload_hash = hashlib.md5(payload.encode()).hexdigest()[:8]
            _LOGGER.debug(
                "Sending IR command to %s (payload hash: %s)",
                self._remote_entity_id,
                payload_hash,
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

            _LOGGER.debug(
                "Successfully sent IR command to %s",
                self._remote_entity_id,
            )

        except Exception as err:
            _LOGGER.exception(
                "Failed to send IR command to %s",
                self._remote_entity_id,
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
