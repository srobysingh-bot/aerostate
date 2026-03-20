"""Shared validation state helpers for onboarding and self-test."""

from __future__ import annotations

from typing import Any

from .engines import create_engine
from .packs.coverage import get_pack_coverage_report


def build_safe_validation_states(pack: object, profile: str = "basic") -> list[tuple[str, dict[str, Any]]]:
    """Build safe validation states based on actual pack capabilities/coverage.

    Order:
    1. off
    2. one resolvable command per supported non-off HVAC mode
    3. (full profile) one extra resolvable command per mode when possible
    """
    coverage = get_pack_coverage_report(pack)
    available_temps = list(coverage.get("available_temperature_points", []))
    temps_by_mode = dict(coverage.get("available_temperatures_by_mode", {}))
    first_temp = available_temps[0] if available_temps else getattr(pack, "min_temperature", 24)
    supported_modes = [
        mode for mode in list(coverage.get("supported_hvac_modes", [])) if mode != "off"
    ]
    supported_fans = list(coverage.get("supported_fan_modes", []))
    swing_by_mode = dict(coverage.get("swing_support_by_mode", {}))

    states: list[tuple[str, dict[str, Any]]] = [
        (
            "off",
            {
                "power": False,
                "hvac_mode": "off",
                "target_temperature": int(first_temp),
            },
        )
    ]

    engine = create_engine(pack)
    for mode in supported_modes:
        mode_candidates: list[tuple[str, dict[str, Any]]] = []
        mode_temps = list(temps_by_mode.get(mode, [])) or (available_temps if available_temps else [int(first_temp)])
        fan_candidates = supported_fans if supported_fans else [None]
        swing_cfg = swing_by_mode.get(mode, {})
        use_vertical = bool(swing_cfg.get("vertical"))
        use_horizontal = bool(swing_cfg.get("horizontal"))
        swing_vertical_values = list(getattr(pack.capabilities, "swing_vertical_modes", []))
        swing_horizontal_values = list(getattr(pack.capabilities, "swing_horizontal_modes", []))
        preset_values = list(getattr(pack.capabilities, "preset_modes", []) or getattr(pack.capabilities, "presets", []))
        preset_candidates = [None]
        if preset_values:
            preset_candidates.append(preset_values[0])
            if profile == "full" and len(preset_values) > 1:
                preset_candidates.append(preset_values[1])

        for fan in fan_candidates:
            for temp in mode_temps:
                for preset in preset_candidates:
                    candidate_state: dict[str, Any] = {
                        "power": True,
                        "hvac_mode": mode,
                        "target_temperature": int(temp),
                    }
                    label = f"{mode}_{int(temp)}"
                    if fan is not None:
                        candidate_state["fan_mode"] = fan
                        label = f"{mode}_{fan}_{int(temp)}"

                    if preset is not None:
                        candidate_state["preset_mode"] = preset
                        label = f"{label}_{preset}"

                    if use_vertical and swing_vertical_values:
                        candidate_state["swing_vertical"] = swing_vertical_values[0]
                        label = f"{label}_sv"
                    if use_horizontal and swing_horizontal_values:
                        candidate_state["swing_horizontal"] = swing_horizontal_values[0]
                        label = f"{label}_sh"

                    try:
                        engine.resolve_command(candidate_state)
                        mode_candidates.append((label, candidate_state))
                    except Exception:
                        continue

        if mode_candidates:
            states.append(mode_candidates[0])
            if profile == "full" and len(mode_candidates) > 1:
                states.append(mode_candidates[1])

    return states
