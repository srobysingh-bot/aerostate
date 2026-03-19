"""Mode-level truth metadata helpers for diagnostics and setup UX."""

from __future__ import annotations

from typing import Any


def build_mode_truth(pack: object) -> dict[str, dict[str, Any]]:
    """Build normalized mode truth flags from pack metadata.

    Returns one record per supported HVAC mode, excluding off.
    """
    supported_modes = list(getattr(getattr(pack, "capabilities", None), "hvac_modes", []))
    supported_modes = [mode for mode in supported_modes if mode != "off"]

    status_overrides = dict(getattr(pack, "mode_status", {}))
    physically_verified = set(getattr(pack, "physically_verified_modes", []))
    pack_verified = bool(getattr(pack, "verified", False))

    mode_truth: dict[str, dict[str, Any]] = {}
    for mode in supported_modes:
        status = status_overrides.get(mode)
        if not status:
            status = "verified" if pack_verified and mode in physically_verified else "experimental"

        mode_truth[mode] = {
            "ui_exposed": True,
            "physically_verified": mode in physically_verified,
            "status": status,
        }

    return mode_truth
