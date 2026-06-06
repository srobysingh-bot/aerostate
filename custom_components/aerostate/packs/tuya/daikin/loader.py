"""Load data-only Daikin Tuya IR code-set packs from this directory."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..schema import TuyaIRCommand, TuyaIRPack

REQUIRED_COMMANDS = frozenset({"power_on", "power_off", "cool_t24_fauto"})
REQUIRED_METADATA = frozenset(
    {
        "brand",
        "provider",
        "remote_index",
        "source",
        "temp_range",
        "fan_modes",
        "swing_support",
        "generated_at",
        "payload_format",
    }
)
_STATE_LABEL = re.compile(
    r"^(?P<mode>cool|heat|dry|auto|fan_only)_t(?P<temp>\d+)_f(?P<fan>[a-z0-9_]+)$"
)


class DaikinTuyaPackValidationError(ValueError):
    """Raised when a local Daikin Tuya pack is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class DaikinTuyaPackInfo:
    """Debug-safe description of one local Daikin Tuya code-set pack."""

    pack_id: str
    display_name: str
    brand: str
    provider: str
    available_commands: tuple[str, ...]
    metadata: dict[str, Any]
    path: Path


def _pack_dir() -> Path:
    return Path(__file__).resolve().parent


def _literal_assignments(path: Path) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as err:
        raise DaikinTuyaPackValidationError(f"Cannot parse {path.name}: {err}") from err

    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value_node = node.value
        if value_node is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {"METADATA", "CODES"}:
                try:
                    values[target.id] = ast.literal_eval(value_node)
                except (ValueError, SyntaxError) as err:
                    raise DaikinTuyaPackValidationError(
                        f"{path.name} {target.id} must contain literals only"
                    ) from err
    return values


def _validate_pack(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    values = _literal_assignments(path)
    metadata = values.get("METADATA")
    codes = values.get("CODES")
    if not isinstance(metadata, dict) or not isinstance(codes, dict):
        raise DaikinTuyaPackValidationError(f"{path.name} must define METADATA and CODES dictionaries")

    missing_metadata = sorted(REQUIRED_METADATA - metadata.keys())
    if missing_metadata:
        raise DaikinTuyaPackValidationError(
            f"{path.name} missing metadata: {', '.join(missing_metadata)}"
        )
    if str(metadata.get("brand", "")).strip().lower() != "daikin":
        raise DaikinTuyaPackValidationError(f"{path.name} brand must be Daikin")
    if str(metadata.get("provider", "")).strip().lower() != "tuya_local":
        raise DaikinTuyaPackValidationError(f"{path.name} provider must be tuya_local")
    payload_format = str(metadata.get("payload_format", "")).strip().lower()
    if payload_format not in {"localtuya_rc_raw", "tuya_raw", "tuya_key1"}:
        raise DaikinTuyaPackValidationError(f"{path.name} has unsupported payload_format")

    normalized_codes: dict[str, str] = {}
    for label, payload in codes.items():
        if not isinstance(label, str) or not label.strip():
            raise DaikinTuyaPackValidationError(f"{path.name} contains an invalid command label")
        if not isinstance(payload, str) or not payload.strip():
            raise DaikinTuyaPackValidationError(f"{path.name} command {label!r} has no payload")
        if payload.strip().lower().startswith("b64:"):
            raise DaikinTuyaPackValidationError(
                f"{path.name} command {label!r} contains a Broadlink/native-b64 payload"
            )
        normalized_codes[label.strip()] = payload.strip()

    missing_commands = sorted(REQUIRED_COMMANDS - normalized_codes.keys())
    if missing_commands:
        raise DaikinTuyaPackValidationError(
            f"{path.name} missing required commands: {', '.join(missing_commands)}"
        )
    return dict(metadata), normalized_codes


def _pack_info(path: Path) -> DaikinTuyaPackInfo:
    metadata, codes = _validate_pack(path)
    pack_id = str(metadata.get("pack_id") or path.stem).strip()
    if not pack_id:
        raise DaikinTuyaPackValidationError(f"{path.name} has no pack_id")
    return DaikinTuyaPackInfo(
        pack_id=pack_id,
        display_name=str(metadata.get("display_name") or pack_id),
        brand="Daikin",
        provider="tuya_local",
        available_commands=tuple(sorted(codes)),
        metadata=metadata,
        path=path,
    )


def list_daikin_tuya_packs(*, directory: Path | None = None) -> list[DaikinTuyaPackInfo]:
    """List valid local Daikin packs, silently excluding invalid files."""
    root = directory or _pack_dir()
    packs: list[DaikinTuyaPackInfo] = []
    for path in sorted(root.glob("*.py")):
        if path.name in {"__init__.py", "loader.py"} or path.name.startswith("_"):
            continue
        try:
            packs.append(_pack_info(path))
        except DaikinTuyaPackValidationError:
            continue
    return packs


def get_daikin_tuya_pack(pack_id: str, *, directory: Path | None = None) -> DaikinTuyaPackInfo:
    """Return one valid local Daikin pack by ID."""
    for pack in list_daikin_tuya_packs(directory=directory):
        if pack.pack_id == pack_id:
            return pack
    raise KeyError(f"Daikin Tuya local pack not found: {pack_id}")


def load_daikin_tuya_pack(pack_id: str, *, directory: Path | None = None) -> TuyaIRPack:
    """Build and register a runtime TuyaIRPack from a local Daikin code set."""
    from ..registry import register_tuya_pack

    info = get_daikin_tuya_pack(pack_id, directory=directory)
    metadata, codes = _validate_pack(info.path)
    temp_range = metadata.get("temp_range", [16, 30])
    if not isinstance(temp_range, (list, tuple)) or len(temp_range) != 2:
        raise DaikinTuyaPackValidationError(f"{info.path.name} temp_range must contain min and max")

    commands: list[TuyaIRCommand] = []
    for label, payload in codes.items():
        if label == "power_off":
            commands.append(TuyaIRCommand(label=label, key1=payload, hvac_mode="off"))
            continue
        match = _STATE_LABEL.match(label)
        if match:
            commands.append(
                TuyaIRCommand(
                    label=label,
                    key1=payload,
                    hvac_mode=match.group("mode"),
                    temperature=int(match.group("temp")),
                    fan_mode=match.group("fan"),
                )
            )
            continue
        commands.append(TuyaIRCommand(label=label, key1=payload, hvac_mode="special"))

    pack = TuyaIRPack(
        pack_id=info.pack_id,
        brand="Daikin",
        models=[info.display_name],
        verified=False,
        notes=f"Imported Tuya code set remote_index={metadata['remote_index']}; cloud disabled at runtime.",
        min_temperature=int(temp_range[0]),
        max_temperature=int(temp_range[1]),
        commands=commands,
        native_base64=False,
        requires_learned_codes=False,
        swing_vertical_modes=["off", "on"] if metadata.get("swing_support") else [],
        transport="localtuya_rc",
        protocol="stateful",
    )
    register_tuya_pack(pack)
    return pack


def register_local_daikin_tuya_packs() -> None:
    """Register every valid bundled/imported Daikin local pack."""
    for info in list_daikin_tuya_packs():
        load_daikin_tuya_pack(info.pack_id)


__all__ = [
    "DaikinTuyaPackInfo",
    "DaikinTuyaPackValidationError",
    "get_daikin_tuya_pack",
    "list_daikin_tuya_packs",
    "load_daikin_tuya_pack",
    "register_local_daikin_tuya_packs",
]
