"""Print the generated Daikin BRC4C158 localtuya_rc code table."""

from __future__ import annotations

HEADER_MARK = 5070
HEADER_SPACE = 2140
BIT_MARK = 370
ONE_SPACE = 1000
ZERO_SPACE = 370
MESSAGE_SPACE = 29000


def build_frame(mode_byte: int, alt_mode: int, temp_c: int, fan_byte: int) -> list[int]:
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


def main() -> None:
    fans = {"fauto": 0xA0, "flow": 0x10, "fhigh": 0x50}
    print("CODES = {")
    print(f'    "power_off": "{to_raw(build_frame(0x00, 0x73, 20, 0xA0))}",')
    for temp in range(16, 31):
        for fan_name, fan_byte in fans.items():
            print(f'    "cool_t{temp}_{fan_name}": "{to_raw(build_frame(0x21, 0x23, temp, fan_byte))}",')
    print("}")


if __name__ == "__main__":
    main()
