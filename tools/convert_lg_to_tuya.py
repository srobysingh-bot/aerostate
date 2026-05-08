#!/usr/bin/env python3
"""Convert raw LG IR timing captures to TuyaIRCommand entries.

Usage:
    python tools/convert_lg_to_tuya.py path/to/lg_commands.txt
"""

from __future__ import annotations

import argparse
import base64
import re
import struct
from pathlib import Path

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
    raw_string = raw_string.strip().removeprefix("raw:").strip()
    timings = [int(x.strip()) for x in raw_string.split(",") if x.strip()]
    payload = struct.pack(f"<{len(timings)}H", *timings)
    return base64.b64encode(_compress(payload)).decode("ascii")


def _parse_label_and_raw(line: str, pending_label: str | None) -> tuple[str, str] | None:
    """Parse common LG capture formats into (label, raw_timings)."""
    if "raw:" in line:
        before, raw = line.split("raw:", 1)
        label = pending_label or before.strip(" :=#")
        return (label, raw) if label else None

    for separator in ("=", ":"):
        if separator in line:
            label, raw = line.split(separator, 1)
            raw = raw.strip()
            if re.fullmatch(r"[0-9,\s]+", raw):
                return label.strip(), raw
    return None


def parse_command_file(path: Path) -> list[tuple[str, str]]:
    """Read a command file and return (label, raw_timings) pairs."""
    commands: list[tuple[str, str]] = []
    pending_label: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            mapped = re.match(r"#\s*Mapped to:\s*(.+)$", line, flags=re.IGNORECASE)
            if mapped:
                pending_label = mapped.group(1).strip()
            continue

        parsed = _parse_label_and_raw(line, pending_label)
        if parsed is None:
            continue
        label, timings = parsed
        commands.append((label, timings))
        pending_label = None
    return commands


def _command_kwargs(label: str) -> dict[str, object]:
    """Infer TuyaIRCommand fields from the normalized command label."""
    parts = label.split("_")
    if label == "off":
        return {"label": label, "hvac_mode": "off"}
    if label in {"turbo_on", "turbo_off", "sleep_on", "sleep_off", "eco_on", "eco_off"}:
        return {"label": label, "hvac_mode": "special"}
    if parts[0] == "fan":
        return {
            "label": label,
            "hvac_mode": "fan_only",
            "fan_mode": parts[1],
            "swing_on": parts[-1] == "on",
        }
    return {
        "label": label,
        "hvac_mode": parts[0],
        "temperature": int(parts[1]),
        "fan_mode": parts[2],
        "swing_on": parts[-1] == "on",
    }


def print_tuya_commands(commands: list[tuple[str, str]]) -> None:
    """Print TuyaIRCommand entries ready to paste into a pack."""
    print("# Generated TuyaIRCommand entries")
    for label, timings in commands:
        kwargs = _command_kwargs(label)
        key1 = raw_timings_to_tuya_key1(timings)
        print("TuyaIRCommand(")
        for key, value in kwargs.items():
            print(f"    {key}={value!r},")
        print(f"    key1={key1!r},")
        print("),")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="LG command file containing raw timing captures")
    args = parser.parse_args()
    print_tuya_commands(parse_command_file(args.path))


if __name__ == "__main__":
    main()
