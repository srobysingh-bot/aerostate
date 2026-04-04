"""Climate entity for AeroState AC control."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PRESET_NONE,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_AREA,
    CONF_BRAND,
    CONF_BROADLINK_ENTITY,
    CONF_HUM_SENSOR,
    CONF_MODEL_PACK,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_TEMP_SENSOR,
    DEFAULT_NAME,
    DOMAIN,
)
from .engines import StateEngine, create_engine
from .providers import BroadlinkProvider
from .repairs import async_clear_command_failure, async_report_command_failure

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .packs.schema import ModelPack

_LOGGER: logging.Logger = logging.getLogger(__name__)


class AeroStateClimate(ClimateEntity, RestoreEntity):
    """Climate entity for AeroState AC control."""

    _attr_has_entity_name = True
    _attr_max_temp = 30
    _attr_min_temp = 16
    _command_debounce_seconds = 0.45

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        pack: ModelPack,
        provider: BroadlinkProvider,
        engine: StateEngine,
    ) -> None:
        """Initialize climate entity.

        Args:
            hass: Home Assistant instance
            entry: Config entry
            pack: Model pack
            provider: Broadlink provider
            engine: State resolution engine
        """
        self._hass = hass
        self._entry = entry
        self._pack = pack
        self._provider = provider
        self._engine = engine
        self._last_requested_hvac_mode: HVACMode = HVACMode.COOL

        # State tracking
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = float(pack.min_temperature)
        self._attr_fan_mode = (
            pack.capabilities.fan_modes[0] if pack.capabilities.fan_modes else None
        )
        declared_vertical = list(pack.capabilities.swing_vertical_modes)
        declared_horizontal = list(pack.capabilities.swing_horizontal_modes)
        declared_presets = list(getattr(pack.capabilities, "preset_modes", []) or pack.capabilities.presets)

        engine_vertical = list(getattr(engine, "supported_vertical_swing_modes", lambda: declared_vertical)())
        engine_horizontal = list(getattr(engine, "supported_horizontal_swing_modes", lambda: declared_horizontal)())
        engine_presets = list(getattr(engine, "supported_preset_modes", lambda: declared_presets)())

        self._supported_swing_vertical_modes = [mode for mode in declared_vertical if mode in engine_vertical]
        self._supported_swing_horizontal_modes = [mode for mode in declared_horizontal if mode in engine_horizontal]
        self._supported_preset_modes = [mode for mode in declared_presets if mode in engine_presets]

        self._attr_swing_mode = (
            self._supported_swing_vertical_modes[0]
            if self._supported_swing_vertical_modes
            else None
        )
        self._attr_swing_horizontal_mode = (
            self._supported_swing_horizontal_modes[0]
            if self._supported_swing_horizontal_modes
            else None
        )
        self._attr_preset_mode = (
            PRESET_NONE
            if PRESET_NONE in self._supported_preset_modes
            else (self._supported_preset_modes[0] if self._supported_preset_modes else None)
        )
        self._attr_current_temperature = None
        self._attr_current_humidity = None
        self._attr_temperature_unit = hass.config.units.temperature_unit
        self._attr_target_temperature_step = float(
            getattr(pack, "temperature_step", 1.0) or 1.0
        )
        self._supported_temperatures = self._derive_supported_temperatures()

        self._attr_min_temp = float(pack.min_temperature)
        self._attr_max_temp = float(pack.max_temperature)

        # If pack matrix has a smaller temperature subset, clamp dynamically.
        if self._supported_temperatures:
            self._attr_min_temp = float(min(self._supported_temperatures))
            self._attr_max_temp = float(max(self._supported_temperatures))
            self._attr_target_temperature = float(min(self._supported_temperatures))

        # Latest-wins command pipeline state.
        self._pending_state: dict[str, Any] | None = None
        self._last_sent_state: dict[str, Any] | None = None
        self._last_sent_payload_hash: str | None = None
        self._last_send_error: str | None = None
        self._debounce_handle: asyncio.TimerHandle | None = None
        self._send_worker_task: asyncio.Task[None] | None = None

    def _entry_value(self, key: str, default: Any = None) -> Any:
        """Read an entry value, preferring options over data."""
        if key in self._entry.options:
            return self._entry.options.get(key)
        return self._entry.data.get(key, default)

    def _collect_temperatures_recursive(self, node: Any, out: set[int]) -> None:
        """Recursively walk command nodes and collect numeric temperature keys."""
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if isinstance(key, str) and key.isdigit() and isinstance(value, str):
                out.add(int(key))
            self._collect_temperatures_recursive(value, out)

    def _derive_supported_temperatures(self) -> list[int]:
        """Collect supported temperatures from all command branches recursively."""
        temps: set[int] = set()
        for mode in self._pack.capabilities.hvac_modes:
            self._collect_temperatures_recursive(self._pack.commands.get(mode), temps)
        return sorted(temps)

    def _power_sensor_state(self) -> str | None:
        """Return linked power sensor state if configured."""
        power_sensor = self._entry_value(CONF_POWER_SENSOR)
        if not power_sensor:
            return None
        state = self._hass.states.get(power_sensor)
        if state is None:
            return "unavailable"
        return state.state

    def _sync_hvac_from_power_sensor(self) -> None:
        """Observe linked power sensor without forcing command intent."""
        power_state = self._power_sensor_state()
        if power_state is None:
            return
        if power_state in {"unavailable", "unknown"}:
            # Preserve command intent while sensor is laggy/unavailable.
            return
        normalized = power_state.lower()
        if normalized in {"off", "false", "0"}:
            _LOGGER.debug(
                "Linked power sensor reports OFF for %s, keeping desired hvac_mode=%s",
                self.entity_id,
                self._attr_hvac_mode,
            )

    @staticmethod
    def _normalize_power_state(power_state: str | None) -> str | None:
        """Normalize linked power sensor values into on/off when possible."""
        if power_state is None:
            return None
        normalized = power_state.lower()
        if normalized in {"on", "true", "1"}:
            return "on"
        if normalized in {"off", "false", "0"}:
            return "off"
        return None

    def _pick_safe_running_mode(self, restored_mode: HVACMode | None = None) -> HVACMode | None:
        """Pick a safe running mode when power feedback says the AC is on."""
        running_modes = [mode for mode in self.hvac_modes if mode != HVACMode.OFF]
        if not running_modes:
            return None
        if self._last_requested_hvac_mode in running_modes:
            return self._last_requested_hvac_mode
        if restored_mode in running_modes:
            return restored_mode
        if HVACMode.COOL in running_modes:
            return HVACMode.COOL
        return running_modes[0]

    async def async_added_to_hass(self) -> None:
        """Restore state after restart and reconcile with linked power sensor."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        restored_hvac_mode: HVACMode | None = None

        if last_state is not None:
            try:
                candidate_hvac_mode = HVACMode(last_state.state)
            except ValueError:
                candidate_hvac_mode = None

            if candidate_hvac_mode is not None and candidate_hvac_mode in self.hvac_modes:
                self._attr_hvac_mode = candidate_hvac_mode
                restored_hvac_mode = candidate_hvac_mode
                if candidate_hvac_mode != HVACMode.OFF:
                    self._last_requested_hvac_mode = candidate_hvac_mode

            restored_temp = last_state.attributes.get(ATTR_TEMPERATURE)
            if restored_temp is not None:
                try:
                    requested = int(round(float(restored_temp)))
                except (TypeError, ValueError):
                    requested = None
                if requested is not None:
                    if self._supported_temperatures:
                        if requested in self._supported_temperatures:
                            self._attr_target_temperature = float(requested)
                    elif int(self._attr_min_temp) <= requested <= int(self._attr_max_temp):
                        self._attr_target_temperature = float(requested)

            restored_fan = last_state.attributes.get("fan_mode")
            if isinstance(restored_fan, str):
                normalized_fan = restored_fan.lower()
                if normalized_fan in self._pack.capabilities.fan_modes:
                    self._attr_fan_mode = normalized_fan

            restored_swing = last_state.attributes.get("swing_mode")
            if isinstance(restored_swing, str) and restored_swing in self._supported_swing_vertical_modes:
                self._attr_swing_mode = restored_swing

            restored_swing_horizontal = last_state.attributes.get("swing_horizontal_mode")
            if (
                isinstance(restored_swing_horizontal, str)
                and restored_swing_horizontal in self._supported_swing_horizontal_modes
            ):
                self._attr_swing_horizontal_mode = restored_swing_horizontal

            restored_preset = last_state.attributes.get("preset_mode")
            if isinstance(restored_preset, str) and restored_preset in self._supported_preset_modes:
                self._attr_preset_mode = restored_preset

            restored_last_requested_hvac = last_state.attributes.get("last_requested_hvac_mode")
            if isinstance(restored_last_requested_hvac, str):
                try:
                    candidate_requested = HVACMode(restored_last_requested_hvac)
                except ValueError:
                    candidate_requested = None
                if candidate_requested in self.hvac_modes and candidate_requested != HVACMode.OFF:
                    self._last_requested_hvac_mode = candidate_requested

        normalized_power = self._normalize_power_state(self._power_sensor_state())
        if normalized_power == "off":
            self._attr_hvac_mode = HVACMode.OFF
        elif normalized_power == "on" and self._attr_hvac_mode == HVACMode.OFF:
            inferred_mode = self._pick_safe_running_mode(restored_hvac_mode)
            if inferred_mode is not None:
                self._attr_hvac_mode = inferred_mode

        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return entity name from config."""
        configured_name = self._entry_value(CONF_NAME)
        if configured_name:
            return str(configured_name)
        area = self._entry_value(CONF_AREA, "")
        if area:
            return f"{area} AC"
        return DEFAULT_NAME

    @property
    def unique_id(self) -> str:
        """Return stable unique ID."""
        return f"{self._entry.entry_id}_climate"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "manufacturer": self._pack.brand,
            "model": ", ".join(self._pack.models) if self._pack.models else "Unknown",
            "name": self.name,
        }

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return bitmask of supported features based on pack."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

        if self._pack.capabilities.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE

        if self._supported_swing_vertical_modes:
            features |= ClimateEntityFeature.SWING_MODE

        if self._supported_swing_horizontal_modes:
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE

        if self._supported_preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE

        return features

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return list of available HVAC modes."""
        modes = [HVACMode.OFF]
        seen: set[str] = {HVACMode.OFF.value}
        for mode_str in self._pack.capabilities.hvac_modes:
            if mode_str == HVACMode.OFF.value:
                continue
            if mode_str in seen:
                continue
            try:
                modes.append(HVACMode(mode_str))
                seen.add(mode_str)
            except ValueError:
                _LOGGER.warning("Ignoring unsupported HVAC mode in pack '%s': %s", self._pack.pack_id, mode_str)
        return modes

    @property
    def fan_modes(self) -> list[str] | None:
        """Return list of available fan modes."""
        if self._pack.capabilities.fan_modes:
            return list(self._pack.capabilities.fan_modes)
        return None

    @property
    def swing_modes(self) -> list[str] | None:
        """Return list of available vertical swing modes."""
        if self._supported_swing_vertical_modes:
            return list(self._supported_swing_vertical_modes)
        return None

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return list of available horizontal swing modes."""
        if self._supported_swing_horizontal_modes:
            return list(self._supported_swing_horizontal_modes)
        return None

    @property
    def preset_modes(self) -> list[str] | None:
        """Return list of available preset modes when supported."""
        if self._supported_preset_modes:
            return list(self._supported_preset_modes)
        return None

    @property
    def preset_mode(self) -> str | None:
        """Return the selected preset mode."""
        return self._attr_preset_mode

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature from linked sensor."""
        temp_sensor = self._entry_value(CONF_TEMP_SENSOR)
        if not temp_sensor:
            return None

        try:
            state = self._hass.states.get(temp_sensor)
            if state and state.state not in ("unavailable", "unknown"):
                return float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse temperature from %s: %s",
                temp_sensor,
                state.state if state else "entity not found",
            )

        return None

    @property
    def current_humidity(self) -> int | None:
        """Return current humidity from linked sensor."""
        humidity_sensor = self._entry_value(CONF_HUM_SENSOR)
        if not humidity_sensor:
            return None

        try:
            state = self._hass.states.get(humidity_sensor)
            if state and state.state not in ("unavailable", "unknown"):
                return int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Could not parse humidity from %s: %s",
                humidity_sensor,
                state.state if state else "entity not found",
            )

        return None

    @property
    def available(self) -> bool:
        """Report entity availability.

        Keep the entity available even when the linked power sensor is laggy,
        so the command pipeline can continue and recover gracefully.
        """
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose pipeline health and linked power sensor diagnostics."""
        power_state = self._power_sensor_state()
        desired_state = self._pending_state or self._build_state_dict(sync_power_sensor=False)
        desired_differs_from_last_sent = desired_state != self._last_sent_state

        attrs: dict[str, Any] = {
            "linked_power_sensor_state": power_state,
            "linked_power_sensor_degraded": power_state in {"unavailable", "unknown"},
            "pending_command": self._pending_state is not None,
            "desired_differs_from_last_sent": desired_differs_from_last_sent,
            "last_requested_hvac_mode": self._last_requested_hvac_mode.value,
        }
        if self._last_send_error:
            attrs["last_command_error"] = self._last_send_error
        return attrs

    @property
    def assumed_state(self) -> bool:
        """This entity is inferred from commands and optional sensors."""
        return True

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode and schedule command apply."""
        if hvac_mode not in self.hvac_modes:
            _LOGGER.warning(
                "Rejected hvac mode '%s' for pack %s. Supported modes: %s",
                hvac_mode,
                self._pack.pack_id,
                [mode.value for mode in self.hvac_modes],
            )
            raise HomeAssistantError(f"HVAC mode '{hvac_mode}' is not supported by selected pack")

        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._last_requested_hvac_mode = hvac_mode
        self._schedule_state_apply()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature and schedule command apply."""
        if ATTR_TEMPERATURE in kwargs:
            requested = int(round(float(kwargs[ATTR_TEMPERATURE])))
            if requested < int(self._attr_min_temp) or requested > int(self._attr_max_temp):
                _LOGGER.warning(
                    "Rejected out-of-range temperature %s for pack %s. Supported range: %s-%s",
                    requested,
                    self._pack.pack_id,
                    int(self._attr_min_temp),
                    int(self._attr_max_temp),
                )
                raise HomeAssistantError(
                    f"Temperature {requested} is outside the supported range {int(self._attr_min_temp)}-{int(self._attr_max_temp)}"
                )
            if self._supported_temperatures and requested not in self._supported_temperatures:
                _LOGGER.warning(
                    "Rejected unsupported temperature %s for pack %s. Supported temperatures: %s",
                    requested,
                    self._pack.pack_id,
                    self._supported_temperatures,
                )
                raise HomeAssistantError(
                    f"Temperature {requested} is not available in the selected pack command matrix"
                )
            self._attr_target_temperature = requested
        self._schedule_state_apply()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode and schedule command apply."""
        normalized_fan_mode = str(fan_mode).lower()
        if normalized_fan_mode not in self._pack.capabilities.fan_modes:
            _LOGGER.warning(
                "Rejected fan mode '%s' for pack %s. Supported fan modes: %s",
                fan_mode,
                self._pack.pack_id,
                self._pack.capabilities.fan_modes,
            )
            raise HomeAssistantError(f"Fan mode '{fan_mode}' is not supported by selected pack")

        self._attr_fan_mode = normalized_fan_mode
        self._schedule_state_apply()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set vertical swing and schedule command apply."""
        if swing_mode not in self._supported_swing_vertical_modes:
            _LOGGER.warning(
                "Rejected vertical swing mode '%s' for pack %s. Supported vertical swing modes: %s",
                swing_mode,
                self._pack.pack_id,
                self._supported_swing_vertical_modes,
            )
            raise HomeAssistantError(
                f"Vertical swing mode '{swing_mode}' is not supported by selected pack"
            )

        self._attr_swing_mode = swing_mode
        self._schedule_state_apply()

    async def async_set_swing_horizontal_mode(
        self, swing_horizontal_mode: str
    ) -> None:
        """Set horizontal swing and schedule command apply."""
        if swing_horizontal_mode not in self._supported_swing_horizontal_modes:
            _LOGGER.warning(
                "Rejected horizontal swing mode '%s' for pack %s. Supported horizontal swing modes: %s",
                swing_horizontal_mode,
                self._pack.pack_id,
                self._supported_swing_horizontal_modes,
            )
            raise HomeAssistantError(
                f"Horizontal swing mode '{swing_horizontal_mode}' is not supported by selected pack"
            )

        self._attr_swing_horizontal_mode = swing_horizontal_mode
        self._schedule_state_apply()

    async def async_turn_on(self) -> None:
        """Turn on (set to last hvac_mode or cool)."""
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = self._last_requested_hvac_mode

        self._schedule_state_apply()

    async def async_turn_off(self) -> None:
        """Turn off."""
        self._attr_hvac_mode = HVACMode.OFF
        self._schedule_state_apply()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode and schedule command apply."""
        if preset_mode not in self._supported_preset_modes:
            _LOGGER.warning(
                "Rejected preset mode '%s' for pack %s. Supported preset modes: %s",
                preset_mode,
                self._pack.pack_id,
                self._supported_preset_modes,
            )
            raise HomeAssistantError(
                f"Preset mode '{preset_mode}' is not supported by selected pack"
            )

        self._attr_preset_mode = preset_mode
        self._schedule_state_apply()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel scheduled command work when entity is removed."""
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
            self._debounce_handle = None
        if self._send_worker_task is not None:
            self._send_worker_task.cancel()
            self._send_worker_task = None

    def _build_state_dict(self, *, sync_power_sensor: bool = True) -> dict[str, Any]:
        """Build a normalized desired state dictionary for engine resolution."""
        if sync_power_sensor:
            self._sync_hvac_from_power_sensor()

        target_temp = max(self._attr_min_temp, min(self._attr_target_temperature, self._attr_max_temp))
        self._attr_target_temperature = target_temp

        state_dict: dict[str, Any] = {
            "power": self._attr_hvac_mode != HVACMode.OFF,
            "hvac_mode": self._attr_hvac_mode.value if self._attr_hvac_mode != HVACMode.OFF else "off",
            "target_temperature": int(round(self._attr_target_temperature)),
        }

        if self._pack.capabilities.fan_modes and self._attr_fan_mode:
            state_dict["fan_mode"] = self._attr_fan_mode
        elif self._pack.capabilities.fan_modes:
            state_dict["fan_mode"] = self._pack.capabilities.fan_modes[0]

        if self._supported_swing_vertical_modes and self._attr_swing_mode:
            state_dict["swing_vertical"] = self._attr_swing_mode
        elif self._supported_swing_vertical_modes:
            state_dict["swing_vertical"] = self._supported_swing_vertical_modes[0]

        if self._supported_swing_horizontal_modes and self._attr_swing_horizontal_mode:
            state_dict["swing_horizontal"] = self._attr_swing_horizontal_mode
        elif self._supported_swing_horizontal_modes:
            state_dict["swing_horizontal"] = self._supported_swing_horizontal_modes[0]

        if self._supported_preset_modes and self._attr_preset_mode:
            state_dict["preset_mode"] = self._attr_preset_mode
        elif self._supported_preset_modes:
            state_dict["preset_mode"] = PRESET_NONE if PRESET_NONE in self._supported_preset_modes else self._supported_preset_modes[0]

        return state_dict

    def _schedule_state_apply(self) -> None:
        """Coalesce rapid UI mutations and enqueue only latest desired state."""
        self._pending_state = self._build_state_dict()
        self.async_write_ha_state()

        if self._debounce_handle is not None:
            self._debounce_handle.cancel()

        loop = asyncio.get_running_loop()
        self._debounce_handle = loop.call_later(
            self._command_debounce_seconds,
            self._start_send_worker,
        )

    def _start_send_worker(self) -> None:
        """Start a single worker to flush latest desired state."""
        self._debounce_handle = None
        if self._send_worker_task is not None and not self._send_worker_task.done():
            return
        self._send_worker_task = asyncio.create_task(self._async_send_worker())

    async def _async_send_worker(self) -> None:
        """Send pipeline with latest-state-wins semantics."""
        try:
            while self._pending_state is not None:
                state_dict = self._pending_state
                self._pending_state = None
                await self._send_state_if_needed(state_dict)
        finally:
            self._send_worker_task = None

    async def _send_state_if_needed(self, state_dict: dict[str, Any]) -> None:
        """Resolve and send only if state or payload effectively changed."""
        try:
            if state_dict == self._last_sent_state:
                _LOGGER.debug("Skipping command send; desired state unchanged")
                return

            _LOGGER.debug("Applying state: %s", state_dict)
            command = self._engine.resolve_command(state_dict)
            commands = command if isinstance(command, list) else [command]
            payload_hash = hashlib.sha256("|".join(commands).encode("ascii")).hexdigest()[:12]

            if payload_hash == self._last_sent_payload_hash:
                _LOGGER.debug("Skipping command send; payload hash unchanged (%s)", payload_hash)
                self._last_sent_state = dict(state_dict)
                return

            if len(commands) == 1:
                await self._provider.send_base64(commands[0])
            else:
                await self._provider.send_sequence(
                    [(f"cmd_{idx + 1}", payload) for idx, payload in enumerate(commands)]
                )

            self._last_sent_state = dict(state_dict)
            self._last_sent_payload_hash = payload_hash
            self._last_send_error = None

            async_clear_command_failure(self._hass, self._entry)
            self._sync_hvac_from_power_sensor()
            self.async_write_ha_state()

            _LOGGER.info(
                "AC command sent successfully for mode %s, temp %s",
                self._attr_hvac_mode,
                self._attr_target_temperature,
            )
        except Exception as err:
            self._last_send_error = str(err)
            _LOGGER.warning(
                "Command resolution/send failed for pack %s and state %s: %s",
                self._pack.pack_id,
                state_dict,
                err,
            )
            _LOGGER.warning(
                "AeroState desired state is not yet confirmed on device. desired=%s last_sent=%s",
                state_dict,
                self._last_sent_state,
            )
            async_report_command_failure(self._hass, self._entry)
            self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> bool:
    """Set up AeroState climate entities from config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities

    Returns:
        True if setup successful
    """
    _LOGGER.debug("Setting up AeroState climate for entry: %s", entry.entry_id)

    try:
        # Get entry data
        entry_data = hass.data[DOMAIN][entry.entry_id]
        registry = entry_data["registry"]

        # Get config values
        broadlink_entity = entry.options.get(CONF_BROADLINK_ENTITY, entry.data.get(CONF_BROADLINK_ENTITY))
        brand = entry.data.get(CONF_BRAND)
        model_pack_id = entry.options.get(CONF_MODEL_PACK, entry.data.get(CONF_MODEL_PACK))

        if not all([broadlink_entity, brand, model_pack_id]):
            _LOGGER.error("Missing required config values")
            return False

        # Load model pack
        pack = registry.get(model_pack_id)
        _LOGGER.debug(
            "Loaded pack: %s (brand: %s, models: %s)",
            model_pack_id,
            brand,
            pack.models,
        )

        # Create provider and engine
        provider = BroadlinkProvider(hass, broadlink_entity)
        engine = create_engine(pack)

        # Test connection
        is_connected = await provider.test_connection()
        if not is_connected:
            _LOGGER.warning(
                "Broadlink remote %s is not available. Climate entity will be created but may not send commands.",
                broadlink_entity,
            )

        # Create climate entity
        climate_entity = AeroStateClimate(hass, entry, pack, provider, engine)

        async_add_entities([climate_entity])

        _LOGGER.debug("AeroState climate entity created successfully")
        return True

    except Exception:
        _LOGGER.exception("Error setting up AeroState climate")
        return False
