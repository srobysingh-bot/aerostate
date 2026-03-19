"""Climate entity for AeroState AC control."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
)
from homeassistant.exceptions import HomeAssistantError

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


class AeroStateClimate(ClimateEntity):
    """Climate entity for AeroState AC control."""

    _attr_has_entity_name = True
    _attr_max_temp = 30
    _attr_min_temp = 16

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
        self._attr_swing_mode = (
            pack.capabilities.swing_vertical_modes[0]
            if pack.capabilities.swing_vertical_modes
            else None
        )
        self._attr_swing_horizontal_mode = (
            pack.capabilities.swing_horizontal_modes[0]
            if pack.capabilities.swing_horizontal_modes
            else None
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
        """Keep HVAC mode conservative when linked power sensor indicates off/unavailable."""
        power_state = self._power_sensor_state()
        if power_state is None:
            return
        if power_state in {"unavailable", "unknown"}:
            # Preserve command intent; state can be restored later.
            return
        normalized = power_state.lower()
        if normalized in {"off", "false", "0"}:
            self._attr_hvac_mode = HVACMode.OFF
        elif normalized in {"on", "true", "1"} and self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = self._last_requested_hvac_mode

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

        if self._pack.capabilities.swing_vertical_modes:
            features |= ClimateEntityFeature.SWING_MODE

        if self._pack.capabilities.swing_horizontal_modes:
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE

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
        if self._pack.capabilities.swing_vertical_modes:
            return list(self._pack.capabilities.swing_vertical_modes)
        return None

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return list of available horizontal swing modes."""
        if self._pack.capabilities.swing_horizontal_modes:
            return list(self._pack.capabilities.swing_horizontal_modes)
        return None

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
        """Report availability, honoring linked power sensor availability when configured."""
        power_state = self._power_sensor_state()
        if power_state in {"unavailable", "unknown"}:
            return False
        return True

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode and send command."""
        if hvac_mode not in self.hvac_modes:
            _LOGGER.warning(
                "Rejected hvac mode '%s' for pack %s. Supported modes: %s",
                hvac_mode,
                self._pack.pack_id,
                [mode.value for mode in self.hvac_modes],
            )
            raise HomeAssistantError(f"HVAC mode '{hvac_mode}' is not supported by selected pack")

        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._last_requested_hvac_mode = hvac_mode
        try:
            await self._apply_state()
        except HomeAssistantError:
            self._attr_hvac_mode = old_mode
            self.async_write_ha_state()
            raise

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature and send command."""
        old_temp = self._attr_target_temperature
        if ATTR_TEMPERATURE in kwargs:
            requested = int(round(float(kwargs[ATTR_TEMPERATURE])))
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
        try:
            await self._apply_state()
        except HomeAssistantError:
            self._attr_target_temperature = old_temp
            self.async_write_ha_state()
            raise

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode and send command."""
        if fan_mode not in self._pack.capabilities.fan_modes:
            _LOGGER.warning(
                "Rejected fan mode '%s' for pack %s. Supported fan modes: %s",
                fan_mode,
                self._pack.pack_id,
                self._pack.capabilities.fan_modes,
            )
            raise HomeAssistantError(f"Fan mode '{fan_mode}' is not supported by selected pack")

        old_mode = self._attr_fan_mode
        self._attr_fan_mode = fan_mode
        try:
            await self._apply_state()
        except HomeAssistantError:
            self._attr_fan_mode = old_mode
            self.async_write_ha_state()
            raise

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set vertical swing and send command."""
        if swing_mode not in self._pack.capabilities.swing_vertical_modes:
            _LOGGER.warning(
                "Rejected vertical swing mode '%s' for pack %s. Supported vertical swing modes: %s",
                swing_mode,
                self._pack.pack_id,
                self._pack.capabilities.swing_vertical_modes,
            )
            raise HomeAssistantError(
                f"Vertical swing mode '{swing_mode}' is not supported by selected pack"
            )

        old_mode = self._attr_swing_mode
        self._attr_swing_mode = swing_mode
        try:
            await self._apply_state()
        except HomeAssistantError:
            self._attr_swing_mode = old_mode
            self.async_write_ha_state()
            raise

    async def async_set_swing_horizontal_mode(
        self, swing_horizontal_mode: str
    ) -> None:
        """Set horizontal swing and send command."""
        if swing_horizontal_mode not in self._pack.capabilities.swing_horizontal_modes:
            _LOGGER.warning(
                "Rejected horizontal swing mode '%s' for pack %s. Supported horizontal swing modes: %s",
                swing_horizontal_mode,
                self._pack.pack_id,
                self._pack.capabilities.swing_horizontal_modes,
            )
            raise HomeAssistantError(
                f"Horizontal swing mode '{swing_horizontal_mode}' is not supported by selected pack"
            )

        old_mode = self._attr_swing_horizontal_mode
        self._attr_swing_horizontal_mode = swing_horizontal_mode
        try:
            await self._apply_state()
        except HomeAssistantError:
            self._attr_swing_horizontal_mode = old_mode
            self.async_write_ha_state()
            raise

    async def async_turn_on(self) -> None:
        """Turn on (set to last hvac_mode or cool)."""
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = self._last_requested_hvac_mode

        await self._apply_state()

    async def async_turn_off(self) -> None:
        """Turn off."""
        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = HVACMode.OFF
        try:
            await self._apply_state()
        except HomeAssistantError:
            self._attr_hvac_mode = old_mode
            self.async_write_ha_state()
            raise

    async def _apply_state(self) -> None:
        """Build full state dict, get command, send via provider, update HA state."""
        try:
            self._sync_hvac_from_power_sensor()

            target_temp = max(self._attr_min_temp, min(self._attr_target_temperature, self._attr_max_temp))
            self._attr_target_temperature = target_temp

            # Build state dictionary for engine
            state_dict = {
                "power": self._attr_hvac_mode != HVACMode.OFF,
                "hvac_mode": self._attr_hvac_mode.value if self._attr_hvac_mode != HVACMode.OFF else "off",
                "target_temperature": int(round(self._attr_target_temperature)),
            }

            # Add optional state if supported
            if self._pack.capabilities.fan_modes and self._attr_fan_mode:
                state_dict["fan_mode"] = self._attr_fan_mode
            elif self._pack.capabilities.fan_modes:
                state_dict["fan_mode"] = self._pack.capabilities.fan_modes[0]

            if self._pack.capabilities.swing_vertical_modes and self._attr_swing_mode:
                state_dict["swing_vertical"] = self._attr_swing_mode
            elif self._pack.capabilities.swing_vertical_modes:
                state_dict["swing_vertical"] = self._pack.capabilities.swing_vertical_modes[0]

            if self._pack.capabilities.swing_horizontal_modes and self._attr_swing_horizontal_mode:
                state_dict["swing_horizontal"] = self._attr_swing_horizontal_mode
            elif self._pack.capabilities.swing_horizontal_modes:
                state_dict["swing_horizontal"] = self._pack.capabilities.swing_horizontal_modes[0]

            _LOGGER.debug("Applying state: %s", state_dict)

            # Resolve command
            command = self._engine.resolve_command(state_dict)

            # Send command
            await self._provider.send_base64(command)

            async_clear_command_failure(self._hass, self._entry)

            self._sync_hvac_from_power_sensor()

            # Update Home Assistant state
            self.async_write_ha_state()

            _LOGGER.info(
                "AC command sent successfully for mode %s, temp %s",
                self._attr_hvac_mode,
                self._attr_target_temperature,
            )

        except Exception as err:
            _LOGGER.warning(
                "Command resolution/send failed for pack %s and state %s: %s",
                self._pack.pack_id,
                state_dict if "state_dict" in locals() else {},
                err,
            )
            async_report_command_failure(self._hass, self._entry)
            raise HomeAssistantError(f"Failed to apply AC state: {err}") from err


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
