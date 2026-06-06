"""AeroState IR climate control integration for Home Assistant."""

from __future__ import annotations

import logging
import time
from typing import Final

from .const import (
    CONF_BRAND,
    CONF_BROADLINK_ENTITY,
    CONF_IR_PROVIDER,
    CONF_MODEL_PACK,
    CONF_SELECTED_TUYA_PACK_ID,
    CONF_TUYA_CLOUD_MODEL_PACK,
    CONF_TUYA_DEVICE_NAME,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    DEFAULT_IR_PROVIDER,
    DEFAULT_TUYA_DEVICE_NAME,
    DOMAIN,
    IR_PROVIDER_TUYA,
    IR_PROVIDER_TUYA_CLOUD,
)

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import entity_registry as er
except ModuleNotFoundError:  # pragma: no cover - enables unit tests without HA runtime
    ConfigEntry = object

    class Platform:
        CLIMATE = "climate"

    class HomeAssistant:
        pass

    class ServiceCall:
        data: dict

    class HomeAssistantError(Exception):
        pass

    class _EntityRegistryFallback:
        @staticmethod
        def async_get(_hass):
            raise RuntimeError("Home Assistant is required for runtime entity registry access")

    er = _EntityRegistryFallback()

try:
    from .engines import create_engine
    from .packs.registry import get_registry
    from .providers.ir_manager import create_ir_manager_from_entry
    from .repairs import (
        async_clear_validation_failed,
        async_report_validation_failed,
        async_validate_entry_runtime,
    )
    from .validation import build_safe_validation_states
except ModuleNotFoundError:  # pragma: no cover - enables unit tests without HA runtime
    create_engine = None
    create_ir_manager_from_entry = None
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
SERVICE_LEARN_IR_COMMAND: Final = "learn_ir_command"
SERVICE_EXPORT_TUYA_RAW_CODES: Final = "export_tuya_raw_codes"
SERVICE_TEST_TUYA_PACK: Final = "test_tuya_pack"
SERVICE_CONFIRM_TUYA_PACK: Final = "confirm_tuya_pack"
EVENT_SELF_TEST_RESULT: Final = "aerostate_self_test_result"
TUYA_PACK_TEST_COOLDOWN_SECONDS: Final = 2.0
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


def _build_mode_results_seed(pack: object) -> dict[str, dict[str, object]]:
    """Initialize per-mode self-test result buckets."""
    capabilities = getattr(pack, "capabilities", None)
    modes = [mode for mode in list(getattr(capabilities, "hvac_modes", [])) if mode != "off"]
    seed: dict[str, dict[str, object]] = {
        "off": {"attempted": [], "success_count": 0, "error_count": 0, "errors": [], "status": "not_tested"}
    }
    for mode in modes:
        seed[mode] = {"attempted": [], "success_count": 0, "error_count": 0, "errors": [], "status": "not_tested"}
    return seed


def _finalize_mode_results(mode_results: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Finalize status fields for per-mode self-test result buckets."""
    for result in mode_results.values():
        attempted_count = len(result["attempted"])
        error_count = int(result["error_count"])
        success_count = int(result["success_count"])
        result["attempted_count"] = attempted_count
        if attempted_count == 0:
            result["status"] = "not_tested"
        elif error_count > 0:
            result["status"] = "failed"
        elif success_count == attempted_count:
            result["status"] = "passed"
        else:
            result["status"] = "partial"
    return mode_results


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

        ir_provider = entry.options.get(CONF_IR_PROVIDER, entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER))
        ir_provider = str(ir_provider or DEFAULT_IR_PROVIDER).strip().lower()
        if ir_provider in {IR_PROVIDER_TUYA, IR_PROVIDER_TUYA_CLOUD}:
            if ir_provider == IR_PROVIDER_TUYA_CLOUD:
                from .providers.tuya_cloud_ac import create_tuya_cloud_ac_manager_from_entry

                device_name = entry.options.get(
                    CONF_TUYA_CLOUD_MODEL_PACK,
                    entry.data.get(CONF_TUYA_CLOUD_MODEL_PACK, "tuya_cloud.daikin_ac.v1"),
                )
                tuya_manager = create_tuya_cloud_ac_manager_from_entry(hass, entry)
                transport_name = "tuya_cloud_ac_code_library"
            else:
                from .providers.tuya_ir_manager import create_tuya_ir_manager_from_entry

                device_name = entry.options.get(
                    CONF_TUYA_DEVICE_NAME,
                    entry.data.get(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
                )
                tuya_manager = create_tuya_ir_manager_from_entry(hass, entry)
                transport_name = "tuya_ir_learned_codes"
            if not await tuya_manager.probe_transport():
                hass.bus.async_fire(
                    EVENT_SELF_TEST_RESULT,
                    {
                        "success": False,
                        "reason": "tuya_transport_unavailable",
                        "entry_id": entry_id,
                        "profile": profile,
                    },
                )
                return

            try:
                await tuya_manager.async_send_climate_state({"hvac_mode": "off"})
            except Exception as err:
                async_report_validation_failed(hass, entry)
                hass.bus.async_fire(
                    EVENT_SELF_TEST_RESULT,
                    {
                        "success": False,
                        "entry_id": entry_id,
                        "profile": profile,
                        "transport": transport_name,
                        "error": str(err),
                    },
                )
                return

            async_clear_validation_failed(hass, entry)
            if DOMAIN in hass.data:
                hass.data.setdefault(DOMAIN, {}).setdefault(entry_id, {})["last_self_test"] = {
                    "success": True,
                    "entry_id": entry_id,
                    "device_name": device_name,
                    "profile": profile,
                    "attempted": ["off"],
                    "errors": [],
                    "ir_transport_effective": transport_name,
                }
            hass.bus.async_fire(
                EVENT_SELF_TEST_RESULT,
                {
                    "success": True,
                    "entry_id": entry_id,
                    "device_name": device_name,
                    "profile": profile,
                    "attempted": ["off"],
                    "errors": [],
                    "transport": transport_name,
                },
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

        registry = get_registry()
        pack = registry.get(pack_id)
        engine = create_engine(pack)
        ir_manager = create_ir_manager_from_entry(hass, entry, lg_engine=engine, registry=registry)

        if not await ir_manager.probe_active_transport():
            _LOGGER.warning(
                "Self-test transport probe failed for entry %s (see ir_provider / effective transport)",
                entry_id,
            )
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
        mode_results = _build_mode_results_seed(pack)
        for label, state in build_safe_validation_states(pack, profile):
            mode = str(state.get("hvac_mode", "unknown"))
            bucket = mode_results.setdefault(
                mode,
                {"attempted": [], "success_count": 0, "error_count": 0, "errors": [], "status": "not_tested"},
            )
            bucket["attempted"].append(label)
            try:
                cmds, _ = ir_manager.resolve_to_ir_commands(state)
                await ir_manager.async_send_commands(cmds)
                attempted.append(label)
                bucket["success_count"] = int(bucket["success_count"]) + 1
            except Exception as err:
                attempted.append(label)
                errors.append(f"{label}: {err}")
                bucket["error_count"] = int(bucket["error_count"]) + 1
                bucket["errors"].append(str(err))
                _LOGGER.warning("Self-test command failed (%s): %s", label, err)
                break

        success = len(errors) == 0
        mode_results = _finalize_mode_results(mode_results)

        if DOMAIN in hass.data:
            hass.data.setdefault(DOMAIN, {}).setdefault(entry_id, {})["last_self_test"] = {
                "success": success,
                "entry_id": entry_id,
                "broadlink_entity": broadlink_entity,
                "pack_id": pack_id,
                "profile": profile,
                "attempted": attempted,
                "errors": errors,
                "mode_results": mode_results,
                "ir_transport_effective": ir_manager.effective_ir_mode(),
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
                "mode_results": mode_results,
                "ir_transport_effective": ir_manager.effective_ir_mode(),
            },
        )
    except Exception:
        _LOGGER.exception("Unexpected error while running AeroState self-test")
        hass.bus.async_fire(EVENT_SELF_TEST_RESULT, {"success": False, "reason": "unexpected_error"})


async def _async_handle_learn_ir_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Ask localtuya_rc to learn one command name for a Tuya AeroState entry."""
    entry_id = call.data.get("entry_id")
    command_name = str(call.data.get("command_name", "")).strip()
    device_name = str(call.data.get("device_name", DEFAULT_TUYA_DEVICE_NAME)).strip()
    if not entry_id or not command_name:
        raise HomeAssistantError("entry_id and command_name are required for learn_ir_command")

    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry:
        raise HomeAssistantError(f"Config entry {entry_id} not found")

    ir_provider = entry.options.get(CONF_IR_PROVIDER, entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER))
    ir_provider = str(ir_provider or DEFAULT_IR_PROVIDER).strip().lower()
    if ir_provider != IR_PROVIDER_TUYA:
        raise HomeAssistantError("IR learning is only available for AeroState Tuya IR entries")

    tuya_entity = entry.options.get(CONF_TUYA_IR_ENTITY, entry.data.get(CONF_TUYA_IR_ENTITY))
    if not tuya_entity:
        raise HomeAssistantError("This entry has no Tuya IR entity configured")

    await hass.services.async_call(
        "remote",
        "learn_command",
        {
            "entity_id": tuya_entity,
            "device": device_name,
            "command": command_name,
        },
        blocking=True,
    )
    _LOGGER.info("Learned command '%s' for device '%s'", command_name, device_name)


async def _async_handle_export_tuya_raw_codes(hass: HomeAssistant, call: ServiceCall) -> None:
    """Export learned Tuya raw codes into AeroState's portable code library."""
    from .providers.localtuya_rc_storage import read_learned_codes
    from .providers.tuya_raw_code_library import export_portable_raw_codes

    entry_id = call.data.get("entry_id")
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    default_device_name = DEFAULT_TUYA_DEVICE_NAME
    if entry:
        default_device_name = entry.options.get(
            CONF_TUYA_DEVICE_NAME,
            entry.data.get(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
        )

    device_name = str(call.data.get("device_name", default_device_name)).strip()
    pack_id = str(call.data.get("pack_id", "")).strip() or None
    title = str(call.data.get("title", "")).strip() or None
    destination = str(call.data.get("destination", "user_library")).strip()
    destination = "bundled" if destination == "integration_bundle" else "user"
    codes = read_learned_codes(hass, device_name)
    if not codes:
        raise HomeAssistantError(f"No Tuya raw codes found for device name '{device_name}'")

    try:
        path = export_portable_raw_codes(
            hass,
            device_name=device_name,
            commands=codes,
            pack_id=pack_id,
            title=title,
            destination=destination,
        )
    except Exception as err:
        raise HomeAssistantError(f"Failed to export Tuya raw codes: {err}") from err

    _LOGGER.info("Exported AeroState Tuya raw code pack to %s", path)


def _require_daikin_tuya_entry(hass: HomeAssistant, call: ServiceCall):
    """Resolve and validate the target local Daikin Tuya config entry."""
    entry_id = _resolve_entry_id_from_service(hass, call)
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if not entry:
        raise HomeAssistantError("AeroState config entry not found")
    provider = str(
        entry.options.get(CONF_IR_PROVIDER, entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER))
        or DEFAULT_IR_PROVIDER
    ).strip().lower()
    if provider != IR_PROVIDER_TUYA:
        raise HomeAssistantError("Daikin Tuya pack services require the local Tuya IR provider")
    configured_brand = str(
        entry.options.get(CONF_BRAND, entry.data.get(CONF_BRAND, "")) or ""
    ).strip().lower()
    if not configured_brand:
        current_pack_id = entry.options.get(
            CONF_TUYA_MODEL_PACK,
            entry.data.get(CONF_TUYA_MODEL_PACK),
        )
        if current_pack_id:
            try:
                from .packs.tuya.registry import get_tuya_pack

                configured_brand = str(get_tuya_pack(str(current_pack_id)).brand).strip().lower()
            except Exception:
                configured_brand = ""
    if configured_brand != "daikin":
        raise HomeAssistantError("Daikin Tuya pack services cannot be used by an LG or non-Daikin entry")
    return entry


async def _async_handle_test_tuya_pack(hass: HomeAssistant, call: ServiceCall) -> None:
    """Send exactly one command from one local Daikin Tuya pack."""
    from .packs.tuya.daikin.loader import load_daikin_tuya_pack
    from .providers.tuya_ir_manager import TuyaIRManager

    entry = _require_daikin_tuya_entry(hass, call)
    brand = str(call.data.get("brand", "")).strip().lower()
    pack_id = str(call.data.get("pack_id", "")).strip()
    command = str(call.data.get("command", "")).strip()
    if brand != "daikin" or not pack_id or not command:
        raise HomeAssistantError("brand=daikin, pack_id, and command are required")

    pack = load_daikin_tuya_pack(pack_id)
    if pack.resolve_by_label(command) is None:
        raise HomeAssistantError(f"Command '{command}' is not available in pack '{pack_id}'")

    cooldowns = hass.data.setdefault(DOMAIN, {}).setdefault("_tuya_pack_test_cooldowns", {})
    cooldown_key = entry.entry_id
    now = time.monotonic()
    if now - float(cooldowns.get(cooldown_key, 0.0)) < TUYA_PACK_TEST_COOLDOWN_SECONDS:
        raise HomeAssistantError("Wait two seconds before testing another Daikin Tuya command")

    remote_entity = entry.options.get(CONF_TUYA_IR_ENTITY, entry.data.get(CONF_TUYA_IR_ENTITY))
    device_name = entry.options.get(
        CONF_TUYA_DEVICE_NAME,
        entry.data.get(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
    )
    if not remote_entity:
        raise HomeAssistantError("This entry has no Tuya IR remote entity configured")
    manager = TuyaIRManager(hass, str(remote_entity), str(device_name), pack_id=pack_id)
    await manager.async_test_pack_command(command)
    cooldowns[cooldown_key] = now


async def _async_handle_confirm_tuya_pack(hass: HomeAssistant, call: ServiceCall) -> None:
    """Persist the manually confirmed local Daikin Tuya pack."""
    from .packs.tuya.daikin.loader import load_daikin_tuya_pack

    entry = _require_daikin_tuya_entry(hass, call)
    brand = str(call.data.get("brand", "")).strip().lower()
    pack_id = str(call.data.get("pack_id", "")).strip()
    if brand != "daikin" or not pack_id:
        raise HomeAssistantError("brand=daikin and pack_id are required")
    load_daikin_tuya_pack(pack_id)

    new_data = dict(entry.data)
    new_options = dict(entry.options)
    new_data[CONF_BRAND] = "Daikin"
    new_options[CONF_SELECTED_TUYA_PACK_ID] = pack_id
    new_options[CONF_TUYA_MODEL_PACK] = pack_id
    hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
    await hass.config_entries.async_reload(entry.entry_id)
    _LOGGER.info(
        "AeroState: provider=tuya_local brand=Daikin pack_id=%s command=confirm "
        "mode=runtime cloud_disabled_at_runtime=True",
        pack_id,
    )


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

    if not hass.services.has_service(DOMAIN, SERVICE_LEARN_IR_COMMAND):
        async def _async_learn_ir_command(call: ServiceCall) -> None:
            await _async_handle_learn_ir_command(hass, call)

        hass.services.async_register(DOMAIN, SERVICE_LEARN_IR_COMMAND, _async_learn_ir_command)

    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_TUYA_RAW_CODES):
        async def _async_export_tuya_raw_codes(call: ServiceCall) -> None:
            await _async_handle_export_tuya_raw_codes(hass, call)

        hass.services.async_register(DOMAIN, SERVICE_EXPORT_TUYA_RAW_CODES, _async_export_tuya_raw_codes)

    if not hass.services.has_service(DOMAIN, SERVICE_TEST_TUYA_PACK):
        async def _async_test_tuya_pack(call: ServiceCall) -> None:
            await _async_handle_test_tuya_pack(hass, call)

        hass.services.async_register(DOMAIN, SERVICE_TEST_TUYA_PACK, _async_test_tuya_pack)

    if not hass.services.has_service(DOMAIN, SERVICE_CONFIRM_TUYA_PACK):
        async def _async_confirm_tuya_pack(call: ServiceCall) -> None:
            await _async_handle_confirm_tuya_pack(hass, call)

        hass.services.async_register(DOMAIN, SERVICE_CONFIRM_TUYA_PACK, _async_confirm_tuya_pack)

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
