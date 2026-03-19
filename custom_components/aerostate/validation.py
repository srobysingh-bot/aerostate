"""Shared validation state helpers for onboarding and self-test."""

from __future__ import annotations

from typing import Any

from .engines import TableEngine
from .packs.coverage import get_pack_coverage_report


def build_safe_validation_states(pack: object, profile: str = "basic") -> list[tuple[str, dict[str, Any]]]:
    """Build safe validation states based on actual pack capabilities/coverage.

    Order:
    1. off
    2. first resolvable non-off hvac/fan/temp state
    3. (full profile) one additional resolvable state if available
    """
    coverage = get_pack_coverage_report(pack)
    available_temps = list(coverage.get("available_temperature_points", []))
    first_temp = available_temps[0] if available_temps else getattr(pack, "min_temperature", 24)
    supported_modes = [
        mode for mode in list(coverage.get("supported_hvac_modes", [])) if mode != "off"
    ]
    supported_fans = list(coverage.get("supported_fan_modes", []))

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

    if not supported_modes:
        return states

    engine = TableEngine(pack)
    base_mode = supported_modes[0]
    candidates: list[tuple[str, dict[str, Any]]] = []
    fan_candidates = supported_fans if supported_fans else [None]

    for fan in fan_candidates:
        temps_to_try = available_temps if available_temps else [int(first_temp)]
        for temp in temps_to_try:
            candidate_state: dict[str, Any] = {
                "power": True,
                "hvac_mode": base_mode,
                "target_temperature": int(temp),
            }
            label = f"{base_mode}_{int(temp)}"
            if fan is not None:
                candidate_state["fan_mode"] = fan
                label = f"{base_mode}_{fan}_{int(temp)}"

            try:
                engine.resolve_command(candidate_state)
                candidates.append((label, candidate_state))
            except Exception:
                continue

    if candidates:
        states.append(candidates[0])
    if profile == "full" and len(candidates) > 1:
        states.append(candidates[1])

    return states
