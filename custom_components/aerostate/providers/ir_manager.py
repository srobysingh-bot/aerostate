"""Routes IR commands through exactly one backend per AeroState entry — no hybrid fallback."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Literal

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    CONF_BROADLINK_ENTITY,
    CONF_IR_CONVERSION_ENABLED,
    CONF_IR_PROVIDER,
    CONF_TUYA_IR_DP,
    CONF_TUYA_IR_ENTITY,
    CONF_TUYA_IR_NO_ACK_MODE,
    CONF_TUYA_IR_SEND_BLOCKING,
    CONF_TUYA_LOCAL_DEVICE_ID,
    CONF_TUYA_MODEL_PACK,
    DEFAULT_TUYA_IR_DP,
    IR_PROVIDER_BROADLINK,
    IR_PROVIDER_TUYA,
)
from ..engines import StateEngine, create_engine
from .broadlink import BroadlinkIRProvider, BroadlinkProvider
from .ir_conversion import IRConversionLayer, IRConverter
from .ir_exceptions import IRRoutingMisconfigured
from .ir_types import IRCommand
from .tuya_ir import TuyaIRProvider


_LOGGER = logging.getLogger(__name__)

BackendDisplay = Literal["broadlink", "tuya", "misconfigured"]


def _opt_bool_from_entry(entry: ConfigEntry | Any, key: str, default: bool) -> bool:
    v = entry.options.get(key, entry.data.get(key, default))
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _opt_int_from_entry(entry: ConfigEntry | Any, key: str, default: int) -> int:
    raw = entry.options.get(key, entry.data.get(key, default))
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip(), 10)
    except ValueError:
        return default


def _normalize_ir_provider_key(raw: str | None, *, explicit: bool, device_id: str) -> str:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if not explicit:
            _LOGGER.warning(
                "AeroState entry %s: ir_provider is not set; assuming %s "
                "(configure ir_provider explicitly in integration options)",
                device_id,
                IR_PROVIDER_BROADLINK,
            )
        return IR_PROVIDER_BROADLINK
    key = raw.strip().lower()
    if key not in {IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA}:
        _LOGGER.warning(
            "AeroState entry %s: invalid ir_provider %r; using %s",
            device_id,
            raw,
            IR_PROVIDER_BROADLINK,
        )
        return IR_PROVIDER_BROADLINK
    return key


def _explain_tuya_blockers(
    tuya_sender: TuyaIRProvider | None,
    tuya_engine: StateEngine | None,
    *,
    ir_conversion_enabled: bool,
) -> str | None:
    if tuya_sender is None:
        return f"{CONF_TUYA_IR_ENTITY} is missing or empty"
    if ir_conversion_enabled:
        return None

    if tuya_engine is None:
        return (
            f"{CONF_TUYA_MODEL_PACK} is missing, invalid, or unloadable non-lg_protocol table pack"
        )
    pack = getattr(tuya_engine, "_pack", None)
    engine_kind = getattr(pack, "engine_type", "") if pack is not None else ""
    if engine_kind == "lg_protocol":
        return (
            f"{CONF_TUYA_MODEL_PACK} uses lg_protocol; use a table-authored hex IR pack instead"
        )
    return None


class IRManager:
    """Exactly one backend per entry: resolves and sends strictly on that path."""

    def __init__(
        self,
        *,
        device_id: str,
        lg_engine: StateEngine,
        normalized_provider_key: str,
        invalid_tuya_reason: str | None,
        broadlink_impl: BroadlinkProvider,
        broadlink_ir: BroadlinkIRProvider,
        tuya_engine: StateEngine | None,
        tuya_sender: TuyaIRProvider | None,
        ir_conversion_enabled: bool = False,
        ir_conversion_layer: IRConversionLayer | None = None,
        tuya_ir_no_ack_mode: bool = False,
    ) -> None:
        self._device_id = device_id
        self._lg_engine = lg_engine

        self._normalized_provider_key = normalized_provider_key
        self._invalid_tuya_reason: str | None = (
            invalid_tuya_reason if normalized_provider_key == IR_PROVIDER_TUYA else None
        )
        self._tuya_ir_no_ack_mode = normalized_provider_key == IR_PROVIDER_TUYA and bool(tuya_ir_no_ack_mode)

        conversion_layer = ir_conversion_layer if ir_conversion_enabled else None

        self._conversion_layer = conversion_layer if normalized_provider_key == IR_PROVIDER_TUYA else None

        self._tuya_can_send = (
            normalized_provider_key == IR_PROVIDER_TUYA
            and invalid_tuya_reason is None
            and tuya_sender is not None
            and (tuya_engine is not None or self._conversion_layer is not None)
        )

        self._broadlink_impl = broadlink_impl
        self._broadlink_ir = broadlink_ir
        self._tuya_engine = tuya_engine
        self._tuya_sender = tuya_sender

        if normalized_provider_key == IR_PROVIDER_TUYA and invalid_tuya_reason:
            _LOGGER.warning(
                "[%s] ir_provider=tuya is incomplete or invalid (%s); IR sends will fail until fixed",
                device_id,
                invalid_tuya_reason,
            )

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def preference_configured(self) -> str:
        """Normalized ir_provider configuration string for this device."""
        return self._normalized_provider_key

    @property
    def active_transport(self) -> str:
        """Backend this device is pinned to (intent; may be tuya while still misconfigured)."""
        return IR_PROVIDER_BROADLINK if self._normalized_provider_key != IR_PROVIDER_TUYA else IR_PROVIDER_TUYA

    def effective_ir_mode(self) -> BackendDisplay:
        if self._normalized_provider_key != IR_PROVIDER_TUYA:
            return IR_PROVIDER_BROADLINK
        return IR_PROVIDER_TUYA if self._tuya_can_send else "misconfigured"

    @property
    def tuya_assumes_no_ack(self) -> bool:
        """When True, climate should not treat IR as producing timely device/power feedback."""

        return self._tuya_ir_no_ack_mode

    def tuya_send_debug(self) -> dict[str, Any]:
        """Structured IR transport hints for diagnostics."""

        if self._tuya_sender is None:
            return {}
        ts = self._tuya_sender
        return {
            "tuya_remote_entity": getattr(ts, "_remote_entity_id", ""),
            "tuya_blocking_send": getattr(ts, "_blocking", False),
            "prefers_localtuya_set_dp": ts.uses_localtuya_dp,
            "configured_ir_dp": ts.configured_ir_dp,
        }

    def resolve_to_ir_commands(self, state_dict: dict[str, Any]) -> tuple[list[IRCommand], str]:
        if self._normalized_provider_key == IR_PROVIDER_TUYA:
            if not self._tuya_can_send or self._tuya_sender is None:
                reason = (
                    self._invalid_tuya_reason
                    or _explain_tuya_blockers(
                        self._tuya_sender,
                        self._tuya_engine,
                        ir_conversion_enabled=self._conversion_layer is not None,
                    )
                    or "tuya prerequisites not satisfied"
                )
                raise IRRoutingMisconfigured(
                    f"[{self._device_id}] Tuya IR selected but unusable ({reason}); fix options — no alternate IR path",
                )

        if self._normalized_provider_key == IR_PROVIDER_BROADLINK:
            resolved = self._lg_engine.resolve_command(state_dict)
            fmt = "broadlink"
        elif self._conversion_layer is not None:
            assert self._tuya_sender is not None
            lg_resolved = self._lg_engine.resolve_command(state_dict)
            b64_parts = lg_resolved if isinstance(lg_resolved, list) else [lg_resolved]
            cmds_optional, failure_reason = self._conversion_layer.sequence_to_ir_commands_or_none(
                broadlink_parts=list(b64_parts),
                payload_hash_src=list(b64_parts),
            )
            if cmds_optional is not None:
                fingerprint = "|".join(c.payload for c in cmds_optional)
                payload_hash = hashlib.sha256(fingerprint.encode("utf-8", errors="replace")).hexdigest()[:12]
                _LOGGER.info(
                    "[%s] IR conversion layer produced hex IR for %s command burst(s)",
                    self._device_id,
                    len(cmds_optional),
                )
                return cmds_optional, payload_hash

            if self._tuya_engine is None:
                raise IRRoutingMisconfigured(
                    f"[{self._device_id}] IR conversion failed ({failure_reason}); "
                    f"configure a manual hex {CONF_TUYA_MODEL_PACK} for fallback",
                )

            _LOGGER.warning(
                "[%s] IR conversion unavailable (%s); using manual Tuya learned IR pack",
                self._device_id,
                failure_reason,
            )
            resolved = self._tuya_engine.resolve_command(state_dict)
            fmt = "tuya"
        else:
            if self._tuya_engine is None:
                raise IRRoutingMisconfigured(
                    f"[{self._device_id}] Tuya IR selected but unusable ({CONF_TUYA_MODEL_PACK}); "
                    "fix options — no alternate IR path",
                )
            resolved = self._tuya_engine.resolve_command(state_dict)
            fmt = "tuya"

        parts = resolved if isinstance(resolved, list) else [resolved]
        commands = [
            IRCommand(
                name=f"cmd_{idx + 1}" if len(parts) > 1 else "cmd",
                payload=p,
                format=fmt,
            )
            for idx, p in enumerate(parts)
        ]
        fingerprint = "|".join(c.payload for c in commands)
        payload_hash = hashlib.sha256(fingerprint.encode("utf-8", errors="replace")).hexdigest()[:12]
        return commands, payload_hash

    async def async_send_commands(self, commands: list[IRCommand]) -> None:
        if not commands:
            return

        formats = {c.format for c in commands}
        if len(formats) != 1:
            raise ValueError("Mixed IR formats in a single batch are not supported")

        fmt = next(iter(formats))
        if fmt == "broadlink":
            selected = IR_PROVIDER_BROADLINK
        else:
            selected = IR_PROVIDER_TUYA

        if self.active_transport != selected:
            raise RuntimeError(
                f"[{self._device_id}] IR internal error: routing has {self.active_transport} commands with {fmt}",
            )

        if fmt == "tuya":
            if self._tuya_sender is None:
                raise IRRoutingMisconfigured(f"[{self._device_id}] Tuya IR sender unavailable")
            for command in commands:
                await self._send_one_tuya(command)
            return

        if len(commands) == 1:
            await self._send_one_broadlink(commands[0])
            return

        result = await self._broadlink_ir.send_sequence(commands)
        if result.get("success", False):
            for cmd in commands:
                _LOGGER.info(
                    "ir_send entry_id=%s selected_ir_provider=%s command=%s result=success format=%s",
                    self._device_id,
                    selected,
                    cmd.name,
                    cmd.format,
                )
            return
        errors = result.get("errors") or []
        detail = errors[-1] if errors else "Broadlink IR sequence failed"
        _LOGGER.warning(
            "ir_send entry_id=%s selected_ir_provider=%s command=batch commands=%s result=failure detail=%s",
            self._device_id,
            selected,
            [c.name for c in commands],
            detail,
        )
        raise HomeAssistantError(str(detail))

    async def _send_one_broadlink(self, command: IRCommand) -> None:
        sel = IR_PROVIDER_BROADLINK
        try:
            await self._broadlink_ir.send_command(command)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "ir_send entry_id=%s selected_ir_provider=%s command=%s result=failure detail=%s format=%s",
                self._device_id,
                sel,
                command.name,
                err,
                command.format,
            )
            raise
        _LOGGER.info(
            "ir_send entry_id=%s selected_ir_provider=%s command=%s result=success format=%s",
            self._device_id,
            sel,
            command.name,
            command.format,
        )

    async def _send_one_tuya(self, command: IRCommand) -> None:
        sel = IR_PROVIDER_TUYA
        try:
            assert self._tuya_sender is not None
            await self._tuya_sender.send_command(command)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "ir_send entry_id=%s selected_ir_provider=%s command=%s result=failure detail=%s format=%s",
                self._device_id,
                sel,
                command.name,
                err,
                command.format,
            )
            raise

        _LOGGER.info(
            "ir_send entry_id=%s selected_ir_provider=%s command=%s result=success format=%s",
            self._device_id,
            sel,
            command.name,
            command.format,
        )

    async def probe_active_transport(self) -> bool:
        """Health-check only for the backend selected by ir_provider (never the other backend)."""
        if self.active_transport == IR_PROVIDER_BROADLINK:
            return await self._broadlink_impl.test_connection()
        if not self._tuya_can_send or self._tuya_sender is None:
            _LOGGER.warning(
                "[%s] active transport is Tuya but hardware/service is unavailable for probe",
                self._device_id,
            )
            return False
        return await self._tuya_sender.test_connection()

    async def probe_broadlink_hardware_when_present(self) -> bool:
        """Optional backbone Broadlink probe (for diagnostics/backward compatibility)."""
        return await self._broadlink_impl.test_connection()


def create_ir_manager_from_entry(
    hass: Any,
    entry: ConfigEntry,
    *,
    lg_engine: StateEngine,
    registry: Any,
) -> IRManager:
    """Construct deterministic IR routing for one AeroState device entry."""

    explicit_ir = CONF_IR_PROVIDER in entry.data or CONF_IR_PROVIDER in entry.options

    pref_raw_any = entry.options.get(CONF_IR_PROVIDER, entry.data.get(CONF_IR_PROVIDER))
    normalized = _normalize_ir_provider_key(
        pref_raw_any if isinstance(pref_raw_any, str) else None,
        explicit=explicit_ir,
        device_id=entry.entry_id,
    )

    broadlink_entity_id = entry.options.get(CONF_BROADLINK_ENTITY, entry.data.get(CONF_BROADLINK_ENTITY))
    broadlink_transport = BroadlinkProvider(hass, str(broadlink_entity_id or ""))
    broadlink_ir = BroadlinkIRProvider(broadlink_transport)

    tuya_entity = entry.options.get(CONF_TUYA_IR_ENTITY, entry.data.get(CONF_TUYA_IR_ENTITY))
    tuya_pack_id = entry.options.get(CONF_TUYA_MODEL_PACK, entry.data.get(CONF_TUYA_MODEL_PACK))

    tuya_engine: StateEngine | None = None
    if isinstance(tuya_pack_id, str) and tuya_pack_id.strip():
        tid = tuya_pack_id.strip()
        try:
            tuya_pack_obj = registry.get(tid)
        except KeyError:
            _LOGGER.warning("[%s] tuya_model_pack %s missing from registry", entry.entry_id, tid)
            tuya_pack_obj = None
        if tuya_pack_obj is not None:
            if getattr(tuya_pack_obj, "engine_type", "") == "lg_protocol":
                pass
            else:
                try:
                    tuya_engine = create_engine(tuya_pack_obj)
                except Exception:
                    _LOGGER.exception("[%s] cannot create Tuya hex pack engine %s", entry.entry_id, tid)
                    tuya_engine = None

    raw_conv = entry.options.get(CONF_IR_CONVERSION_ENABLED, entry.data.get(CONF_IR_CONVERSION_ENABLED, False))
    if isinstance(raw_conv, str):
        ir_conversion_enabled = raw_conv.strip().lower() in ("1", "true", "yes", "on")
    else:
        ir_conversion_enabled = bool(raw_conv)

    conversion_layer: IRConversionLayer | None = None
    if normalized == IR_PROVIDER_TUYA and ir_conversion_enabled:
        conversion_layer = IRConversionLayer(IRConverter())

    tuya_blocking = _opt_bool_from_entry(entry, CONF_TUYA_IR_SEND_BLOCKING, True)
    tuya_no_ack = _opt_bool_from_entry(entry, CONF_TUYA_IR_NO_ACK_MODE, True)
    ir_dp_cfg = _opt_int_from_entry(entry, CONF_TUYA_IR_DP, DEFAULT_TUYA_IR_DP)
    raw_ld = entry.options.get(CONF_TUYA_LOCAL_DEVICE_ID, entry.data.get(CONF_TUYA_LOCAL_DEVICE_ID))
    local_dev = raw_ld.strip() if isinstance(raw_ld, str) and raw_ld.strip() else None

    tuya_sender: TuyaIRProvider | None = None
    if isinstance(tuya_entity, str) and tuya_entity.strip():
        tid_ent = tuya_entity.strip()
        tuya_sender = TuyaIRProvider(
            hass,
            tid_ent,
            blocking=tuya_blocking,
            entry_id=entry.entry_id,
            localtuya_device_id=local_dev,
            ir_dp=ir_dp_cfg,
        )
        if normalized == IR_PROVIDER_TUYA and not local_dev:
            _LOGGER.warning(
                "[%s] Tuya IR: %s unset — using remote.send_command on %s. "
                "If Local Tuya shows 'Detect control type failed', set YAML control_type ir "
                "and AeroState option %s (often DP %s → localtuya.set_dp); see Hass LocalTuya services docs.",
                entry.entry_id,
                CONF_TUYA_LOCAL_DEVICE_ID,
                tid_ent,
                CONF_TUYA_LOCAL_DEVICE_ID,
                ir_dp_cfg,
            )

    invalid_tuya_reason: str | None = None
    if normalized == IR_PROVIDER_TUYA:
        invalid_tuya_reason = _explain_tuya_blockers(
            tuya_sender,
            tuya_engine,
            ir_conversion_enabled=ir_conversion_enabled,
        )

    return IRManager(
        device_id=entry.entry_id,
        lg_engine=lg_engine,
        normalized_provider_key=normalized,
        invalid_tuya_reason=invalid_tuya_reason,
        broadlink_impl=broadlink_transport,
        broadlink_ir=broadlink_ir,
        tuya_engine=tuya_engine,
        tuya_sender=tuya_sender,
        ir_conversion_enabled=ir_conversion_enabled,
        ir_conversion_layer=conversion_layer,
        tuya_ir_no_ack_mode=tuya_no_ack if normalized == IR_PROVIDER_TUYA else False,
    )


def create_ir_manager_explicit(
    *,
    device_id: str = "explicit_test_device",
    lg_engine: StateEngine,
    preference_raw: str,
    broadlink_impl: BroadlinkProvider,
    broadlink_ir: BroadlinkIRProvider,
    tuya_engine: StateEngine | None,
    tuya_sender: TuyaIRProvider | None,
    ir_conversion_enabled: bool = False,
    ir_conversion_layer: IRConversionLayer | None = None,
    tuya_ir_no_ack_mode: bool = False,
) -> IRManager:
    """Test helper."""

    nk = preference_raw.strip().lower() if preference_raw else IR_PROVIDER_BROADLINK
    conv_layer = ir_conversion_layer
    if nk == IR_PROVIDER_TUYA and ir_conversion_enabled and conv_layer is None:
        conv_layer = IRConversionLayer(IRConverter())

    if nk == IR_PROVIDER_TUYA:
        inv = _explain_tuya_blockers(tuya_sender, tuya_engine, ir_conversion_enabled=ir_conversion_enabled)
        return IRManager(
            device_id=device_id,
            lg_engine=lg_engine,
            normalized_provider_key=IR_PROVIDER_TUYA,
            invalid_tuya_reason=inv,
            broadlink_impl=broadlink_impl,
            broadlink_ir=broadlink_ir,
            tuya_engine=tuya_engine,
            tuya_sender=tuya_sender,
            ir_conversion_enabled=ir_conversion_enabled,
            ir_conversion_layer=conv_layer,
            tuya_ir_no_ack_mode=tuya_ir_no_ack_mode,
        )

    return IRManager(
        device_id=device_id,
        lg_engine=lg_engine,
        normalized_provider_key=nk if nk in {IR_PROVIDER_BROADLINK, IR_PROVIDER_TUYA} else IR_PROVIDER_BROADLINK,
        invalid_tuya_reason=None,
        broadlink_impl=broadlink_impl,
        broadlink_ir=broadlink_ir,
        tuya_engine=tuya_engine,
        tuya_sender=tuya_sender,
        tuya_ir_no_ack_mode=False,
    )
