"""Tuya IR helper tests."""

from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.aerostate.providers.tuya_ir import TuyaIRProvider


def test_normalize_hex_strips_non_hex_and_requires_even_length() -> None:
    assert TuyaIRProvider.normalize_hex_payload("aa:bb cc dd") == "aabbccdd"
    assert TuyaIRProvider.normalize_hex_payload("aa bb") == "aabb"
    with pytest.raises(ValueError):
        TuyaIRProvider.normalize_hex_payload("aaa")
