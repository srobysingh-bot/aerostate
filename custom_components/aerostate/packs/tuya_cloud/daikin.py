"""Daikin capability pack for Tuya Cloud IR code-library control."""

from __future__ import annotations

from ..schema import ModelPack, PackCapabilities

PACK_ID = "tuya_cloud.daikin_ac.v1"

_TEMPS = range(16, 31)
_FANS = ("auto", "low", "medium", "high")
_MODES = ("cool", "heat", "heat_cool", "fan_only", "dry")


def _command_tree() -> dict[str, object]:
    """Build a table-shaped capability tree for climate validation/UI."""
    commands: dict[str, object] = {"off": "tuya_cloud:power:0"}
    for mode in _MODES:
        commands[mode] = {
            fan: {
                str(temp): f"tuya_cloud:{mode}:{fan}:{temp}"
                for temp in _TEMPS
            }
            for fan in _FANS
        }
    return commands


def build_pack() -> ModelPack:
    """Return the built-in Daikin Tuya Cloud AC code-library pack."""
    return ModelPack(
        pack_id=PACK_ID,
        brand="Daikin",
        models=["Daikin AC via Tuya IR code library"],
        transport="tuya_cloud_ac",
        pack_version=1,
        min_temperature=16,
        max_temperature=30,
        capabilities=PackCapabilities(
            hvac_modes=list(_MODES),
            fan_modes=list(_FANS),
            swing_vertical_modes=[],
            swing_horizontal_modes=[],
            presets=[],
            preset_modes=[],
        ),
        engine_type="table",
        commands=_command_tree(),
        verified=False,
        notes=(
            "Tuya Cloud IR code-library route for Daikin ACs. Uses Tuya's AC single-command "
            "API for power, mode, temp, and fan. Swing and special modes are intentionally "
            "not exposed until confirmed through the selected Tuya remote profile."
        ),
        mode_status={
            "cool": "tuya_code_library",
            "heat": "tuya_code_library",
            "heat_cool": "tuya_code_library",
            "fan_only": "tuya_code_library",
            "dry": "tuya_code_library",
        },
    )
