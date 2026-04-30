"""Tuya / Local Tuya compatible IR transport.

Primary path: Home Assistant ``remote.send_command`` with a plain hex ``command`` payload.

Optional path: ``localtuya.set_dp`` when :data:`tuya_local_device_id` is set (recommended when
the ``remote`` entity reports *control_type must be set manually*). See
https://xzetsubou.github.io/hass-localtuya/ha_services/

Local Tuya device YAML should use ``control_type: ir`` and map IR send DP (often 201) as
documented for your fork/device.
"""

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

SERVICE_LOCALTUYA = "localtuya"
SERVICE_SET_DP = "set_dp"


class TuyaIRProvider(IRProvider):
    """Deliver hex LG timing payloads to Local Tuya IR (DP ``ir_send``) or HA ``remote``.

    AeroState never emits Broadlink ``b64:`` payloads here; payloads are validated hex digits only.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        remote_entity_id: str,
        *,
        blocking: bool = True,
        entry_id: str | None = None,
        localtuya_device_id: str | None = None,
        ir_dp: int = 201,
    ) -> None:
        """Initialize.

        Args:
            hass: Home Assistant core.
            remote_entity_id: ``remote.*`` exposed by Local Tuya (fallback / probe entity).
            blocking: Passed to ``async_call`` — default ``True`` can improve DP sequencing.
            entry_id: AeroState config_entry id for structured logs only.
            localtuya_device_id: If set, prefer ``localtuya.set_dp`` with ``ir_dp``.
            ir_dp: ``ir_send`` datapoint ID (often 201 on MCU IR peripherals).
        """
        self._hass = hass
        self._remote_entity_id = remote_entity_id.strip()
        self._blocking = blocking
        self._entry_id = entry_id
        self._localtuya_device_id = (
            localtuya_device_id.strip() if isinstance(localtuya_device_id, str) and localtuya_device_id.strip() else None
        )
        self._ir_dp = ir_dp if ir_dp >= 1 else 201
        self._send_lock = asyncio.Lock()

    @property
    def uses_localtuya_dp(self) -> bool:
        return bool(self._localtuya_device_id)

    @property
    def configured_ir_dp(self) -> int:
        return self._ir_dp

    @staticmethod
    def normalize_hex_payload(payload: str) -> str:
        """Normalize user or pack-supplied hex to a continuous hex digit string."""
        hex_only = "".join(ch for ch in payload if ch in "0123456789abcdefABCDEF")
        if not hex_only or len(hex_only) % 2 != 0:
            raise ValueError(
                f"Tuya IR payload must be an even-length hexadecimal string, got: {payload!r}"
            )
        return hex_only

    def _ir_route_kw(self, *, send_path: str, payload_hash: str) -> dict[str, object]:
        return {
            "entry_id": self._entry_id or "",
            "device_hint": self._remote_entity_id,
            "provider": "tuya",
            "send_path": send_path,
            "payload_type": "ir_send_hex",
            "dp_id": self._ir_dp if send_path == "localtuya_set_dp" else None,
            "payload_sha12": payload_hash,
            "blocking": self._blocking,
        }

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
            use_dp = (
                bool(self._localtuya_device_id)
                and self._hass.services.has_service(SERVICE_LOCALTUYA, SERVICE_SET_DP)
            )

            send_path = "localtuya_set_dp" if use_dp else "ha_remote_send_command"

            _LOGGER.debug(
                "ir_route_enqueue %s queued_ms=%.1f",
                self._ir_route_kw(send_path=send_path, payload_hash=payload_hash),
                queued_ms,
            )

            try:
                if use_dp:
                    await self._hass.services.async_call(
                        SERVICE_LOCALTUYA,
                        SERVICE_SET_DP,
                        {
                            "device_id": self._localtuya_device_id,
                            "dp": self._ir_dp,
                            "value": normalized,
                        },
                        blocking=self._blocking,
                    )
                else:
                    if self._localtuya_device_id and not use_dp:
                        _LOGGER.warning(
                            "Configured %s=%s but %s.%s unavailable; using remote.send_command on %s. "
                            "Set Local Tuya YAML control_type ir or install Hass LocalTuya with set_dp.",
                            "tuya_local_device_id",
                            self._localtuya_device_id,
                            SERVICE_LOCALTUYA,
                            SERVICE_SET_DP,
                            self._remote_entity_id,
                        )
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
                    "IR ROUTE FAILURE %s detail=%s",
                    self._ir_route_kw(send_path=send_path, payload_hash=payload_hash),
                    err,
                )
                raise HomeAssistantError(
                    f"Failed Tuya IR send ({send_path}) for {self._remote_entity_id}: {err}"
                ) from err

            send_finish = time.monotonic()
            send_ms = (send_finish - send_start) * 1000
            total_ms = (send_finish - enqueue_ts) * 1000

            _LOGGER.info(
                "IR ROUTE %s command=%s send_ms=%.1f total_ms=%.1f",
                self._ir_route_kw(send_path=send_path, payload_hash=payload_hash),
                command.name,
                send_ms,
                total_ms,
            )

    async def test_connection(self, hex_payload: str | None = None) -> bool:
        """Probe IR path availability; optionally sends one payload end-to-end."""
        try:
            if (
                bool(self._localtuya_device_id)
                and self._hass.services.has_service(SERVICE_LOCALTUYA, SERVICE_SET_DP)
            ):
                # Device presence validated on first failure; HA has no canonical device lookup.
                if hex_payload:
                    await self.send_command(
                        IRCommand(name="transport_test", payload=TuyaIRProvider.normalize_hex_payload(hex_payload), format="tuya"),
                    )
                return True

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
                    norm = self.normalize_hex_payload(hex_payload)
                except ValueError as err:
                    _LOGGER.warning("Invalid Tuya hex test payload: %s", err)
                    return False

                try:
                    await self.send_command(
                        IRCommand(name="transport_test", payload=norm, format="tuya"),
                    )
                except HomeAssistantError as err:
                    _LOGGER.warning("Tuya IR end-to-end transport test failed: %s", err)
                    return False

            return True

        except Exception:
            _LOGGER.exception("Error testing Tuya IR connection to %s", self._remote_entity_id)
            return False
