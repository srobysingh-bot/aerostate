"""Table-driven state resolution engine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import StateEngine

if TYPE_CHECKING:
    from ..packs.schema import ModelPack

_LOGGER: logging.Logger = logging.getLogger(__name__)


class TableEngine(StateEngine):
    """Resolves AC state to command using table-driven lookups."""

    def __init__(self, pack: ModelPack) -> None:
        """Initialize with a ModelPack.

        Args:
            pack: ModelPack instance
        """
        self._pack = pack
        self._commands = pack.commands
        self._capabilities = pack.capabilities

    def resolve_command(self, state: dict) -> str:
        """Resolve state to command by traversing pack command tree.

        Supports lookup paths based on pack capabilities:
        1. If power=off: return commands["off"]
        2. Otherwise dynamically build path based on capabilities:
           - Start with commands[hvac_mode]
           - If swing_vertical supported: -> commands[...][swing_vertical]
           - If swing_horizontal supported: -> commands[...][swing_horizontal]
           - If fan_mode supported: -> commands[...][fan_mode]
           - If temperature supported: -> commands[...][int(temperature)]

        Args:
            state: Dictionary containing AC state

        Returns:
            Base64-encoded IR command

        Raises:
            ValueError: If state cannot be resolved with available keys
        """
        power = state.get("power")

        # If power is off, return the off command
        if power is False or power == "off":
            try:
                return self._commands["off"]
            except KeyError:
                available_keys = list(self._commands.keys())
                raise ValueError(
                    f"No 'off' command found in pack. Available keys: {available_keys}"
                ) from None

        # Start navigation from hvac_mode
        hvac_mode = state.get("hvac_mode")
        if hvac_mode is None:
            raise ValueError("hvac_mode is required when power is on")

        current_node = self._commands

        try:
            current_node = current_node[hvac_mode]
        except KeyError:
            available_keys = list(self._commands.keys())
            raise ValueError(
                f"hvac_mode '{hvac_mode}' not found in commands. Available: {available_keys}"
            ) from None

        target_temperature = state.get("target_temperature")
        if target_temperature is None:
            raise ValueError("target_temperature is required but not provided")

        temp_str = str(int(target_temperature))

        fan_mode = state.get("fan_mode")
        if self._capabilities.fan_modes and fan_mode is None:
            raise ValueError("fan_mode is required but not provided")

        swing_vertical = state.get("swing_vertical")
        if swing_vertical is None and self._capabilities.swing_vertical_modes:
            swing_vertical = self._capabilities.swing_vertical_modes[0]

        swing_horizontal = state.get("swing_horizontal")
        if swing_horizontal is None and self._capabilities.swing_horizontal_modes:
            swing_horizontal = self._capabilities.swing_horizontal_modes[0]

        # Option A MVP resolution order support:
        # 1) mode -> fan -> temp
        # 2) mode -> swing_vertical -> fan -> temp
        # 3) mode -> swing_vertical -> swing_horizontal -> fan -> temp
        # Swing levels are traversed only if they exist in the command tree.
        candidates: list[list[str]] = []
        if fan_mode is not None:
            candidates.append([fan_mode, temp_str])
            if swing_vertical is not None:
                candidates.append([swing_vertical, fan_mode, temp_str])
                if swing_horizontal is not None:
                    candidates.append([swing_vertical, swing_horizontal, fan_mode, temp_str])

        last_error: ValueError | None = None
        for candidate in candidates:
            node: Any = current_node
            trial_path = [hvac_mode]
            valid = True
            for segment in candidate:
                if not isinstance(node, dict):
                    valid = False
                    break
                if segment not in node:
                    available_keys = list(node.keys())
                    last_error = ValueError(
                        f"State segment '{segment}' not found at {'.'.join(trial_path)}. "
                        f"Available keys: {available_keys}"
                    )
                    valid = False
                    break
                node = node[segment]
                trial_path.append(segment)

            if valid:
                if not isinstance(node, str):
                    raise ValueError(
                        f"Command at {'.'.join(trial_path)} is not a base64 string (type={type(node).__name__})"
                    )
                _LOGGER.debug("Resolved state to command via path: %s", " -> ".join(trial_path))
                return node

        raise ValueError(
            f"Unable to resolve command for hvac_mode={hvac_mode}, fan_mode={fan_mode}, "
            f"swing_vertical={swing_vertical}, swing_horizontal={swing_horizontal}, temp={temp_str}. "
            f"Last error: {last_error}"
        )
