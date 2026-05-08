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
    CONF_TUYA_HOST,
    CONF_TUYA_IR_DP,
    CONF_TUYA_IR_SEND_BLOCKING,
    CONF_TUYA_LOCAL_DEVICE_ID,
    CONF_TUYA_LOCAL_KEY,
    CONF_TUYA_MODEL_PACK,
    DEFAULT_IR_PROVIDER,
    DEFAULT_TUYA_IR_DP,
    DOMAIN,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
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
            self._ir_provider = provider if provider in {IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA} else IR_PROVIDER_BROADLINK
            self._selected_ir_provider = self._ir_provider
            if self._ir_provider == IR_PROVIDER_TUYA:
                return await self.async_step_tuya_device()
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
                            selector.SelectOptionDict(value=IR_PROVIDER_TUYA, label="Tuya IR (LocalTuya DP-201)"),
                        ],
                        mode="list",
                    ),
                ),
            }
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
        from .providers.tuya_ir_transport import TuyaIRTransport

        errors: dict[str, str] = {}
        tuya_pack_options = get_tuya_pack_options_for_ui()

        if not tuya_pack_options:
            return self.async_abort(reason="no_tuya_packs_available")

        default_pack = tuya_pack_options[0]["value"] if tuya_pack_options else ""

        schema = vol.Schema(
            {
                vol.Required(CONF_TUYA_LOCAL_DEVICE_ID): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Required(CONF_TUYA_LOCAL_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
                ),
                vol.Required(CONF_TUYA_HOST): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                ),
                vol.Optional(CONF_TUYA_IR_DP, default=str(DEFAULT_TUYA_IR_DP)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=999, mode="box"),
                ),
                vol.Required(CONF_TUYA_MODEL_PACK, default=default_pack): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=p["value"], label=p["label"])
                            for p in tuya_pack_options
                        ],
                        mode="list",
                    ),
                ),
                vol.Optional(CONF_TUYA_IR_SEND_BLOCKING, default=True): selector.BooleanSelector(),
            },
        )

        if user_input is not None:
            transport = TuyaIRTransport(
                hass=self.hass,
                device_id=str(user_input.get(CONF_TUYA_LOCAL_DEVICE_ID, "")),
                local_key=str(user_input.get(CONF_TUYA_LOCAL_KEY, "")),
                host=str(user_input.get(CONF_TUYA_HOST, "")),
                dp=int(user_input.get(CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP)),
                send_blocking=bool(user_input.get(CONF_TUYA_IR_SEND_BLOCKING, True)),
            )
            if not await transport.probe_transport():
                errors["base"] = "tuya_set_dp_not_available"
            else:
                selected_pack_id = str(user_input.get(CONF_TUYA_MODEL_PACK, ""))
                try:
                    get_tuya_pack(selected_pack_id)
                except KeyError:
                    errors["base"] = "tuya_pack_not_found"

            if not errors:
                self._tuya_data = dict(user_input)
                self._tuya_data[CONF_TUYA_IR_DP] = int(
                    self._tuya_data.get(CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP),
                )
                self._selected_ir_provider = IR_PROVIDER_TUYA
                return await self.async_step_tuya_confirm()

        return self.async_show_form(
            step_id="tuya_device",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "dp_hint": "Default is 201. Only change if your Tuya IR blaster uses a different DP for IR send.",
                "service_hint": "Requires LocalTuya integration with localtuya.set_dp service.",
            },
        )

    async def async_step_tuya_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Confirm Tuya setup and create the entry."""
        from .packs.tuya.registry import get_tuya_pack

        if user_input is not None:
            pack_id = str(self._tuya_data.get(CONF_TUYA_MODEL_PACK, ""))
            device_id = str(self._tuya_data.get(CONF_TUYA_LOCAL_DEVICE_ID, ""))
            unique_id = f"tuya::{device_id}::{pack_id}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            try:
                pack = get_tuya_pack(pack_id)
                title = f"{pack.models[0] if pack.models else pack_id} (Tuya IR)"
            except KeyError:
                title = f"AeroState Tuya IR - {pack_id}"
            return self.async_create_entry(
                title=title,
                data={
                    **self._tuya_data,
                    CONF_IR_PROVIDER: IR_PROVIDER_TUYA,
                },
            )

        pack_id = str(self._tuya_data.get(CONF_TUYA_MODEL_PACK, ""))
        device_id = str(self._tuya_data.get(CONF_TUYA_LOCAL_DEVICE_ID, ""))
        host = str(self._tuya_data.get(CONF_TUYA_HOST, ""))
        device_id_short = device_id[:8] + "..." if len(device_id) > 8 else device_id

        try:
            pack = get_tuya_pack(pack_id)
            pack_label = pack.models[0] if pack.models else pack_id
            pack_verified = "Yes" if pack.verified else "No - experimental pack"
            pack_commands = str(len(pack.commands))
        except KeyError:
            pack_label = pack_id
            pack_verified = "Unknown"
            pack_commands = "Unknown"

        return self.async_show_form(
            step_id="tuya_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "device_id_short": device_id_short,
                "host": host,
                "pack_label": pack_label,
                "pack_id": pack_id,
                "pack_verified": pack_verified,
                "pack_commands": pack_commands,
                "dp": str(self._tuya_data.get(CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP)),
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
