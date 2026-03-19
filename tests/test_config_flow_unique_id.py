"""Tests for config flow duplicate-entry unique ID behavior."""

from types import SimpleNamespace

from custom_components.aerostate.flow_helpers import (
    build_entry_unique_id,
    has_entry_collision,
)


def test_build_entry_unique_id_is_deterministic() -> None:
    """Unique ID generation should be deterministic for same inputs."""
    assert (
        build_entry_unique_id("remote.living_room", "lg.pc09sq_nsj.v1")
        == "remote.living_room::lg.pc09sq_nsj.v1"
    )


def test_build_entry_unique_id_changes_with_pack() -> None:
    """Different packs must produce different unique IDs."""
    assert build_entry_unique_id("remote.living_room", "pack.a") != build_entry_unique_id(
        "remote.living_room", "pack.b"
    )


def test_build_entry_unique_id_changes_with_remote() -> None:
    """Different remote entities must produce different unique IDs."""
    assert build_entry_unique_id("remote.one", "pack.a") != build_entry_unique_id(
        "remote.two", "pack.a"
    )


class _FakeConfigEntries:
    def __init__(self, entries):
        self._entries = entries

    def async_entries(self, domain: str):
        assert domain == "aerostate"
        return self._entries


class _FakeHass:
    def __init__(self, entries):
        self.config_entries = _FakeConfigEntries(entries)


def test_has_entry_collision_detects_existing_identity() -> None:
    hass = _FakeHass(
        [
            SimpleNamespace(
                entry_id="entry_1",
                unique_id="remote.lr::lg.v1",
                data={"broadlink_entity": "remote.lr", "model_pack": "lg.v1"},
                options={},
            )
        ]
    )

    assert has_entry_collision(hass, "remote.lr", "lg.v1") is True


def test_has_entry_collision_ignores_current_entry() -> None:
    hass = _FakeHass(
        [
            SimpleNamespace(
                entry_id="entry_1",
                unique_id="remote.lr::lg.v1",
                data={"broadlink_entity": "remote.lr", "model_pack": "lg.v1"},
                options={},
            )
        ]
    )

    assert (
        has_entry_collision(
            hass,
            "remote.lr",
            "lg.v1",
            current_entry_id="entry_1",
        )
        is False
    )
