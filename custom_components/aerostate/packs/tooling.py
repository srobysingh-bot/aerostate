"""Pack tooling helpers for validation and coverage reporting."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .schema import ModelPack


def _walk_temp_leaves(node: Any, path: list[str], out: list[tuple[list[str], int]]) -> None:
    """Collect temperature leaves as (path_without_temp, temperature)."""
    if not isinstance(node, dict):
        return

    for key, value in node.items():
        if isinstance(key, str) and key.isdigit() and isinstance(value, str):
            out.append((path.copy(), int(key)))
            continue
        if isinstance(key, str):
            path.append(key)
            _walk_temp_leaves(value, path, out)
            path.pop()


def validate_pack_coverage(pack: ModelPack) -> list[str]:
    """Validate pack command matrix and return human-readable issues."""
    issues: list[str] = []
    expected_temps = set(range(pack.min_temperature, pack.max_temperature + 1))

    for hvac_mode in pack.capabilities.hvac_modes:
        mode_node = pack.commands.get(hvac_mode)
        if not isinstance(mode_node, dict):
            issues.append(f"Missing command tree for hvac mode '{hvac_mode}'")
            continue

        temp_leaves: list[tuple[list[str], int]] = []
        _walk_temp_leaves(mode_node, [], temp_leaves)

        if not temp_leaves:
            issues.append(f"No temperature leaves found for hvac mode '{hvac_mode}'")
            continue

        branch_to_temps: dict[tuple[str, ...], set[int]] = defaultdict(set)
        for branch, temp in temp_leaves:
            branch_to_temps[tuple(branch)].add(temp)

        for branch, seen_temps in branch_to_temps.items():
            missing = sorted(expected_temps - seen_temps)
            if missing:
                issues.append(
                    f"Missing temperatures for mode '{hvac_mode}' branch '{'/'.join(branch) or '<root>'}': {missing}"
                )

            # For current table engine support, path depth before temperature should be <= 3:
            # fan | vertical/fan | vertical/horizontal/fan
            if len(branch) > 3:
                issues.append(
                    f"Unsupported swing tree depth for mode '{hvac_mode}' branch '{'/'.join(branch)}'"
                )

        if pack.capabilities.fan_modes:
            top_keys = {k for k, v in mode_node.items() if isinstance(v, dict)}
            missing_fans = sorted(set(pack.capabilities.fan_modes) - top_keys)
            # Only flag missing top-level fan branches when tree appears to be fan-first.
            if top_keys & set(pack.capabilities.fan_modes) and missing_fans:
                issues.append(
                    f"Missing fan branches for mode '{hvac_mode}': {missing_fans}"
                )

    return issues


def get_pack_coverage_report(pack: ModelPack) -> dict[str, Any]:
    """Return a compact coverage report for a model pack."""
    expected_temps = list(range(pack.min_temperature, pack.max_temperature + 1))
    per_mode: dict[str, Any] = {}

    for hvac_mode in pack.capabilities.hvac_modes:
        mode_node = pack.commands.get(hvac_mode)
        temp_leaves: list[tuple[list[str], int]] = []
        _walk_temp_leaves(mode_node, [], temp_leaves)

        branch_to_temps: dict[str, list[int]] = defaultdict(list)
        for branch, temp in temp_leaves:
            key = "/".join(branch) or "<root>"
            branch_to_temps[key].append(temp)

        per_mode[hvac_mode] = {
            "branches": {
                branch: {
                    "temperatures": sorted(set(temps)),
                    "missing": sorted(set(expected_temps) - set(temps)),
                    "count": len(set(temps)),
                }
                for branch, temps in branch_to_temps.items()
            },
            "branch_count": len(branch_to_temps),
        }

    issues = validate_pack_coverage(pack)
    return {
        "pack_id": pack.pack_id,
        "mvp_test_pack": pack.mvp_test_pack,
        "temperature_range": [pack.min_temperature, pack.max_temperature],
        "modes": per_mode,
        "issues": issues,
        "is_complete": len(issues) == 0,
    }
