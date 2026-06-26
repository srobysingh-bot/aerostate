"""Load data-only Daikin Tuya IR code-set packs from this directory."""

from __future__ import annotations

import ast
import pprint
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..schema import TuyaIRCommand, TuyaIRPack

REQUIRED_COMMANDS = frozenset({"power_on", "power_off", "cool_t24_fauto"})
TARGET_REQUIRED_COMMANDS = frozenset(
    {
        "power_on",
        "power_off",
        "cool_t24_fauto",
        "cool_t24_flow",
        "cool_t24_fmid",
        "cool_t24_fhigh",
    }
)
REQUIRED_METADATA = frozenset(
    {
        "pack_id",
        "display_name",
        "brand",
        "provider",
        "source",
        "payload_format",
        "cloud_disabled_at_runtime",
    }
)
TARGET_PACK_ID = "daikin_brc4m150w_fxaq63pve6_localtuya_rc_v1"
TARGET_DISPLAY_NAME = "Daikin BRC4M150W / FXAQ63PVE6"
TARGET_REMOTE_MODEL = "BRC4M150W"
TARGET_INDOOR_MODEL = "FXAQ63PVE6"
TARGET_SOURCE = "tuya_cloud_one_time_import_or_physical_remote_capture"
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


def user_pack_dir(hass) -> Path:
    """Return the generated Daikin pack directory inside the integration tree."""
    return _pack_dir()


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
    if payload_format != "localtuya_rc_raw":
        raise DaikinTuyaPackValidationError(f"{path.name} has unsupported payload_format")
    if metadata.get("cloud_disabled_at_runtime") is not True:
        raise DaikinTuyaPackValidationError(f"{path.name} must disable Tuya Cloud at runtime")

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
    pack_id = str(metadata.get("pack_id") or path.stem).strip()
    if pack_id == TARGET_PACK_ID:
        missing_target_commands = sorted(TARGET_REQUIRED_COMMANDS - normalized_codes.keys())
        if missing_target_commands:
            raise DaikinTuyaPackValidationError(
                f"{path.name} missing target commands: {', '.join(missing_target_commands)}"
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


def _pack_roots(*, hass=None, directory: Path | None = None) -> list[Path]:
    if directory is not None:
        return [directory]
    roots = [_pack_dir()]
    if hass is not None and getattr(getattr(hass, "config", None), "path", None):
        roots.append(user_pack_dir(hass))
    return roots


def list_daikin_tuya_packs(*, hass=None, directory: Path | None = None) -> list[DaikinTuyaPackInfo]:
    """List valid bundled and user Daikin packs, excluding invalid files."""
    packs: list[DaikinTuyaPackInfo] = []
    seen: set[str] = set()
    for root in _pack_roots(hass=hass, directory=directory):
        for path in sorted(root.glob("*.py")):
            if path.name in {"__init__.py", "loader.py"} or path.name.startswith("_"):
                continue
            try:
                pack = _pack_info(path)
            except DaikinTuyaPackValidationError:
                continue
            if pack.pack_id not in seen:
                packs.append(pack)
                seen.add(pack.pack_id)
    return sorted(packs, key=lambda pack: pack.pack_id)


def get_daikin_tuya_pack(pack_id: str, *, hass=None, directory: Path | None = None) -> DaikinTuyaPackInfo:
    """Return one valid local Daikin pack by ID."""
    for pack in list_daikin_tuya_packs(hass=hass, directory=directory):
        if pack.pack_id == pack_id:
            return pack
    raise KeyError(f"Daikin Tuya local pack not found: {pack_id}")


def load_daikin_tuya_pack(pack_id: str, *, hass=None, directory: Path | None = None) -> TuyaIRPack:
    """Build and register a runtime TuyaIRPack from a local Daikin code set."""
    from ..registry import register_tuya_pack

    info = get_daikin_tuya_pack(pack_id, hass=hass, directory=directory)
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
        notes=(
            f"{metadata.get('display_name', info.pack_id)}; "
            f"remote_index={metadata.get('remote_index', 'n/a')}; cloud disabled at runtime."
        ),
        min_temperature=int(temp_range[0]),
        max_temperature=int(temp_range[1]),
        commands=commands,
        native_base64=False,
        requires_learned_codes=False,
        swing_vertical_modes=["off", "on"] if metadata.get("swing_support", "swing_vertical" in codes) else [],
        transport="localtuya_rc",
        protocol="stateful",
    )
    register_tuya_pack(pack)
    return pack


def write_daikin_tuya_pack(
    output: Path,
    sequence: int,
    remote_index: str,
    codes: dict[str, str],
    *,
    pack_id: str | None = None,
    display_name: str | None = None,
    remote_model: str | None = None,
    indoor_model: str | None = None,
    source: str = "tuya_cloud_one_time_import",
) -> Path:
    """Validate and save one imported Tuya Daikin set as a data-only pack."""
    missing = sorted(REQUIRED_COMMANDS - codes.keys())
    if missing:
        raise DaikinTuyaPackValidationError(
            f"remote_index={remote_index} missing required commands: {', '.join(missing)}"
        )
    if any(value.lower().startswith("b64:") for value in codes.values()):
        raise DaikinTuyaPackValidationError(
            f"remote_index={remote_index} contains a Broadlink/native-b64 payload"
        )

    pack_id = pack_id or f"daikin_tuya_set_{sequence:03d}"
    fans = sorted(
        {match.group(1) for label in codes if (match := re.search(r"_f([a-z0-9_]+)$", label))}
    )
    temps = sorted(
        {int(match.group(1)) for label in codes if (match := re.search(r"_t(\d+)_", label))}
    )
    metadata = {
        "pack_id": pack_id,
        "display_name": display_name or f"Daikin Tuya code set {sequence:03d}",
        "brand": "Daikin",
        "provider": "tuya_local",
        "remote_index": remote_index,
        "source": source,
        "temp_range": [min(temps), max(temps)] if temps else [16, 30],
        "fan_modes": fans or ["auto"],
        "swing_support": "swing_vertical" in codes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "payload_format": "localtuya_rc_raw",
        "cloud_disabled_at_runtime": True,
    }
    if remote_model:
        metadata["remote_model"] = remote_model
    if indoor_model:
        metadata["indoor_model"] = indoor_model
    if "remote_model" not in metadata and "indoor_model" not in metadata:
        metadata["model_hint"] = TARGET_INDOOR_MODEL
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{pack_id}.py"
    path.write_text(
        '"""Generated Daikin Tuya local IR code-set pack. Do not edit manually."""\n\n'
        f"METADATA = {pprint.pformat(metadata, sort_dicts=True, width=100)}\n\n"
        f"CODES = {pprint.pformat(dict(sorted(codes.items())), sort_dicts=True, width=100)}\n",
        encoding="utf-8",
    )
    _validate_pack(path)
    return path


def write_daikin_target_pack(
    output: Path,
    codes: dict[str, str],
    *,
    remote_index: str = "",
    source: str = TARGET_SOURCE,
) -> Path:
    """Write the confirmed BRC4M150W / FXAQ63PVE6 local Tuya pack."""
    return write_daikin_tuya_pack(
        output,
        1,
        remote_index,
        codes,
        pack_id=TARGET_PACK_ID,
        display_name=TARGET_DISPLAY_NAME,
        remote_model=TARGET_REMOTE_MODEL,
        indoor_model=TARGET_INDOOR_MODEL,
        source=source,
    )


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
    "TARGET_DISPLAY_NAME",
    "TARGET_INDOOR_MODEL",
    "TARGET_PACK_ID",
    "TARGET_REMOTE_MODEL",
    "TARGET_REQUIRED_COMMANDS",
    "TARGET_SOURCE",
    "user_pack_dir",
    "write_daikin_target_pack",
    "write_daikin_tuya_pack",
]
