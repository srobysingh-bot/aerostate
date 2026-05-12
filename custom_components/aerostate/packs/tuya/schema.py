"""Schema for standalone Tuya IR key1 packs."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schema import ModelPack, PackCapabilities


@dataclass
class TuyaIRCommand:
    """One pre-converted Tuya DP 201 IR command."""

    label: str
    key1: str
    hvac_mode: str
    temperature: int | None = None
    fan_mode: str | None = None
    swing_on: bool = False
    turn_on_variant: bool = False


@dataclass
class TuyaIRPack:
    """Flat lookup table of Tuya base64 key1 commands."""

    pack_id: str
    brand: str
    models: list[str]
    verified: bool
    notes: str
    min_temperature: int
    max_temperature: int
    commands: list[TuyaIRCommand] = field(default_factory=list)
    native_base64: bool = False
    requires_learned_codes: bool = True
    swing_toggle_label: str | None = None
    transport: str = "tuya_key1"
    protocol: str = "stateless"

    def resolve(
        self,
        hvac_mode: str,
        temperature: int | None = None,
        fan_mode: str | None = None,
        swing_on: bool = False,
        previously_off: bool = False,
    ) -> str | None:
        """Return the matching Tuya key1 base64 payload."""
        preferred_turn_on = previously_off and hvac_mode != "off"
        fallback: str | None = None
        for cmd in self.commands:
            if cmd.hvac_mode != hvac_mode:
                continue
            if cmd.temperature is not None and temperature is not None and cmd.temperature != temperature:
                continue
            if cmd.fan_mode is not None and fan_mode is not None and cmd.fan_mode != fan_mode:
                continue
            if cmd.swing_on != swing_on:
                continue
            if cmd.turn_on_variant == preferred_turn_on:
                return cmd.key1
            if fallback is None and not cmd.turn_on_variant:
                fallback = cmd.key1
        return fallback

    def resolve_by_label(self, label: str) -> str | None:
        """Look up key1 directly by command label for preset/special commands."""
        for cmd in self.commands:
            if cmd.label == label:
                return cmd.key1
        return None

    def resolve_swing_toggle(self) -> str | None:
        """Return the independent swing toggle command when the pack defines one."""
        if not self.swing_toggle_label:
            return None
        return self.resolve_by_label(self.swing_toggle_label)

    def to_model_pack(self) -> ModelPack:
        """Expose Tuya pack capabilities through the existing climate UI model."""
        hvac_modes = []
        for cmd in self.commands:
            if cmd.hvac_mode not in {"off", "special"} and cmd.hvac_mode not in hvac_modes:
                hvac_modes.append(cmd.hvac_mode)

        fan_modes = []
        for cmd in self.commands:
            if cmd.fan_mode and cmd.fan_mode not in fan_modes:
                fan_modes.append(cmd.fan_mode)

        swing_modes = ["off", "on"] if self.swing_toggle_label or any(cmd.swing_on for cmd in self.commands) else []
        commands_tree: dict[str, object] = {}

        for cmd in self.commands:
            if cmd.turn_on_variant:
                continue
            if cmd.hvac_mode == "special":
                continue
            if cmd.hvac_mode == "off":
                commands_tree["off"] = cmd.key1
                continue

            mode_node = commands_tree.setdefault(cmd.hvac_mode, {})
            if not isinstance(mode_node, dict):
                continue

            if cmd.temperature is None:
                fan_key = cmd.fan_mode or "auto"
                swing_key = "on" if cmd.swing_on else "off"
                mode_node.setdefault(fan_key, {})[swing_key] = cmd.key1
                continue

            fan_key = cmd.fan_mode or "auto"
            swing_key = "on" if cmd.swing_on else "off"
            fan_node = mode_node.setdefault(fan_key, {})
            if isinstance(fan_node, dict):
                swing_node = fan_node.setdefault(swing_key, {})
                if isinstance(swing_node, dict):
                    swing_node[str(cmd.temperature)] = cmd.key1

        return ModelPack(
            pack_id=self.pack_id,
            brand=self.brand,
            models=self.models,
            transport="tuya_remote" if self.native_base64 else self.transport,
            pack_version=1,
            min_temperature=self.min_temperature,
            max_temperature=self.max_temperature,
            capabilities=PackCapabilities(
                hvac_modes=hvac_modes,
                fan_modes=fan_modes,
                swing_vertical_modes=swing_modes,
                swing_horizontal_modes=[],
                presets=[],
                preset_modes=[],
            ),
            engine_type="table",
            commands=commands_tree,
            verified=self.verified,
            notes=self.notes,
        )
