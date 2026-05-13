"""Registry for standalone Tuya IR key1 packs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import TuyaIRPack

_TUYA_REGISTRY: dict[str, "TuyaIRPack"] = {}
_BUILTINS_IMPORTED = True


def _ensure_builtin_packs() -> None:
    """Bundled Tuya packs are imported eagerly at module load."""
    return


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


def get_tuya_pack_options_for_ui() -> list[dict]:
    """Return selector options for config and options flows."""
    return [
        {"value": p.pack_id, "label": f"{p.models[0] if p.models else p.pack_id} ({p.pack_id})"}
        for p in list_tuya_packs()
    ]


from . import lg_pc09sq_nsj_tuya_v1 as _lg_pc09sq_nsj_tuya_v1  # noqa: E402,F401
from . import lg_akb75415308_tuya_protocol_v1 as _lg_akb75415308_tuya_protocol_v1  # noqa: E402,F401
