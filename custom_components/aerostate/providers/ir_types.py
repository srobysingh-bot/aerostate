"""Unified IR command types for multi-transport backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IRFormat = Literal["broadlink", "tuya"]


@dataclass(frozen=True, slots=True)
class IRCommand:
    """Single IR transmission intent for a specific backend format."""

    name: str
    payload: str
    format: IRFormat
