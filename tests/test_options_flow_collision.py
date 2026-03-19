"""Unit tests for options flow collision protection helpers."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.aerostate.flow_helpers import has_entry_collision


class _FakeConfigEntries:
    def __init__(self, entries):
        self._entries = entries

    def async_entries(self, domain: str):
        assert domain == "aerostate"
        return self._entries


class _FakeHass:
    def __init__(self, entries):
        self.config_entries = _FakeConfigEntries(entries)


def test_options_collision_detected_on_remote_change() -> None:
    hass = _FakeHass(
        [
            SimpleNamespace(
                entry_id="entry_target",
                unique_id="remote.a::lg.a",
                data={"broadlink_entity": "remote.a", "model_pack": "lg.a"},
                options={},
            ),
            SimpleNamespace(
                entry_id="entry_other",
                unique_id="remote.b::lg.b",
                data={"broadlink_entity": "remote.b", "model_pack": "lg.b"},
                options={},
            ),
        ]
    )

    assert has_entry_collision(
        hass,
        broadlink_entity="remote.b",
        model_pack_id="lg.b",
        current_entry_id="entry_target",
    )


def test_options_collision_detected_on_pack_change() -> None:
    hass = _FakeHass(
        [
            SimpleNamespace(
                entry_id="entry_target",
                unique_id="remote.a::lg.a",
                data={"broadlink_entity": "remote.a", "model_pack": "lg.a"},
                options={},
            ),
            SimpleNamespace(
                entry_id="entry_other",
                unique_id="remote.a::lg.release",
                data={"broadlink_entity": "remote.a", "model_pack": "lg.release"},
                options={},
            ),
        ]
    )

    assert has_entry_collision(
        hass,
        broadlink_entity="remote.a",
        model_pack_id="lg.release",
        current_entry_id="entry_target",
    )


def test_options_no_collision_for_current_identity() -> None:
    hass = _FakeHass(
        [
            SimpleNamespace(
                entry_id="entry_target",
                unique_id="remote.a::lg.a",
                data={"broadlink_entity": "remote.a", "model_pack": "lg.a"},
                options={},
            )
        ]
    )

    assert not has_entry_collision(
        hass,
        broadlink_entity="remote.a",
        model_pack_id="lg.a",
        current_entry_id="entry_target",
    )
