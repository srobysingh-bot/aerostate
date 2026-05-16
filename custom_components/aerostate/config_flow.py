"""Configuration flow for AeroState integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AREA,
    CONF_BRAND,
    CONF_BROADLINK_ENTITY,
    CONF_HUM_SENSOR,
    CONF_IR_PROVIDER,
    CONF_MODEL_PACK,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_TUYA_CLOUD_ACCESS_ID,
    CONF_TUYA_CLOUD_ACCESS_SECRET,
    CONF_TUYA_CLOUD_ENDPOINT,
    CONF_TUYA_CLOUD_MODEL_PACK,
    CONF_TUYA_DEVICE_NAME,
    CONF_TUYA_INFRARED_ID,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_MODEL_PACK,
    CONF_TUYA_REMOTE_ID,
    DEFAULT_IR_PROVIDER,
    DEFAULT_TUYA_CLOUD_ENDPOINT,
    DEFAULT_TUYA_DEVICE_NAME,
    DOMAIN,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
    IR_PROVIDER_TUYA_CLOUD,
)
from .engines import create_engine
from .flow_helpers import (
    build_entry_title,
    build_entry_unique_id,
    describe_pack_limitations,
    has_entry_collision,
)
from .options_flow import AeroStateOptionsFlowHandler
from .packs.registry import get_registry
from .packs.truth import build_mode_truth
from .providers.broadlink import BroadlinkProvider
from .validation import build_safe_validation_states

_LOGGER: logging.Logger = logging.getLogger(__name__)


class AeroStateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for AeroState."""

    VERSION = 1
    MINOR_VERSION = 0

    def __init__(self) -> None:
        """Initialize config flow."""
        self._selected_brand: str | None = None
        self._selected_pack_id: str | None = None
        self._ir_provider: str = IR_PROVIDER_BROADLINK
        self._selected_ir_provider: str = DEFAULT_IR_PROVIDER
        self._broadlink_entity: str | None = None
        self._sensor_data: dict[str, Any] = {}
        self._tuya_data: dict[str, Any] = {}
        self._tuya_cloud_data: dict[str, Any] = {}
        self._tuya_setup_warning: str = ""
        self._validation_summary: dict[str, Any] = {
            "status": "not_run",
            "transport_ok": False,
            "set_available": False,
            "supported_modes": [],
            "mode_truth": {},
            "attempted": [],
            "error": "",
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: choose IR provider and branch to the provider-specific path."""
        if user_input is not None:
            provider = str(user_input.get(CONF_IR_PROVIDER, IR_PROVIDER_BROADLINK)).strip().lower()
            self._ir_provider = provider if provider in {IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA, IR_PROVIDER_TUYA_CLOUD} else IR_PROVIDER_BROADLINK
            self._selected_ir_provider = self._ir_provider
            if self._ir_provider == IR_PROVIDER_TUYA:
                return await self.async_step_tuya_device()
            if self._ir_provider == IR_PROVIDER_TUYA_CLOUD:
                return await self.async_step_tuya_cloud_device()
            return await self.async_step_broadlink_remote()

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
        )

    @staticmethod
    def _user_schema() -> vol.Schema:
        """Build the first-step provider/controller schema."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_IR_PROVIDER,
                    default=IR_PROVIDER_BROADLINK,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=IR_PROVIDER_BROADLINK, label="Broadlink IR (default)"),
                            selector.SelectOptionDict(value=IR_PROVIDER_TUYA, label="Tuya IR Device (LG/Daikin local packs)"),
                        ],
                        mode="list",
                    ),
                ),
            }
        )

    async def async_step_tuya_cloud_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Collect Tuya Cloud code-library details for Daikin AC control."""
        from .packs.tuya_cloud.registry import get_tuya_cloud_pack_options_for_ui

        errors: dict[str, str] = {}
        pack_options = get_tuya_cloud_pack_options_for_ui()
        default_pack = pack_options[0]["value"] if pack_options else ""

        schema = vol.Schema(
            {
                vol.Required(CONF_TUYA_CLOUD_ENDPOINT, default=DEFAULT_TUYA_CLOUD_ENDPOINT): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Required(CONF_TUYA_CLOUD_ACCESS_ID): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Required(CONF_TUYA_CLOUD_ACCESS_SECRET): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
                ),
                vol.Required(CONF_TUYA_INFRARED_ID): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Required(CONF_TUYA_REMOTE_ID): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Required(CONF_TUYA_CLOUD_MODEL_PACK, default=default_pack): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=pack_options),
                ),
            }
        )

        if user_input is not None:
            cleaned = {
                key: str(user_input.get(key, "")).strip()
                for key in (
                    CONF_TUYA_CLOUD_ENDPOINT,
                    CONF_TUYA_CLOUD_ACCESS_ID,
                    CONF_TUYA_CLOUD_ACCESS_SECRET,
                    CONF_TUYA_INFRARED_ID,
                    CONF_TUYA_REMOTE_ID,
                    CONF_TUYA_CLOUD_MODEL_PACK,
                )
            }
            if not cleaned[CONF_TUYA_CLOUD_ENDPOINT].startswith(("http://", "https://")):
                errors["base"] = "tuya_cloud_endpoint_invalid"
            elif not all(cleaned.values()):
                errors["base"] = "tuya_cloud_required_fields_missing"
            else:
                self._tuya_cloud_data = cleaned
                self._selected_ir_provider = IR_PROVIDER_TUYA_CLOUD
                return await self.async_step_tuya_cloud_confirm()

        return self.async_show_form(
            step_id="tuya_cloud_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "setup_hint": (
                    "Create or select the Daikin virtual remote in Tuya first, then paste "
                    "the Tuya OpenAPI endpoint, Access ID, Access Secret, infrared_id, "
                    "and AC remote_id here. This route does not use learned raw codes."
                ),
            },
        )

    async def async_step_tuya_cloud_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Confirm Tuya Cloud code-library setup and create the entry."""
        from .packs.tuya_cloud.registry import get_tuya_cloud_pack

        pack_id = self._tuya_cloud_data.get(CONF_TUYA_CLOUD_MODEL_PACK)
        try:
            pack = get_tuya_cloud_pack(pack_id)
        except KeyError:
            return self.async_abort(reason="tuya_cloud_pack_not_found")

        if user_input is not None:
            infrared_id = str(self._tuya_cloud_data.get(CONF_TUYA_INFRARED_ID, ""))
            remote_id = str(self._tuya_cloud_data.get(CONF_TUYA_REMOTE_ID, ""))
            unique_id = f"tuya_cloud::{infrared_id}::{remote_id}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"AeroState Tuya Cloud - {pack.brand}",
                data={
                    **self._tuya_cloud_data,
                    CONF_IR_PROVIDER: IR_PROVIDER_TUYA_CLOUD,
                },
            )

        return self.async_show_form(
            step_id="tuya_cloud_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "endpoint": self._tuya_cloud_data.get(CONF_TUYA_CLOUD_ENDPOINT, ""),
                "infrared_id": self._tuya_cloud_data.get(CONF_TUYA_INFRARED_ID, ""),
                "remote_id": self._tuya_cloud_data.get(CONF_TUYA_REMOTE_ID, ""),
                "pack_id": pack.pack_id,
                "modes": ", ".join(pack.capabilities.hvac_modes),
                "fan_modes": ", ".join(pack.capabilities.fan_modes),
                "temperature_range": f"{pack.min_temperature}-{pack.max_temperature}",
            },
        )

    async def async_step_broadlink_remote(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Broadlink path Step 2: choose Broadlink remote entity."""
        if user_input is not None:
            self._broadlink_entity = user_input[CONF_BROADLINK_ENTITY]
            return await self.async_step_brand()

        if not self.hass.states.async_entity_ids("remote"):
            return self.async_abort(reason="no_remote_entities")

        return self.async_show_form(
            step_id="broadlink_remote",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BROADLINK_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="remote"),
                    ),
                },
            ),
        )

    async def async_step_tuya_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Collect Tuya IR blaster connection details."""
        from .packs.tuya.registry import get_tuya_pack, get_tuya_pack_options_for_ui
        from .providers.learned_code_resolver import get_coverage_summary
        from .providers.localtuya_rc_storage import list_available_code_sources, read_learned_codes

        errors: dict[str, str] = {}
        tuya_pack_options = get_tuya_pack_options_for_ui()
        code_sources = list_available_code_sources(self.hass)

        if not tuya_pack_options:
            return self.async_abort(reason="no_tuya_packs_available")

        default_pack = tuya_pack_options[0]["value"] if tuya_pack_options else ""
        for option in tuya_pack_options:
            if option["value"] == "daikin.brc4c158.localtuya_rc.smartir1109.v1":
                default_pack = option["value"]
                break
        default_code_source = ""
        if len(code_sources) == 1:
            default_code_source = str(code_sources[0].get("name", "")).strip()

        schema = vol.Schema(
            {
                vol.Required(CONF_TUYA_IR_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="remote"),
                ),
                vol.Optional(CONF_TUYA_DEVICE_NAME, default=default_code_source): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Required(CONF_TUYA_MODEL_PACK, default=default_pack): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=tuya_pack_options),
                ),
            },
        )

        if user_input is not None:
            remote_entity = user_input.get(CONF_TUYA_IR_ENTITY)
            selected_pack_id = str(user_input.get(CONF_TUYA_MODEL_PACK, default_pack)).strip()
            try:
                selected_pack = get_tuya_pack(selected_pack_id)
            except Exception:
                selected_pack = None
                errors["base"] = "tuya_pack_not_found"

            state = self.hass.states.get(remote_entity)
            if state is None and not errors:
                errors["base"] = "tuya_remote_entity_not_found"
            elif state is not None and state.state in ("unavailable", "unknown") and not errors:
                errors["base"] = "tuya_remote_entity_unavailable"
            elif selected_pack is not None and getattr(selected_pack, "requires_learned_codes", True):
                device_name = str(user_input.get(CONF_TUYA_DEVICE_NAME, "")).strip()
                codes = read_learned_codes(self.hass, device_name)
                if not codes:
                    self._tuya_setup_warning = "No raw-code source found yet. Setup can continue, but commands will not send until a portable pack is copied or localtuya_rc codes are learned."
                elif "power_off" not in codes:
                    self._tuya_setup_warning = "Raw-code source found, but it is missing power_off. Setup can continue, but power-off will not work until that command is added."
                else:
                    self._tuya_setup_warning = ""
                    get_coverage_summary(codes)
            elif selected_pack is not None:
                self._tuya_setup_warning = "Pre-generated Tuya code pack selected. No learning required."

            if not errors:
                self._tuya_data = dict(user_input)
                self._tuya_data[CONF_TUYA_DEVICE_NAME] = str(
                    self._tuya_data.get(CONF_TUYA_DEVICE_NAME, default_code_source),
                ).strip()
                self._tuya_data[CONF_TUYA_MODEL_PACK] = selected_pack_id
                self._selected_ir_provider = IR_PROVIDER_TUYA
                return await self.async_step_tuya_confirm()

        return self.async_show_form(
            step_id="tuya_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "code_source_hint": (
                    "For Daikin BRC4C158, select the built-in "
                    "daikin.brc4c158.localtuya_rc.smartir1109.v1 pack. It contains generated "
                    "Daikin BRC4CXXX raw commands for cool-only operation and uses the selected "
                    "Tuya IR remote entity directly. It does not need Tuya Cloud, Access ID, "
                    "infrared_id, remote_id, learned commands, or a raw-code source name. "
                    "Learned LG-style packs can still use portable raw-code JSON files in "
                    "/config/aerostate_tuya_raw_codes/ or localtuya_rc storage/backups."
                ),
            },
        )

    async def async_step_tuya_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Confirm Tuya setup and create the entry."""
        from .packs.tuya.registry import get_tuya_pack
        from .providers.learned_code_resolver import get_coverage_summary
        from .providers.localtuya_rc_storage import read_learned_codes

        pack_id = str(self._tuya_data.get(CONF_TUYA_MODEL_PACK, "")).strip()
        try:
            selected_pack = get_tuya_pack(pack_id)
        except Exception:
            return self.async_abort(reason="tuya_pack_not_found")

        if user_input is not None:
            remote_entity = str(self._tuya_data.get(CONF_TUYA_IR_ENTITY, ""))
            device_name = str(self._tuya_data.get(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME))
            unique_id = f"tuya::{remote_entity}::{pack_id or device_name or 'auto'}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            title_suffix = selected_pack.models[0] if selected_pack.models else (device_name or remote_entity or "auto")
            return self.async_create_entry(
                title=f"AeroState Tuya IR - {title_suffix}",
                data={
                    **self._tuya_data,
                    CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
                },
            )

        device_name = str(self._tuya_data.get(CONF_TUYA_DEVICE_NAME, ""))
        if not getattr(selected_pack, "requires_learned_codes", True):
            model_pack = selected_pack.to_model_pack()
            fan_codes = [
                cmd
                for cmd in selected_pack.commands
                if (
                    (cmd.hvac_mode == "fan_only" or cmd.label.startswith("fan_speed_"))
                    and not cmd.turn_on_variant
                )
            ]
            return self.async_show_form(
                step_id="tuya_confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "device_name": selected_pack.models[0] if selected_pack.models else selected_pack.pack_id,
                    "code_source_status": self._tuya_setup_warning or "Pre-generated pack ready",
                    "total_codes": str(len(selected_pack.commands)),
                    "cool_temps_auto": f"{selected_pack.min_temperature}-{selected_pack.max_temperature}",
                    "cool_temps_fan": f"{selected_pack.min_temperature}-{selected_pack.max_temperature}",
                    "fan_codes": str(len(fan_codes)),
                    "has_power_off": "Yes",
                    "heat_supported": "Yes" if "heat" in model_pack.capabilities.hvac_modes else "No",
                    "dry_supported": "Yes" if "dry" in model_pack.capabilities.hvac_modes else "No",
                    "gaps": "none",
                },
            )

        codes = read_learned_codes(self.hass, device_name)
        coverage = get_coverage_summary(codes)
        gaps = coverage["gaps"]
        gaps_text = ", ".join(gaps[:3]) if gaps else "none"
        if len(gaps) > 3:
            gaps_text += f" (+{len(gaps) - 3} more)"

        return self.async_show_form(
            step_id="tuya_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_name": device_name or "Auto-detect",
                "code_source_status": self._tuya_setup_warning or "Ready",
                "total_codes": str(coverage["total_learned"]),
                "cool_temps_auto": str(coverage["cool_temps_auto_fan"]),
                "cool_temps_fan": str(coverage["cool_temps_with_specific_fan"]),
                "fan_codes": str(len(coverage["fan_only_codes"])),
                "has_power_off": "Yes" if coverage["has_power_off"] else "No",
                "heat_supported": "No - not learned",
                "dry_supported": "No - not learned",
                "gaps": gaps_text,
            },
        )

    async def async_step_brand(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2: choose brand."""
        if user_input is not None:
            self._selected_brand = user_input[CONF_BRAND]
            return await self.async_step_model()

        registry = get_registry()
        brands = sorted({pack.brand for pack in registry.list_all()})
        if not brands:
            return self.async_abort(reason="no_packs_available")

        return self.async_show_form(
            step_id="brand",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BRAND): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=brand, label=brand)
                                for brand in brands
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3: choose model pack."""
        if user_input is not None:
            self._selected_pack_id = user_input[CONF_MODEL_PACK]
            return await self.async_step_sensors()

        registry = get_registry()
        packs = sorted(
            registry.list_brand_packs(self._selected_brand or ""),
            key=lambda p: p.models[0] if p.models else p.pack_id,
        )
        if not packs:
            return self.async_abort(reason="no_packs_for_brand")

        return self.async_show_form(
            step_id="model",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL_PACK): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=pack.pack_id,
                                    label=(
                                        f"{pack.models[0] if pack.models else pack.pack_id} ({pack.pack_id})"
                                        f" - {describe_pack_limitations(pack) or ('Verified pack' if pack.verified else 'Experimental pack')}"
                                    ),
                                )
                                for pack in packs
                            ]
                        )
                    )
                }
            ),
            description_placeholders={
                "pack_notes_hint": "Pack notes and limitations are shown in the next steps.",
            },
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 4: choose optional sensors."""
        if user_input is not None:
            self._sensor_data = user_input
            return await self.async_step_validation()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_TEMP_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_HUM_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["sensor", "switch"])
                    ),
                    vol.Optional(CONF_AREA): str,
                    vol.Optional(CONF_NAME): str,
                }
            ),
        )

    async def async_step_validation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 5: optionally run onboarding validation test commands."""
        if user_input is not None:
            run_validation = user_input.get("run_validation", False)
            if not run_validation:
                self._validation_summary = {
                    "status": "skipped",
                    "transport_ok": False,
                    "set_available": False,
                    "supported_modes": [],
                    "mode_truth": {},
                    "attempted": [],
                    "error": "",
                }
                return await self.async_step_validation_result()

            registry = get_registry()
            try:
                pack = registry.get(self._selected_pack_id or "")
            except Exception:
                self._validation_summary = {
                    "status": "failed",
                    "transport_ok": False,
                    "set_available": False,
                    "supported_modes": [],
                    "mode_truth": {},
                    "attempted": [],
                    "error": "selected_pack_unavailable",
                }
                return await self.async_step_validation_result()
            provider = BroadlinkProvider(self.hass, self._broadlink_entity or "")
            engine = create_engine(pack)

            transport_ok = await provider.test_connection()
            if not transport_ok:
                self._validation_summary = {
                    "status": "failed",
                    "transport_ok": False,
                    "set_available": False,
                    "supported_modes": list(pack.capabilities.hvac_modes),
                    "mode_truth": build_mode_truth(pack),
                    "attempted": [],
                    "error": "validation_transport_unavailable",
                }
                return await self.async_step_validation_result()

            attempted: list[str] = []
            states = build_safe_validation_states(pack, "basic")
            set_available = len(states) > 1
            try:
                for label, test_state in states:
                    attempted.append(label)
                    payload = engine.resolve_command(test_state)
                    if isinstance(payload, list):
                        await provider.send_sequence(
                            [(f"cmd_{idx + 1}", item) for idx, item in enumerate(payload)]
                        )
                    else:
                        await provider.send_base64(payload)
                self._validation_summary = {
                    "status": "passed",
                    "transport_ok": True,
                    "set_available": set_available,
                    "supported_modes": list(pack.capabilities.hvac_modes),
                    "mode_truth": build_mode_truth(pack),
                    "attempted": attempted,
                    "error": "",
                }
                _LOGGER.info(
                    "Validation commands attempted for %s/%s: %s",
                    self._broadlink_entity,
                    self._selected_pack_id,
                    attempted,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Onboarding validation failed for %s/%s after %s: %s",
                    self._broadlink_entity,
                    self._selected_pack_id,
                    attempted,
                    err,
                )
                self._validation_summary = {
                    "status": "failed",
                    "transport_ok": True,
                    "set_available": set_available,
                    "supported_modes": list(pack.capabilities.hvac_modes),
                    "mode_truth": build_mode_truth(pack),
                    "attempted": attempted,
                    "error": "validation_failed",
                }

            return await self.async_step_validation_result()

        return self.async_show_form(
            step_id="validation",
            data_schema=vol.Schema(
                {
                    vol.Optional("run_validation", default=True): bool,
                }
            ),
            description_placeholders={
                "info": "Run safe validation commands now, or skip and continue setup.",
            },
        )

    async def async_step_validation_result(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 6: show friendly validation summary before confirm."""
        if user_input is not None:
            return await self.async_step_confirm()

        summary = self._validation_summary
        attempted = summary.get("attempted", [])
        supported_modes = summary.get("supported_modes", [])
        mode_truth = summary.get("mode_truth", {})
        physically_verified_modes = [
            mode for mode, meta in mode_truth.items() if isinstance(meta, dict) and meta.get("physically_verified")
        ]
        experimental_modes = [
            mode for mode, meta in mode_truth.items() if isinstance(meta, dict) and meta.get("status") == "experimental"
        ]
        try:
            pack = get_registry().get(self._selected_pack_id or "")
        except Exception:
            return self.async_abort(reason="selected_pack_unavailable")
        limitation = describe_pack_limitations(pack)
        return self.async_show_form(
            step_id="validation_result",
            data_schema=vol.Schema({}),
            description_placeholders={
                "status": str(summary.get("status", "not_run")),
                "transport_ok": "yes" if summary.get("transport_ok") else "no",
                "set_available": "yes" if summary.get("set_available") else "no",
                "supported_modes": ", ".join(supported_modes) if supported_modes else "none",
                "physically_verified_modes": ", ".join(physically_verified_modes) if physically_verified_modes else "none",
                "experimental_modes": ", ".join(experimental_modes) if experimental_modes else "none",
                "attempted": ", ".join(attempted) if attempted else "none",
                "error": str(summary.get("error", "")) or "none",
                "pack_notes": pack.notes or "none",
                "pack_limitations": limitation or "none",
            },
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 7: confirm and create entry."""
        registry = get_registry()
        try:
            pack = registry.get(self._selected_pack_id or "")
        except Exception:
            return self.async_abort(reason="selected_pack_unavailable")

        if user_input is not None:
            if has_entry_collision(
                self.hass,
                self._broadlink_entity or "",
                self._selected_pack_id or "",
            ):
                return self.async_abort(reason="already_configured")

            unique_id = build_entry_unique_id(
                self._broadlink_entity or "",
                self._selected_pack_id or "",
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            data = {
                CONF_BROADLINK_ENTITY: self._broadlink_entity,
                CONF_BRAND: self._selected_brand,
                CONF_MODEL_PACK: self._selected_pack_id,
            }
            options = {
                key: value
                for key, value in self._sensor_data.items()
                if key
                in (
                    CONF_TEMP_SENSOR,
                    CONF_HUM_SENSOR,
                    CONF_POWER_SENSOR,
                    CONF_AREA,
                    CONF_NAME,
                )
                and value
            }
            return self.async_create_entry(
                title=build_entry_title(pack, options),
                data=data,
                options=options,
            )

        limitation = describe_pack_limitations(pack)
        placeholders = {
            "broadlink": self._broadlink_entity or "",
            "brand": self._selected_brand or "",
            "model": pack.models[0] if pack.models else "Unknown",
            "pack_id": self._selected_pack_id or "",
            "pack_verified": "yes" if pack.verified else "no",
            "pack_notes": pack.notes or "none",
            "pack_limitations": limitation or "none",
            "temp_sensor": self._sensor_data.get(CONF_TEMP_SENSOR, "Not configured"),
            "humidity_sensor": self._sensor_data.get(CONF_HUM_SENSOR, "Not configured"),
            "power_sensor": self._sensor_data.get(CONF_POWER_SENSOR, "Not configured"),
            "area": self._sensor_data.get(CONF_AREA, "Not configured"),
            "name": self._sensor_data.get(CONF_NAME, "Not configured"),
        }
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AeroStateOptionsFlowHandler:
        """Return options flow handler."""
        return AeroStateOptionsFlowHandler(config_entry)
