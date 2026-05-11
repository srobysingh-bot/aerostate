"""Registry for Tuya Cloud code-library packs."""

from __future__ import annotations

from ..schema import ModelPack
from .daikin import PACK_ID as DAIKIN_PACK_ID
from .daikin import build_pack as build_daikin_pack

_PACKS: dict[str, ModelPack] | None = None


def _ensure_packs() -> dict[str, ModelPack]:
    """Return built-in Tuya Cloud packs, creating them once."""
    global _PACKS
    if _PACKS is None:
        daikin_pack = build_daikin_pack()
        _PACKS = {daikin_pack.pack_id: daikin_pack}
    return _PACKS


def get_tuya_cloud_pack(pack_id: str | None = None) -> ModelPack:
    """Return a Tuya Cloud code-library pack by ID."""
    packs = _ensure_packs()
    selected = pack_id or DAIKIN_PACK_ID
    if selected not in packs:
        raise KeyError(f"Tuya Cloud pack not found: {selected}")
    return packs[selected]


def list_tuya_cloud_packs() -> list[ModelPack]:
    """Return all Tuya Cloud code-library packs."""
    return list(_ensure_packs().values())


def get_tuya_cloud_pack_options_for_ui() -> list[dict[str, str]]:
    """Return selector options for config and options flows."""
    return [
        {
            "value": pack.pack_id,
            "label": f"{pack.models[0] if pack.models else pack.pack_id} ({pack.pack_id})",
        }
        for pack in list_tuya_cloud_packs()
    ]

