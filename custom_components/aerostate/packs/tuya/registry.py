"""Registry for standalone Tuya IR key1 packs."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import TuyaIRPack

_TUYA_REGISTRY: dict[str, "TuyaIRPack"] = {}
_BUILTINS_IMPORTED = False
_BUILTIN_MODULES = (
    "daikin_brc4c158_localtuya_v1",
    "lg_akb75415308_tuya_protocol_v1",
    "lg_pc09sq_nsj_tuya_v1",
)


def _ensure_builtin_packs() -> None:
    """Import bundled and generated local Tuya packs exactly once."""
    global _BUILTINS_IMPORTED

    if _BUILTINS_IMPORTED:
        return
    _BUILTINS_IMPORTED = True
    for module_name in _BUILTIN_MODULES:
        import_module(f"{__package__}.{module_name}")

    from .daikin.loader import register_local_daikin_tuya_packs

    register_local_daikin_tuya_packs()


def register_tuya_pack(pack: "TuyaIRPack") -> None:
    """Register a Tuya IR pack."""
    _TUYA_REGISTRY[pack.pack_id] = pack


def get_tuya_pack(pack_id: str) -> "TuyaIRPack":
    """Return a Tuya IR pack by ID."""
    _ensure_builtin_packs()
    if pack_id not in _TUYA_REGISTRY:
        raise KeyError(f"Tuya IR pack not found: {pack_id}")
    return _TUYA_REGISTRY[pack_id]


def list_tuya_packs() -> list["TuyaIRPack"]:
    """Return all registered Tuya IR packs."""
    _ensure_builtin_packs()
    return list(_TUYA_REGISTRY.values())


def get_tuya_pack_options_for_ui(brand: str | None = None) -> list[dict]:
    """Return selector options, optionally limited to one brand."""
    normalized_brand = str(brand or "").strip().casefold()
    return [
        {"value": p.pack_id, "label": f"{p.models[0] if p.models else p.pack_id} ({p.pack_id})"}
        for p in list_tuya_packs()
        if not normalized_brand or str(p.brand).strip().casefold() == normalized_brand
    ]
