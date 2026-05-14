"""Generated localtuya_rc raw-code table for LG AKB75415308.

The v2 table uses combined mode+temperature+fan LG frames so every climate
state change is represented by a single AC command.
"""

from __future__ import annotations

MODE_NIBBLES = {
    "cool": 0x0,
    "dry": 0x1,
    "fan_only": 0x2,
    "auto": 0x3,
    "heat": 0x4,
}

FAN_NIBBLES = {
    "auto": 0x4,
    "low": 0x0,
    "mid_low": 0x9,
    "mid": 0x2,
    "mid_high": 0xA,
    "high": 0x4,
}

TEMPERATURES = range(16, 31)

POWER_ON = (
    "raw:3200,9570,452,1565,452,554,452,554,452,554,452,1565,452,554,"
    "452,554,452,554,452,554,452,554,452,554,452,554,452,554,452,554,"
    "452,554,452,554,452,1565,452,554,452,1565,452,1565,452,554,"
    "452,1565,452,554,452,1565,452,554,452,554,452,554,452,554,450"
)
POWER_OFF = (
    "raw:3200,9570,452,1565,452,554,452,554,452,554,452,1565,452,554,"
    "452,554,452,554,452,1565,452,1565,452,554,452,554,452,554,452,554,"
    "452,554,452,554,452,554,452,554,452,554,452,554,452,554,452,1565,"
    "452,554,452,1565,452,554,452,554,452,554,452,1565,450"
)

SWING_VERTICAL_TOGGLE = (
    "raw:3218,9549,535,1496,535,507,535,507,535,507,535,1496,535,507,"
    "535,507,535,507,535,507,535,507,535,507,535,1496,535,507,535,507,"
    "535,1496,535,1496,535,507,535,507,535,507,535,507,535,1496,"
    "535,507,535,507,535,507,535,1496,535,1496,535,507,535,507,528"
)
SWING_HORIZONTAL_TOGGLE = (
    "raw:3257,9556,553,1490,553,484,553,484,553,484,553,1490,553,484,"
    "553,484,553,484,553,484,553,484,553,484,553,1490,553,484,553,484,"
    "553,1490,553,1490,553,484,553,484,553,484,553,484,553,1490,"
    "553,1490,553,484,553,1490,553,484,553,484,553,484,553,1490,535"
)


def _checksum(frame_without_checksum: int) -> int:
    checksum = 0
    value = frame_without_checksum
    for _ in range(7):
        checksum += value & 0xF
        value >>= 4
    return checksum & 0xF


def _frame_for(mode: str, temperature: int, fan: str) -> int:
    frame_without_checksum = (
        (0x88 << 20)
        | (MODE_NIBBLES[mode] << 16)
        | (0x8 << 12)
        | ((temperature - 15) << 8)
        | (FAN_NIBBLES[fan] << 4)
    )
    return frame_without_checksum | _checksum(frame_without_checksum)


def _raw_for_frame(frame: int) -> str:
    pulses = [3200, 9570]
    for bit_index in range(27, -1, -1):
        pulses.append(452)
        pulses.append(1565 if frame & (1 << bit_index) else 554)
    pulses.append(450)
    return "raw:" + ",".join(str(pulse) for pulse in pulses)


CODES: dict[str, str] = {
    "power_on": POWER_ON,
    "power_off": POWER_OFF,
}

for _mode in MODE_NIBBLES:
    for _temp in TEMPERATURES:
        for _fan in FAN_NIBBLES:
            CODES[f"{_mode}_t{_temp}_f{_fan}"] = _raw_for_frame(
                _frame_for(_mode, _temp, _fan)
            )

CODES.update(
    {
        "swing_vertical_toggle": SWING_VERTICAL_TOGGLE,
        "swing_horizontal_toggle": SWING_HORIZONTAL_TOGGLE,
    }
)

