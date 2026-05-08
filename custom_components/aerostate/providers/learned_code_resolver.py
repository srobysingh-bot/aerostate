"""Map AeroState climate states to learned localtuya_rc command names."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

FAN_TO_SUFFIX: dict[str, str | None] = {
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "auto": None,
    "low": "f1",
    "mid": "f3",
    "high": "f5",
}

FAN_ONLY_MAP: dict[str, str] = {
    "f1": "fan_speed_1",
    "f2": "fan_speed_2",
    "f3": "fan_speed_3",
    "f4": "fan_speed_4",
    "f5": "fan_speed_5",
    "auto": "fan_speed_3",
    "low": "fan_speed_1",
    "mid": "fan_speed_3",
    "high": "fan_speed_5",
}


class LearnedCodeNotAvailable(KeyError):
    """Raised when no learned code covers the requested state."""


def resolve_learned_code(learned_codes: dict[str, str], state: dict[str, Any]) -> str:
    """Resolve a climate state dictionary to a learned raw IR string."""
    hvac_mode = state.get("hvac_mode", "off")
    temp = state.get("target_temperature")
    fan = state.get("fan_mode") or "auto"

    if hvac_mode == "off":
        code = learned_codes.get("power_off")
        if code:
            return code
        raise LearnedCodeNotAvailable(
            "power_off not learned. Point AC remote at IR blaster and run "
            "remote.learn_command for 'power_off'.",
        )

    if hvac_mode in ("fan_only", "fan"):
        fan_key = FAN_ONLY_MAP.get(fan, "fan_speed_3")
        code = learned_codes.get(fan_key)
        if code:
            _LOGGER.debug("fan_only resolved via %s", fan_key)
            return code
        for fallback in ("fan_speed_1", "fan_speed_2", "fan_speed_3"):
            code = learned_codes.get(fallback)
            if code:
                _LOGGER.warning("fan_only: requested fan=%s not found, using %s as fallback", fan, fallback)
                return code
        raise LearnedCodeNotAvailable("No fan_speed codes learned for fan_only mode. Learn fan_speed_1 through fan_speed_5.")

    if hvac_mode == "cool":
        if temp is None:
            temp = 24
        temp = int(temp)
        if not (16 <= temp <= 30):
            raise LearnedCodeNotAvailable(f"Temperature {temp}C out of range 16-30.")

        fan_suffix = FAN_TO_SUFFIX.get(fan)
        if fan_suffix:
            exact_key = f"temp_{temp}_{fan_suffix}"
            code = learned_codes.get(exact_key)
            if code:
                _LOGGER.debug("cool resolved via exact key %s", exact_key)
                return code

        temp_key = f"temp_{temp}"
        code = learned_codes.get(temp_key)
        if code:
            _LOGGER.warning(
                "cool %dC fan=%s: exact code not learned, falling back to %s (auto fan)",
                temp,
                fan,
                temp_key,
            )
            return code

        for fallback_temp in _nearest_temps(temp):
            fallback_key = f"temp_{fallback_temp}"
            code = learned_codes.get(fallback_key)
            if code:
                _LOGGER.warning("cool %dC: no code learned, using nearest fallback temp_%d", temp, fallback_temp)
                return code

        raise LearnedCodeNotAvailable(
            f"No cool mode codes learned for temp={temp}C fan={fan}. "
            f"Learn temp_{temp} or temp_{temp}_{fan_suffix or 'fX'}.",
        )

    if hvac_mode == "heat":
        raise LearnedCodeNotAvailable(
            "Heat mode: no codes learned. To use heat mode, physically learn heat commands "
            "from AC remote and name them heat_{temp}_f{num} (e.g. heat_24_f3).",
        )

    if hvac_mode == "dry":
        raise LearnedCodeNotAvailable("Dry mode: no codes learned. To use dry mode, learn dry_{temp} commands from AC remote.")

    if hvac_mode == "auto":
        if temp is not None:
            temp_key = f"temp_{int(temp)}"
            code = learned_codes.get(temp_key)
            if code:
                _LOGGER.warning("auto mode: no auto codes learned, using cool code %s as fallback", temp_key)
                return code
        raise LearnedCodeNotAvailable("Auto mode: no codes learned. Learn auto_{temp} commands.")

    raise LearnedCodeNotAvailable(f"Unknown hvac_mode: {hvac_mode}")


def _nearest_temps(target: int) -> list[int]:
    """Return temperatures 16-30 ordered by proximity to target."""
    return sorted(range(16, 31), key=lambda temp: abs(temp - target))


def get_coverage_summary(learned_codes: dict[str, str]) -> dict[str, Any]:
    """Return a summary of learned-code coverage."""
    fan_codes = [key for key in learned_codes if key.startswith("fan_speed_")]
    temp_codes = [key for key in learned_codes if key.startswith("temp_")]
    temp_only = [key for key in temp_codes if "_f" not in key]
    temp_with_fan = [key for key in temp_codes if "_f" in key]

    covered_temps_auto = sorted(
        {int(parts[1]) for key in temp_only if len((parts := key.split("_"))) > 1 and parts[1].isdigit()},
    )
    covered_temps_fan = sorted(
        {int(parts[1]) for key in temp_with_fan if len((parts := key.split("_"))) > 1 and parts[1].isdigit()},
    )

    return {
        "total_learned": len(learned_codes),
        "has_power_off": "power_off" in learned_codes,
        "has_power_on": "power_on" in learned_codes,
        "fan_only_codes": fan_codes,
        "cool_temps_auto_fan": covered_temps_auto,
        "cool_temps_with_specific_fan": covered_temps_fan,
        "heat_supported": False,
        "dry_supported": False,
        "swing_on_supported": False,
        "gaps": _identify_gaps(learned_codes),
    }


def _identify_gaps(learned_codes: dict[str, str]) -> list[str]:
    gaps = []
    if "power_off" not in learned_codes:
        gaps.append("power_off missing")
    for temp in range(16, 31):
        if f"temp_{temp}" not in learned_codes:
            has_any_fan = any(f"temp_{temp}_f{fan_num}" in learned_codes for fan_num in range(1, 6))
            if not has_any_fan:
                gaps.append(f"cool temp {temp}C: no code at all")
    for temp in range(25, 31):
        for fan_num in range(1, 6):
            if f"temp_{temp}_f{fan_num}" not in learned_codes:
                gaps.append(f"cool {temp}C f{fan_num}: not learned (will use auto fan fallback)")
    return gaps
