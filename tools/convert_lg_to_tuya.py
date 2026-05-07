#!/usr/bin/env python3
"""Convert raw microsecond IR timings to Tuya base64 key1 format."""

from __future__ import annotations

import base64
import struct

try:
    import fastlz

    def _compress(data: bytes) -> bytes:
        return fastlz.compress(data, 1)

except ImportError as exc:
    raise ImportError(
        "Install fastlz: pip install python-fastlz\n"
        "Or use https://github.com/pasthev/irtuya online converter instead."
    ) from exc


def raw_timings_to_tuya_key1(raw_string: str) -> str:
    """Convert comma-separated raw timings to a Tuya key1 base64 string."""
    timings = [int(x.strip()) for x in raw_string.removeprefix("raw:").split(",") if x.strip()]
    payload = struct.pack(f"<{len(timings)}H", *timings)
    return base64.b64encode(_compress(payload)).decode("ascii")


EXAMPLE_TIMINGS = {
    "off": "3060,9586,469,1562,437,562,500,531",
}


if __name__ == "__main__":
    print("# Generated Tuya key1 values - paste into lg_pc09sq_nsj_tuya_v1.py")
    print()
    for label, timings in EXAMPLE_TIMINGS.items():
        key1 = raw_timings_to_tuya_key1(timings)
        print(f"# {label}")
        print(f'key1="{key1}",')
        print()
