#!/usr/bin/env python3
"""Generate LG AKB75415308 AC IR codes for Tuya IR blasters.

The output is a Python module containing a ``CODES`` dictionary of Tuya-native
base64 strings. Home Assistant runtime code does not need FastLZ; this tool is
for offline pack generation only.

Usage:
    python tools/generate_lg_tuya_pack.py > generated_codes.py
"""

from __future__ import annotations

import argparse
import base64
import struct

try:
    import fastlz  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised when the optional package is absent
    fastlz = None


CARRIER_HZ = 38000
HEADER_PULSE = 8600
HEADER_SPACE = 4200
BIT1_PULSE = 450
BIT1_SPACE = 1600
BIT0_PULSE = 450
BIT0_SPACE = 550
TRAIL_PULSE = 450
GAP = 40000

MODE_COOL_ON = 0x0
MODE_DRY_ON = 0x1
MODE_FAN_ON = 0x2
MODE_AUTO_ON = 0x3
MODE_HEAT_ON = 0x4
MODE_COOL = 0x8
MODE_DRY = 0x9
MODE_FAN_ONLY = 0xA
MODE_AUTO = 0xB
MODE_HEAT = 0xC

FAN_AUTO = 0x5
FAN_LOW = 0x0
FAN_MED = 0x2
FAN_HIGH = 0x4
FAN_HIGHEST = 0x6

SWING_OFF = 0x0

FAN_MAP = {
    "auto": FAN_AUTO,
    "low": FAN_LOW,
    "mid": FAN_MED,
    "high": FAN_HIGH,
    "highest": FAN_HIGHEST,
}


def build_frame(mode_nibble: int, temp_c: int, fan_nibble: int, swing: int = SWING_OFF) -> int:
    """Build a 28-bit LG AC IR frame."""

    n1 = 0x8
    n2 = mode_nibble & 0xF
    n3 = (temp_c - 15) & 0xF
    n4 = fan_nibble & 0xF
    n5 = swing & 0xF
    n6 = 0x0
    checksum = (n1 + n2 + n3 + n4 + n5 + n6) & 0xF
    return (
        (n1 << 24)
        | (n2 << 20)
        | (n3 << 16)
        | (n4 << 12)
        | (n5 << 8)
        | (n6 << 4)
        | checksum
    )


def build_off_frame() -> int:
    """Build the LG power-off frame."""

    n1, n2, n3, n4, n5, n6 = 0x8, 0xC, 0x0, 0x0, 0x0, 0x0
    checksum = (n1 + n2 + n3 + n4 + n5 + n6) & 0xF
    return (n1 << 24) | (n2 << 20) | checksum


def build_swing_frame() -> int:
    """Build the LG swing-toggle frame."""

    n1, n2, n3, n4, n5, n6 = 0x8, 0x1, 0x0, 0x0, 0x0, 0x0
    checksum = (n1 + n2 + n3 + n4 + n5 + n6) & 0xF
    return (n1 << 24) | (n2 << 20) | checksum


def frame_to_pulses(frame: int, nbits: int = 28) -> list[int]:
    """Convert a 28-bit frame to alternating pulse/space microsecond timings."""

    pulses = [HEADER_PULSE, HEADER_SPACE]
    for bit_index in range(nbits - 1, -1, -1):
        bit = (frame >> bit_index) & 1
        pulses.append(BIT1_PULSE if bit else BIT0_PULSE)
        pulses.append(BIT1_SPACE if bit else BIT0_SPACE)
    pulses.append(TRAIL_PULSE)
    pulses.append(GAP)
    return pulses


def _fastlz_literal_only(data: bytes) -> bytes:
    """Return a valid FastLZ stream using literal runs only.

    FastLZ literal controls are encoded as ``length - 1`` for chunks of 1..32
    bytes followed by the literal bytes. It is larger than real LZ matching but
    interoperable with FastLZ decoders and keeps this offline tool self-hosted.
    """

    output = bytearray()
    for offset in range(0, len(data), 32):
        chunk = data[offset : offset + 32]
        output.append(len(chunk) - 1)
        output.extend(chunk)
    return bytes(output)


def _fastlz_compress(data: bytes) -> bytes:
    """Compress bytes with python-fastlz when present, otherwise use literals."""

    if fastlz is None:
        return _fastlz_literal_only(data)
    try:
        return fastlz.compress(data, 1)
    except TypeError:
        return fastlz.compress(data)


def pulses_to_tuya_b64(pulses: list[int]) -> str:
    """Convert raw timings to Tuya base64 FastLZ uint16LE format."""

    raw_bytes = b"".join(struct.pack("<H", min(pulse, 65535)) for pulse in pulses)
    return base64.b64encode(_fastlz_compress(raw_bytes)).decode("ascii")


def generate_all_codes() -> dict[str, str]:
    """Generate all LG AKB75415308 state commands in Tuya format."""

    codes: dict[str, str] = {
        "off": pulses_to_tuya_b64(frame_to_pulses(build_off_frame())),
        "swing_toggle": pulses_to_tuya_b64(frame_to_pulses(build_swing_frame())),
    }

    for temp in range(16, 31):
        for fan_name, fan_val in FAN_MAP.items():
            codes[f"cool_on_t{temp}_f{fan_name}"] = pulses_to_tuya_b64(
                frame_to_pulses(build_frame(MODE_COOL_ON, temp, fan_val))
            )
            codes[f"cool_t{temp}_f{fan_name}"] = pulses_to_tuya_b64(
                frame_to_pulses(build_frame(MODE_COOL, temp, fan_val))
            )
            codes[f"heat_on_t{temp}_f{fan_name}"] = pulses_to_tuya_b64(
                frame_to_pulses(build_frame(MODE_HEAT_ON, temp, fan_val))
            )
            codes[f"heat_t{temp}_f{fan_name}"] = pulses_to_tuya_b64(
                frame_to_pulses(build_frame(MODE_HEAT, temp, fan_val))
            )
            codes[f"dry_on_t{temp}_f{fan_name}"] = pulses_to_tuya_b64(
                frame_to_pulses(build_frame(MODE_DRY_ON, temp, fan_val))
            )
            codes[f"dry_t{temp}_f{fan_name}"] = pulses_to_tuya_b64(
                frame_to_pulses(build_frame(MODE_DRY, temp, fan_val))
            )

    for fan_name, fan_val in FAN_MAP.items():
        codes[f"fan_on_f{fan_name}"] = pulses_to_tuya_b64(
            frame_to_pulses(build_frame(MODE_FAN_ON, 25, fan_val))
        )
        codes[f"fan_f{fan_name}"] = pulses_to_tuya_b64(
            frame_to_pulses(build_frame(MODE_FAN_ONLY, 25, fan_val))
        )
        codes[f"auto_on_f{fan_name}"] = pulses_to_tuya_b64(
            frame_to_pulses(build_frame(MODE_AUTO_ON, 25, fan_val))
        )
        codes[f"auto_f{fan_name}"] = pulses_to_tuya_b64(
            frame_to_pulses(build_frame(MODE_AUTO, 25, fan_val))
        )

    return codes


def print_codes_module(codes: dict[str, str]) -> None:
    """Print the generated code table as a Python module."""

    print('"""Auto-generated LG AKB75415308 Tuya IR code table."""')
    print()
    print("# Generated by tools/generate_lg_tuya_pack.py")
    print("# Remote: LG AKB75415308")
    print("# Protocol: LG 28-bit AC IR")
    print("# Transport payload: FastLZ(uint16LE timings) encoded as base64")
    print(f"# Total codes: {len(codes)}")
    print()
    print("CODES: dict[str, str] = {")
    for key in sorted(codes):
        print(f'    "{key}": "{codes[key]}",')
    print("}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print_codes_module(generate_all_codes())


if __name__ == "__main__":
    main()
