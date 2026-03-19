"""Data schema for model packs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PackCapabilities:
    """Capabilities supported by a model pack."""

    hvac_modes: list[str]
    fan_modes: list[str]
    swing_vertical_modes: list[str]
    swing_horizontal_modes: list[str]
    presets: list[str]


@dataclass
class ModelPack:
    """Complete model pack definition."""

    pack_id: str
    brand: str
    models: list[str]
    transport: str
    pack_version: int
    min_temperature: int
    max_temperature: int
    capabilities: PackCapabilities
    engine_type: str
    commands: dict[str, Any]
    temperature_step: float = 1.0
    verified: bool = False
    notes: str = ""
    mvp_test_pack: bool = False
    physically_verified_modes: list[str] = field(default_factory=list)
    mode_status: dict[str, str] = field(default_factory=dict)
