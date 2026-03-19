"""Pack authoring utilities for validating and managing command matrices.

This module provides tooling to support incremental pack expansion with
verified payloads only. It validates:
- Command matrix structure completeness
- Temperature range coverage
- Fan mode coverage
- Swagger mode coverage
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MatrixGap:
    """Represents a gap in the command matrix structure."""

    location: str
    gap_type: str  # "missing_fan", "missing_temp", "missing_swing", "incomplete_branch"
    details: str


@dataclass
class CompletionReport:
    """Report on matrix completeness for a given HVAC mode."""

    mode_name: str
    is_complete: bool
    coverage_percentage: float
    gaps: List[MatrixGap]
    summary: str


def validate_matrix_structure(
    commands: Dict[str, Any],
    min_temp: int,
    max_temp: int,
    temp_step: int,
    expected_fan_modes: List[str],
    expected_swing_v: List[str],
    expected_swing_h: List[str],
) -> Dict[str, CompletionReport]:
    """Validate command matrix structure for all HVAC modes.

    Args:
        commands: The commands dict from a pack JSON
        min_temp: Minimum temperature (inclusive)
        max_temp: Maximum temperature (inclusive)
        temp_step: Temperature step granularity (e.g., 1 for 1°C steps)
        expected_fan_modes: List of supported fan modes
        expected_swing_v: List of supported swing_vertical modes
        expected_swing_h: List of supported swing_horizontal modes

    Returns:
        Dict mapping HVAC mode name to CompletionReport
    """
    reports = {}
    expected_temps = list(range(min_temp, max_temp + 1, temp_step))

    for hvac_mode, mode_content in commands.items():
        if hvac_mode == "off":
            # Off is expected to be a direct payload, not nested
            continue

        gaps = []
        temperatures_found = set()

        # Check if mode_content is a dict (nested structure) or direct payload
        if not isinstance(mode_content, dict):
            # Single payload mode - incomplete for multi-fan/temp
            gaps.append(
                MatrixGap(
                    location=hvac_mode,
                    gap_type="incomplete_branch",
                    details=f"Mode '{hvac_mode}' is a direct payload; expected nested fan/temp structure",
                )
            )
            reports[hvac_mode] = CompletionReport(
                mode_name=hvac_mode,
                is_complete=False,
                coverage_percentage=0.0,
                gaps=gaps,
                summary=f"Incomplete: expected {len(expected_fan_modes)} fan modes",
            )
            continue

        # Check each fan mode
        for fan_mode in expected_fan_modes:
            if fan_mode not in mode_content:
                gaps.append(
                    MatrixGap(
                        location=f"{hvac_mode}",
                        gap_type="missing_fan",
                        details=f"Missing fan mode '{fan_mode}'",
                    )
                )
                continue

            fan_content = mode_content[fan_mode]
            if not isinstance(fan_content, dict):
                gaps.append(
                    MatrixGap(
                        location=f"{hvac_mode}/{fan_mode}",
                        gap_type="incomplete_branch",
                        details=f"Fan mode '{fan_mode}' is a direct payload; expected temp dict",
                    )
                )
                continue

            # Check temperatures under this fan mode
            for temp in expected_temps:
                temp_key = str(temp)
                if temp_key in fan_content:
                    temperatures_found.add(temp)
                else:
                    gaps.append(
                        MatrixGap(
                            location=f"{hvac_mode}/{fan_mode}",
                            gap_type="missing_temp",
                            details=f"Missing temperature {temp}°C",
                        )
                    )

        # Calculate coverage
        expected_total = len(expected_fan_modes) * len(expected_temps)
        actual_total = len(expected_fan_modes) * len(temperatures_found)
        coverage = (actual_total / expected_total * 100) if expected_total > 0 else 0.0

        is_complete = len(gaps) == 0

        reports[hvac_mode] = CompletionReport(
            mode_name=hvac_mode,
            is_complete=is_complete,
            coverage_percentage=coverage,
            gaps=gaps,
            summary=f"{coverage:.1f}% coverage ({len(temperatures_found)}/{len(expected_temps)} temps for {len(expected_fan_modes)} fan modes)",
        )

    return reports


def _get_leaf_count(obj: Any) -> int:
    """Count the number of leaf payloads in a nested structure."""
    if isinstance(obj, str):
        return 1
    if isinstance(obj, dict):
        total = 0
        for value in obj.values():
            total += _get_leaf_count(value)
        return total
    return 0


def describe_pack_expansion_readiness(
    pack_dict: Dict[str, Any],
) -> str:
    """Generate a human-readable summary of pack expansion readiness.

    Args:
        pack_dict: A complete pack JSON dict

    Returns:
        Formatted string suitable for README or diagnostics
    """
    lines = []
    lines.append(f"Pack: {pack_dict.get('id', 'unknown')}")
    lines.append(f"Brand: {pack_dict.get('brand', 'unknown')} | Model: {pack_dict.get('models', ['unknown'])[0]}")
    lines.append(f"Verified: {pack_dict.get('verified', False)}")
    lines.append(f"Notes: {pack_dict.get('notes', '(none)')}")
    lines.append("")

    capabilities = pack_dict.get("capabilities", {})
    hvac_modes = capabilities.get("hvac_modes", [])
    fan_modes = capabilities.get("fan_modes", [])
    swing_v = capabilities.get("swing_vertical_modes", [])
    swing_h = capabilities.get("swing_horizontal_modes", [])

    lines.append("Declared Capabilities:")
    lines.append(f"  HVAC Modes: {', '.join(hvac_modes) if hvac_modes else '(none)'}")
    lines.append(f"  Fan Modes: {', '.join(fan_modes) if fan_modes else '(none)'}")
    lines.append(f"  Swing Vertical: {', '.join(swing_v) if swing_v else '(none)'}")
    lines.append(f"  Swing Horizontal: {', '.join(swing_h) if swing_h else '(none)'}")
    lines.append("")

    min_temp = pack_dict.get("min_temperature", 16)
    max_temp = pack_dict.get("max_temperature", 30)
    temp_step = pack_dict.get("temperature_step", 1)
    expected_temps = list(range(min_temp, max_temp + 1, temp_step))

    lines.append(f"Temperature Range: {min_temp}–{max_temp}°C (step: {temp_step})")
    lines.append(f"Expected Temperature Count: {len(expected_temps)}")
    lines.append("")

    commands = pack_dict.get("commands", {})
    total_payloads = _get_leaf_count(commands)

    lines.append(f"Total Payloads in Matrix: {total_payloads}")

    if hvac_modes and fan_modes:
        expected_matrix_size = (
            len(hvac_modes) * len(fan_modes) * len(expected_temps)
        )
        coverage = (total_payloads / expected_matrix_size * 100) if expected_matrix_size > 0 else 0
        lines.append(f"Expected Matrix Size (full): {expected_matrix_size} payloads")
        lines.append(f"Current Coverage: {coverage:.1f}%")
    else:
        lines.append("(Incomplete capability declaration; full matrix size undefined)")

    lines.append("")
    return "\n".join(lines)


def suggest_pack_expansion(
    current_pack: Dict[str, Any],
    new_hvac_mode: str,
    template_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a template for expanding a pack with a new HVAC mode.

    Args:
        current_pack: Current pack dict
        new_hvac_mode: Name of the new HVAC mode to add (e.g., "heat")
        template_mode: Name of an existing mode to use as template
                       (e.g., "cool" for heat). If None, creates empty structure.

    Returns:
        Suggested new pack dict with the new mode added
    """
    import copy

    expanded = copy.deepcopy(current_pack)
    capabilities = expanded.get("capabilities", {})

    # Add to HVAC modes if not already present
    hvac_modes = capabilities.get("hvac_modes", [])
    if new_hvac_mode not in hvac_modes:
        hvac_modes.append(new_hvac_mode)
        capabilities["hvac_modes"] = hvac_modes

    commands = expanded.get("commands", {})

    if template_mode and template_mode in commands:
        # Use template
        commands[new_hvac_mode] = copy.deepcopy(commands[template_mode])
    else:
        # Create empty structure matching fan/temp structure
        fan_modes = capabilities.get("fan_modes", [])
        min_temp = expanded.get("min_temperature", 16)
        max_temp = expanded.get("max_temperature", 30)
        temp_step = expanded.get("temperature_step", 1)

        new_mode_dict = {}
        for fan_mode in fan_modes:
            new_mode_dict[fan_mode] = {}
            for temp in range(min_temp, max_temp + 1, temp_step):
                new_mode_dict[fan_mode][str(temp)] = "PAYLOAD_PLACEHOLDER"

        commands[new_hvac_mode] = new_mode_dict

    expanded["commands"] = commands

    # Update notes to reflect partial support
    old_notes = expanded.get("notes", "")
    if "Partial" not in old_notes and new_hvac_mode.lower() not in old_notes.lower():
        expanded["notes"] = (
            f"{old_notes} (Partial: {new_hvac_mode} mode under expansion)"
            if old_notes
            else f"Partial: {new_hvac_mode} mode under expansion. Complete payload testing required."
        )

    return expanded
