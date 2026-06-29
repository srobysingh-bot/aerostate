"""Options flow for AeroState integration."""

from __future__ import annotations

import time
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
    CONF_SELECTED_TUYA_PACK_ID,
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
from .packs.tuya.registry import DAIKIN_REFERENCE_PACK_ID, get_tuya_pack_options_for_ui
from .packs.tuya_cloud.registry import get_tuya_cloud_pack_options_for_ui


class AeroStateOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for AeroState config entries."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_tuya_input: dict[str, Any] = {}
        self._tested_daikin_pack_ids: set[str] = set()
        self._last_daikin_pack_test_at = 0.0

    @staticmethod
    def _schema(
        config_entry: config_entries.ConfigEntry,
        pack_options: list[selector.SelectOptionDict],
        tuya_pack_options: list[selector.SelectOptionDict],
        tuya_cloud_pack_options: list[selector.SelectOptionDict],
        *,
        show_daikin_actions: bool = False,
    ) -> vol.Schema:
        """Build options form schema."""
        ir_default = config_entry.options.get(
            CONF_IR_PROVIDER, config_entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER)
        )
        tuya_entity_default = config_entry.options.get(
            CONF_TUYA_IR_ENTITY, config_entry.data.get(CONF_TUYA_IR_ENTITY)
        )
        tuya_device_default = config_entry.options.get(
            CONF_TUYA_DEVICE_NAME,
            config_entry.data.get(CONF_TUYA_DEVICE_NAME, DEFAULT_TUYA_DEVICE_NAME),
        )
        tuya_pack_default = config_entry.options.get(
            CONF_TUYA_MODEL_PACK, config_entry.data.get(CONF_TUYA_MODEL_PACK)
        )
        tuya_cloud_endpoint_default = config_entry.options.get(
            CONF_TUYA_CLOUD_ENDPOINT,
            config_entry.data.get(CONF_TUYA_CLOUD_ENDPOINT, DEFAULT_TUYA_CLOUD_ENDPOINT),
        )
        tuya_cloud_pack_default = config_entry.options.get(
            CONF_TUYA_CLOUD_MODEL_PACK,
            config_entry.data.get(CONF_TUYA_CLOUD_MODEL_PACK),
        )

        fields: dict[Any, Any] = {
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
                        selector.SelectOptionDict(
                            value="broadlink", label="Broadlink IR (default)"
                        ),
                        selector.SelectOptionDict(
                            value="tuya", label="Tuya IR Device (LG/Daikin local packs)"
                        ),
                        selector.SelectOptionDict(
                            value="tuya_cloud", label="Tuya Cloud code library (legacy)"
                        ),
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
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_TUYA_MODEL_PACK,
                default=tuya_pack_default if tuya_pack_default else "",
            ): selector.SelectSelector(selector.SelectSelectorConfig(options=tuya_pack_options)),
            vol.Optional(
                CONF_TUYA_CLOUD_ENDPOINT,
                default=tuya_cloud_endpoint_default,
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_TUYA_CLOUD_ACCESS_ID,
                default=config_entry.options.get(
                    CONF_TUYA_CLOUD_ACCESS_ID,
                    config_entry.data.get(CONF_TUYA_CLOUD_ACCESS_ID, ""),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_TUYA_CLOUD_ACCESS_SECRET,
                default=config_entry.options.get(
                    CONF_TUYA_CLOUD_ACCESS_SECRET,
                    config_entry.data.get(CONF_TUYA_CLOUD_ACCESS_SECRET, ""),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_TUYA_INFRARED_ID,
                default=config_entry.options.get(
                    CONF_TUYA_INFRARED_ID,
                    config_entry.data.get(CONF_TUYA_INFRARED_ID, ""),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_TUYA_REMOTE_ID,
                default=config_entry.options.get(
                    CONF_TUYA_REMOTE_ID,
                    config_entry.data.get(CONF_TUYA_REMOTE_ID, ""),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_TUYA_CLOUD_MODEL_PACK,
                default=tuya_cloud_pack_default if tuya_cloud_pack_default else "",
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=tuya_cloud_pack_options)
            ),
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
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "switch"])),
            vol.Optional(
                CONF_AREA,
                default=config_entry.options.get(CONF_AREA),
            ): str,
            vol.Optional(
                CONF_NAME,
                default=config_entry.options.get(CONF_NAME),
            ): str,
        }
        if show_daikin_actions:
            fields[vol.Required("daikin_setup_action", default="keep_current")] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value="keep_current",
                                label="Keep current Daikin pack",
                            ),
                            selector.SelectOptionDict(
                                value="test_installed",
                                label="Test and select an installed Daikin pack",
                            ),
                            selector.SelectOptionDict(
                                value="import_daikin",
                                label="Import Daikin packs from Tuya once",
                            ),
                        ],
                        mode="list",
                    )
                )
            )
        return vol.Schema(fields)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Edit Broadlink entity, pack, optional sensors, and title."""
        from .packs.tuya.daikin.loader import list_daikin_tuya_packs, load_daikin_tuya_pack

        imported_daikin_packs = list_daikin_tuya_packs(hass=self.hass)
        for imported_pack in imported_daikin_packs:
            load_daikin_tuya_pack(imported_pack.pack_id, hass=self.hass)
        installed_daikin_pack_ids = {pack.pack_id for pack in imported_daikin_packs}

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

        for option in get_tuya_pack_options_for_ui(brand):
            if (
                str(brand).strip().casefold() == "daikin"
                and str(option["value"]) != DAIKIN_REFERENCE_PACK_ID
                and str(option["value"]) not in installed_daikin_pack_ids
            ):
                continue
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

        is_daikin = str(brand).strip().casefold() == "daikin"
        schema = self._schema(
            self._config_entry,
            pack_options,
            tuya_pack_options,
            tuya_cloud_pack_options,
            show_daikin_actions=is_daikin,
        )

        if user_input is not None:
            selected_remote = user_input.get(
                CONF_BROADLINK_ENTITY,
                self._config_entry.data.get(CONF_BROADLINK_ENTITY),
            )
            selected_pack = user_input.get(
                CONF_MODEL_PACK,
                self._config_entry.data.get(CONF_MODEL_PACK),
            )
            sel_ir = (
                str(user_input.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER) or DEFAULT_IR_PROVIDER)
                .strip()
                .lower()
            )
            sel_ir = (
                sel_ir
                if sel_ir in (IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA, IR_PROVIDER_TUYA_CLOUD)
                else DEFAULT_IR_PROVIDER
            )
            daikin_action = str(user_input.get("daikin_setup_action", "keep_current")).strip()

            if is_daikin and sel_ir == IR_PROVIDER_TUYA and daikin_action != "keep_current":
                self._pending_tuya_input = dict(user_input)
                if daikin_action == "import_daikin":
                    return await self.async_step_daikin_import()
                return await self.async_step_daikin_pack_test()

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

            if (
                sel_ir == IR_PROVIDER_BROADLINK
                and selected_pack
                and selected_pack != self._config_entry.data.get(CONF_MODEL_PACK)
            ):
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
                    selected_tuya_pack = get_tuya_pack(str(raw_tuya_pack))
                    if (
                        str(selected_tuya_pack.brand).strip().casefold()
                        != str(brand).strip().casefold()
                    ):
                        raise ValueError("Tuya pack brand does not match the configured brand")
                    selected_pack_obj = selected_tuya_pack.to_model_pack()
                except Exception:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=schema,
                        errors={"base": "tuya_pack_not_found"},
                    )
                if str(selected_tuya_pack.brand).strip().lower() == "daikin":
                    previous_pack = self._config_entry.options.get(
                        CONF_TUYA_MODEL_PACK,
                        self._config_entry.data.get(CONF_TUYA_MODEL_PACK),
                    )
                    if str(raw_tuya_pack) != str(previous_pack):
                        new_options.pop(CONF_SELECTED_TUYA_PACK_ID, None)
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

        current_provider = (
            str(
                self._config_entry.options.get(
                    CONF_IR_PROVIDER,
                    self._config_entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER),
                )
                or DEFAULT_IR_PROVIDER
            )
            .strip()
            .lower()
        )
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

    async def async_step_daikin_import(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Import Daikin Tuya packs once, then open the manual tester."""
        from .providers.tuya_daikin_importer import async_import_daikin_tuya_codes

        errors: dict[str, str] = {}
        status = (
            "Credentials are used only for this import and are not saved. "
            "The generated payload packs run locally after import."
        )
        if user_input is not None:
            endpoint = str(user_input.get(CONF_TUYA_CLOUD_ENDPOINT, "")).strip()
            access_id = str(user_input.get(CONF_TUYA_CLOUD_ACCESS_ID, "")).strip()
            access_secret = str(user_input.get(CONF_TUYA_CLOUD_ACCESS_SECRET, "")).strip()
            infrared_id = str(user_input.get(CONF_TUYA_INFRARED_ID, "")).strip()
            if not endpoint.startswith(("http://", "https://")):
                errors["base"] = "tuya_cloud_endpoint_invalid"
            elif not all([access_id, access_secret, infrared_id]):
                errors["base"] = "daikin_import_fields_missing"
            else:
                try:
                    result = await async_import_daikin_tuya_codes(
                        self.hass,
                        endpoint=endpoint,
                        access_id=access_id,
                        access_secret=access_secret,
                        infrared_id=infrared_id,
                    )
                except Exception:
                    errors["base"] = "daikin_import_failed"
                else:
                    self._pending_tuya_input[CONF_TUYA_MODEL_PACK] = result.pack_ids[0]
                    status = (
                        f"Imported {result.imported_count} valid Daikin packs; "
                        f"skipped {result.skipped_count}. Credentials were not saved."
                    )
                    return await self.async_step_daikin_pack_test(import_status=status)

        return self.async_show_form(
            step_id="daikin_import",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TUYA_CLOUD_ENDPOINT,
                        default=DEFAULT_TUYA_CLOUD_ENDPOINT,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_TUYA_CLOUD_ACCESS_ID): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_TUYA_CLOUD_ACCESS_SECRET): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_TUYA_INFRARED_ID): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"status": status},
        )

    async def async_step_daikin_pack_test(
        self,
        user_input: dict[str, Any] | None = None,
        *,
        import_status: str | None = None,
    ) -> config_entries.FlowResult:
        """Test one Daikin command and explicitly confirm the runtime pack."""
        from .packs.tuya.daikin.loader import (
            get_daikin_tuya_pack,
            list_daikin_tuya_packs,
            load_daikin_tuya_pack,
        )
        from .providers.tuya_ir_manager import TuyaIRManager

        packs = list_daikin_tuya_packs(hass=self.hass)
        if not packs:
            return self.async_abort(reason="no_daikin_tuya_sets_available")

        selected_pack_id = str(
            (user_input or {}).get(
                "daikin_pack_id",
                self._pending_tuya_input.get(
                    CONF_TUYA_MODEL_PACK,
                    self._config_entry.options.get(
                        CONF_SELECTED_TUYA_PACK_ID,
                        self._config_entry.options.get(
                            CONF_TUYA_MODEL_PACK,
                            self._config_entry.data.get(CONF_TUYA_MODEL_PACK, packs[0].pack_id),
                        ),
                    ),
                ),
            )
        ).strip()
        try:
            selected_info = get_daikin_tuya_pack(selected_pack_id, hass=self.hass)
        except KeyError:
            selected_info = packs[0]
            selected_pack_id = selected_info.pack_id

        pack_options = [
            selector.SelectOptionDict(
                value=pack.pack_id,
                label=(
                    f"{pack.display_name} "
                    f"(remote_index={pack.metadata.get('remote_index', 'captured')})"
                ),
            )
            for pack in packs
        ]
        command_options = [
            selector.SelectOptionDict(value=command, label=command)
            for command in selected_info.available_commands
        ]
        default_command = (
            "power_on"
            if "power_on" in selected_info.available_commands
            else selected_info.available_commands[0]
        )
        errors: dict[str, str] = {}
        status = import_status or "Choose one pack and command. Test sends only that command."

        if user_input is not None:
            action = str(user_input.get("daikin_pack_action", "test")).strip().lower()
            command = str(user_input.get("daikin_command", default_command)).strip()
            if command not in selected_info.available_commands:
                errors["base"] = "daikin_command_not_available"
            elif action == "confirm":
                if selected_pack_id not in self._tested_daikin_pack_ids:
                    errors["base"] = "daikin_pack_not_tested"
                else:
                    new_options = dict(self._config_entry.options)
                    new_options[CONF_IR_PROVIDER] = IR_PROVIDER_TUYA
                    new_options[CONF_TUYA_MODEL_PACK] = selected_pack_id
                    new_options[CONF_SELECTED_TUYA_PACK_ID] = selected_pack_id
                    for key in (CONF_TUYA_IR_ENTITY, CONF_TUYA_DEVICE_NAME):
                        value = self._pending_tuya_input.get(key)
                        if isinstance(value, str) and value.strip():
                            new_options[key] = value.strip()
                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        options=new_options,
                    )
                    await self.hass.config_entries.async_reload(self._config_entry.entry_id)
                    return self.async_create_entry(title="", data={})
            else:
                now = time.monotonic()
                if now - self._last_daikin_pack_test_at < 2.0:
                    errors["base"] = "daikin_pack_test_cooldown"
                else:
                    remote_entity = str(
                        self._pending_tuya_input.get(
                            CONF_TUYA_IR_ENTITY,
                            self._config_entry.options.get(
                                CONF_TUYA_IR_ENTITY,
                                self._config_entry.data.get(CONF_TUYA_IR_ENTITY, ""),
                            ),
                        )
                    ).strip()
                    device_name = str(
                        self._pending_tuya_input.get(
                            CONF_TUYA_DEVICE_NAME,
                            self._config_entry.options.get(
                                CONF_TUYA_DEVICE_NAME,
                                self._config_entry.data.get(
                                    CONF_TUYA_DEVICE_NAME,
                                    DEFAULT_TUYA_DEVICE_NAME,
                                ),
                            ),
                        )
                    ).strip()
                    try:
                        load_daikin_tuya_pack(selected_pack_id, hass=self.hass)
                        manager = TuyaIRManager(
                            self.hass,
                            remote_entity,
                            device_name,
                            pack_id=selected_pack_id,
                        )
                        await manager.async_test_pack_command(command)
                    except Exception:
                        errors["base"] = "daikin_pack_test_failed"
                    else:
                        self._last_daikin_pack_test_at = now
                        self._tested_daikin_pack_ids.add(selected_pack_id)
                        status = (
                            f"Sent {command} from {selected_info.display_name}. "
                            "Confirm only after the physical AC responds correctly."
                        )

        return self.async_show_form(
            step_id="daikin_pack_test",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "daikin_pack_id",
                        default=selected_pack_id,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=pack_options, mode="dropdown")
                    ),
                    vol.Required(
                        "daikin_command",
                        default=default_command,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=command_options, mode="dropdown")
                    ),
                    vol.Required(
                        "daikin_pack_action",
                        default="test",
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value="test",
                                    label="Test one command",
                                ),
                                selector.SelectOptionDict(
                                    value="confirm",
                                    label="Confirm this pack for runtime",
                                ),
                            ],
                            mode="list",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "pack_count": str(len(packs)),
                "selected_pack": selected_info.display_name,
                "remote_index": str(selected_info.metadata.get("remote_index", "captured")),
                "status": status,
            },
        )
