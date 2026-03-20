"""Load and validate model packs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import ModelPack, PackCapabilities


def _ensure_list_of_strings(value: Any, field_name: str) -> None:
    """Validate a field is a list of strings."""
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"'{field_name}' must be a list of strings")


def _ensure_dict_of_strings(value: Any, field_name: str) -> None:
    """Validate a field is a dictionary of string keys and values."""
    if not isinstance(value, dict):
        raise ValueError(f"'{field_name}' must be an object with string values")
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError(f"'{field_name}' must contain only string keys and values")


def validate_pack_dict(data: dict[str, Any]) -> None:
    """Validate pack dictionary has required keys.

    Args:
        data: Dictionary to validate

    Raises:
        ValueError: If required keys are missing
    """
    required_keys = {
        "id",
        "brand",
        "pack_version",
        "models",
        "transport",
        "capabilities",
        "commands",
        "min_temperature",
        "max_temperature",
    }
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(f"Pack missing required keys: {sorted(missing)}")

    if not isinstance(data["id"], str) or not data["id"].strip():
        raise ValueError("'id' must be a non-empty string")
    if not isinstance(data["brand"], str) or not data["brand"].strip():
        raise ValueError("'brand' must be a non-empty string")
    if not isinstance(data["pack_version"], int) or data["pack_version"] < 1:
        raise ValueError("'pack_version' must be an integer >= 1")
    _ensure_list_of_strings(data["models"], "models")
    if not isinstance(data["transport"], str) or not data["transport"].strip():
        raise ValueError("'transport' must be a non-empty string")
    if not isinstance(data["commands"], dict) or not data["commands"]:
        raise ValueError("'commands' must be a non-empty object")

    min_temp = data["min_temperature"]
    max_temp = data["max_temperature"]
    if not isinstance(min_temp, int) or not isinstance(max_temp, int):
        raise ValueError("'min_temperature' and 'max_temperature' must be integers")
    if min_temp > max_temp:
        raise ValueError("'min_temperature' must be less than or equal to 'max_temperature'")

    step = data.get("temperature_step", 1)
    if not isinstance(step, (int, float)) or step <= 0:
        raise ValueError("'temperature_step' must be a positive number when provided")

    verified = data.get("verified", False)
    if not isinstance(verified, bool):
        raise ValueError("'verified' must be a boolean when provided")

    notes = data.get("notes", "")
    if not isinstance(notes, str):
        raise ValueError("'notes' must be a string when provided")

    physically_verified_modes = data.get("physically_verified_modes", [])
    _ensure_list_of_strings(physically_verified_modes, "physically_verified_modes")

    mode_status = data.get("mode_status", {})
    _ensure_dict_of_strings(mode_status, "mode_status")

    # Validate capabilities structure
    if not isinstance(data.get("capabilities"), dict):
        raise ValueError("Capabilities must be a dictionary")

    cap_required = {
        "hvac_modes",
        "fan_modes",
        "swing_vertical_modes",
        "swing_horizontal_modes",
        "presets",
    }
    cap_missing = cap_required - set(data["capabilities"].keys())
    if cap_missing:
        raise ValueError(f"Capabilities missing required keys: {sorted(cap_missing)}")

    cap_data = data["capabilities"]
    for key in cap_required:
        _ensure_list_of_strings(cap_data[key], f"capabilities.{key}")

    if "preset_modes" in cap_data:
        _ensure_list_of_strings(cap_data["preset_modes"], "capabilities.preset_modes")

    supports_jet = cap_data.get("supports_jet", False)
    if not isinstance(supports_jet, bool):
        raise ValueError("'capabilities.supports_jet' must be a boolean when provided")
    declared_presets = cap_data.get("preset_modes", cap_data["presets"])
    if supports_jet and "jet" not in declared_presets:
        raise ValueError("'capabilities.supports_jet' requires 'jet' in preset_modes/presets")

    if "off" in cap_data["hvac_modes"]:
        raise ValueError("capabilities.hvac_modes must not contain 'off'; OFF is managed by ClimateEntity")

    mode_set = set(cap_data["hvac_modes"])
    unknown_verified = [mode for mode in physically_verified_modes if mode not in mode_set]
    if unknown_verified:
        raise ValueError("'physically_verified_modes' contains unsupported modes")

    unknown_status_modes = [mode for mode in mode_status.keys() if mode not in mode_set]
    if unknown_status_modes:
        raise ValueError("'mode_status' contains unsupported modes")

    if data["transport"] != "broadlink_base64":
        raise ValueError("Only 'broadlink_base64' transport is currently supported")

    engine_data = data.get("engine", {})
    if engine_data is None:
        engine_data = {}
    if not isinstance(engine_data, dict):
        raise ValueError("'engine' must be an object when provided")

    engine_type = engine_data.get("type", "table")
    if engine_type not in {"table", "lg_protocol"}:
        raise ValueError(
            f"Unsupported engine type '{engine_type}'. Supported: table, lg_protocol"
        )

    if "off" not in data["commands"]:
        raise ValueError("commands.off is required")


def load_pack_from_path(path: str) -> ModelPack:
    """Load and validate a model pack from JSON file.

    Args:
        path: Path to JSON pack file

    Returns:
        ModelPack instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If pack is invalid
        json.JSONDecodeError: If JSON is malformed
    """
    pack_path = Path(path)
    if not pack_path.exists():
        raise FileNotFoundError(f"Pack file not found: {path}")

    with open(pack_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    validate_pack_dict(data)

    # Parse engine type
    engine_data = data.get("engine", {})
    if engine_data is None:
        engine_data = {}
    engine_type = engine_data.get("type", "table")

    # Create capabilities
    cap_data = data["capabilities"]
    capabilities = PackCapabilities(
        hvac_modes=cap_data["hvac_modes"],
        fan_modes=cap_data["fan_modes"],
        swing_vertical_modes=cap_data["swing_vertical_modes"],
        swing_horizontal_modes=cap_data["swing_horizontal_modes"],
        presets=cap_data["presets"],
        preset_modes=cap_data.get("preset_modes", cap_data["presets"]),
        supports_jet=bool(cap_data.get("supports_jet", "jet" in cap_data.get("preset_modes", cap_data["presets"]))),
    )

    # Create and return pack
    return ModelPack(
        pack_id=data["id"],
        brand=data["brand"],
        pack_version=data["pack_version"],
        models=data["models"],
        transport=data["transport"],
        min_temperature=data["min_temperature"],
        max_temperature=data["max_temperature"],
        capabilities=capabilities,
        engine_type=engine_type,
        commands=data["commands"],
        temperature_step=float(data.get("temperature_step", 1)),
        verified=bool(data.get("verified", False)),
        notes=str(data.get("notes", "")),
        mvp_test_pack=bool(data.get("mvp_test_pack", False)),
        physically_verified_modes=list(data.get("physically_verified_modes", [])),
        mode_status=dict(data.get("mode_status", {})),
    )
