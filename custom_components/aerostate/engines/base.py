"""Abstract base class for AC state resolution engines."""

from __future__ import annotations

from abc import ABC, abstractmethod


class StateEngine(ABC):
    """Abstract base for AC state resolution engines."""

    @abstractmethod
    def resolve_command(self, state: dict) -> str:
        """Resolve full AC state into Broadlink base64 command.

        Args:
            state: Dictionary with keys like:
                - power: bool
                - hvac_mode: str (off, cool, heat, etc.)
                - target_temperature: int or float
                - fan_mode: str (auto, low, mid, high)
                - swing_vertical: str (off, swing, etc.)
                - swing_horizontal: str (off, swing, etc.)

        Returns:
            Base64-encoded IR command

        Raises:
            ValueError: If state cannot be resolved to a known command
        """
        pass
