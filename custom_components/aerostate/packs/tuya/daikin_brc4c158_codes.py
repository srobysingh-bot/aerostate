"""
Daikin BRC4C158 IR code table for Tuya IR blasters.

Remote: BRC4C158 ceiling cassette cooling-only remote
Protocol: Daikin BRC4CXXX, matching ESPHome's daikin_brc component
Format: raw microsecond timings for localtuya_rc remote.send_command

Capabilities:
  Mode: cool only
  Temperature: 16-30 C
  Fan: auto, low, high
"""

from __future__ import annotations

HEADER_MARK = 5070
HEADER_SPACE = 2140
BIT_MARK = 370
ONE_SPACE = 1000
ZERO_SPACE = 370
MESSAGE_SPACE = 29000

COOL_ALT_MODE = 0x23
OFF_ALT_MODE = 0x73
COOL_ON_MODE = 0x21
OFF_MODE = 0x00

FANS = {
    "fauto": 0xA0,
    "flow": 0x10,
    "fhigh": 0x50,
}


def build_frame(mode_byte: int, alt_mode: int, temp_c: int, fan_byte: int) -> list[int]:
    """Build the 22-byte Daikin BRC4CXXX state frame."""
    frame = [
        0x11,
        0xDA,
        0x17,
        0x18,
        0x04,
        0x00,
        0x1E,
        0x11,
        0xDA,
        0x17,
        0x18,
        0x00,
        alt_mode,
        0x00,
        mode_byte,
        0x00,
        0x00,
        int(temp_c * 2),
        fan_byte,
        0x00,
        0x20,
        0x00,
    ]
    frame[21] = sum(frame[:21]) & 0xFF
    return frame


def to_raw(frame: list[int]) -> str:
    """Encode one Daikin BRC4CXXX frame as localtuya_rc raw timings."""
    pulses = [HEADER_MARK, HEADER_SPACE]
    for byte in frame[:8]:
        for bit in range(8):
            pulses.extend([BIT_MARK, ONE_SPACE if (byte >> bit) & 1 else ZERO_SPACE])

    pulses.extend([BIT_MARK, MESSAGE_SPACE, HEADER_MARK, HEADER_SPACE])
    for byte in frame[8:22]:
        for bit in range(8):
            pulses.extend([BIT_MARK, ONE_SPACE if (byte >> bit) & 1 else ZERO_SPACE])
    pulses.append(BIT_MARK)
    return "raw:" + ",".join(str(pulse) for pulse in pulses)


def _build_codes() -> dict[str, str]:
    codes = {
        "power_off": to_raw(build_frame(OFF_MODE, OFF_ALT_MODE, 20, FANS["fauto"])),
    }
    for temp in range(16, 31):
        for fan_name, fan_byte in FANS.items():
            codes[f"cool_t{temp}_{fan_name}"] = to_raw(
                build_frame(COOL_ON_MODE, COOL_ALT_MODE, temp, fan_byte),
            )
    return codes


CODES: dict[str, str] = _build_codes()

__all__ = [
    "BIT_MARK",
    "CODES",
    "FANS",
    "HEADER_MARK",
    "HEADER_SPACE",
    "MESSAGE_SPACE",
    "ONE_SPACE",
    "ZERO_SPACE",
    "build_frame",
    "to_raw",
]
