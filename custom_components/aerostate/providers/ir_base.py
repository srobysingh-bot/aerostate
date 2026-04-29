"""Abstract IR transport contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .ir_types import IRCommand


class IRProvider(ABC):
    """Backend that sends normalized IRCommand instances."""

    @abstractmethod
    async def send_command(self, command: IRCommand) -> None:
        """Send one IR command."""
