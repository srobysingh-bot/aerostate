"""Tuya IR manager backed by learned localtuya_rc raw codes."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from .learned_code_resolver import (
    LearnedCodeNotAvailable,
    get_coverage_summary,
    resolve_independent_swing_commands,
    resolve_learned_code,
)
from .localtuya_rc_storage import find_localtuya_command_device, read_learned_codes

try:
    from ..packs.tuya.registry import get_tuya_pack as _get_tuya_pack
except Exception:
    _get_tuya_pack = None

_LOGGER = logging.getLogger(__name__)

POWER_ON_SETTLE_SECONDS = 0.8
STATEFUL_COMMAND_GAP_SECONDS = 0.4
REMOTE_RETRY_SECONDS = 2.0
SWING_COMMAND_GAP_SECONDS = 0.35


class TuyaIRManager:
    """Send IR commands to a Tuya IR blaster using learned raw localtuya_rc codes."""

    def __init__(
        self,
        hass,
        remote_entity_id: str,
        device_name: str,
        pack_id: str | None = None,
    ) -> None:
        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._device_name = device_name
        self._pack_id = pack_id
        self._command_pack = self._load_command_pack(pack_id)
        self._learned_codes: dict[str, str] = {}
        self._codes_loaded = False
        self._last_known_power: bool | None = None
        self._last_sent_fan_mode: str | None = None
        self._last_sent_hvac_mode: str | None = None
        self._last_sent_temperature: int | None = None
        self._last_swing_vertical: str | None = None
        self._last_swing_horizontal: str | None = None
        self._last_main_state_signature: tuple[object, ...] | None = None
        self._localtuya_named_command_devices: dict[str, str | None] = {}

    @staticmethod
    def _load_command_pack(pack_id: str | None):
        """Load a registered Tuya command pack when one was selected."""
        if not isinstance(pack_id, str) or not pack_id.strip():
            return None
        if _get_tuya_pack is None:
            _LOGGER.warning("TuyaIRManager: Tuya pack registry not available")
            return None
        try:
            return _get_tuya_pack(pack_id.strip())
        except Exception as err:
            _LOGGER.warning("TuyaIRManager: could not load Tuya pack '%s': %s", pack_id, err)
            return None

    def _uses_native_b64_pack(self) -> bool:
        """Return True when the selected pack contains direct Tuya base64 codes."""
        return bool(getattr(self._command_pack, "native_base64", False))

    def _uses_stateful_raw_pack(self) -> bool:
        """Return True when the selected pack contains stateful localtuya_rc raw codes."""
        return bool(
            self._command_pack is not None
            and getattr(self._command_pack, "protocol", "") == "stateful"
            and getattr(self._command_pack, "transport", "") == "localtuya_rc"
        )

    def _uses_precomputed_pack(self) -> bool:
        """Return True when commands come from the selected pack, not learned storage."""
        return bool(
            self._command_pack is not None
            and not getattr(self._command_pack, "requires_learned_codes", True)
        )

    def _ensure_codes_loaded(self) -> None:
        """Load learned codes from storage on first use."""
        if self._uses_precomputed_pack():
            return
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
        if self._uses_stateful_raw_pack():
            await self._async_send_stateful_raw_state(state)
            return

        if self._uses_native_b64_pack():
            await self._async_send_precomputed_state(state)
            return

        self._ensure_codes_loaded()
        hvac_mode = str(state.get("hvac_mode", "off")).lower()
        wants_power = hvac_mode != "off" and bool(state.get("power", True))
        try:
            raw_command = resolve_learned_code(self._learned_codes, state)
        except LearnedCodeNotAvailable as err:
            _LOGGER.warning("TuyaIRManager: no learned code for state=%s - %s", state, err)
            await self._async_notify_missing_code(state, err)
            raise

        swing_commands: list[tuple[str, str, str]] = []
        if wants_power:
            swing_commands = resolve_independent_swing_commands(
                self._learned_codes,
                state,
                previous_vertical=self._last_swing_vertical,
                previous_horizontal=self._last_swing_horizontal,
            )

        main_signature = self._main_state_signature(state, wants_power=wants_power)
        main_unchanged = main_signature == self._last_main_state_signature

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

        if main_unchanged and swing_commands:
            _LOGGER.debug("TuyaIRManager: skipping main AC command for swing-only state=%s", state)
        else:
            _LOGGER.debug("TuyaIRManager: sending state=%s via %s", state, self._remote_entity_id)
            await self._async_send_raw_command(raw_command)

        for axis, label, swing_command in swing_commands:
            await asyncio.sleep(SWING_COMMAND_GAP_SECONDS)
            _LOGGER.info(
                "TuyaIRManager: sending independent %s swing command '%s' via %s",
                axis,
                label,
                self._remote_entity_id,
            )
            await self._async_send_independent_command(label, swing_command)

        self._last_known_power = wants_power
        self._last_main_state_signature = main_signature
        self._last_swing_vertical = self._normalize_swing_state(state.get("swing_vertical"))
        self._last_swing_horizontal = self._normalize_swing_state(state.get("swing_horizontal"))

    async def _async_send_stateful_raw_state(self, state: dict[str, Any]) -> None:
        """Send a stateful localtuya_rc pack as power, temperature, then fan commands."""
        pack = self._command_pack
        if pack is None:
            raise LearnedCodeNotAvailable("Stateful Tuya command pack is not loaded")

        hvac_mode = str(state.get("hvac_mode", "off")).lower()
        wants_power = hvac_mode != "off" and bool(state.get("power", True))
        previously_off = bool(state.get("previously_off", self._last_known_power is not True))

        if not wants_power:
            await self._async_send_raw_command(self._resolve_pack_label("power_off"))
            self._last_known_power = False
            self._last_sent_hvac_mode = None
            self._last_sent_temperature = None
            self._last_sent_fan_mode = None
            self._last_main_state_signature = self._main_state_signature(state, wants_power=False)
            return

        if hvac_mode == "fan":
            hvac_mode = "fan_only"

        if previously_off:
            _LOGGER.info(
                "TuyaIRManager: waking stateful localtuya_rc AC with power_on via %s",
                self._remote_entity_id,
            )
            await self._async_send_raw_command(self._resolve_pack_label("power_on"))
            await asyncio.sleep(POWER_ON_SETTLE_SECONDS)

        temperature = self._state_temperature(state)
        if temperature is None:
            temperature = 25 if hvac_mode == "fan_only" else 24
        temperature = max(
            int(getattr(pack, "min_temperature", 16)),
            min(int(getattr(pack, "max_temperature", 30)), temperature),
        )

        current_fan = str(state.get("fan_mode") or "auto").lower()
        fan_key = self._fan_mode_to_key(current_fan)

        mode_changed = hvac_mode != self._last_sent_hvac_mode
        temp_changed = temperature != self._last_sent_temperature
        fan_changed = current_fan != self._last_sent_fan_mode

        if previously_off:
            # Powering on: send mode+temp first, then fan.
            temp_key = f"{hvac_mode}_t{temperature}"
            _LOGGER.debug("TuyaIRManager: power-on send mode/temp %s", temp_key)
            await self._async_send_raw_command(self._resolve_pack_label(temp_key))
            if fan_key:
                await asyncio.sleep(STATEFUL_COMMAND_GAP_SECONDS)
                _LOGGER.debug("TuyaIRManager: power-on send fan %s", fan_key)
                await self._async_send_raw_command(self._resolve_pack_label(fan_key))

        elif fan_changed and not mode_changed and not temp_changed:
            # Only fan changed. Do not send a temp frame; LG will reset the setpoint.
            if fan_key:
                _LOGGER.debug("TuyaIRManager: fan-only send %s", fan_key)
                await self._async_send_raw_command(self._resolve_pack_label(fan_key))
            else:
                _LOGGER.debug("TuyaIRManager: fan mode 'auto' - no fan command needed")

        elif mode_changed or temp_changed:
            # Mode or temp changed. Do not send a fan frame after it.
            temp_key = f"{hvac_mode}_t{temperature}"
            _LOGGER.debug("TuyaIRManager: mode/temp send %s", temp_key)
            await self._async_send_raw_command(self._resolve_pack_label(temp_key))

        else:
            _LOGGER.debug("TuyaIRManager: stateful state unchanged, skipping send")

        self._last_sent_hvac_mode = hvac_mode
        self._last_sent_temperature = temperature
        self._last_sent_fan_mode = current_fan

        desired_vertical = self._normalize_swing_state(state.get("swing_vertical"))
        desired_horizontal = self._normalize_swing_state(state.get("swing_horizontal"))

        if desired_vertical is not None and desired_vertical != self._last_swing_vertical:
            try:
                v_code = self._resolve_pack_label("swing_vertical_toggle")
            except LearnedCodeNotAvailable:
                _LOGGER.debug("TuyaIRManager: no vertical swing toggle in pack")
            else:
                await asyncio.sleep(SWING_COMMAND_GAP_SECONDS)
                _LOGGER.debug(
                    "TuyaIRManager: sending vertical swing toggle (%s -> %s)",
                    self._last_swing_vertical,
                    desired_vertical,
                )
                await self._async_send_raw_command(v_code)
                self._last_swing_vertical = desired_vertical

        if desired_horizontal is not None and desired_horizontal != self._last_swing_horizontal:
            try:
                h_code = self._resolve_pack_label("swing_horizontal_toggle")
            except LearnedCodeNotAvailable:
                _LOGGER.debug("TuyaIRManager: no horizontal swing toggle in pack")
            else:
                await asyncio.sleep(SWING_COMMAND_GAP_SECONDS)
                _LOGGER.debug(
                    "TuyaIRManager: sending horizontal swing toggle (%s -> %s)",
                    self._last_swing_horizontal,
                    desired_horizontal,
                )
                await self._async_send_raw_command(h_code)
                self._last_swing_horizontal = desired_horizontal

        self._last_known_power = True
        self._last_main_state_signature = self._stateful_main_state_signature(
            state,
            wants_power=True,
            hvac_mode=hvac_mode,
            temperature=temperature,
        )

    def _resolve_pack_label(self, label: str) -> str:
        """Return a selected-pack command payload by label."""
        pack = self._command_pack
        code = pack.resolve_by_label(label) if pack is not None else None
        if code:
            return code
        raise LearnedCodeNotAvailable(f"Selected Tuya pack does not contain command '{label}'")

    @staticmethod
    def _fan_mode_to_key(fan_mode: str) -> str | None:
        """Map Home Assistant fan modes to stateful localtuya_rc command labels."""
        mapping = {
            "low": "fan_low",
            "mid_low": "fan_mid_low",
            "mid": "fan_mid",
            "medium": "fan_mid",
            "med": "fan_mid",
            "mid_high": "fan_mid_high",
            "high": "fan_high",
            "f1": "fan_low",
            "f2": "fan_mid_low",
            "f3": "fan_mid",
            "f4": "fan_mid_high",
            "f5": "fan_high",
            "auto": None,
        }
        return mapping.get(fan_mode)

    async def _async_send_precomputed_state(self, state: dict[str, Any]) -> None:
        """Resolve and send a pre-generated native Tuya base64 command."""
        pack = self._command_pack
        if pack is None:
            raise LearnedCodeNotAvailable("Tuya native command pack is not loaded")

        hvac_mode = str(state.get("hvac_mode", "off")).lower()
        wants_power = hvac_mode != "off" and bool(state.get("power", True))
        previously_off = bool(state.get("previously_off", self._last_known_power is not True))
        fan_mode = str(state.get("fan_mode", "auto") or "auto").lower()
        temperature = self._state_temperature(state)

        raw_command = pack.resolve(
            hvac_mode,
            temperature,
            fan_mode,
            False,
            previously_off=previously_off,
        )
        if raw_command is None:
            err = LearnedCodeNotAvailable(
                f"No pre-generated Tuya code for mode={hvac_mode}, temp={temperature}, fan={fan_mode}"
            )
            _LOGGER.warning("TuyaIRManager: no pre-generated code for state=%s - %s", state, err)
            await self._async_notify_missing_code(state, err)
            raise err

        swing_command: str | None = None
        desired_vertical = self._normalize_swing_state(state.get("swing_vertical"))
        if wants_power and self._should_send_swing_toggle(desired_vertical):
            swing_command = pack.resolve_swing_toggle()

        main_signature = self._main_state_signature(state, wants_power=wants_power)
        main_unchanged = main_signature == self._last_main_state_signature

        if main_unchanged and swing_command:
            _LOGGER.debug("TuyaIRManager: skipping native b64 main command for swing-only state=%s", state)
        else:
            payload_hash = hashlib.sha256(raw_command.encode("ascii", errors="replace")).hexdigest()[:12]
            _LOGGER.info(
                "TuyaIRManager: sending native b64 state=%s via %s payload_sha12=%s previously_off=%s",
                state,
                self._remote_entity_id,
                payload_hash,
                previously_off,
            )
            await self._async_send_native_b64_command(raw_command)

        if swing_command:
            await asyncio.sleep(SWING_COMMAND_GAP_SECONDS)
            _LOGGER.info(
                "TuyaIRManager: sending native b64 swing toggle via %s",
                self._remote_entity_id,
            )
            await self._async_send_native_b64_command(swing_command)

        self._last_known_power = wants_power
        self._last_main_state_signature = main_signature
        self._last_swing_vertical = desired_vertical
        self._last_swing_horizontal = self._normalize_swing_state(state.get("swing_horizontal"))

    @staticmethod
    def _state_temperature(state: dict[str, Any]) -> int | None:
        """Return an integer target temperature when present."""
        if state.get("target_temperature") is None:
            return None
        try:
            return int(round(float(state["target_temperature"])))
        except (TypeError, ValueError):
            return None

    def _should_send_swing_toggle(self, desired_vertical: str | None) -> bool:
        """Return True when a native-b64 pack needs its independent swing toggle."""
        if desired_vertical is None:
            return False
        if desired_vertical not in {"on", "swing"}:
            return self._last_swing_vertical not in {None, desired_vertical}
        if self._last_swing_vertical is None:
            return True
        return desired_vertical != self._last_swing_vertical

    @staticmethod
    def _main_state_signature(state: dict[str, Any], *, wants_power: bool) -> tuple[object, ...]:
        """Return the part of state represented by the full AC IR command."""
        return (
            wants_power,
            str(state.get("hvac_mode", "off")).lower(),
            state.get("target_temperature"),
            state.get("fan_mode"),
            state.get("preset_mode"),
        )

    @staticmethod
    def _stateful_main_state_signature(
        state: dict[str, Any],
        *,
        wants_power: bool,
        hvac_mode: str,
        temperature: int,
    ) -> tuple[object, ...]:
        """Return the state represented by the stateful mode/temperature IR frame."""
        return (
            wants_power,
            hvac_mode,
            temperature,
            state.get("preset_mode"),
        )

    @staticmethod
    def _normalize_swing_state(value: object) -> str | None:
        """Normalize cached swing values the same way the resolver expects them."""
        if value is None:
            return None
        return str(value).strip().lower().replace(" ", "_").replace("-", "_")

    async def _async_send_native_b64_command(self, command_b64: str) -> None:
        """Send one pre-generated Tuya base64 command with the required b64 prefix."""
        command = command_b64 if command_b64.startswith("b64:") else f"b64:{command_b64}"
        await self._hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": self._remote_entity_id,
                "command": command,
            },
            blocking=False,
        )

    def _remote_is_unavailable(self) -> bool:
        """Return True when the configured remote entity cannot send right now."""
        state = self._hass.states.get(self._remote_entity_id)
        return state is None or state.state in ("unavailable", "unknown")

    async def _async_send_raw_command(self, raw_command: str) -> None:
        """Send one learned raw command through the configured remote entity.

        Re-check the remote entity immediately before every send. localtuya_rc
        devices can reconnect after startup, so availability must not be based
        only on the setup-time transport probe.
        """
        if self._remote_is_unavailable():
            _LOGGER.warning(
                "TuyaIRManager: remote entity %s is unavailable, retrying in %.1fs",
                self._remote_entity_id,
                REMOTE_RETRY_SECONDS,
            )
            await asyncio.sleep(REMOTE_RETRY_SECONDS)
            if self._remote_is_unavailable():
                _LOGGER.error(
                    "TuyaIRManager: remote entity %s still unavailable, command dropped",
                    self._remote_entity_id,
                )
                raise RuntimeError(f"remote entity {self._remote_entity_id} is unavailable")

        await self._hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": self._remote_entity_id,
                "command": raw_command,
                "num_repeats": 1,
                "delay_secs": 0.4,
            },
            blocking=True,
        )

    async def _async_send_independent_command(self, label: str, raw_command: str) -> None:
        """
        Send an independent learned command.

        When the label exists in localtuya_rc storage, prefer the exact named
        command path the user tested manually. If the integration is running on
        another Home Assistant without localtuya_rc storage, fall back to the
        portable raw command.
        """
        device_name = self._localtuya_named_command_device(label)
        if device_name:
            await self._hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self._remote_entity_id,
                    "device": device_name,
                    "command": label,
                },
                blocking=False,
            )
            return

        await self._async_send_raw_command(raw_command)

    def _localtuya_named_command_device(self, label: str) -> str | None:
        """Return cached localtuya_rc device name for a command label."""
        if label not in self._localtuya_named_command_devices:
            self._localtuya_named_command_devices[label] = find_localtuya_command_device(
                self._hass,
                label,
                preferred_device_name=self._device_name,
            )
        return self._localtuya_named_command_devices[label]

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

        if self._uses_precomputed_pack():
            return True

        self._ensure_codes_loaded()
        if not self._learned_codes:
            _LOGGER.warning("TuyaIRManager: no learned codes found for device '%s'", self._device_name)
            return False
        return True

    def describe(self) -> dict[str, Any]:
        """Return debug-safe manager details."""
        self._ensure_codes_loaded()
        return {
            "transport": (
                "localtuya_rc_stateful_pack"
                if self._uses_stateful_raw_pack()
                else "tuya_ir_native_b64"
                if self._uses_native_b64_pack()
                else "tuya_ir_learned_codes"
            ),
            "remote_entity": self._remote_entity_id,
            "device_name": self._device_name,
            "pack_id": self._pack_id or "",
            "coverage": (
                {
                    "pack_id": getattr(self._command_pack, "pack_id", ""),
                    "total_codes": len(getattr(self._command_pack, "commands", []) or []),
                    "requires_learning": False,
                }
                if self._uses_precomputed_pack()
                else get_coverage_summary(self._learned_codes)
            ),
        }


def create_tuya_ir_manager_from_entry(hass, entry) -> TuyaIRManager:
    """Build TuyaIRManager from config entry."""
    from ..const import (
        CONF_TUYA_DEVICE_NAME,
        CONF_TUYA_IR_ENTITY,
        CONF_TUYA_MODEL_PACK,
        DEFAULT_TUYA_DEVICE_NAME,
    )

    def _opt(key, default=None):
        return entry.options.get(key, entry.data.get(key, default))

    return TuyaIRManager(
        hass=hass,
        remote_entity_id=_opt(CONF_TUYA_IR_ENTITY),
        device_name=_opt(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
        pack_id=_opt(CONF_TUYA_MODEL_PACK),
    )


__all__ = ["LearnedCodeNotAvailable", "TuyaIRManager", "create_tuya_ir_manager_from_entry"]
