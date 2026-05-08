"""Standalone Tuya IR manager with persistent learned-code overlay."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any

from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

LEARNED_CODES_STORAGE_KEY = "aerostate_learned_codes"
LEARNED_CODES_STORAGE_VERSION = 1
LOCALTUYA_RC_CODES_STORAGE_KEY = "localtuya_rc_codes"
LOCALTUYA_RC_CODES_STORAGE_VERSION = 1


class LearnedCodeStore:
    """Persist learned raw IR payloads by entry and command label."""

    def __init__(self, hass: Any) -> None:
        self._store = Store(hass, LEARNED_CODES_STORAGE_VERSION, LEARNED_CODES_STORAGE_KEY)
        self._data: dict[str, str] = {}
        self._loaded = False

    @staticmethod
    def _key(entry_id: str, label: str) -> str:
        return f"{entry_id}:{label}"

    async def async_load(self) -> None:
        """Load learned commands from Home Assistant storage."""
        if self._loaded:
            return
        data = await self._store.async_load()
        if isinstance(data, dict):
            self._data = {
                str(key): str(value)
                for key, value in data.items()
                if isinstance(value, str)
            }
        self._loaded = True

    async def async_save(self, entry_id: str, label: str, raw_payload: str) -> None:
        """Save one learned command."""
        await self.async_load()
        self._data[self._key(entry_id, label)] = raw_payload
        await self._store.async_save(self._data)

    def get(self, entry_id: str, label: str) -> str | None:
        """Return a stored learned payload, if present."""
        return self._data.get(self._key(entry_id, label))

    async def async_delete(self, entry_id: str, label: str) -> None:
        """Remove one learned command."""
        await self.async_load()
        self._data.pop(self._key(entry_id, label), None)
        await self._store.async_save(self._data)

    def list_labels(self, entry_id: str) -> list[str]:
        """List learned labels for one config entry."""
        prefix = f"{entry_id}:"
        return sorted(key[len(prefix) :] for key in self._data if key.startswith(prefix))


class LocalTuyaRCLearnedCodeStore:
    """Read learned raw IR payloads from LocalTuyaIR Remote Control storage."""

    def __init__(self, hass: Any) -> None:
        self._store = Store(hass, LOCALTUYA_RC_CODES_STORAGE_VERSION, LOCALTUYA_RC_CODES_STORAGE_KEY)
        self._devices: dict[str, dict[str, str]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load LocalTuyaIR learned codes if the integration storage exists."""
        if self._loaded:
            return
        try:
            data = await self._store.async_load()
        except Exception as err:
            _LOGGER.debug("LocalTuyaIR learned-code storage is not available: %s", err)
            self._loaded = True
            return
        if isinstance(data, dict):
            self._devices = {
                str(device_name): {
                    str(command_name): str(payload)
                    for command_name, payload in commands.items()
                    if isinstance(payload, str) and payload.startswith(("raw:", "b64:"))
                }
                for device_name, commands in data.items()
                if isinstance(commands, dict)
            }
        self._loaded = True

    @staticmethod
    def aliases_for_label(label: str) -> list[str]:
        """Return LocalTuyaIR command-name aliases for an AeroState pack label."""
        if label == "off":
            return ["power_off", "off"]

        match = re.fullmatch(r"fan_(f[1-5]|auto)_swing_off", label)
        if match:
            fan = match.group(1)
            return [f"fan_speed_{fan[1]}"] if fan.startswith("f") else ["fan_speed_auto"]

        match = re.fullmatch(r"cool_(\d{2})_(f[1-5]|auto)_swing_off", label)
        if not match:
            return []

        temp, fan = match.groups()
        if fan == "auto":
            return [f"temp_{int(temp)}"]

        fan_num = fan[1]
        return [
            f"temp_{int(temp)}_{fan}",
            f"ac_{int(temp)}_fan{fan_num}",
        ]

    def get(self, label: str) -> str | None:
        """Return a matching LocalTuyaIR learned payload when unambiguous."""
        aliases = set(self.aliases_for_label(label))
        if not aliases:
            return None

        matches: list[tuple[str, str, str]] = []
        for device_name, commands in self._devices.items():
            for alias in aliases:
                payload = commands.get(alias)
                if payload:
                    matches.append((device_name, alias, payload))

        if not matches:
            return None
        if len(matches) > 1:
            _LOGGER.warning(
                "LocalTuyaIR learned code lookup for %s is ambiguous: %s",
                label,
                [(device, alias) for device, alias, _payload in matches],
            )
            return None
        device_name, alias, payload = matches[0]
        _LOGGER.debug(
            "TuyaIRManager: using LocalTuyaIR learned code device=%s alias=%s label=%s",
            device_name,
            alias,
            label,
        )
        return payload


class TuyaIRManager:
    """Resolve Tuya IR commands and send learned raw payloads when available."""

    def __init__(
        self,
        hass: Any,
        remote_entity_id: str,
        pack: Any,
        *,
        entry_id: str = "",
        learned_store: LearnedCodeStore | None = None,
        localtuya_rc_store: LocalTuyaRCLearnedCodeStore | None = None,
    ) -> None:
        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._pack = pack
        self._entry_id = entry_id
        self._learned_store = learned_store or LearnedCodeStore(hass)
        self._localtuya_rc_store = localtuya_rc_store or LocalTuyaRCLearnedCodeStore(hass)

    @staticmethod
    def _is_placeholder(key1: str) -> bool:
        """Return True for known empty placeholder payloads."""
        if key1 in {"AA==", "AQ=="}:
            return True
        try:
            decoded = base64.b64decode(key1, validate=True)
        except (binascii.Error, ValueError):
            return False
        return decoded.startswith(b"PLACEHOLDER:")

    @staticmethod
    def build_label(
        hvac_mode: str,
        temperature: int | float | str | None = None,
        fan_mode: str | None = None,
        swing_on: bool = False,
    ) -> str:
        """Build a Tuya pack label for a climate state."""
        if hvac_mode == "off":
            return "off"

        swing = "on" if swing_on else "off"
        fan = fan_mode or "auto"
        if hvac_mode == "fan_only":
            return f"fan_{fan}_swing_{swing}"

        if temperature is None:
            raise ValueError(f"Temperature is required for {hvac_mode} Tuya IR command")
        return f"{hvac_mode}_{int(float(temperature))}_{fan}_swing_{swing}"

    @staticmethod
    def _extract_learned_payload(attributes: dict[str, Any], label: str) -> str | None:
        """Extract a learned raw payload from common LocalTuyaIR attributes."""

        def _payload_from(value: Any) -> str | None:
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                if label in value:
                    return _payload_from(value[label])
                for key in ("raw", "payload", "code", "command", "last_learned_ir"):
                    if key in value:
                        found = _payload_from(value[key])
                        if found:
                            return found
            if isinstance(value, list):
                for item in value:
                    found = _payload_from(item)
                    if found:
                        return found
            return None

        for attr_name in ("last_learned_ir", "learned_commands"):
            found = _payload_from(attributes.get(attr_name))
            if found:
                return found
        return None

    async def async_send_climate_state(self, state: dict[str, Any]) -> None:
        """Resolve and send one climate state."""
        hvac_mode = state.get("hvac_mode", "off")
        temperature = state.get("target_temperature")
        fan_mode = state.get("fan_mode")
        swing_on = bool(state.get("swing_on", state.get("swing_vertical") == "on"))
        preset_mode = state.get("preset_mode")

        if preset_mode and preset_mode not in (None, "none", ""):
            label = f"{preset_mode}_on"
            learned = await self._async_get_learned_payload(label)
            if learned:
                await self._send_command(learned)
                return
            key1 = self._pack.resolve_by_label(label)
            if key1 and not self._is_placeholder(key1):
                await self._send_command(key1)
                return
            raise KeyError(
                f"IR command not learned yet for: {label}. "
                "Use aerostate.learn_ir_command service first.",
            )

        label = self.build_label(
            hvac_mode=str(hvac_mode),
            temperature=temperature,
            fan_mode=fan_mode,
            swing_on=swing_on,
        )

        learned = await self._async_get_learned_payload(label)
        if learned:
            await self._send_command(learned)
            return

        key1 = self._pack.resolve(
            hvac_mode=hvac_mode,
            temperature=int(temperature) if temperature is not None else None,
            fan_mode=fan_mode,
            swing_on=swing_on,
        )

        if not key1 or self._is_placeholder(key1):
            raise KeyError(
                f"IR command not learned yet for: {label}. "
                "Use aerostate.learn_ir_command service first.",
            )

        await self._send_command(key1)

    async def _async_get_learned_payload(self, label: str) -> str | None:
        """Resolve a learned payload from AeroState storage, then LocalTuyaIR storage."""
        if not self._entry_id:
            return None

        await self._learned_store.async_load()
        learned = self._learned_store.get(self._entry_id, label)
        if learned:
            return learned

        await self._localtuya_rc_store.async_load()
        return self._localtuya_rc_store.get(label)

    async def async_learn_command(
        self,
        entry_id: str,
        label: str,
        hvac_mode: str,
        temperature: int | None,
        fan_mode: str | None,
        swing_on: bool,
    ) -> None:
        """Learn one IR command from the physical remote and persist it."""
        await self._hass.services.async_call(
            "remote",
            "learn_command",
            {
                "entity_id": self._remote_entity_id,
                "device": "AeroState",
                "command": [label],
            },
            blocking=True,
        )

        state = self._hass.states.get(self._remote_entity_id)
        attributes = dict(getattr(state, "attributes", {}) or {}) if state else {}
        raw_payload = self._extract_learned_payload(attributes, label)
        if not raw_payload:
            raise RuntimeError(
                f"Learned IR payload for {label} was not exposed by {self._remote_entity_id}",
            )

        await self._learned_store.async_save(entry_id, label, raw_payload)
        _LOGGER.info(
            "TuyaIRManager: learned command label=%s mode=%s temp=%s fan=%s swing_on=%s",
            label,
            hvac_mode,
            temperature,
            fan_mode,
            swing_on,
        )

    async def _send_command(self, payload: str) -> None:
        """Send one IR command using the payload's native format."""
        if payload.startswith(("raw:", "b64:")):
            command = payload
        else:
            command = f"b64:{payload}"

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
            "learned_labels": self._learned_store.list_labels(self._entry_id) if self._entry_id else [],
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
        entry_id=entry.entry_id,
    )
