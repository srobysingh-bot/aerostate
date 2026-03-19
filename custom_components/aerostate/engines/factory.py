"""Factory helpers for selecting the right state engine per pack."""

from __future__ import annotations

from .base import StateEngine
from .lg_engine import LGProtocolEngine
from .table_engine import TableEngine


def create_engine(pack: object) -> StateEngine:
    """Create an engine instance based on pack.engine_type."""
    engine_type = str(getattr(pack, "engine_type", "table") or "table")
    if engine_type == "table":
        return TableEngine(pack)
    if engine_type == "lg_protocol":
        return LGProtocolEngine(pack)
    raise ValueError(f"Unsupported engine type '{engine_type}'")
