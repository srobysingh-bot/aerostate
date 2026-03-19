"""AeroState IR climate control integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import Final

from .const import CONF_BROADLINK_ENTITY, CONF_MODEL_PACK, DOMAIN

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers import entity_registry as er
except ModuleNotFoundError:  # pragma: no cover - enables unit tests without HA runtime
    ConfigEntry = object

    class Platform:
        CLIMATE = "climate"

    class HomeAssistant:
        pass

    class ServiceCall:
        data: dict

    class _EntityRegistryFallback:
        @staticmethod
        def async_get(_hass):
            raise RuntimeError("Home Assistant is required for runtime entity registry access")

    er = _EntityRegistryFallback()

try:
    from .engines import TableEngine
    from .packs.registry import get_registry
    from .providers import BroadlinkProvider
    from .repairs import (
        async_clear_validation_failed,
        async_report_validation_failed,
        async_validate_entry_runtime,
    )
    from .validation import build_safe_validation_states
except ModuleNotFoundError:  # pragma: no cover - enables unit tests without HA runtime
    TableEngine = None
    BroadlinkProvider = None
    get_registry = None

    async def async_validate_entry_runtime(*_args, **_kwargs):
        return None

    def async_clear_validation_failed(*_args, **_kwargs):
        return None

    def async_report_validation_failed(*_args, **_kwargs):
        return None

    def build_safe_validation_states(*_args, **_kwargs):
        return []

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.CLIMATE]
SERVICE_RUN_SELF_TEST: Final = "run_self_test"
EVENT_SELF_TEST_RESULT: Final = "aerostate_self_test_result"
CONFIG_ENTRY_VERSION: Final = 1
CONFIG_ENTRY_MINOR_VERSION: Final = 0


def _resolve_entry_id_from_service(hass: HomeAssistant, call: ServiceCall) -> str | None:
    """Resolve target entry_id from service payload."""
    entry_id = call.data.get("entry_id")
    if isinstance(entry_id, str) and entry_id:
        return entry_id

    entity_id = call.data.get("entity_id")
    if isinstance(entity_id, str) and entity_id:
        entity_registry = er.async_get(hass)
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry and entity_entry.config_entry_id:
            return entity_entry.config_entry_id

    domain_entries = list(hass.data.get(DOMAIN, {}).keys())
    if len(domain_entries) == 1:
        return domain_entries[0]
    return None


async def _async_handle_run_self_test(hass: HomeAssistant, call: ServiceCall) -> None:
    """Run safe service-level transport self-test for an AeroState entry."""
    try:
        profile = str(call.data.get("profile", "basic"))
        if profile not in {"basic", "full"}:
            profile = "basic"

        entry_id = _resolve_entry_id_from_service(hass, call)
        if not entry_id:
            _LOGGER.error("Self-test failed: unable to resolve target config entry")
            hass.bus.async_fire(
                EVENT_SELF_TEST_RESULT,
                {"success": False, "reason": "entry_not_found", "profile": profile},
            )
            return

        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            _LOGGER.error("Self-test failed: config entry %s not found", entry_id)
            hass.bus.async_fire(
                EVENT_SELF_TEST_RESULT,
                {"success": False, "reason": "entry_not_found", "entry_id": entry_id, "profile": profile},
            )
            return

        broadlink_entity = entry.options.get(CONF_BROADLINK_ENTITY, entry.data.get(CONF_BROADLINK_ENTITY))
        pack_id = entry.options.get(CONF_MODEL_PACK, entry.data.get(CONF_MODEL_PACK))
        if not broadlink_entity or not pack_id:
            _LOGGER.error("Self-test failed: missing broadlink entity or pack id")
            hass.bus.async_fire(
                EVENT_SELF_TEST_RESULT,
                {"success": False, "reason": "invalid_entry_config", "entry_id": entry_id, "profile": profile},
            )
            return

        pack = get_registry().get(pack_id)
        provider = BroadlinkProvider(hass, broadlink_entity)
        engine = TableEngine(pack)

        if not await provider.test_connection():
            _LOGGER.warning("Self-test transport unavailable for %s", broadlink_entity)
            hass.bus.async_fire(
                EVENT_SELF_TEST_RESULT,
                {
                    "success": False,
                    "reason": "validation_transport_unavailable",
                    "entry_id": entry_id,
                    "broadlink_entity": broadlink_entity,
                    "profile": profile,
                },
            )
            return

        attempted: list[str] = []
        errors: list[str] = []
        for label, state in build_safe_validation_states(pack, profile):
            try:
                payload = engine.resolve_command(state)
                await provider.send_base64(payload)
                attempted.append(label)
            except Exception as err:
                attempted.append(label)
                errors.append(f"{label}: {err}")
                _LOGGER.warning("Self-test command failed (%s): %s", label, err)
                break

        success = len(errors) == 0

        if DOMAIN in hass.data:
            hass.data.setdefault(DOMAIN, {}).setdefault(entry_id, {})["last_self_test"] = {
                "success": success,
                "entry_id": entry_id,
                "broadlink_entity": broadlink_entity,
                "pack_id": pack_id,
                "profile": profile,
                "attempted": attempted,
                "errors": errors,
            }

        if success:
            async_clear_validation_failed(hass, entry)
        else:
            async_report_validation_failed(hass, entry)

        _LOGGER.info(
            "AeroState self-test summary entry=%s profile=%s success=%s transport=%s attempted_count=%s attempted=%s errors=%s",
            entry_id,
            profile,
            success,
            True,
            len(attempted),
            attempted,
            errors,
        )
        hass.bus.async_fire(
            EVENT_SELF_TEST_RESULT,
            {
                "success": success,
                "entry_id": entry_id,
                "broadlink_entity": broadlink_entity,
                "pack_id": pack_id,
                "profile": profile,
                "attempted": attempted,
                "errors": errors,
            },
        )
    except Exception:
        _LOGGER.exception("Unexpected error while running AeroState self-test")
        hass.bus.async_fire(EVENT_SELF_TEST_RESULT, {"success": False, "reason": "unexpected_error"})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the AeroState integration from YAML config (not used if config_flow).

    Args:
        hass: Home Assistant instance
        config: Configuration dictionary

    Returns:
        True if setup successful
    """
    # Ensure data storage exists
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if not hass.services.has_service(DOMAIN, SERVICE_RUN_SELF_TEST):
        async def _async_run_self_test(call: ServiceCall) -> None:
            await _async_handle_run_self_test(hass, call)

        hass.services.async_register(DOMAIN, SERVICE_RUN_SELF_TEST, _async_run_self_test)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AeroState from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if setup successful
    """
    _LOGGER.debug("Setting up AeroState config entry: %s", entry.entry_id)

    # Ensure data storage exists
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    entry_data: dict = {}

    try:
        # Load pack registry
        registry = get_registry()
        entry_data["registry"] = registry
        _LOGGER.debug("Pack registry initialized with %d packs", len(registry.list_all()))

        # Store entry data
        hass.data[DOMAIN][entry.entry_id] = entry_data

        # Forward to climate platform
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Validate runtime dependencies and raise repair issues if needed.
        async_validate_entry_runtime(hass, entry)

        _LOGGER.debug("AeroState setup complete for entry: %s", entry.entry_id)
        return True

    except Exception:
        _LOGGER.exception("Error setting up AeroState")
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if unload successful
    """
    _LOGGER.debug("Unloading AeroState config entry: %s", entry.entry_id)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up entry data
        if DOMAIN in hass.data:
            hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older AeroState config entries to the current version."""
    if entry.version > CONFIG_ENTRY_VERSION:
        _LOGGER.error(
            "Cannot migrate AeroState entry %s from newer version %s.%s",
            entry.entry_id,
            entry.version,
            getattr(entry, "minor_version", 0),
        )
        return False

    current_minor = getattr(entry, "minor_version", 0)
    if entry.version == CONFIG_ENTRY_VERSION and current_minor == CONFIG_ENTRY_MINOR_VERSION:
        return True

    new_data = dict(entry.data)
    new_options = dict(entry.options)

    # Placeholder for future migration logic when pack metadata or options evolve.
    hass.config_entries.async_update_entry(
        entry,
        data=new_data,
        options=new_options,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
    )

    _LOGGER.info(
        "Migrated AeroState entry %s to version %s.%s",
        entry.entry_id,
        CONFIG_ENTRY_VERSION,
        CONFIG_ENTRY_MINOR_VERSION,
    )
    return True
