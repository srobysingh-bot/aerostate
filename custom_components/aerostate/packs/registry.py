"""Pack registry and discovery."""

import logging
from pathlib import Path

from .loader import load_pack_from_path
from .schema import ModelPack

_LOGGER: logging.Logger = logging.getLogger(__name__)


class PackRegistry:
    """Registry for model packs."""

    def __init__(self) -> None:
        """Initialize registry."""
        self._packs: dict[str, ModelPack] = {}

    def add_pack(self, pack: ModelPack) -> None:
        """Add a pack to the registry.

        Args:
            pack: ModelPack instance
        """
        self._packs[pack.pack_id] = pack

    def get(self, pack_id: str) -> ModelPack:
        """Get a pack by ID.

        Args:
            pack_id: Pack identifier

        Returns:
            ModelPack instance

        Raises:
            KeyError: If pack not found
        """
        if pack_id not in self._packs:
            raise KeyError(f"Pack not found: {pack_id}")
        return self._packs[pack_id]

    def list_brand_packs(self, brand: str) -> list[ModelPack]:
        """List all packs for a brand.

        Args:
            brand: Brand name

        Returns:
            List of ModelPack instances
        """
        return [p for p in self._packs.values() if p.brand.lower() == brand.lower()]

    def list_all(self) -> list[ModelPack]:
        """List all packs.

        Returns:
            List of all ModelPack instances
        """
        return list(self._packs.values())


def discover_builtin_packs() -> dict[str, ModelPack]:
    """Discover all built-in model packs.

    Recursively scans packs/builtin/ for .json files and loads them.

    Returns:
        Dictionary mapping pack_id to ModelPack
    """
    packs = {}

    # Get the directory of this file
    builtin_dir = Path(__file__).parent / "builtin"

    if not builtin_dir.exists():
        return packs

    # Recursively find all .json files
    for json_file in builtin_dir.rglob("*.json"):
        try:
            pack = load_pack_from_path(str(json_file))
            packs[pack.pack_id] = pack
        except Exception as e:
            # Log but continue discovery on error
            _LOGGER.warning("Error loading pack %s: %s", json_file, e)

    return packs


# Global registry instance
_registry: PackRegistry | None = None


def get_registry() -> PackRegistry:
    """Get or initialize the global registry.

    Discovers and loads all built-in packs on first call.

    Returns:
        PackRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = PackRegistry()
        packs = discover_builtin_packs()
        for pack in packs.values():
            _registry.add_pack(pack)
    return _registry


def get_pack(pack_id: str) -> ModelPack:
    """Get a pack by ID.

    Args:
        pack_id: Pack identifier

    Returns:
        ModelPack instance

    Raises:
        KeyError: If pack not found
    """
    return get_registry().get(pack_id)


def list_brand_packs(brand: str) -> list[ModelPack]:
    """List all packs for a brand.

    Args:
        brand: Brand name

    Returns:
        List of ModelPack instances
    """
    return get_registry().list_brand_packs(brand)
