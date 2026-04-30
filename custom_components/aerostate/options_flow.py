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
    CONF_IR_CONVERSION_ENABLED,
    CONF_IR_PROVIDER,
    CONF_MODEL_PACK,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_TUYA_IR_DP,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_IR_NO_ACK_MODE,
    CONF_TUYA_IR_SEND_BLOCKING,
    CONF_TUYA_LOCAL_DEVICE_ID,
    CONF_TUYA_MODEL_PACK,
    DEFAULT_IR_PROVIDER,
    DEFAULT_TUYA_IR_DP,
)
from .flow_helpers import (
    build_entry_title,
    describe_pack_limitations,
    has_entry_collision,
)
from .packs.registry import get_registry


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
    ) -> vol.Schema:
        """Build options form schema."""
        ir_default = config_entry.options.get(CONF_IR_PROVIDER, config_entry.data.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER))
        tuya_entity_default = config_entry.options.get(CONF_TUYA_IR_ENTITY, config_entry.data.get(CONF_TUYA_IR_ENTITY))
        tuya_pack_default = config_entry.options.get(CONF_TUYA_MODEL_PACK, config_entry.data.get(CONF_TUYA_MODEL_PACK))
        conv_default = config_entry.options.get(CONF_IR_CONVERSION_ENABLED, config_entry.data.get(CONF_IR_CONVERSION_ENABLED, False))
        if isinstance(conv_default, str):
            conv_default = conv_default.strip().lower() in ("1", "true", "yes", "on")
        conv_default = bool(conv_default)

        raw_na = config_entry.options.get(CONF_TUYA_IR_NO_ACK_MODE, config_entry.data.get(CONF_TUYA_IR_NO_ACK_MODE, True))
        if isinstance(raw_na, str):
            no_ack_default = raw_na.strip().lower() in ("1", "true", "yes", "on")
        else:
            no_ack_default = bool(raw_na)

        raw_blk = config_entry.options.get(CONF_TUYA_IR_SEND_BLOCKING, config_entry.data.get(CONF_TUYA_IR_SEND_BLOCKING, True))
        if isinstance(raw_blk, str):
            blk_default = raw_blk.strip().lower() in ("1", "true", "yes", "on")
        else:
            blk_default = bool(raw_blk)

        ld_raw = config_entry.options.get(CONF_TUYA_LOCAL_DEVICE_ID, config_entry.data.get(CONF_TUYA_LOCAL_DEVICE_ID, ""))
        ld_default = ld_raw.strip() if isinstance(ld_raw, str) else ""

        dp_raw = config_entry.options.get(CONF_TUYA_IR_DP, config_entry.data.get(CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP))
        try:
            dp_default_val = int(str(dp_raw).strip(), 10) if dp_raw not in (None, "") else DEFAULT_TUYA_IR_DP
        except ValueError:
            dp_default_val = DEFAULT_TUYA_IR_DP

        return vol.Schema(
            {
                vol.Required(
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
                            selector.SelectOptionDict(value="tuya", label="Local Tuya IR (optional hex pack)"),
                        ]
                    ),
                ),
                vol.Optional(
                    CONF_TUYA_IR_ENTITY,
                    default=tuya_entity_default,
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="remote")),
                vol.Optional(
                    CONF_TUYA_MODEL_PACK,
                    default=tuya_pack_default if tuya_pack_default else "",
                ): selector.SelectSelector(selector.SelectSelectorConfig(options=tuya_pack_options)),
                vol.Optional(
                    CONF_IR_CONVERSION_ENABLED,
                    default=conv_default,
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_TUYA_LOCAL_DEVICE_ID,
                    default=ld_default,
                ): selector.TextSelector(),
                vol.Optional(CONF_TUYA_IR_DP, default=str(dp_default_val)): str,
                vol.Optional(
                    CONF_TUYA_IR_NO_ACK_MODE,
                    default=no_ack_default,
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_TUYA_IR_SEND_BLOCKING,
                    default=blk_default,
                ): selector.BooleanSelector(),
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

        all_packs = sorted(registry.list_all(), key=lambda p: p.pack_id)
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

        schema = self._schema(self._config_entry, pack_options, tuya_pack_options)

        if user_input is not None:
            selected_remote = user_input.get(
                CONF_BROADLINK_ENTITY,
                self._config_entry.data.get(CONF_BROADLINK_ENTITY),
            )
            selected_pack = user_input.get(
                CONF_MODEL_PACK,
                self._config_entry.data.get(CONF_MODEL_PACK),
            )

            if has_entry_collision(
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

            if selected_pack and selected_pack != self._config_entry.data.get(CONF_MODEL_PACK):
                # Keep pack changes explicit by only updating when a new pack is selected.
                new_data[CONF_MODEL_PACK] = selected_pack

            try:
                selected_pack_obj = registry.get(new_data.get(CONF_MODEL_PACK))
            except Exception:
                return self.async_show_form(
                    step_id="init",
                    data_schema=schema,
                    errors={"base": "invalid_model_pack"},
                )

            sel_ir = str(user_input.get(CONF_IR_PROVIDER, DEFAULT_IR_PROVIDER) or DEFAULT_IR_PROVIDER).strip().lower()
            new_options[CONF_IR_PROVIDER] = sel_ir if sel_ir in ("broadlink", "tuya") else DEFAULT_IR_PROVIDER

            raw_tuya_entity = user_input.get(CONF_TUYA_IR_ENTITY)
            if isinstance(raw_tuya_entity, str) and raw_tuya_entity.strip():
                new_options[CONF_TUYA_IR_ENTITY] = raw_tuya_entity.strip()
            else:
                new_options.pop(CONF_TUYA_IR_ENTITY, None)

            raw_tp = user_input.get(CONF_TUYA_MODEL_PACK)
            if isinstance(raw_tp, str) and raw_tp.strip():
                new_options[CONF_TUYA_MODEL_PACK] = raw_tp.strip()
            else:
                new_options.pop(CONF_TUYA_MODEL_PACK, None)

            new_options[CONF_IR_CONVERSION_ENABLED] = bool(user_input.get(CONF_IR_CONVERSION_ENABLED, False))

            raw_ld_in = user_input.get(CONF_TUYA_LOCAL_DEVICE_ID)
            if isinstance(raw_ld_in, str) and raw_ld_in.strip():
                new_options[CONF_TUYA_LOCAL_DEVICE_ID] = raw_ld_in.strip()
            else:
                new_options.pop(CONF_TUYA_LOCAL_DEVICE_ID, None)

            try:
                dpi = int(str(user_input.get(CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP)).strip(), 10)
                new_options[CONF_TUYA_IR_DP] = max(1, min(999, dpi))
            except ValueError:
                new_options[CONF_TUYA_IR_DP] = DEFAULT_TUYA_IR_DP

            new_options[CONF_TUYA_IR_NO_ACK_MODE] = bool(user_input.get(CONF_TUYA_IR_NO_ACK_MODE, True))
            new_options[CONF_TUYA_IR_SEND_BLOCKING] = bool(user_input.get(CONF_TUYA_IR_SEND_BLOCKING, True))

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

        try:
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
