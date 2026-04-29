"""Best-effort Broadlink (base64) → Tuya (hex timing) translation — not a guaranteed IR protocol bridge."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Literal

from .ir_types import IRCommand

_LOGGER = logging.getLogger(__name__)

# LG engine uses identical pulse extraction; keep in sync manually (do not change LG engine here).
MIN_PULSE_COUNT = 4
MAX_PULSE_COUNT = 280
# Broadlink-learned packets may use single-byte timing steps (see LG engine); small values are normal.
MIN_PULSE_US = 8
MAX_PULSE_US = 65535


@dataclass(frozen=True)
class ConversionResult:
    """Outcome of converting one Broadlink base64 burst to a hex payload."""

    hex_payload: str | None
    confidence: float
    failure_reason: str | None


def decode_broadlink_b64_to_pulses(packet_b64: str) -> list[int]:
    """Decode Broadlink-learned/base64 envelope into μs timing bursts (excluding zero padding tail)."""

    packet = base64.b64decode(packet_b64.strip())
    if len(packet) < 6:
        raise ValueError("broadlink packet too short")
    data = packet[4:-2]
    out: list[int] = []
    idx = 0
    while idx < len(data):
        value = data[idx]
        if value == 0:
            if idx + 2 >= len(data):
                break
            out.append((data[idx + 1] << 8) + data[idx + 2])
            idx += 3
        else:
            out.append(int(value))
            idx += 1
    out = [x for x in out if x > 0]
    if not out:
        raise ValueError("no pulse timings in broadlink envelope")
    return out


def pulses_to_tuya_timing_hex_uint16_le(pulses: list[int]) -> str | None:
    """Emit raw timing burst as hexadecimal (uint16 LE per timing). Best-effort for Local Tuya remotes."""

    if len(pulses) % 2 == 1:
        return None
    if len(pulses) < MIN_PULSE_COUNT or len(pulses) > MAX_PULSE_COUNT:
        return None
    buf = bytearray()
    for tick in pulses:
        if tick < MIN_PULSE_US or tick > MAX_PULSE_US:
            return None
        buf.extend(int(tick).to_bytes(2, "little"))
    hx = buf.hex()
    assert len(hx) % 2 == 0
    return hx


def _normalize_hex_like_tuya_remote(payload: str) -> str:
    """Match :meth:`TuyaIRProvider.normalize_hex_payload` semantics (no homeassistant import cycles)."""

    hex_only = "".join(ch for ch in payload if ch in "0123456789abcdefABCDEF")
    if not hex_only or len(hex_only) % 2 != 0:
        raise ValueError(
            f"Tuya IR payload must be an even-length hexadecimal string, got: {payload!r}",
        )
    return hex_only


class IRConverter:
    """Converts LG/Broadlink-style base64 payloads into timing hex suited for Tuya `remote.send_command`."""

    def convert(self, broadlink_packet: str, *, target: Literal["tuya"] = "tuya") -> ConversionResult:
        if target != "tuya":
            return ConversionResult(None, 0.0, f"unsupported target {target!r}")
        hdr = broadlink_packet.strip()
        if not hdr:
            return ConversionResult(None, 0.0, "empty_broadlink_packet")
        try:
            pulses = decode_broadlink_b64_to_pulses(hdr)
        except Exception as err:
            _LOGGER.debug("Broadlink decode failed: %s", err)
            return ConversionResult(None, 0.0, f"decode_failed:{type(err).__name__}")

        hx = pulses_to_tuya_timing_hex_uint16_le(pulses)
        if hx is None:
            return ConversionResult(None, 0.0, "timing_encode_rejected_pulse_shape_or_range")

        conf = self._confidence(pulses)

        try:
            _normalize_hex_like_tuya_remote(hx)
        except ValueError as err:
            return ConversionResult(None, 0.0, f"hex_normalize_failed:{err}")

        if conf >= 0.95:
            _LOGGER.debug("IR conversion acceptable confidence=%0.2f pulses=%s", conf, len(pulses))
        else:
            _LOGGER.warning("IR conversion marginal confidence=%0.2f pulses=%s — verify on device", conf, len(pulses))
        return ConversionResult(hex_payload=hx, confidence=conf, failure_reason=None)

    @staticmethod
    def _confidence(pulses: list[int]) -> float:
        score = 1.0
        if len(pulses) % 2:
            score -= 0.5  # guarded above; theoretical
        if len(pulses) > 200:
            score -= 0.15
        if len(pulses) < 50:
            score -= 0.05
        return max(0.0, min(1.0, score))


class IRConversionLayer:
    """Translates LG/Broadlink output into IRCommand(format=tuya) without touching Broadlink send semantics."""

    def __init__(self, converter: IRConverter):
        self._converter = converter

    def sequence_to_ir_commands_or_none(
        self,
        *,
        broadlink_parts: list[str],
        payload_hash_src: list[str],
    ) -> tuple[list[IRCommand] | None, str | None]:
        """Either convert every burst or return `(None, reason)` — never emits partial tuples."""

        out: list[IRCommand] = []
        for idx, b64_part in enumerate(broadlink_parts):
            name = "cmd" if len(broadlink_parts) == 1 else f"cmd_{idx + 1}"
            res = self._converter.convert(b64_part)
            if res.hex_payload is None:
                reason = res.failure_reason or "unknown"
                _LOGGER.warning("IR conversion failed for command %s: %s", name, reason)
                return None, reason
            if res.confidence < 0.4:
                _LOGGER.warning(
                    "IR conversion confidence too low (%0.2f) for command %s — rejecting send",
                    res.confidence,
                    name,
                )
                return None, "confidence_below_minimum"
            out.append(
                IRCommand(
                    name=name,
                    payload=str(res.hex_payload),
                    format="tuya",
                )
            )

        return out, None
