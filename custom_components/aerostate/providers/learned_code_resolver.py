"""Map AeroState climate states to learned localtuya_rc command names."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class LearnedCodeNotAvailable(KeyError):
    """No learned code covers the requested climate state."""


FAN_TO_SUFFIX: dict[str, str | None] = {
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "auto": None,
    "low": "f1",
    "medium": "f3",
    "high": "f5",
    "med": "f3",
    "mid": "f3",
    "turbo": "f5",
}

FAN_ONLY_KEY: dict[str, str] = {
    "f1": "fan_speed_1",
    "f2": "fan_speed_2",
    "f3": "fan_speed_3",
    "f4": "fan_speed_4",
    "f5": "fan_speed_5",
    "auto": "fan_speed_3",
    "low": "fan_speed_1",
    "medium": "fan_speed_3",
    "high": "fan_speed_5",
    "med": "fan_speed_3",
    "mid": "fan_speed_3",
}


def resolve_learned_code(learned_codes: dict[str, str], state: dict[str, Any]) -> str:
    """Resolve a climate state dictionary to a learned raw IR string."""
    hvac_mode = str(state.get("hvac_mode", "off")).lower()
    temp = state.get("target_temperature")
    fan = str(state.get("fan_mode") or "auto").lower()

    if hvac_mode == "off":
        code = learned_codes.get("power_off")
        if code:
            return code
        raise LearnedCodeNotAvailable(
            "power_off not in storage. Learn it: remote.learn_command "
            "device='Living AC IR' command='power_off'",
        )

    if hvac_mode in ("fan_only", "fan"):
        key = FAN_ONLY_KEY.get(fan, "fan_speed_3")
        code = learned_codes.get(key)
        if code:
            _LOGGER.debug("fan_only -> %s", key)
            return code
        for fallback in ("fan_speed_1", "fan_speed_2", "fan_speed_3", "fan_speed_4", "fan_speed_5"):
            code = learned_codes.get(fallback)
            if code:
                _LOGGER.warning("fan_only fan=%s not found, using %s", fan, fallback)
                return code
        raise LearnedCodeNotAvailable(
            "No fan_speed codes in storage. Learn: fan_speed_1 through fan_speed_5",
        )

    if hvac_mode == "cool":
        if temp is None:
            temp = 24
        temp = int(round(float(temp)))
        temp = max(16, min(30, temp))

        fan_suffix = FAN_TO_SUFFIX.get(fan)
        if fan_suffix is not None:
            exact = f"temp_{temp}_{fan_suffix}"
            code = learned_codes.get(exact)
            if code:
                _LOGGER.debug("cool exact -> %s", exact)
                return code

        auto_key = f"temp_{temp}"
        code = learned_codes.get(auto_key)
        if code:
            if fan_suffix is not None:
                _LOGGER.warning(
                    "cool %dC fan=%s not learned, falling back to %s (auto fan)",
                    temp,
                    fan,
                    auto_key,
                )
            else:
                _LOGGER.debug("cool auto -> %s", auto_key)
            return code

        for fallback_temp in _nearest_temps(temp, learned_codes):
            fallback_key = f"temp_{fallback_temp}"
            code = learned_codes.get(fallback_key)
            if code:
                _LOGGER.warning("cool %dC not learned, using nearest fallback %s", temp, fallback_key)
                return code

        raise LearnedCodeNotAvailable(
            f"No cool codes found for temp={temp}C fan={fan}. "
            f"Learn: temp_{temp} or temp_{temp}_{fan_suffix or 'fX'}",
        )

    if hvac_mode == "heat":
        if temp is None:
            temp = 24
        temp = int(round(float(temp)))
        heat_suffix = FAN_TO_SUFFIX.get(fan) or "auto"
        for key in (f"heat_{temp}_f{heat_suffix}", f"heat_{temp}"):
            code = learned_codes.get(key)
            if code:
                _LOGGER.debug("heat -> %s", key)
                return code
        raise LearnedCodeNotAvailable(
            f"Heat mode not learned. To add heat: point AC remote at blaster "
            f"and run remote.learn_command device='Living AC IR' command='heat_{temp}_f{heat_suffix}'",
        )

    if hvac_mode == "dry":
        if temp is None:
            temp = 24
        temp = int(round(float(temp)))
        for key in (f"dry_{temp}_auto", f"dry_{temp}", "dry_auto", "dry"):
            code = learned_codes.get(key)
            if code:
                _LOGGER.debug("dry -> %s", key)
                return code
        raise LearnedCodeNotAvailable(
            f"Dry mode not learned. Learn: remote.learn_command device='Living AC IR' command='dry_{temp}'",
        )

    if hvac_mode == "auto":
        if temp is None:
            temp = 24
        temp = int(round(float(temp)))
        for key in (f"auto_{temp}", f"auto_{temp}_auto"):
            code = learned_codes.get(key)
            if code:
                _LOGGER.debug("auto -> %s", key)
                return code

        cool_key = f"temp_{temp}"
        code = learned_codes.get(cool_key)
        if code:
            _LOGGER.warning("auto mode not learned, using cool code %s as fallback", cool_key)
            return code

        raise LearnedCodeNotAvailable(
            f"Auto mode not learned. Learn: remote.learn_command device='Living AC IR' command='auto_{temp}'",
        )

    raise LearnedCodeNotAvailable(f"Unknown hvac_mode: {hvac_mode}")


def _nearest_temps(target: int, learned_codes: dict[str, str]) -> list[int]:
    """Return temperatures 16-30 that exist in learned_codes, sorted by proximity."""
    available = [temp for temp in range(16, 31) if f"temp_{temp}" in learned_codes]
    return sorted(available, key=lambda temp: abs(temp - target))


def get_coverage_summary(learned_codes: dict[str, str]) -> dict[str, Any]:
    """Return coverage summary for diagnostics and confirm step."""
    has_off = "power_off" in learned_codes
    fan_keys = [key for key in learned_codes if key.startswith("fan_speed_")]

    cool_auto = sorted(temp for temp in range(16, 31) if f"temp_{temp}" in learned_codes)
    cool_fan_exact: dict[int, list[str]] = {}
    for temp in range(16, 31):
        fans = [f"f{fan_num}" for fan_num in range(1, 6) if f"temp_{temp}_f{fan_num}" in learned_codes]
        if fans:
            cool_fan_exact[temp] = fans

    heat_keys = [key for key in learned_codes if key.startswith("heat_")]
    dry_keys = [key for key in learned_codes if key.startswith("dry_")]
    auto_keys = [key for key in learned_codes if key.startswith("auto_")]

    gaps = _identify_gaps(learned_codes, has_off=has_off, heat_keys=heat_keys, dry_keys=dry_keys)
    cool_exact_fan_temps = list(cool_fan_exact.keys())

    return {
        "total_learned": len(learned_codes),
        "has_power_off": has_off,
        "has_power_on": "power_on" in learned_codes,
        "fan_only_codes": fan_keys,
        "fan_only_code_count": len(fan_keys),
        "cool_auto_temps": cool_auto,
        "cool_exact_fan_temps": cool_exact_fan_temps,
        "cool_temps_auto_fan": cool_auto,
        "cool_temps_with_specific_fan": cool_exact_fan_temps,
        "heat_codes": len(heat_keys),
        "dry_codes": len(dry_keys),
        "auto_codes": len(auto_keys),
        "heat_supported": bool(heat_keys),
        "dry_supported": bool(dry_keys),
        "swing_on_supported": False,
        "gaps": gaps,
        "total_gaps": len(gaps),
    }


def _identify_gaps(
    learned_codes: dict[str, str],
    *,
    has_off: bool,
    heat_keys: list[str],
    dry_keys: list[str],
) -> list[str]:
    gaps: list[str] = []
    if not has_off:
        gaps.append("power_off missing")
    for temp in range(16, 31):
        if f"temp_{temp}" not in learned_codes and not any(
            f"temp_{temp}_f{fan_num}" in learned_codes for fan_num in range(1, 6)
        ):
            gaps.append(f"cool temp {temp}C: no code at all")
    if "temp_24_f5" not in learned_codes:
        gaps.append("cool 24C f5 missing (falls back to auto fan)")
    for temp in range(25, 31):
        for fan_num in range(1, 6):
            if f"temp_{temp}_f{fan_num}" not in learned_codes:
                gaps.append(f"cool {temp}C f{fan_num} missing (falls back to auto fan)")
                break
    if not heat_keys:
        gaps.append("heat mode: not learned")
    if not dry_keys:
        gaps.append("dry mode: not learned")
    return gaps
