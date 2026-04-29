"""Minimal IR manager stand-ins for unit tests."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from custom_components.aerostate.providers.ir_types import IRCommand


class IdleIRManager:
    """Exposes only metadata APIs used by climate entity property paths."""

    def effective_ir_mode(self) -> str:
        return "broadlink"

    def preference_configured(self) -> str:
        return "broadlink"


class EchoTrackingIRManager(IdleIRManager):
    """Mirrors production IRManager resolve/hash semantics for throughput tests."""

    def __init__(self, echo_engine: object, *, send_delay: float = 0.0) -> None:
        self._engine = echo_engine
        self.sent_payloads: list[str] = []
        self.send_delay = send_delay

    def resolve_to_ir_commands(self, state_dict: dict[str, Any]):
        raw = self._engine.resolve_command(state_dict)
        parts = raw if isinstance(raw, list) else [raw]
        cmds = [
            IRCommand(name=f"cmd_{idx + 1}", payload=p, format="broadlink")
            for idx, p in enumerate(parts)
        ]
        fingerprint = "|".join(c.payload for c in cmds)
        payload_hash = hashlib.sha256(fingerprint.encode("utf-8", errors="replace")).hexdigest()[:12]
        return cmds, payload_hash

    async def async_send_commands(self, commands: list[IRCommand]) -> None:
        if self.send_delay:
            await asyncio.sleep(self.send_delay)
        for c in commands:
            self.sent_payloads.append(c.payload)
