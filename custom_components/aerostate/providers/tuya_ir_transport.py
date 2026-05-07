"""Standalone Tuya IR DP 201 transport."""

from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

TUYA_IR_DP = 201
DEFAULT_DELAY_MS = 300


class TuyaIRTransport:
    """Send pre-converted Tuya key1 payloads through localtuya.set_dp."""

    def __init__(
        self,
        hass: Any,
        device_id: str,
        local_key: str,
        host: str,
        dp: int = TUYA_IR_DP,
        delay_ms: int = DEFAULT_DELAY_MS,
        no_ack_mode: bool = False,
        send_blocking: bool = True,
    ) -> None:
        self._hass = hass
        self._device_id = device_id
        self._local_key = local_key
        self._host = host
        self._dp = dp
        self._delay_ms = delay_ms
        self._no_ack_mode = no_ack_mode
        self._send_blocking = send_blocking

    def _build_dp201_payload(self, key1_base64: str) -> str:
        """Build the exact JSON string localtuya expects on DP 201."""
        return json.dumps(
            {
                "control": "send_ir",
                "head": "",
                "key1": key1_base64,
                "type": 0,
                "delay": self._delay_ms,
            },
        )

    async def async_send_command(self, key1_base64: str) -> None:
        """Send one pre-computed Tuya key1 payload."""
        payload = self._build_dp201_payload(key1_base64)

        _LOGGER.debug(
            "TuyaIRTransport: sending to device_id=%s dp=%s payload_len=%d",
            self._device_id,
            self._dp,
            len(payload),
        )

        service_data: dict[str, Any] = {
            "device_id": self._device_id,
            "dp": str(self._dp),
            "value": payload,
        }

        try:
            await self._hass.services.async_call(
                "localtuya",
                "set_dp",
                service_data,
                blocking=self._send_blocking,
            )
        except Exception as err:
            _LOGGER.error(
                "TuyaIRTransport: set_dp failed for device_id=%s: %s",
                self._device_id,
                err,
            )
            raise RuntimeError(f"Tuya IR send failed: {err}") from err

    async def probe_transport(self) -> bool:
        """Check whether the required localtuya service exists without sending IR."""
        if not self._hass.services.has_service("localtuya", "set_dp"):
            _LOGGER.warning("TuyaIRTransport: localtuya.set_dp service not found")
            return False
        return True

    def describe(self) -> dict[str, Any]:
        """Return debug-safe transport configuration."""
        return {
            "transport": "tuya_ir",
            "device_id": self._device_id,
            "host": self._host,
            "dp": self._dp,
            "no_ack_mode": self._no_ack_mode,
            "send_blocking": self._send_blocking,
        }

