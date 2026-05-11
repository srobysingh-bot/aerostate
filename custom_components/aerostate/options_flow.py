"""Options flow for AeroState integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
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
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
    IR_PROVIDER_TUYA_CLOUD,
)
from .flow_helpers import (
    build_entry_title,
    describe_pack_limitations,
    has_entry_collision,
)
from .packs.registry import get_registry
from .packs.tuya.registry import get_tuya_pack_options_for_ui
from .packs.tuya_cloud.registry import get_tuya_cloud_pack_options_for_ui


class AeroStateOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for AeroState config entries."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    @staticmethod
    def _schema(
        config_entry: config_entries.ConfigEntry,
        pack_options: list[selector.SelectOptionDict],
        tuya_pack_options: list[selector.SelectOptionDict],
        tuya_cloud_pack_options: list[selector.SelectOptionDict],
    ) -> vol.Schema:
        """Build options form schema."""
        ir_default = config_entry.options.get(CONF_IR_PROVIDER, config_entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER))
        tuya_entity_default = config_entry.options.get(CONF_TUYA_IR_ENTITY, config_entry.data.get(CONF_TUYA_IR_ENTITY))
        tuya_device_default = config_entry.options.get(
            CONF_TUYA_DEVICE_NAME,
            config_entry.data.get(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
        )
        tuya_pack_default = config_entry.options.get(CONF_TUYA_MODEL_PACK, config_entry.data.get(CONF_TUYA_MODEL_PACK))
        tuya_cloud_endpoint_default = config_entry.options.get(
            CONF_TUYA_CLOUD_ENDPOINT,
            config_entry.data.get(CONF_TUYA_CLOUD_ENDPOINT, DEFAULT_TUYA_CLOUD_ENDPOINT),
        )
        tuya_cloud_pack_default = config_entry.options.get(
            CONF_TUYA_CLOUD_MODEL_PACK,
            config_entry.data.get(CONF_TUYA_CLOUD_MODEL_PACK),
        )

        return vol.Schema(
            {
                vol.Optional(
                    CONF_BROADLINK_ENTITY,
                    default=config_entry.data.get(CONF_BROADLINK_ENTITY),
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="remote")),
                vol.Optional(
                    CONF_MODEL_PACK,
                    default=config_entry.data.get(CONF_MODEL_PACK),
                ): selector.SelectSelector(selector.SelectSelectorConfig(options=pack_options)),
                vol.Required(
                    CONF_IR_PROVIDER,
                    default=ir_default if ir_default else DEFAULT_IR_PROVIDER,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="broadlink", label="Broadlink IR (default)"),
                            selector.SelectOptionDict(value="tuya", label="Tuya IR learned/raw codes"),
                            selector.SelectOptionDict(value="tuya_cloud", label="Tuya Cloud code library (Daikin)"),
                        ]
                    ),
                ),
                vol.Optional(
                    CONF_TUYA_IR_ENTITY,
                    default=tuya_entity_default,
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="remote")),
                vol.Optional(
                    CONF_TUYA_DEVICE_NAME,
                    default=tuya_device_default,
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)),
                vol.Optional(
                    CONF_TUYA_MODEL_PACK,
                    default=tuya_pack_default if tuya_pack_default else "",
                ): selector.SelectSelector(selector.SelectSelectorConfig(options=tuya_pack_options)),
                vol.Optional(
                    CONF_TUYA_CLOUD_ENDPOINT,
                    default=tuya_cloud_endpoint_default,
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)),
                vol.Optional(
                    CONF_TUYA_CLOUD_ACCESS_ID,
                    default=config_entry.options.get(
                        CONF_TUYA_CLOUD_ACCESS_ID,
                        config_entry.data.get(CONF_TUYA_CLOUD_ACCESS_ID, ""),
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)),
                vol.Optional(
                    CONF_TUYA_CLOUD_ACCESS_SECRET,
                    default=config_entry.options.get(
                        CONF_TUYA_CLOUD_ACCESS_SECRET,
                        config_entry.data.get(CONF_TUYA_CLOUD_ACCESS_SECRET, ""),
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
                vol.Optional(
                    CONF_TUYA_INFRARED_ID,
                    default=config_entry.options.get(
                        CONF_TUYA_INFRARED_ID,
                        config_entry.data.get(CONF_TUYA_INFRARED_ID, ""),
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)),
                vol.Optional(
                    CONF_TUYA_REMOTE_ID,
                    default=config_entry.options.get(
                        CONF_TUYA_REMOTE_ID,
                        config_entry.data.get(CONF_TUYA_REMOTE_ID, ""),
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)),
                vol.Optional(
                    CONF_TUYA_CLOUD_MODEL_PACK,
                    default=tuya_cloud_pack_default if tuya_cloud_pack_default else "",
                ): selector.SelectSelector(selector.SelectSelectorConfig(options=tuya_cloud_pack_options)),
                vol.Optional(
                    CONF_TEMP_SENSOR,
                    default=config_entry.options.get(CONF_TEMP_SENSOR),
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_HUM_SENSOR,
                    default=config_entry.options.get(CONF_HUM_SENSOR),
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_POWER_SENSOR,
                    default=config_entry.options.get(CONF_POWER_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "switch"])
                ),
                vol.Optional(
                    CONF_AREA,
                    default=config_entry.options.get(CONF_AREA),
                ): str,
                vol.Optional(
                    CONF_NAME,
                    default=config_entry.options.get(CONF_NAME),
                ): str,
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Edit Broadlink entity, pack, optional sensors, and title."""
        registry = get_registry()
        brand = self._config_entry.data.get(CONF_BRAND, "")
        packs = registry.list_brand_packs(brand)

        pack_options = [
            selector.SelectOptionDict(
                value=pack.pack_id,
                label=(
                    f"{pack.models[0] if pack.models else pack.pack_id} ({pack.pack_id})"
                    f" - {describe_pack_limitations(pack) or ('Verified pack' if pack.verified else 'Experimental pack')}"
                ),
            )
            for pack in packs
        ]

        all_packs = []
        tuya_pack_options: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(value="", label="(none)"),
        ]
        for pack in all_packs:
            tuya_pack_options.append(
                selector.SelectOptionDict(
                    value=pack.pack_id,
                    label=(
                        f"{pack.models[0] if pack.models else pack.pack_id} ({pack.pack_id})"
                        f" — {pack.engine_type}"
                    ),
                ),
            )

        for option in get_tuya_pack_options_for_ui():
            tuya_pack_options.append(
                selector.SelectOptionDict(value=str(option["value"]), label=str(option["label"])),
            )

        tuya_cloud_pack_options: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(value="", label="(none)"),
        ]
        for option in get_tuya_cloud_pack_options_for_ui():
            tuya_cloud_pack_options.append(
                selector.SelectOptionDict(value=str(option["value"]), label=str(option["label"])),
            )

        schema = self._schema(self._config_entry, pack_options, tuya_pack_options, tuya_cloud_pack_options)

        if user_input is not None:
            selected_remote = user_input.get(
                CONF_BROADLINK_ENTITY,
                self._config_entry.data.get(CONF_BROADLINK_ENTITY),
            )
            selected_pack = user_input.get(
                CONF_MODEL_PACK,
                self._config_entry.data.get(CONF_MODEL_PACK),
            )
            sel_ir = str(user_input.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER) or DEFAULT_IR_PROVIDER).strip().lower()
            sel_ir = sel_ir if sel_ir in (IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA, IR_PROVIDER_TUYA_CLOUD) else DEFAULT_IR_PROVIDER

            if sel_ir == IR_PROVIDER_BROADLINK and not selected_remote:
                return self.async_show_form(
                    step_id="init",
                    data_schema=schema,
                    errors={"base": "broadlink_entity_required"},
                )

            if sel_ir == IR_PROVIDER_BROADLINK and has_entry_collision(
                self.hass,
                selected_remote,
                selected_pack,
                current_entry_id=self._config_entry.entry_id,
            ):
                return self.async_show_form(
                    step_id="init",
                    data_schema=schema,
                    errors={"base": "already_configured"},
                )

            new_data = dict(self._config_entry.data)
            new_options = dict(self._config_entry.options)

            if selected_remote:
                new_data[CONF_BROADLINK_ENTITY] = selected_remote

            if sel_ir == IR_PROVIDER_BROADLINK and selected_pack and selected_pack != self._config_entry.data.get(CONF_MODEL_PACK):
                # Keep pack changes explicit by only updating when a new pack is selected.
                new_data[CONF_MODEL_PACK] = selected_pack

            if sel_ir == IR_PROVIDER_TUYA:
                from .packs.tuya.registry import get_tuya_pack

                raw_tuya_pack = user_input.get(
                    CONF_TUYA_MODEL_PACK,
                    self._config_entry.options.get(
                        CONF_TUYA_MODEL_PACK,
                        self._config_entry.data.get(CONF_TUYA_MODEL_PACK),
                    ),
                )
                try:
                    selected_pack_obj = get_tuya_pack(str(raw_tuya_pack)).to_model_pack()
                except Exception:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=schema,
                        errors={"base": "tuya_pack_not_found"},
                    )
            elif sel_ir == IR_PROVIDER_TUYA_CLOUD:
                from .packs.tuya_cloud.registry import get_tuya_cloud_pack

                raw_cloud_pack = user_input.get(
                    CONF_TUYA_CLOUD_MODEL_PACK,
                    self._config_entry.options.get(
                        CONF_TUYA_CLOUD_MODEL_PACK,
                        self._config_entry.data.get(CONF_TUYA_CLOUD_MODEL_PACK),
                    ),
                )
                try:
                    selected_pack_obj = get_tuya_cloud_pack(str(raw_cloud_pack))
                except Exception:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=schema,
                        errors={"base": "tuya_cloud_pack_not_found"},
                    )
            else:
                try:
                    selected_pack_obj = registry.get(new_data.get(CONF_MODEL_PACK))
                except Exception:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=schema,
                        errors={"base": "invalid_model_pack"},
                    )

            new_options[CONF_IR_PROVIDER] = sel_ir

            raw_tuya_entity = user_input.get(CONF_TUYA_IR_ENTITY)
            if isinstance(raw_tuya_entity, str) and raw_tuya_entity.strip():
                new_options[CONF_TUYA_IR_ENTITY] = raw_tuya_entity.strip()
            else:
                new_options.pop(CONF_TUYA_IR_ENTITY, None)

            raw_tuya_device_name = user_input.get(CONF_TUYA_DEVICE_NAME)
            if isinstance(raw_tuya_device_name, str) and raw_tuya_device_name.strip():
                new_options[CONF_TUYA_DEVICE_NAME] = raw_tuya_device_name.strip()
            else:
                new_options.pop(CONF_TUYA_DEVICE_NAME, None)

            raw_tp = user_input.get(CONF_TUYA_MODEL_PACK)
            if isinstance(raw_tp, str) and raw_tp.strip():
                new_options[CONF_TUYA_MODEL_PACK] = raw_tp.strip()
            else:
                new_options.pop(CONF_TUYA_MODEL_PACK, None)

            for cloud_key in (
                CONF_TUYA_CLOUD_ENDPOINT,
                CONF_TUYA_CLOUD_ACCESS_ID,
                CONF_TUYA_CLOUD_ACCESS_SECRET,
                CONF_TUYA_INFRARED_ID,
                CONF_TUYA_REMOTE_ID,
                CONF_TUYA_CLOUD_MODEL_PACK,
            ):
                value = user_input.get(cloud_key)
                if isinstance(value, str) and value.strip():
                    new_options[cloud_key] = value.strip()
                else:
                    new_options.pop(cloud_key, None)

            for sensor_key in (
                CONF_TEMP_SENSOR,
                CONF_HUM_SENSOR,
                CONF_POWER_SENSOR,
                CONF_AREA,
                CONF_NAME,
            ):
                value = user_input.get(sensor_key)
                if value:
                    new_options[sensor_key] = value
                else:
                    new_options.pop(sensor_key, None)

            new_title = build_entry_title(selected_pack_obj, new_options)

            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_data,
                options=new_options,
                title=new_title,
            )
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        current_provider = str(
            self._config_entry.options.get(
                CONF_IR_PROVIDER,
                self._config_entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER),
            )
            or DEFAULT_IR_PROVIDER
        ).strip().lower()
        try:
            if current_provider == IR_PROVIDER_TUYA_CLOUD:
                from .packs.tuya_cloud.registry import get_tuya_cloud_pack

                current_pack = get_tuya_cloud_pack(
                    self._config_entry.options.get(
                        CONF_TUYA_CLOUD_MODEL_PACK,
                        self._config_entry.data.get(CONF_TUYA_CLOUD_MODEL_PACK),
                    )
                )
            elif current_provider == IR_PROVIDER_TUYA:
                from .packs.tuya.registry import get_tuya_pack

                current_pack = get_tuya_pack(
                    self._config_entry.options.get(
                        CONF_TUYA_MODEL_PACK,
                        self._config_entry.data.get(CONF_TUYA_MODEL_PACK),
                    )
                ).to_model_pack()
            else:
                current_pack = registry.get(self._config_entry.data.get(CONF_MODEL_PACK))
        except Exception:
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
                errors={"base": "invalid_model_pack"},
            )
        limitation = describe_pack_limitations(current_pack)
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "pack_notes": current_pack.notes or "none",
                "pack_limitations": limitation or "none",
            },
        )
