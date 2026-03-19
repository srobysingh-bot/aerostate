"""Pack import and conversion utilities for command matrix ingestion.

Provides tools to convert known command matrix formats into AeroState pack format.
Supports various matrix structures (nested dicts, CSV exports, etc.).
"""

import json
from typing import Any, Dict, List, Optional, Tuple


class ImportError(Exception):
    """Error during pack import/conversion."""

    pass


def convert_flat_matrix_to_pack(
    flat_matrix: Dict[str, str],
    brand: str,
    model: str,
    min_temperature: int = 16,
    max_temperature: int = 30,
    temperature_step: int = 1,
    hvac_modes: Optional[List[str]] = None,
    fan_modes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convert a flat matrix (mode+temp -> payload) to AeroState pack.

    Input format: {"cool_18_auto": "PAYLOAD", "cool_19_auto": "PAYLOAD", ...}
    Output: Nested structure {mode: {fan: {temp: payload}}}

    Args:
        flat_matrix: Dict mapping composite key to payload
        brand: AC brand (e.g., "LG")
        model: Model name (e.g., "PC09SQ NSJ")
        min_temperature: Minimum temperature
        max_temperature: Maximum temperature
        temperature_step: Temperature granularity
        hvac_modes: List of HVAC modes to extract (if None, auto-detect)
        fan_modes: List of fan modes to extract (if None, auto-detect)

    Returns:
        AeroState pack dict
    """
    if not flat_matrix:
        raise ImportError("flat_matrix cannot be empty")

    # Auto-detect modes if not provided
    if hvac_modes is None or fan_modes is None:
        detected_hvac, detected_fan = _detect_modes_from_flat_keys(flat_matrix.keys())
        hvac_modes = hvac_modes or detected_hvac
        fan_modes = fan_modes or detected_fan

    if not hvac_modes or not fan_modes:
        raise ImportError(
            "Could not detect HVAC or fan modes. Provide them explicitly."
        )

    # Build nested structure
    commands = {}
    for key, payload in flat_matrix.items():
        # Handle "off" mode specially (direct payload)
        if key == "off":
            commands["off"] = payload
            continue

        parts = key.split("_")
        if len(parts) < 3:
            continue

        hvac_mode = parts[0]
        temp = parts[1]
        fan_mode = parts[2]

        if hvac_mode not in commands:
            commands[hvac_mode] = {}
        if fan_mode not in commands[hvac_mode]:
            commands[hvac_mode][fan_mode] = {}

        commands[hvac_mode][fan_mode][temp] = payload

    # Filter to only declared modes
    filtered_commands = {}
    for mode in hvac_modes:
        if mode in commands:
            filtered_commands[mode] = commands[mode]

    for mode in filtered_commands:
        filtered_commands[mode] = {
            fan: filtered_commands[mode][fan]
            for fan in fan_modes
            if fan in filtered_commands[mode]
        }

    if "off" not in filtered_commands and "off" in commands:
        filtered_commands["off"] = commands["off"]

    # Create pack
    pack = {
        "id": f"{brand.lower()}.{model.lower().replace(' ', '_')}.v1",
        "brand": brand,
        "models": [model],
        "transport": "broadlink_base64",
        "min_temperature": min_temperature,
        "max_temperature": max_temperature,
        "temperature_step": temperature_step,
        "verified": False,
        "notes": "Imported from external matrix. Verification required.",
        "pack_version": 1,
        "mvp_test_pack": False,
        "engine": {"type": "table"},
        "capabilities": {
            "hvac_modes": hvac_modes,
            "fan_modes": fan_modes,
            "swing_vertical_modes": [],
            "swing_horizontal_modes": [],
            "presets": [],
        },
        "commands": filtered_commands,
    }

    return pack


def _detect_modes_from_flat_keys(keys: List[str]) -> Tuple[List[str], List[str]]:
    """Auto-detect HVAC and fan modes from flat matrix keys.

    Assumes key format: "hvac_mode_temp_fan_mode" or "hvac_mode_fan_mode_temp"
    """
    hvac_modes = set()
    fan_modes = set()

    # Common mode values to recognize
    common_hvac = {"off", "cool", "heat", "dry", "fan"}
    common_fan = {"auto", "low", "mid", "medium", "high", "quiet"}

    for key in keys:
        parts = key.split("_")
        for i, part in enumerate(parts):
            if part.lower() in common_hvac:
                hvac_modes.add(part)
            if part.lower() in common_fan:
                fan_modes.add(part)

    return sorted(list(hvac_modes)), sorted(list(fan_modes))


def convert_csv_matrix_to_pack(
    csv_content: str,
    brand: str,
    model: str,
    min_temperature: int = 16,
    max_temperature: int = 30,
    temperature_step: int = 1,
) -> Dict[str, Any]:
    """Convert CSV format matrix to AeroState pack.

    CSV format:
      HVAC Mode, Fan Mode, 18, 19, 20, ..., 30
      cool,      auto,     PAYLOAD, PAYLOAD, ...
      cool,      low,      PAYLOAD, PAYLOAD, ...

    Args:
        csv_content: CSV as string
        brand: AC brand
        model: Model name
        min_temperature: Min temp
        max_temperature: Max temp
        temperature_step: Temp step

    Returns:
        AeroState pack dict
    """
    lines = csv_content.strip().split("\n")
    if not lines:
        raise ImportError("CSV content is empty")

    # Parse header
    header = lines[0].split(",")
    header = [h.strip() for h in header]

    if len(header) < 3:
        raise ImportError("CSV must have at least 3 columns (HVAC, Fan, and temps)")

    temp_columns = [int(h.strip()) for h in header[2:] if h.strip().isdigit()]

    if not temp_columns:
        raise ImportError("CSV must have numeric temperature columns")

    # Parse data
    flat_matrix = {}
    hvac_modes = set()
    fan_modes = set()

    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 3:
            continue

        hvac_mode = parts[0].strip().lower()
        fan_mode = parts[1].strip().lower()
        payloads = [p.strip() for p in parts[2:]]

        hvac_modes.add(hvac_mode)
        fan_modes.add(fan_mode)

        for temp, payload in zip(temp_columns, payloads):
            if payload and payload != "N/A" and payload != "":
                key = f"{hvac_mode}_{temp}_{fan_mode}"
                flat_matrix[key] = payload

    if not flat_matrix:
        raise ImportError("No valid payloads found in CSV")

    return convert_flat_matrix_to_pack(
        flat_matrix=flat_matrix,
        brand=brand,
        model=model,
        min_temperature=min_temperature,
        max_temperature=max_temperature,
        temperature_step=temperature_step,
        hvac_modes=sorted(list(hvac_modes)),
        fan_modes=sorted(list(fan_modes)),
    )


def validate_imported_pack(pack: Dict[str, Any]) -> List[str]:
    """Validate an imported pack for completeness and consistency.

    Args:
        pack: Pack dict to validate

    Returns:
        List of warning/error messages (empty if valid)
    """
    issues = []

    # Check required fields
    required = ["id", "brand", "models", "transport", "capabilities", "commands"]
    for field in required:
        if field not in pack:
            issues.append(f"Missing required field: {field}")

    # Check transport
    if pack.get("transport") != "broadlink_base64":
        issues.append(
            "Transport must be 'broadlink_base64' for AeroState compatibility"
        )

    # Check verified flag
    if pack.get("verified", False):
        issues.append("Imported pack must have verified=False until tested")

    # Check capabilities
    capabilities = pack.get("capabilities", {})
    hvac_modes = capabilities.get("hvac_modes", [])
    fan_modes = capabilities.get("fan_modes", [])

    if not hvac_modes:
        issues.append("No HVAC modes declared")

    if not fan_modes:
        issues.append("No fan modes declared")

    # Check command structure
    commands = pack.get("commands", {})
    for hvac_mode in hvac_modes:
        if hvac_mode == "off":
            continue
        if hvac_mode not in commands:
            issues.append(f"HVAC mode '{hvac_mode}' declared but not in commands")
        else:
            cmd_data = commands[hvac_mode]
            if not isinstance(cmd_data, dict):
                issues.append(
                    f"HVAC mode '{hvac_mode}' must be nested dict, not flat"
                )
            else:
                for fan_mode in fan_modes:
                    if fan_mode not in cmd_data:
                        issues.append(
                            f"Missing fan mode '{fan_mode}' under hvac '{hvac_mode}'"
                        )

    return issues


def export_pack_to_json_string(pack: Dict[str, Any], pretty: bool = True) -> str:
    """Export pack dict to JSON string suitable for saving.

    Args:
        pack: AeroState pack dict
        pretty: If True, use indentation for readability

    Returns:
        JSON string
    """
    if pretty:
        return json.dumps(pack, indent=2, ensure_ascii=False)
    return json.dumps(pack, ensure_ascii=False)
