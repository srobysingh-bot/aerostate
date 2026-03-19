"""Coverage and validation helpers for model packs."""

from __future__ import annotations

from typing import Any

from .schema import ModelPack


def _walk(node: Any, path: list[str], points: list[tuple[list[str], int]]) -> None:
    """Walk a command tree and capture numeric temperature leaves."""
    if not isinstance(node, dict):
        return

    for key, value in node.items():
        if isinstance(key, str) and key.isdigit() and isinstance(value, str):
            points.append((path.copy(), int(key)))
            continue
        if isinstance(key, str):
            path.append(key)
            _walk(value, path, points)
            path.pop()


def _collect_temperature_points(pack: ModelPack) -> list[int]:
    """Collect all available temperature points in the pack."""
    points: list[tuple[list[str], int]] = []
    for mode in pack.capabilities.hvac_modes:
        _walk(pack.commands.get(mode), [], points)
    return sorted({temp for _, temp in points})


def _swing_tree_exists(pack: ModelPack, horizontal: bool = False) -> bool:
    """Detect whether swing trees are present in commands."""
    swing_values = (
        pack.capabilities.swing_horizontal_modes
        if horizontal
        else pack.capabilities.swing_vertical_modes
    )
    if not swing_values:
        return False

    expected = set(swing_values)
    for mode in pack.capabilities.hvac_modes:
        node = pack.commands.get(mode)
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in expected and isinstance(value, dict):
                return True
            if isinstance(value, dict):
                for sub_key in value.keys():
                    if sub_key in expected:
                        return True
    return False


def validate_pack_coverage(pack: ModelPack) -> list[str]:
    """Validate coverage and return human-readable issue list."""
    issues: list[str] = []

    expected_temps = set(range(pack.min_temperature, pack.max_temperature + 1))
    available = set(_collect_temperature_points(pack))
    missing = sorted(expected_temps - available)
    if missing:
        issues.append(f"Missing temperatures in expected range: {missing}")

    for mode in pack.capabilities.hvac_modes:
        mode_node = pack.commands.get(mode)
        if not isinstance(mode_node, dict):
            issues.append(f"Missing command tree for hvac mode '{mode}'")
            continue

        if pack.capabilities.fan_modes:
            fan_keys = [k for k, v in mode_node.items() if isinstance(v, dict)]
            fan_overlap = set(fan_keys) & set(pack.capabilities.fan_modes)
            if fan_overlap:
                missing_fans = sorted(set(pack.capabilities.fan_modes) - set(fan_keys))
                if missing_fans:
                    issues.append(f"Missing fan branches for mode '{mode}': {missing_fans}")

        points: list[tuple[list[str], int]] = []
        _walk(mode_node, [], points)
        for branch, _ in points:
            if len(branch) > 3:
                issues.append(
                    f"Unsupported swing tree depth in mode '{mode}' branch '{'/'.join(branch)}'"
                )

    return issues


def get_pack_coverage_report(pack: ModelPack) -> dict[str, Any]:
    """Return pack coverage summary for diagnostics/tooling."""
    temps = _collect_temperature_points(pack)
    expected = set(range(pack.min_temperature, pack.max_temperature + 1))
    missing = sorted(expected - set(temps))

    report = {
        "pack_id": pack.pack_id,
        "pack_version": pack.pack_version,
        "verified": pack.verified,
        "notes": pack.notes,
        "supported_hvac_modes": pack.capabilities.hvac_modes,
        "supported_fan_modes": pack.capabilities.fan_modes,
        "available_temperature_points": temps,
        "missing_temperature_gaps": missing,
        "has_vertical_swing_tree": _swing_tree_exists(pack, horizontal=False),
        "has_horizontal_swing_tree": _swing_tree_exists(pack, horizontal=True),
        "swing_vertical_support": _swing_tree_exists(pack, horizontal=False),
        "swing_horizontal_support": _swing_tree_exists(pack, horizontal=True),
    }
    report["issues"] = validate_pack_coverage(pack)
    report["is_complete"] = len(report["issues"]) == 0
    return report
