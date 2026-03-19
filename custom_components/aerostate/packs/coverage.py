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


def _walk_mode(node: Any, path: list[str], leaves: list[list[str]]) -> None:
    """Walk a command tree and collect full key paths to string payload leaves."""
    if isinstance(node, str):
        leaves.append(path.copy())
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if isinstance(key, str):
            path.append(key)
            _walk_mode(value, path, leaves)
            path.pop()


def _collect_temperature_points(pack: ModelPack) -> list[int]:
    """Collect all available temperature points in the pack."""
    points: list[tuple[list[str], int]] = []
    for mode in pack.capabilities.hvac_modes:
        _walk(pack.commands.get(mode), [], points)
    return sorted({temp for _, temp in points})


def _collect_mode_temperature_points(mode_node: Any) -> list[int]:
    """Collect available temperature points for one HVAC mode node."""
    points: list[tuple[list[str], int]] = []
    _walk(mode_node, [], points)
    return sorted({temp for _, temp in points})


def _collect_mode_swing_support(pack: ModelPack, mode: str) -> dict[str, bool]:
    """Detect whether a mode has vertical/horizontal swing branches in the command tree."""
    mode_node = pack.commands.get(mode)
    leaves: list[list[str]] = []
    _walk_mode(mode_node, [], leaves)

    vertical = set(pack.capabilities.swing_vertical_modes)
    horizontal = set(pack.capabilities.swing_horizontal_modes)

    has_vertical = False
    has_horizontal = False

    for path in leaves:
        keys = set(path)
        if vertical and keys & vertical:
            has_vertical = True
        if horizontal and keys & horizontal:
            has_horizontal = True

    return {
        "vertical": has_vertical,
        "horizontal": has_horizontal,
    }


def _collect_mode_fan_branches(mode_node: Any, fan_modes: list[str]) -> list[str]:
    """Collect fan branches present for a mode at any depth of the command tree."""
    if not isinstance(mode_node, dict):
        return []

    found: set[str] = set()

    def _recurse(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key in fan_modes and isinstance(value, dict):
                found.add(key)
            _recurse(value)

    _recurse(mode_node)
    return sorted(found)


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
    if pack.engine_type != "table":
        return []

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
            fan_keys = _collect_mode_fan_branches(mode_node, pack.capabilities.fan_modes)
            if fan_keys:
                missing_fans = sorted(set(pack.capabilities.fan_modes) - set(fan_keys))
                if missing_fans:
                    issues.append(f"Missing fan branches for mode '{mode}': {missing_fans}")
            else:
                issues.append(
                    f"Missing fan branches for mode '{mode}'. Expected any of: {pack.capabilities.fan_modes}"
                )

        points: list[tuple[list[str], int]] = []
        _walk(mode_node, [], points)
        mode_temps = sorted({temp for _, temp in points})
        missing_mode_temps = sorted(expected_temps - set(mode_temps))
        if missing_mode_temps:
            issues.append(
                f"Missing temperatures for mode '{mode}': {missing_mode_temps}"
            )

        for branch, _ in points:
            if len(branch) > 3:
                issues.append(
                    f"Unsupported swing tree depth in mode '{mode}' branch '{'/'.join(branch)}'"
                )

    return issues


def get_pack_coverage_report(pack: ModelPack) -> dict[str, Any]:
    """Return pack coverage summary for diagnostics/tooling."""
    if pack.engine_type != "table":
        temps = list(range(pack.min_temperature, pack.max_temperature + 1))
        mode_matrix = {
            mode: {
                "fan_branches": list(pack.capabilities.fan_modes),
                "available_temperature_points": list(temps),
                "missing_temperature_points": [],
                "swing": {
                    "vertical": bool(pack.capabilities.swing_vertical_modes),
                    "horizontal": bool(pack.capabilities.swing_horizontal_modes),
                },
                "has_command_tree": True,
            }
            for mode in pack.capabilities.hvac_modes
        }
        return {
            "pack_id": pack.pack_id,
            "pack_version": pack.pack_version,
            "verified": pack.verified,
            "notes": pack.notes,
            "supported_hvac_modes": pack.capabilities.hvac_modes,
            "supported_fan_modes": pack.capabilities.fan_modes,
            "available_temperature_points": temps,
            "available_temperatures_by_mode": {
                mode: list(temps) for mode in pack.capabilities.hvac_modes
            },
            "missing_temperature_gaps": [],
            "has_vertical_swing_tree": bool(pack.capabilities.swing_vertical_modes),
            "has_horizontal_swing_tree": bool(pack.capabilities.swing_horizontal_modes),
            "swing_vertical_support": bool(pack.capabilities.swing_vertical_modes),
            "swing_horizontal_support": bool(pack.capabilities.swing_horizontal_modes),
            "swing_support_by_mode": {
                mode: {
                    "vertical": bool(pack.capabilities.swing_vertical_modes),
                    "horizontal": bool(pack.capabilities.swing_horizontal_modes),
                }
                for mode in pack.capabilities.hvac_modes
            },
            "mode_matrix": mode_matrix,
            "issues": [],
            "is_complete": True,
        }

    temps = _collect_temperature_points(pack)
    expected = set(range(pack.min_temperature, pack.max_temperature + 1))
    missing = sorted(expected - set(temps))

    mode_matrix: dict[str, Any] = {}
    for mode in pack.capabilities.hvac_modes:
        mode_node = pack.commands.get(mode)
        temps_by_mode = _collect_mode_temperature_points(mode_node)
        mode_matrix[mode] = {
            "fan_branches": _collect_mode_fan_branches(mode_node, pack.capabilities.fan_modes),
            "available_temperature_points": temps_by_mode,
            "missing_temperature_points": sorted(expected - set(temps_by_mode)),
            "swing": _collect_mode_swing_support(pack, mode),
            "has_command_tree": isinstance(mode_node, dict),
        }

    report = {
        "pack_id": pack.pack_id,
        "pack_version": pack.pack_version,
        "verified": pack.verified,
        "notes": pack.notes,
        "supported_hvac_modes": pack.capabilities.hvac_modes,
        "supported_fan_modes": pack.capabilities.fan_modes,
        "available_temperature_points": temps,
        "available_temperatures_by_mode": {
            mode: data["available_temperature_points"] for mode, data in mode_matrix.items()
        },
        "missing_temperature_gaps": missing,
        "has_vertical_swing_tree": _swing_tree_exists(pack, horizontal=False),
        "has_horizontal_swing_tree": _swing_tree_exists(pack, horizontal=True),
        "swing_vertical_support": _swing_tree_exists(pack, horizontal=False),
        "swing_horizontal_support": _swing_tree_exists(pack, horizontal=True),
        "swing_support_by_mode": {
            mode: data["swing"] for mode, data in mode_matrix.items()
        },
        "mode_matrix": mode_matrix,
    }
    report["issues"] = validate_pack_coverage(pack)
    report["is_complete"] = len(report["issues"]) == 0
    return report
